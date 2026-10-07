"""Tests for installing bimai bridges: verified downloads, one-click installs, status, and the flows."""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import os
import shutil
import threading
import xml.etree.ElementTree as ET
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimai import bridges
from bimai import connections as conn
from bimai.cli import main

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (ROOT / "bridges" / "civil3d" / "bundle" / "PackageContents.xml").read_text(encoding="utf-8")


def make_zip(path: Path, *, version="0.1.0", extra: dict | None = None, without_script=False) -> Path:
    manifest = MANIFEST.replace('AppVersion="0.1.0"', f'AppVersion="{version}"')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("bimai-civil3d.bundle/PackageContents.xml", manifest)
        z.writestr("bimai-civil3d.bundle/Contents/net8.0-windows/Bimai.Civil3D.dll", b"MZ fake")
        if not without_script:
            z.writestr("install.ps1", "# installer")
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeWindows:
    """Windows for tests: Program Files under tmp, tasklist, and the elevated installer/uninstaller."""

    def __init__(self, tmp: Path):
        self.program_files = tmp / "PF"
        self.environ = {"ProgramFiles": str(self.program_files), "ProgramData": str(tmp / "PD"), "APPDATA": str(tmp / "AD")}
        self.target = f"{self.program_files}\\Autodesk\\ApplicationPlugins\\bimai-civil3d.bundle"
        self.acad_running = []          # successive answers for tasklist
        self.elevated = []              # the argument strings passed to the elevated PowerShell
        self.decline = False
        self.fail = False

    def run(self, cmd, **kwargs):
        if cmd[0] == "tasklist":
            running = self.acad_running.pop(0) if self.acad_running else False
            return SimpleNamespace(returncode=0, stdout="acad.exe  1234 Console" if running else "INFO: No tasks", stderr="")
        assert cmd[0] == "powershell.exe"
        command = cmd[-1]
        self.elevated.append(command)
        if self.decline:
            return SimpleNamespace(returncode=1, stdout="", stderr="Start-Process : This command cannot be run due to the error: The operation was canceled by the user.")
        if self.fail:
            # The elevated window's errors only reach bimai through the error file.
            error_file = command.split('-ErrorFile "')[1].split('"')[0]
            Path(error_file).write_text("\ufeffCivil 3D (acad.exe) is running. Close Civil 3D first.", encoding="utf-8")
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if "Remove-Item" in command:
            shutil.rmtree(self.target, ignore_errors=True)
        else:
            bundle = command.split('-Bundle "')[1].split('"')[0]
            shutil.copytree(bundle, self.target)
        return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.fixture
def win(tmp_path, monkeypatch):
    w = FakeWindows(tmp_path)
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn.os, "environ", w.environ)
    return w


def bridge(sha256: str | None = None) -> conn.Server:
    server = conn.load_servers()["civil3d"]
    return dataclasses.replace(server, release={**server.release, "sha256": sha256})


def opener_for(path: Path, seen: list | None = None):
    def opener(request, timeout=None):
        if seen is not None:
            seen.append(request.full_url)
        return io.BytesIO(path.read_bytes())
    return opener


def install(server, win, **kw):
    said = []
    kw.setdefault("ask", lambda q: True)
    version = bridges.install(server, say=said.append, run=win.run, environ=win.environ, **kw)
    return version, said


# -- catalogue and release consistency -------------------------------------------

def test_catalogue_release_matches_the_bridge_version():
    rel = bridges.release_of(conn.load_servers()["civil3d"])
    props = ET.parse(ROOT / "bridges" / "civil3d" / "Directory.Build.props").getroot()
    version = props.find("PropertyGroup/Version").text
    assert rel.version == version
    assert rel.tag == f"civil3d-bridge-v{version}"
    assert rel.asset == "bimai-civil3d-bridge.zip"
    assert rel.sha256 is None or (len(rel.sha256) == 64 and all(c in "0123456789abcdef" for c in rel.sha256))
    workflow = (ROOT / ".github" / "workflows" / "release-civil3d-bridge.yml").read_text(encoding="utf-8")
    assert "civil3d-bridge-v*" in workflow and rel.asset in workflow


# -- install ---------------------------------------------------------------------

def test_no_pinned_hash_refuses_download(win):
    with pytest.raises(bridges.BridgeError, match="No verified release.*--from"):
        install(bridge(None), win)
    assert win.elevated == []


def test_not_on_windows(monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "macos")
    with pytest.raises(bridges.BridgeError, match="only be installed on Windows"):
        bridges.install(bridge("0" * 64), ask=lambda q: True, say=print)


def test_verified_download_installs(win, tmp_path):
    z = make_zip(tmp_path / "release.zip")
    seen = []
    version, said = install(bridge(sha(z)), win, opener=opener_for(z, seen))
    assert version == "0.1.0"
    assert seen == ["https://github.com/StefanDaniels1/BIMAI/releases/download/civil3d-bridge-v0.1.0/bimai-civil3d-bridge.zip"]
    assert any("verified" in s for s in said) and any("installed" in s for s in said)
    why = next(s for s in said if "allow this app" in s)
    assert "Program Files" in why and "always trusts" in why and "ask IT" in why
    [command] = win.elevated
    assert "-Verb RunAs" in command and "-ExecutionPolicy Bypass -File" in command and 'install.ps1" -Bundle "' in command
    assert os.path.isdir(win.target)


def test_tampered_download_is_not_installed(win, tmp_path):
    z = make_zip(tmp_path / "release.zip")
    with pytest.raises(bridges.BridgeError, match="could not be verified"):
        install(bridge("f" * 64), win, opener=opener_for(z))
    assert win.elevated == [] and not os.path.exists(win.target)


def test_declined_permission(win, tmp_path):
    z = make_zip(tmp_path / "release.zip")
    win.decline = True
    with pytest.raises(bridges.BridgeError, match="permission prompt was declined.*ask IT"):
        install(bridge(sha(z)), win, opener=opener_for(z))
    assert not os.path.exists(win.target)


def test_installer_failure_is_explained(win, tmp_path):
    z = make_zip(tmp_path / "release.zip")
    win.fail = True
    with pytest.raises(bridges.BridgeError, match="installer stopped with an error.*acad.exe"):
        install(bridge(sha(z)), win, opener=opener_for(z))


def test_civil3d_running_must_be_closed(win, tmp_path):
    z = make_zip(tmp_path / "release.zip")
    win.acad_running = [True]
    with pytest.raises(bridges.BridgeError, match="must be closed"):
        install(bridge(sha(z)), win, opener=opener_for(z), ask=lambda q: False)
    assert win.elevated == []
    win.acad_running = [True, False]                     # the person closes it, then continues
    version, _ = install(bridge(sha(z)), win, opener=opener_for(z), ask=lambda q: True)
    assert version == "0.1.0"


def test_local_zip_without_hash(win, tmp_path):
    z = make_zip(tmp_path / "mine.zip", version="0.1.0")
    version, said = install(bridge(None), win, zip_path=z)
    assert version == "0.1.0"
    assert any(sha(z) in s for s in said)


@pytest.mark.parametrize("extra, without_script, message", [
    ({"../evil.ps1": "x"}, False, "unsafe paths"),
    ({}, True, "install.ps1"),
])
def test_bad_zips_are_refused(win, tmp_path, extra, without_script, message):
    z = make_zip(tmp_path / "bad.zip", extra=extra, without_script=without_script)
    with pytest.raises(bridges.BridgeError, match=message):
        install(bridge(None), win, zip_path=z)
    assert win.elevated == []


def test_not_a_zip(win, tmp_path):
    f = tmp_path / "x.zip"
    f.write_bytes(b"not a zip")
    with pytest.raises(bridges.BridgeError, match="not a valid bridge zip"):
        install(bridge(None), win, zip_path=f)


def test_oversized_download(win, tmp_path, monkeypatch):
    z = make_zip(tmp_path / "release.zip")
    monkeypatch.setattr(bridges, "MAX_DOWNLOAD", 10)
    with pytest.raises(bridges.BridgeError, match="larger than expected"):
        bridges.download("https://x/y.zip", tmp_path / "d.zip", opener=opener_for(z), max_bytes=10)


def test_network_error_suggests_from(tmp_path):
    def broken(request, timeout=None):
        raise OSError("proxy refused")
    with pytest.raises(bridges.BridgeError, match="proxy refused.*--from"):
        bridges.download("https://x/y.zip", tmp_path / "d.zip", opener=broken)


# -- status and uninstall --------------------------------------------------------

class FakeBridge(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["method"] == "server/discover" and self.headers["Mcp-Method"] == "server/discover"
        out = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"resultType": "complete", "supportedVersions": ["2026-07-28"],
                          "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "bimai-civil3d", "version": "0.1.0"}}}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


def test_probe_against_a_running_bridge():
    server = HTTPServer(("127.0.0.1", 0), FakeBridge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert bridges.probe(server.server_address[1]) == {"name": "bimai-civil3d", "version": "0.1.0"}
    finally:
        server.shutdown()
    assert bridges.probe(server.server_address[1], timeout=0.5) is None


def test_status_installed_old_version_and_not_running(win, tmp_path):
    install(bridge(None), win, zip_path=make_zip(tmp_path / "old.zip", version="0.0.9"))
    st = bridges.status(bridge(None), environ=win.environ, opener=lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    assert st["installed"] and st["version"] == "0.0.9" and st["latest"] == "0.1.0"
    assert st["update_available"] and not st["running"]


def test_status_not_installed(win):
    st = bridges.status(bridge(None), environ=win.environ, opener=lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    assert not st["installed"] and st["version"] is None


def test_uninstall(win, tmp_path):
    install(bridge(None), win, zip_path=make_zip(tmp_path / "z.zip"))
    said = []
    bridges.uninstall(bridge(None), say=said.append, run=win.run, environ=win.environ)
    assert not os.path.exists(win.target)
    assert "Remove-Item" in win.elevated[-1] and any("removed" in s for s in said)


# -- flows -----------------------------------------------------------------------

@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(conn, "claude_cli", lambda: None)
    root = tmp_path / "project"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--yes"]) == 0
    return root


def fake_install(win):
    def _install(server, **kw):
        os.makedirs(win.target, exist_ok=True)
        Path(win.target, "PackageContents.xml").write_text(MANIFEST, encoding="utf-8")
        return "0.1.0"
    return _install


def test_connect_offers_install_then_connects(project, win, monkeypatch, capsys):
    monkeypatch.setattr(bridges, "install", fake_install(win))
    monkeypatch.setattr(bridges, "probe", lambda port, **k: None)
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert main(["connect", "civil3d", "--path", str(project)]) == 0
    data = json.loads((project / ".mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["civil3d"]["url"] == "http://127.0.0.1:27184/mcp"
    assert "open Civil 3D with a drawing" in capsys.readouterr().out


def test_connect_without_asking_points_to_the_install_command(project, win, capsys):
    assert main(["connect", "civil3d", "--path", str(project), "--yes"]) == 2
    assert "bimai bridge install civil3d" in capsys.readouterr().err


def test_connect_reports_a_running_bridge(project, win, monkeypatch, capsys):
    fake_install(win)(None)
    monkeypatch.setattr(bridges, "probe", lambda port, **k: {"version": "0.1.0"})
    assert main(["connect", "civil3d", "--path", str(project), "--yes"]) == 0
    assert "Civil 3D is running with the bridge" in capsys.readouterr().out


def test_connect_install_failure_exits_1(project, win, monkeypatch, capsys):
    def failing(server, **kw):
        raise bridges.BridgeError("The bridge was not installed: the Windows permission prompt was declined.")
    monkeypatch.setattr(bridges, "install", failing)
    assert main(["connect", "civil3d", "--path", str(project), "--install"]) == 1
    assert "declined" in capsys.readouterr().err
    assert "civil3d" not in json.loads((project / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def test_init_offers_the_bridge_for_civil3d(tmp_path, win, monkeypatch, capsys):
    monkeypatch.setattr(conn, "claude_cli", lambda: None)
    monkeypatch.setattr(bridges, "install", fake_install(win))
    monkeypatch.setattr(bridges, "probe", lambda port, **k: None)
    answers = iter(["", "", "BIM modeller", "", "civil3d", "", "", "", "y"])   # ... write? yes; connect bridge? yes
    asked = []
    monkeypatch.setattr("builtins.input", lambda prompt="": asked.append(prompt) or next(answers))
    assert main(["init", str(tmp_path / "p"), "--person", "Anna"]) == 0
    assert any("Set it up now" in q and "permission once" in q for q in asked)
    data = json.loads((tmp_path / "p" / ".mcp.json").read_text(encoding="utf-8"))
    assert "civil3d" in data["mcpServers"]


def test_bridge_commands(win, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(bridges, "probe", lambda port, **k: None)
    assert main(["bridge", "status", "civil3d"]) == 0
    assert "not installed" in capsys.readouterr().out
    assert main(["bridge", "install", "autodesk-help"]) == 2
    servers = {**conn.load_servers(), "civil3d": bridge(None)}       # as if no release were pinned yet
    monkeypatch.setattr(conn, "load_servers", lambda: servers)
    assert main(["bridge", "install", "civil3d"]) == 1
    assert "--from" in capsys.readouterr().err


def test_published_release_is_pinned():
    rel = bridges.release_of(conn.load_servers()["civil3d"])
    assert rel.sha256 and len(rel.sha256) == 64
