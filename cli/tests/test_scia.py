"""The SCIA Engineer bridge (scia.py, mcpstdio.py) with a simulated SCIA, and pythonnet on Windows."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from bimai import connections as conn
from bimai import scia
from bimai.cli import main
from bimai.mcpstdio import ToolError

RESULTS = {
    ("member", "internal_forces", "LC1", False, "B3"): scia.ResultView(
        ["N", "Vz", "My"], [[-10.0, -10.0, -10.0], [5.0, 0.0, -5.0], [0.0, 12.5, 0.0]], [0.0, 2.5, 5.0]),
    ("member", "internal_forces", "CO1", True, "B3"): scia.ResultView(["My"], [[0.0, 18.0, 0.0]], [0.0, 2.5, 5.0]),
    ("surface", "deformations", "LC2", False, "S1"): scia.ResultView(["Uz"], [[-0.001, -0.012, -0.004]]),
    ("support", "reactions", "LC1", False, "Sn1"): scia.ResultView(["Rz"], [[42.0]]),
}


class FakeScia:
    def __init__(self, results=True):
        self.started = 0
        self.opened: list[str] = []
        self.results = results
        self.calculated = False
        self.closed = self.shut = False
        self.data = dict(RESULTS)

    def start(self):
        self.started += 1

    def open(self, path):
        self.opened.append(path)
        Path(path).write_bytes(b"changed by SCIA")          # SCIA may write its own copy: never the original

    def has_results(self):
        return self.results

    def calculate(self):
        self.calculated = self.results = True

    def load(self, entity, kind, case, combination, name):
        return self.data.get((entity, kind, case, combination, name))

    def close(self):
        self.closed = True

    def shutdown(self):
        self.shut = True


@pytest.fixture
def project(tmp_path):
    (tmp_path / "calc").mkdir()
    (tmp_path / "calc" / "Viaduct.esa").write_bytes(b"original esa")
    return tmp_path


@pytest.fixture
def fake():
    return FakeScia()


@pytest.fixture
def session(project, fake, tmp_path):
    return scia.Session(project, lambda: fake, workdir=tmp_path / "work")


# -- the session -------------------------------------------------------------------

def test_opens_a_copy_and_never_touches_the_original(session, project, fake):
    info = session.open_project("calc/Viaduct.esa")
    assert info["opened"].startswith("a copy") and info["results"] == "available"
    assert fake.opened[0] != str(project / "calc" / "Viaduct.esa") and fake.opened[0].endswith("Viaduct.esa")
    session.run_calculation()
    session.shutdown()
    assert (project / "calc" / "Viaduct.esa").read_bytes() == b"original esa"
    assert fake.shut and not Path(fake.opened[0]).exists()           # the copy is cleaned up


def test_open_without_path_uses_the_only_esa(session, project, fake):
    assert session.open_project(None)["project"] == str(Path("calc") / "Viaduct.esa")
    (project / "second.esa").write_bytes(b"x")
    with pytest.raises(ToolError, match="Which SCIA project.*second.esa"):
        session.open_project(None)
    with pytest.raises(ToolError, match="No SCIA project file"):
        session.open_project("calc/missing.esa")


def test_member_results(session):
    r = session.member_results("B3", "LC1")
    assert r["case_type"] == "load case" and r["sections_total"] == 3
    assert r["sections"][1] == {"position": 2.5, "N": -10.0, "Vz": 0.0, "My": 12.5}
    assert r["extremes"]["My"] == {"min": 0.0, "min_position": 0.0, "max": 12.5, "max_position": 2.5}
    assert "SI" in r["units"]


def test_auto_finds_the_combination(session):
    r = session.member_results("B3", "CO1")
    assert r["case_type"] == "combination" and r["extremes"]["My"]["max"] == 18.0
    with pytest.raises(ToolError, match="No internal forces for 'B3' in 'CO1'"):
        session.member_results("B3", "CO1", case_type="load_case")


def test_long_members_are_thinned_but_keep_both_ends(session, fake):
    n = 1001
    fake.data[("member", "deformations", "LC1", False, "C1")] = scia.ResultView(
        ["Uz"], [[float(i) for i in range(n)]], [i / 100 for i in range(n)])
    r = session.member_results("C1", "LC1", "deformations")
    assert len(r["sections"]) <= scia.MAX_SECTIONS + 1
    assert r["sections"][0]["position"] == 0.0 and r["sections"][-1]["position"] == 10.0
    assert r["extremes"]["Uz"]["max"] == 1000.0                         # extremes from all sections


def test_surface_and_support(session):
    s = session.surface_results("S1", "LC2", "deformations")
    assert s["mesh_elements"] == 3 and s["extremes"]["Uz"] == {"min": -0.012, "min_mesh_element": 1, "max": -0.001,
                                                              "max_mesh_element": 0}
    assert session.support_reactions("Sn1", "LC1")["reactions"] == {"Rz": 42.0}


def test_no_results_asks_before_calculating(project, tmp_path):
    fake = FakeScia(results=False)
    session = scia.Session(project, lambda: fake, workdir=tmp_path / "w")
    with pytest.raises(ToolError, match="no calculation results yet.*run_calculation"):
        session.member_results("B3", "LC1")
    assert not fake.calculated
    assert session.run_calculation()["your_file"] == "unchanged" and fake.calculated
    assert session.member_results("B3", "LC1")["extremes"]["My"]["max"] == 12.5


def test_bad_arguments(session):
    with pytest.raises(ToolError, match="result must be one of"):
        session.member_results("B3", "LC1", "stresses")
    with pytest.raises(ToolError, match="case_type must be"):
        session.member_results("B3", "LC1", case_type="both")


# -- the MCP server over stdio --------------------------------------------------------

def talk(project, fake, *messages) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" if not isinstance(m, str) else m + "\n" for m in messages))
    stdout = io.StringIO()
    scia.serve(project, backend_factory=lambda: fake, stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def test_protocol(project, fake):
    out = talk(project, fake,
               {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
               {"jsonrpc": "2.0", "method": "notifications/initialized"},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
               {"jsonrpc": "2.0", "id": 3, "method": "server/discover",
                "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}},
               {"jsonrpc": "2.0", "id": 4, "method": "tools/list",
                "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2099-01-01"}}},
               "not json",
               {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "nope"}},
               {"jsonrpc": "2.0", "id": 6, "method": "no/such"})
    assert [o.get("id") for o in out] == [1, 2, 3, 4, None, 5, 6]          # no answer to the notification
    assert out[0]["result"]["protocolVersion"] == "2025-06-18"
    assert out[0]["result"]["serverInfo"]["name"] == "bimai-scia"
    names = [t["name"] for t in out[1]["result"]["tools"]]
    assert names == sorted(names) == ["get_member_results", "get_support_reactions", "get_surface_results",
                                      "open_project", "run_calculation"]
    assert all(t["annotations"]["readOnlyHint"] for t in out[1]["result"]["tools"])
    assert fake.started == 0                                                # listing tools doesn't start SCIA
    assert "2026-07-28" in out[2]["result"]["supportedVersions"]
    assert out[3]["error"]["code"] == -32022
    assert out[4]["error"]["code"] == -32700
    assert out[5]["error"]["code"] == -32602 and "open_project" in out[5]["error"]["message"]
    assert out[6]["error"]["code"] == -32601


def test_tool_calls_over_stdio(project, fake):
    out = talk(project, fake,
               {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_member_results",
                "arguments": {"member": "B3", "case": "LC1"}}},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_member_results",
                "arguments": {"member": "XX", "case": "LC1"}}})
    first = out[0]["result"]
    assert first["isError"] is False and first["structuredContent"]["extremes"]["My"]["max"] == 12.5
    assert fake.started == 1 and len(fake.opened) == 1                      # opened the only .esa by itself
    assert out[1]["result"]["isError"] is True and "Check the names" in out[1]["result"]["content"][0]["text"]
    assert fake.shut                                                        # SCIA closed when the session ends


# -- finding SCIA ----------------------------------------------------------------------

def test_installations_from_registry_and_program_files(tmp_path):
    pf = tmp_path / "PF"
    for version in ("Engineer24.0", "Engineer25.0", "Engineer19.1"):
        (pf / "SCIA" / version / "OpenAPI_dll").mkdir(parents=True)
        if version != "Engineer19.1":
            (pf / "SCIA" / version / "OpenAPI_dll" / "SCIA.OpenAPI.dll").write_bytes(b"MZ")
    other = tmp_path / "custom"
    (other / "OpenAPI_dll").mkdir(parents=True)
    (other / "OpenAPI_dll" / "SCIA.OpenAPI.dll").write_bytes(b"MZ")
    found = scia.installations({"ProgramFiles": str(pf)}, registry=lambda: [("26.0", str(other)), ("23.0", str(tmp_path / "gone"))])
    assert [i.version for i in found] == ["26.0", "25.0", "24.0"]           # newest first; no OpenAPI: skipped
    assert found[0].path == str(other)


def test_connection_status(monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "macos")
    c = {c["server"]: c for c in conn.tool_connections(["scia"])}["scia"]
    assert c["status"] == "other-platform"
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(scia, "installations", lambda environ=None, exists=None: [])
    c = {c["server"]: c for c in conn.tool_connections(["scia"])}["scia"]
    assert c["status"] == "needs-app" and "SCIA Engineer 21" in c["message"]
    monkeypatch.setattr(scia, "installations", lambda environ=None, exists=None: [scia.Installation("25.0", "C:/SCIA")])
    c = {c["server"]: c for c in conn.tool_connections(["scia"])}["scia"]
    assert c["status"] == "ready" and c["config"] == {"type": "stdio", "command": "bimai", "args": ["scia", "serve"]}


def test_onboarding_a_constructeur(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn, "claude_cli", lambda: None)
    monkeypatch.setattr(scia, "installations", lambda environ=None, exists=None: [scia.Installation("25.0", "C:/SCIA")])
    root = tmp_path / "viaduct"
    root.mkdir()
    (root / "Viaduct.esa").write_bytes(b"esa")
    assert main(["init", str(root), "--person", "Anna", "--role", "constructeur", "--goals", "calculations",
                 "--tools", "scia", "--yes"]) == 0
    mcp = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]
    assert mcp["scia"] == {"type": "stdio", "command": "bimai", "args": ["scia", "serve"]}
    assert (root / ".claude" / "agents" / "structural-analyst.md").exists()
    agent = (root / ".claude" / "agents" / "structural-analyst.md").read_text(encoding="utf-8")
    assert "mcp__scia" not in agent.split("---")[1]                          # the analyst may use SCIA


def test_scia_status_without_scia(monkeypatch, capsys):
    monkeypatch.setattr(scia, "installations", lambda environ=None, exists=None: [])
    assert main(["scia", "status"]) == 1
    assert "wasn't found" in capsys.readouterr().out


# -- pythonnet on Windows ------------------------------------------------------------------

@pytest.mark.skipif(sys.platform != "win32", reason="SCIA's OpenAPI and pythonnet's .NET Framework loader are Windows only")
def test_pythonnet_loads_the_dotnet_framework():
    import pythonnet
    try:
        pythonnet.load("netfx")
    except RuntimeError:
        pass
    import clr  # noqa: F401
    import System
    assert System.Environment.Version.Major == 4                            # .NET Framework 4.x, as SCIA's OpenAPI needs
    assert System.Type.GetType("System.ResolveEventHandler") is not None
