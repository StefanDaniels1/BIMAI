"""Tests for setting up pyRevit (apps.py) and connecting it: versions, agent switch, prerequisites, write rules."""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimai import apps
from bimai import connections as conn
from bimai.bridges import BridgeError
from bimai.cli import main

REAL_EXISTS, REAL_LISTDIR = os.path.exists, os.listdir
INSTALLER = b"pretend pyRevit installer"
RUNTIMES = {"8": b"pretend .NET 8", "10": b"pretend .NET 10"}


def pyrevit(**app_changes) -> conn.Server:
    """The catalogue's pyrevit entry, with download hashes for the fake files."""
    server = conn.load_servers()["pyrevit"]
    app = json.loads(json.dumps(server.app))
    app["installer"]["sha256"] = hashlib.sha256(INSTALLER).hexdigest()
    for pre in app["prerequisites"]:
        pre["sha512"] = hashlib.sha512(RUNTIMES[pre["min"].split(".")[0]]).hexdigest()
    app.update(app_changes)
    return dataclasses.replace(server, app=app)


class FakePC:
    """Windows for tests: what is installed, the pyRevit CLI, the installers and the administrator prompt."""

    def __init__(self, tmp: Path):
        self.environ = {"APPDATA": str(tmp / "AD"), "ProgramFiles": str(tmp / "PF")}
        self.user_exe = conn.expand(r"{APPDATA}\pyRevit-Master\bin\pyrevit.exe", self.environ)
        self.admin_exe = conn.expand(r"{ProgramFiles}\pyRevit-Master\bin\pyrevit.exe", self.environ)
        self.dotnet = conn.expand(r"{ProgramFiles}\dotnet\shared\Microsoft.WindowsDesktop.App", self.environ)
        self.config = Path(conn.expand(r"{APPDATA}\pyRevit\pyRevit_config.ini", self.environ))
        self.files: set[str] = set()
        self.runtimes: list[str] = []
        self.version: str | None = None       # what `pyrevit --version` says; None: it doesn't start
        self.revit_running: list[bool] = []
        self.elevated: list[str] = []         # scripts run with the administrator prompt
        self.ran: list[list[str]] = []
        self.decline = False
        self.downloads: list[str] = []

    def install_pyrevit(self, version="7.0.0.26278", where="user", enabled=False):
        self.files.add(self.user_exe if where == "user" else self.admin_exe)
        self.version = version
        if enabled:
            self.enable()

    def enable(self):
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.config.write_text("[core]\nchecks = true\n\n[agent]\nenabled = true\n", encoding="utf-8")

    def exists(self, path):
        """Fake inside the fake AppData and Program Files; the real file system elsewhere (the project)."""
        if str(path).startswith(tuple(self.environ.values())):
            return str(path) in self.files
        return REAL_EXISTS(path)

    def listdir(self, path):
        if path == self.dotnet:
            if not self.runtimes:
                raise FileNotFoundError(path)
            return list(self.runtimes)
        return REAL_LISTDIR(path)

    def opener(self, request, timeout=None):
        url = request.full_url
        self.downloads.append(url)
        if "windowsdesktop-runtime-8" in url:
            return io.BytesIO(RUNTIMES["8"])
        if "windowsdesktop-runtime-10" in url:
            return io.BytesIO(RUNTIMES["10"])
        return io.BytesIO(INSTALLER)

    def run(self, cmd, **kwargs):
        self.ran.append([str(c) for c in cmd])
        if cmd[0] == "tasklist":
            running = self.revit_running.pop(0) if self.revit_running else False
            return SimpleNamespace(returncode=0, stdout="Revit.exe  42 Console" if running else "INFO: No tasks", stderr="")
        if cmd[0] == "powershell.exe":
            script = cmd[-1].split('-File "')[1].split('"')[0]
            self.elevated.append(Path(script).read_text(encoding="utf-8"))
            if self.decline:
                return SimpleNamespace(returncode=1, stdout="", stderr="The operation was canceled by the user.")
            self.runtimes += ["8.0.31", "10.0.12"]
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[0] in (self.user_exe, self.admin_exe):
            if cmd[1:] == ["--version"]:
                ok = self.version is not None
                return SimpleNamespace(returncode=0 if ok else 1, stdout=f"pyRevit CLI v{self.version}+2233\n" if ok else "",
                                       stderr="" if ok else "You must install .NET to run this application.")
            if cmd[1:] == ["configs", "agent", "enable"]:
                self.enable()
                return SimpleNamespace(returncode=0, stdout="Agent host enabled.", stderr="")
        if str(cmd[0]).endswith("_signed.exe"):          # pyRevit's per-user installer
            assert "/VERYSILENT" in cmd
            self.install_pyrevit()
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command {cmd}")

    def setup(self, server=None, **kw):
        said = []
        version = apps.setup(server or pyrevit(), ask=kw.pop("ask", lambda q: True), say=said.append, platform="windows",
                             run=self.run, opener=self.opener, environ=self.environ, exists=self.exists,
                             listdir=self.listdir, **kw)
        return version, said


@pytest.fixture
def pc(tmp_path):
    return FakePC(tmp_path)


# -- what is installed -------------------------------------------------------------

def test_versions_and_the_agent_switch(pc):
    server = pyrevit()
    assert apps.installed_exe(server, pc.environ, pc.exists) is None
    pc.install_pyrevit("6.5.5.26237", where="admin")
    assert apps.installed_exe(server, pc.environ, pc.exists) == pc.admin_exe
    assert "6.5.5.26237 is installed" in apps.problem(server, pc.admin_exe, pc.run, pc.environ)
    pc.install_pyrevit("7.0.0.26278")
    assert apps.installed_exe(server, pc.environ, pc.exists) == pc.user_exe        # per user first
    assert "switched off" in apps.problem(server, pc.user_exe, pc.run, pc.environ)
    pc.enable()
    assert apps.problem(server, pc.user_exe, pc.run, pc.environ) is None
    pc.version = None
    assert "doesn't start" in apps.problem(server, pc.user_exe, pc.run, pc.environ)


def test_prerequisites(pc):
    server = pyrevit()
    assert [p["name"] for p in apps.missing_prerequisites(server, pc.environ, pc.listdir)] == [
        ".NET 8 Desktop Runtime", ".NET 10 Desktop Runtime"]
    pc.runtimes = ["8.0.11", "10.0.2"]                     # Revit's older .NET 8 patch isn't enough
    assert [p["min"] for p in apps.missing_prerequisites(server, pc.environ, pc.listdir)] == ["8.0.23"]
    pc.runtimes = ["8.0.31", "9.0.1", "10.0.12"]
    assert apps.missing_prerequisites(server, pc.environ, pc.listdir) == []


# -- setting it up -----------------------------------------------------------------

def test_fresh_pc_one_permission_prompt_then_pyrevit(pc):
    version, said = pc.setup()
    assert version == "7.0.0.26278"
    assert len(pc.elevated) == 1                            # both runtimes in one prompt
    assert "windowsdesktop-runtime-8.0.31" in pc.elevated[0] and "windowsdesktop-runtime-10.0.12" in pc.elevated[0]
    assert any("Windows asks you once" in s and ".NET 8 Desktop Runtime and .NET 10" in s for s in said)
    assert any("no administrator rights needed" in s for s in said)
    assert apps.agent_enabled(pyrevit(), pc.environ)
    assert apps.problem(pyrevit(), pc.user_exe, pc.run, pc.environ) is None


def test_runtimes_present_no_permission_prompt(pc):
    pc.runtimes = ["8.0.31", "10.0.12"]
    pc.setup()
    assert pc.elevated == []
    assert not any("windowsdesktop" in u for u in pc.downloads)


def test_up_to_date_pyrevit_only_switches_the_agent_on(pc):
    pc.install_pyrevit()
    questions = []
    pc.setup(ask=lambda q: questions.append(q) or True)
    assert pc.downloads == [] and pc.elevated == []
    assert len(questions) == 1 and "agent runtime" in questions[0] and "Revit needs a restart" in questions[0]


def test_agent_switch_declined(pc):
    pc.install_pyrevit()
    with pytest.raises(BridgeError, match="agent runtime is off"):
        pc.setup(ask=lambda q: False)


def test_old_pyrevit_is_updated(pc):
    pc.install_pyrevit("6.5.5.26237")
    pc.runtimes = ["8.0.31", "10.0.12"]
    version, _ = pc.setup()
    assert version == "7.0.0.26278" and pc.downloads == [pyrevit().app["installer"]["url"]]


def test_bad_download_installs_nothing(pc):
    pc.runtimes = ["8.0.31", "10.0.12"]
    bad = pyrevit()
    bad.app["installer"]["sha256"] = "0" * 64
    with pytest.raises(BridgeError, match="could not be verified"):
        pc.setup(bad)
    assert pc.version is None and not any(c[0].endswith("_signed.exe") for c in pc.ran)


def test_bad_runtime_download_installs_nothing(pc):
    bad = pyrevit()
    bad.app["prerequisites"][1]["sha512"] = "0" * 128
    with pytest.raises(BridgeError, match="SHA512"):
        pc.setup(bad)
    assert pc.elevated == []


def test_declined_permission(pc):
    pc.decline = True
    with pytest.raises(BridgeError, match="declined"):
        pc.setup()
    assert pc.version is None


def test_revit_running(pc):
    pc.revit_running = [True, True]
    with pytest.raises(BridgeError, match="Revit must be closed"):
        pc.setup()                                          # nobody to ask: stop instead of waiting
    assert pc.downloads == []
    pc.revit_running = [True, False]
    pc.setup(close_app=lambda q: True)                      # closed after the question
    assert pc.version == "7.0.0.26278"


def test_only_on_windows(pc):
    with pytest.raises(BridgeError, match="only be set up on Windows"):
        apps.setup(pyrevit(), ask=lambda q: True, say=print, platform="macos")


def test_config_parser_reads_pyrevit_style(pc):
    pc.config.parent.mkdir(parents=True, exist_ok=True)
    pc.config.write_text("﻿[agent]\nenabled = True\npolicy = \"ask\"\n", encoding="utf-8")
    assert apps.agent_enabled(pyrevit(), pc.environ)
    pc.config.write_text("[agent]\nenabled = false\n", encoding="utf-8")
    assert not apps.agent_enabled(pyrevit(), pc.environ)


# -- connecting it -----------------------------------------------------------------

@pytest.fixture
def windows(pc, monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn, "claude_cli", lambda: None)
    for key, value in pc.environ.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(conn.os.path, "exists", pc.exists)
    monkeypatch.setattr(apps.os, "listdir", pc.listdir)
    monkeypatch.setattr(apps.subprocess, "run", pc.run)
    monkeypatch.setattr(apps.urllib.request, "urlopen", pc.opener)
    servers = {**conn.load_servers(), "pyrevit": pyrevit()}
    monkeypatch.setattr(conn, "load_servers", lambda: servers)
    return pc


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(conn, "claude_cli", lambda: None)
    root = tmp_path / "project"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--tools", "ifc", "--yes"]) == 0
    return root


def mcp(root):
    return json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def permissions(root):
    return json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8")).get("permissions", {})


def test_connect_read_only_by_default(project, windows, capsys):
    windows.install_pyrevit(enabled=True)
    assert main(["connect", "pyrevit", "--path", str(project), "--yes"]) == 0
    assert mcp(project)["pyrevit"] == {"type": "stdio", "command": windows.user_exe, "args": ["mcp"]}
    assert permissions(project)["deny"] == ["mcp__pyrevit__run_modify"]
    assert "mcp__pyrevit__run_modify" not in permissions(project).get("ask", [])
    assert "Read-only" in capsys.readouterr().out


def test_connect_with_changes_allowed_then_disconnect(project, windows):
    windows.install_pyrevit(where="admin", enabled=True)
    assert main(["connect", "pyrevit", "--path", str(project), "--yes"]) == 0
    assert main(["connect", "pyrevit", "--path", str(project), "--yes", "--allow-writes"]) == 0
    assert mcp(project)["pyrevit"]["command"] == windows.admin_exe
    assert permissions(project) .get("ask") == ["mcp__pyrevit__run_modify"] and "deny" not in permissions(project)
    assert main(["disconnect", "pyrevit", "--path", str(project)]) == 0
    assert "pyrevit" not in mcp(project) and permissions(project) == {}


def test_connect_installs_everything(project, windows, capsys):
    assert main(["connect", "pyrevit", "--path", str(project), "--install", "--yes"]) == 0
    assert mcp(project)["pyrevit"]["command"] == windows.user_exe
    assert len(windows.elevated) == 1
    assert "pyRevit's agent runtime is on" in capsys.readouterr().out


def test_connect_without_consent_explains(project, windows, capsys):
    windows.install_pyrevit("6.5.5.26237")
    assert main(["connect", "pyrevit", "--path", str(project), "--yes"]) == 2
    assert "needs pyRevit 7.0 or newer" in capsys.readouterr().err
    assert "pyrevit" not in mcp(project)


def test_onboarding_offers_pyrevit(tmp_path, windows, capsys):
    assert main(["init", str(tmp_path / "p"), "--person", "Anna", "--role", "bim modeller", "--tools", "revit",
                 "--dry-run", "--json", "--yes"]) == 0
    c = {c["server"]: c for c in json.loads(capsys.readouterr().out)["connections"]}["pyrevit"]
    assert c["status"] == "needs-install" and c["command"] == "bimai connect pyrevit --install --yes"


def test_onboarding_connects_ready_pyrevit_read_only(tmp_path, windows):
    windows.install_pyrevit(enabled=True)
    root = tmp_path / "p"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--tools", "revit", "--yes"]) == 0
    assert mcp(root)["pyrevit"]["command"] == windows.user_exe
    assert permissions(root)["deny"] == ["mcp__pyrevit__run_modify"]
