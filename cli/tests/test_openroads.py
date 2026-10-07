"""Installing the OpenRoads bridge (openroads.py) on a simulated Windows PC: find, build, register, remove."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimai import bridges
from bimai import connections as conn
from bimai import openroads
from bimai.bridges import BridgeError
from bimai.cli import main

ROOT = Path(__file__).resolve().parents[2]


def pack(tmp: Path) -> Path:
    spec = importlib.util.spec_from_file_location("pack", ROOT / "bridges" / "openroads" / "pack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.pack(tmp / "bimai-openroads-bridge.zip")


class FakePC:
    """Windows for tests: OpenRoads installations, csc.exe, tasklist and the administrator prompt."""

    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.environ = {"ProgramFiles": str(tmp / "PF"), "ProgramData": str(tmp / "PD"), "WINDIR": str(tmp / "WIN")}
        self.running: list[bool] = []
        self.compiles: list[list[str]] = []
        self.elevated: list[str] = []
        self.needs_general_purpose = False
        self.compile_error = ""
        self.decline = False

    def add_openroads(self, name="OpenRoads Designer 2024", assemblies_subfolder=False) -> openroads.Installation:
        root = Path(self.environ["ProgramFiles"], "Bentley", name, "OpenRoadsDesigner")
        (root / ("Assemblies" if assemblies_subfolder else "")).mkdir(parents=True, exist_ok=True)
        (root / "OpenRoadsDesigner.exe").write_bytes(b"MZ")
        (root / ("Assemblies" if assemblies_subfolder else "") / "Bentley.MstnPlatformNET.dll").write_bytes(b"MZ")
        (root / "Bentley.GeneralPurpose.dll").write_bytes(b"MZ")
        return openroads.Installation(name, str(root))

    def run(self, cmd, **kwargs):
        if cmd[0] == "tasklist":
            running = self.running.pop(0) if self.running else False
            return SimpleNamespace(returncode=0, stdout="OpenRoadsDesigner.exe 7 Console" if running else "INFO: No tasks", stderr="")
        if cmd[0].endswith("csc.exe"):
            self.compiles.append(cmd)
            assert "/langversion:5" in cmd and "/target:library" in cmd
            assert any(c.endswith("AddIn.cs") for c in cmd)
            refs = [c[3:] for c in cmd if c.startswith("/r:")]
            if self.compile_error:
                return SimpleNamespace(returncode=1, stdout=f"AddIn.cs(12,5): error CS0115: {self.compile_error}", stderr="")
            if self.needs_general_purpose and not any(r.endswith("Bentley.GeneralPurpose.dll") for r in refs):
                return SimpleNamespace(returncode=1, stdout=(
                    "AddIn.cs(14,25): error CS0012: The type 'Bentley.GeneralPurpose.Thing' is defined in an assembly "
                    "that is not referenced. You must add a reference to assembly 'Bentley.GeneralPurpose, Version=10.0.0.0, "
                    "Culture=neutral, PublicKeyToken=4bf6c96a266e58d4'."), stderr="")
            out = next(c for c in cmd if c.startswith("/out:"))[5:]
            Path(out).write_bytes(b"compiled")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[0] == "powershell.exe":
            script = Path(cmd[-1].split('-File "')[1].split('"')[0]).read_text(encoding="utf-8")
            self.elevated.append(script)
            if self.decline:
                return SimpleNamespace(returncode=1, stdout="", stderr="The operation was canceled by the user.")
            for line in script.splitlines():
                quoted = re.findall(r"'((?:[^']|'')*)'", line)
                if line.startswith("Copy-Item"):
                    shutil.copyfile(quoted[0], quoted[1])
                elif line.startswith("Remove-Item"):
                    os.remove(quoted[0])
                elif line.startswith("New-Item"):
                    os.makedirs(quoted[0], exist_ok=True)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"unexpected command {cmd}")

    def install(self, zip_path=None, ask=lambda q: False):
        said = []
        names = openroads.install(server(), zip_path=zip_path, ask=ask, say=said.append, platform="windows",
                                  run=self.run, environ=self.environ)
        return names, said


def server() -> conn.Server:
    return conn.load_servers()["openroads"]


@pytest.fixture
def pc(tmp_path):
    return FakePC(tmp_path)


@pytest.fixture
def zip_path(tmp_path):
    return pack(tmp_path / "dist")


# -- finding OpenRoads ------------------------------------------------------------

def test_finds_installations_and_assemblies(pc):
    a = pc.add_openroads("OpenRoads Designer 2024")
    b = pc.add_openroads("OpenRoads Designer CE 10.12", assemblies_subfolder=True)
    found = openroads.installations(pc.environ)
    assert [i.name for i in found] == ["OpenRoads Designer 2024", "OpenRoads Designer CE 10.12"]
    assert found[1].slug == "openroads-designer-ce-10-12"
    assert openroads.platform_assembly(a).endswith("Bentley.MstnPlatformNET.dll")
    assert os.path.join("Assemblies", "Bentley.MstnPlatformNET.dll") in openroads.platform_assembly(b)


def test_cfg_follows_bentleys_documented_pattern():
    text = openroads.cfg_text(r"C:\ProgramData\bimai\openroads\openroads-designer-2024")
    assert "_BIMAI_OPENROADS_=C:\\ProgramData\\bimai\\openroads\\openroads-designer-2024\\\n" in text
    assert "%if exists ($(_BIMAI_OPENROADS_)BimaiOpenRoads.dll)" in text
    assert "MS_ADDINPATH < $(_BIMAI_OPENROADS_)" in text and "MS_DGNAPPS < BimaiOpenRoads.dll" in text
    assert text.rstrip().endswith("%endif")


def test_release_zip_has_the_sources(tmp_path, zip_path):
    work = tmp_path / "src"
    work.mkdir()
    names = [p.name for p in openroads.unpack_sources(zip_path, work)]
    assert "AddIn.cs" in names and "Mcp.cs" in names and "CivilTools.cs" in names
    assert bridges.sha256_file(zip_path) == bridges.sha256_file(pack(tmp_path / "again"))   # reproducible


# -- installing --------------------------------------------------------------------

def test_install_builds_for_every_version_with_one_permission_prompt(pc, zip_path):
    pc.add_openroads("OpenRoads Designer 2024")
    pc.add_openroads("OpenRoads Designer 2025", assemblies_subfolder=True)
    names, said = pc.install(zip_path)
    assert names == ["OpenRoads Designer 2024", "OpenRoads Designer 2025"]
    assert len(pc.compiles) == 2 and len(pc.elevated) == 1
    assert any("Windows will now ask" in s and "bimai-openroads.cfg" in s for s in said)
    for inst in openroads.installations(pc.environ):
        dll = Path(openroads.target_dir(inst, pc.environ), "BimaiOpenRoads.dll")
        assert dll.read_bytes() == b"compiled"
        assert Path(inst.cfg).read_text(encoding="utf-8") == openroads.cfg_text(str(dll.parent))
        assert openroads.installed_version(inst, pc.environ) == "local"
    assert [i.name for i in openroads.installed(pc.environ)] == names


def test_reinstall_needs_no_permission(pc, zip_path):
    pc.add_openroads()
    pc.install(zip_path)
    pc.install(zip_path)
    assert len(pc.elevated) == 1                     # the cfg is already right: no second prompt


def test_missing_reference_is_added(pc, zip_path):
    pc.add_openroads()
    pc.needs_general_purpose = True
    pc.install(zip_path)
    assert len(pc.compiles) == 2
    assert any(c.endswith("Bentley.GeneralPurpose.dll") for c in pc.compiles[1])


def test_compile_error_names_the_version(pc, zip_path):
    pc.add_openroads("OpenRoads Designer 2023")
    pc.compile_error = "'BridgeAddIn.Run(string[])': no suitable method found to override"
    with pytest.raises(BridgeError, match=r"(?s)OpenRoads Designer 2023: the bridge didn't compile.*CS0115"):
        pc.install(zip_path)
    assert pc.elevated == [] and openroads.installed(pc.environ) == []


def test_one_version_failing_doesnt_stop_the_others(pc, zip_path, monkeypatch):
    pc.add_openroads("OpenRoads Designer 2024")
    broken = Path(pc.environ["ProgramFiles"], "Bentley", "OpenRoads Designer 2025", "OpenRoadsDesigner")
    broken.mkdir(parents=True)
    (broken / "OpenRoadsDesigner.exe").write_bytes(b"MZ")      # no Bentley.MstnPlatformNET.dll
    names, said = pc.install(zip_path)
    assert names == ["OpenRoads Designer 2024"]
    assert any("2025" in s and "Bentley.MstnPlatformNET.dll wasn't found" in s for s in said)


def test_no_openroads(pc, zip_path):
    with pytest.raises(BridgeError, match="No OpenRoads Designer was found"):
        pc.install(zip_path)


def test_openroads_running(pc, zip_path):
    pc.add_openroads()
    pc.running = [True, True]
    with pytest.raises(BridgeError, match="must be closed"):
        pc.install(zip_path)
    pc.running = [True, False]
    pc.install(zip_path, ask=lambda q: True)
    assert openroads.installed(pc.environ)


def test_permission_declined(pc, zip_path):
    pc.add_openroads()
    pc.decline = True
    with pytest.raises(BridgeError, match="declined"):
        pc.install(zip_path)
    assert openroads.installed(pc.environ) == []


def test_download_needs_a_pinned_release(pc):
    pc.add_openroads()
    unpinned = conn.Server(**{**server().__dict__, "release": {**server().release, "sha256": None}})
    with pytest.raises(BridgeError, match="No verified release"):
        openroads.install(unpinned, ask=lambda q: False, say=print, platform="windows", run=pc.run, environ=pc.environ)


def test_only_on_windows(pc, zip_path):
    with pytest.raises(BridgeError, match="only be installed on Windows"):
        openroads.install(server(), zip_path=zip_path, ask=lambda q: False, say=print, platform="macos")


def test_uninstall(pc, zip_path):
    pc.add_openroads()
    pc.install(zip_path)
    said = []
    openroads.uninstall(server(), say=said.append, platform="windows", run=pc.run, environ=pc.environ)
    assert openroads.installed(pc.environ) == [] and said == ["✓ OpenRoads Designer (bimai bridge, read-only, beta) removed."]
    inst = openroads.installations(pc.environ)[0]
    assert not os.path.exists(inst.cfg) and not os.path.exists(openroads.target_dir(inst, pc.environ))


# -- connecting --------------------------------------------------------------------

@pytest.fixture
def windows(pc, monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn, "claude_cli", lambda: None)
    for key, value in pc.environ.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(bridges, "probe", lambda port, **k: None)
    return pc


def test_status_from_onboarding_to_connected(tmp_path, windows, zip_path, capsys):
    windows.add_openroads()
    root = tmp_path / "project"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--tools", "openroads",
                 "--dry-run", "--json", "--yes"]) == 0
    c = {c["server"]: c for c in json.loads(capsys.readouterr().out)["connections"]}["openroads"]
    assert c["status"] == "needs-install" and c["command"] == "bimai connect openroads --install --yes"

    windows.install(zip_path)
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--tools", "openroads", "--yes"]) == 0
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert mcp["openroads"] == {"type": "http", "url": "http://127.0.0.1:27185/mcp"}


def test_connect_and_bridge_status(tmp_path, windows, zip_path, capsys, monkeypatch):
    windows.add_openroads()
    root = tmp_path / "project"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--yes"]) == 0
    assert main(["connect", "openroads", "--path", str(root), "--yes"]) == 2
    assert "bimai bridge install openroads" in capsys.readouterr().err
    windows.install(zip_path)
    assert main(["connect", "openroads", "--path", str(root), "--yes"]) == 0
    out = capsys.readouterr().out
    assert "starts together with OpenRoads Designer" in out
    assert main(["bridge", "status", "openroads"]) == 0
    assert "installed for OpenRoads Designer 2024, version local" in capsys.readouterr().out


def test_bentley_microstation_server_is_unavailable(tmp_path, windows, capsys):
    root = tmp_path / "project"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--yes"]) == 0
    assert main(["connect", "microstation", "--path", str(root), "--yes"]) == 2
    assert "early access" in capsys.readouterr().err
