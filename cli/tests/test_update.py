"""Tests for `bimai update`."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from bimai import update
from bimai.cli import main


class Dist:
    def __init__(self, direct):
        self.direct = direct

    def read_text(self, name):
        return self.direct


@pytest.mark.parametrize("prefix, expected", [
    ("/Users/anna/.local/share/uv/tools/bimai", "uv"),
    (r"C:\Users\Anna\AppData\Roaming\uv\tools\bimai", "uv"),
    ("/Users/anna/.local/pipx/venvs/bimai", "pipx"),
    (r"C:\Users\Anna\pipx\venvs\bimai", "pipx"),
    ("/usr/local/anaconda3", "pip"),
])
def test_install_method(prefix, expected):
    assert update.install_method(prefix, dist_files=Dist(None)) == expected


def test_editable_install_is_detected_and_refused():
    dist = Dist(json.dumps({"url": "file:///src/bimai", "dir_info": {"editable": True}}))
    assert update.install_method("/usr/local", dist_files=dist) == "editable"
    with pytest.raises(update.UpdateError, match="git pull"):
        update.update_command("editable")


def test_update_commands():
    which = lambda name: f"/bin/{name}"
    assert update.update_command("uv", which) == ["/bin/uv", "tool", "upgrade", "bimai"]
    assert update.update_command("pipx", which) == ["/bin/pipx", "upgrade", "bimai"]
    assert update.update_command("pip", which)[1:] == ["-m", "pip", "install", "--upgrade", "bimai"]


def opener(payload):
    return lambda request, timeout=None: io.BytesIO(json.dumps(payload).encode())


def test_latest_version_from_pypi():
    assert update.latest_version(opener({"info": {"version": "0.3.0"}})) == "0.3.0"


def test_not_published_yet_is_explained():
    import urllib.error
    def not_found(request, timeout=None):
        raise urllib.error.HTTPError(update.PYPI_URL, 404, "Not Found", {}, None)
    with pytest.raises(update.UpdateError, match="isn't published on PyPI yet"):
        update.latest_version(not_found)


def test_offline_check_is_explained():
    def broken(request, timeout=None):
        raise OSError("no route")
    with pytest.raises(update.UpdateError, match="Couldn't reach PyPI"):
        update.latest_version(broken)


@pytest.mark.parametrize("a, b, expected", [("0.2.0", "0.1.0", True), ("0.1.0", "0.1.0", False),
                                            ("0.1.10", "0.1.9", True), ("0.1.0", "0.2.0", False)])
def test_newer(a, b, expected):
    assert update.newer(a, b) is expected


def test_check_command(monkeypatch, capsys):
    monkeypatch.setattr(update, "latest_version", lambda: "9.9.9")
    assert main(["update", "--check"]) == 0
    assert "9.9.9 is available" in capsys.readouterr().out
    monkeypatch.setattr(update, "latest_version", lambda: "0.0.1")
    assert main(["update", "--check"]) == 0
    assert "is up to date" in capsys.readouterr().out


def test_update_runs_the_installers_command(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(update, "install_method", lambda: "uv")
    monkeypatch.setattr(update.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(update.subprocess, "run", lambda cmd: calls.append(cmd) or SimpleNamespace(returncode=0))
    assert main(["update"]) == 0
    assert calls == [["/bin/uv", "tool", "upgrade", "bimai"]]


def test_update_from_source_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(update, "install_method", lambda: "editable")
    assert main(["update"]) == 1
    assert "git pull" in capsys.readouterr().err
