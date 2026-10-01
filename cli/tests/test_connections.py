"""Tests for MCP connections: catalogue, .mcp.json, consent, sign-in, keys, team integration, validate."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from bimai import connections as conn
from bimai.cli import main
from bimai.team import load_catalogue
from bimai.validate import validate

HELP_URL = "https://developer.api.autodesk.com/knowledge/public/v1/mcp"


class FakeKeyring:
    """Stands in for the OS keychain, so tests never touch the real one."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service, user, password):
        self.store[(service, user)] = password

    def get_password(self, service, user):
        return self.store.get((service, user))

    def delete_password(self, service, user):
        del self.store[(service, user)]


@pytest.fixture(autouse=True)
def keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(conn, "_keyring", lambda: fake)
    return fake


@pytest.fixture(autouse=True)
def no_claude(monkeypatch):
    """By default there is no `claude` CLI; tests that need it install a fake."""
    monkeypatch.setattr(conn, "claude_cli", lambda: None)


@pytest.fixture
def project(tmp_path):
    assert main(["init", str(tmp_path), "--person", "Anna", "--role", "bim coordinator",
                 "--tools", "acc,revit", "--yes"]) == 0
    return tmp_path


def mcp(root: Path) -> dict:
    return json.loads((root / ".mcp.json").read_text(encoding="utf-8"))


def settings(root: Path) -> dict:
    return json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))


def connect(root: Path, *args: str) -> int:
    return main(["connect", *args, "--path", str(root)])


def front(root: Path, role: str) -> dict:
    return yaml.safe_load((root / ".claude" / "agents" / f"{role}.md").read_text(encoding="utf-8").split("---\n")[1])


# -- catalogue -------------------------------------------------------------------

def test_catalogue_is_complete_and_consistent():
    servers = conn.load_servers()
    known = set(load_catalogue().capabilities)
    assert {"autodesk-help", "revit", "fusion", "fusion-data", "hydraulic-modeling", "autocad-civil3d"} <= set(servers)
    for s in servers.values():
        assert s.label and s.vendor and s.docs.startswith("https://help.autodesk.com/"), s.name
        assert set(s.provides) <= known, s.name
        if s.unavailable:
            assert not s.config, s.name
            continue
        assert s.auth in ("none", "signin", "key") and s.access in ("read-only", "read-write"), s.name
        assert set(s.platforms) <= {"windows", "macos", "linux"} and s.platforms, s.name
        assert s.config.get("type") in ("http", "stdio"), s.name
        if s.auth == "signin":
            assert s.config["type"] == "http", s.name
    assert servers["revit"].access == "read-only"
    for variant in servers["revit"].config["variants"]:
        assert "Read-Tools" in variant["command"] or "--tool-permission=StableReadOnly" in variant["args"]


def test_tools_matched_by_servers_exist():
    tools = load_catalogue().tools
    for s in conn.load_servers().values():
        assert set(s.matches_tools) <= set(tools), s.name


# -- server configuration --------------------------------------------------------

def test_revit_only_on_windows():
    with pytest.raises(conn.ConnectError, match="only works on Windows"):
        conn.server_config(conn.load_servers()["revit"], platform="macos")


def test_revit_detects_the_installed_variant():
    revit = conn.load_servers()["revit"]
    env = {"ProgramFiles": r"D:\Apps"}
    write_tools = r"D:\Apps\Autodesk\Revit 2027 MCP Server Write-Tools Technical Preview\Autodesk.RevitMcpServer.Stdio.exe"
    cfg = conn.server_config(revit, platform="windows", environ=env, exists=lambda p: p == write_tools)
    assert cfg == {"type": "stdio", "command": write_tools,
                   "args": ["--tool-permission=StableReadOnly", "--ManageConfigurationWithAutodeskRevitPluginInstaller=true"]}
    with pytest.raises(conn.ConnectError, match="isn't installed"):
        conn.server_config(revit, platform="windows", environ=env, exists=lambda p: False)


def test_regions():
    hydro = conn.load_servers()["hydraulic-modeling"]
    assert conn.server_config(hydro, region="gbr")["url"] == "https://api.aps.gbr.autodesk.com/water/modeling-mcp/mcp"
    with pytest.raises(conn.ConnectError, match="usa, gbr, aus"):
        conn.server_config(hydro)


def test_custom_key_server_uses_the_helper():
    cfg = conn.custom_config("https://x.example/mcp", "key", "X-API-Key", "raw")
    assert cfg == {"type": "http", "url": "https://x.example/mcp",
                   "headersHelper": "bimai auth headers --header X-API-Key --scheme raw"}
    with pytest.raises(conn.ConnectError):
        conn.custom_config("https://x.example/mcp", "key", "X-API-Key; rm -rf /")


# -- .mcp.json and settings ------------------------------------------------------

def test_init_adds_product_help(project, capsys):
    assert mcp(project) == {"mcpServers": {"autodesk-help": {"type": "http", "url": HELP_URL}}}


def test_init_keeps_existing_servers_and_suggests_connects(tmp_path, capsys):
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"my-tool": {"type": "stdio", "command": "x"}}}),
                                        encoding="utf-8")
    assert main(["init", str(tmp_path), "--person", "Anna", "--role", "bim modeller", "--tools", "revit", "--yes"]) == 0
    assert set(mcp(tmp_path)["mcpServers"]) == {"my-tool", "autodesk-help"}
    assert mcp(tmp_path)["mcpServers"]["my-tool"] == {"type": "stdio", "command": "x"}
    out = capsys.readouterr().out
    assert "bimai connect revit" in out
    seat = yaml.safe_load((tmp_path / ".bimai" / "seats" / "anna" / "seat.yaml").read_text(encoding="utf-8"))
    assert seat["tools"] == ["revit"]


def test_connect_keeps_other_servers(project):
    data = mcp(project)
    data["mcpServers"]["my-tool"] = {"type": "stdio", "command": "x", "args": ["--a"]}
    data["extra"] = {"kept": True}
    (project / ".mcp.json").write_text(json.dumps(data), encoding="utf-8")
    assert connect(project, "hydraulic-modeling", "--region", "usa", "--allow-writes", "--yes") == 0
    after = mcp(project)
    assert after["mcpServers"]["my-tool"] == {"type": "stdio", "command": "x", "args": ["--a"]}
    assert after["extra"] == {"kept": True}


def test_invalid_mcp_json_is_refused(project, capsys):
    (project / ".mcp.json").write_text("{ broken", encoding="utf-8")
    assert connect(project, "fusion-data", "--allow-writes", "--yes") == 2
    assert (project / ".mcp.json").read_text(encoding="utf-8") == "{ broken"
    assert "not valid JSON" in capsys.readouterr().err


def test_settings_rule_keeps_other_settings():
    data = {"model": "opus", "permissions": {"allow": ["Read"], "ask": ["Bash(rm *)"]}}
    added = conn.settings_with_ask(data, "fusion-data")
    assert added == {"model": "opus", "permissions": {"allow": ["Read"], "ask": ["Bash(rm *)", "mcp__fusion-data"]}}
    assert conn.settings_with_ask(added, "fusion-data") == added
    assert conn.settings_without_ask(added, "fusion-data") == data
    assert conn.settings_without_ask({"permissions": {"ask": ["mcp__x"]}}, "x") == {}


# -- bimai connect ---------------------------------------------------------------

def test_list(project, capsys):
    assert connect(project) == 0
    out = capsys.readouterr().out
    assert "autodesk-help" in out and "connected" in out
    assert "sign in with your Autodesk account" in out and "can change data" in out
    assert "not connectable yet" in out


def test_public_server(project, capsys):
    (project / ".mcp.json").unlink()
    assert connect(project, "autodesk-help", "--yes") == 0
    assert mcp(project)["mcpServers"]["autodesk-help"] == {"type": "http", "url": HELP_URL}
    assert "No sign-in needed" in capsys.readouterr().out


def test_unavailable_server(project, capsys):
    before = mcp(project)
    assert connect(project, "autocad-civil3d", "--yes") == 2
    assert "Autodesk Assistant" in capsys.readouterr().err
    assert mcp(project) == before


def test_revit_on_a_mac(project, monkeypatch, capsys):
    monkeypatch.setattr(conn, "PLATFORM", "macos")
    assert connect(project, "revit", "--yes") == 2
    assert "only works on Windows" in capsys.readouterr().err
    assert "revit" not in mcp(project)["mcpServers"]


def test_revit_on_windows(project, monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn.os.path, "exists", lambda p: "Read-Tools" in p)
    assert connect(project, "revit", "--yes") == 0
    assert mcp(project)["mcpServers"]["revit"]["type"] == "stdio"
    assert "permissions" not in settings(project)          # read-only: no approval rule needed


def test_unknown_server(project, capsys):
    assert connect(project, "sketchup", "--yes") == 2
    assert "autodesk-help" in capsys.readouterr().err


def test_write_capable_server_needs_consent(project, capsys):
    before = mcp(project)
    assert connect(project, "fusion-data", "--yes") == 2
    assert "--allow-writes" in capsys.readouterr().err
    assert mcp(project) == before


def test_interactive_consent(project, monkeypatch):
    answers = iter(["y", "n"])           # connect it? yes; sign in now? no
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert connect(project, "fusion-data") == 0
    assert "mcp__fusion-data" in settings(project)["permissions"]["ask"]


def test_ask_rule_and_sign_in_hint(project, capsys):
    assert connect(project, "fusion-data", "--allow-writes", "--yes") == 0
    assert settings(project) == {"model": "sonnet", "permissions": {"ask": ["mcp__fusion-data"]}}
    out = capsys.readouterr().out
    assert "/mcp" in out and "Authenticate" in out


def test_region_is_asked_when_interactive(project, monkeypatch):
    answers = iter(["aus", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    assert connect(project, "hydraulic-modeling", "--allow-writes") == 0
    assert "aus.autodesk.com" in mcp(project)["mcpServers"]["hydraulic-modeling"]["url"]


def test_custom_server_with_key(project, monkeypatch, keyring):
    monkeypatch.setattr("getpass.getpass", lambda *_: "s3cret")
    assert connect(project, "--custom", "my-api", "--url", "https://x.example/mcp", "--auth", "key") == 0
    assert mcp(project)["mcpServers"]["my-api"]["headersHelper"].startswith("bimai auth headers")
    assert keyring.store == {("bimai-mcp", "my-api"): "s3cret"}
    for f in project.rglob("*"):
        if f.is_file():
            assert b"s3cret" not in f.read_bytes(), f


def test_custom_name_rules(project):
    assert connect(project, "--custom", "revit", "--url", "https://x/mcp", "--yes") == 2
    assert connect(project, "--custom", "My Tool", "--url", "https://x/mcp", "--yes") == 2
    assert connect(project, "--custom", "my-tool", "--yes") == 2


def test_connect_needs_a_project(tmp_path):
    assert connect(tmp_path, "autodesk-help", "--yes") == 2


# -- bimai disconnect ------------------------------------------------------------

def test_disconnect(project):
    assert connect(project, "fusion-data", "--allow-writes", "--yes") == 0
    assert main(["disconnect", "fusion-data", "--path", str(project)]) == 0
    assert "fusion-data" not in mcp(project)["mcpServers"]
    assert settings(project) == {"model": "sonnet"}
    assert "fusion-data" not in (project / "CLAUDE.md").read_text(encoding="utf-8")


def test_disconnect_removes_a_stored_key(project, monkeypatch, keyring):
    monkeypatch.setattr("getpass.getpass", lambda *_: "s3cret")
    connect(project, "--custom", "my-api", "--url", "https://x/mcp", "--auth", "key")
    assert main(["disconnect", "my-api", "--path", str(project)]) == 0
    assert keyring.store == {}


def test_disconnect_unknown(project):
    assert main(["disconnect", "nope", "--path", str(project)]) == 2


# -- bimai auth ------------------------------------------------------------------

def test_login_runs_claude_code_sign_in(project, monkeypatch):
    connect(project, "fusion-data", "--allow-writes", "--yes")
    calls = []
    monkeypatch.setattr(conn, "claude_cli", lambda: "/usr/local/bin/claude")
    monkeypatch.setattr(conn.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or type("R", (), {"returncode": 0})())
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert main(["auth", "login", "fusion-data", "--path", str(project)]) == 0
    assert calls == [["/usr/local/bin/claude", "mcp", "login", "fusion-data"]]


def test_login_without_the_cli_explains_the_session_steps(project, monkeypatch, capsys):
    connect(project, "fusion-data", "--allow-writes", "--yes")
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    assert main(["auth", "login", "fusion-data", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "approve" in out and "/mcp" in out


def test_login_key_server_hides_and_stores_the_key(project, monkeypatch, keyring, capsys):
    connect(project, "--custom", "my-api", "--url", "https://x/mcp", "--auth", "key", "--yes")
    monkeypatch.setattr("getpass.getpass", lambda *_: "k-123")
    assert main(["auth", "login", "my-api", "--path", str(project)]) == 0
    assert keyring.store[("bimai-mcp", "my-api")] == "k-123"
    assert "k-123" not in capsys.readouterr().out


def test_status_never_shows_the_key(project, keyring, capsys):
    connect(project, "--custom", "my-api", "--url", "https://x/mcp", "--auth", "key", "--yes")
    keyring.set_password("bimai-mcp", "my-api", "k-123")
    assert main(["auth", "status", "--path", str(project)]) == 0
    out = capsys.readouterr().out
    assert "key stored" in out and "k-123" not in out and "no sign-in needed" in out


def test_logout_removes_the_key(project, keyring):
    connect(project, "--custom", "my-api", "--url", "https://x/mcp", "--auth", "key", "--yes")
    keyring.set_password("bimai-mcp", "my-api", "k-123")
    assert main(["auth", "logout", "my-api", "--path", str(project)]) == 0
    assert keyring.store == {}


@pytest.mark.parametrize("scheme, expected", [("bearer", {"Authorization": "Bearer abc"}),
                                              ("raw", {"Authorization": "abc"})])
def test_headers_helper(keyring, monkeypatch, capsys, scheme, expected):
    keyring.set_password("bimai-mcp", "my-api", "abc")
    monkeypatch.setenv("CLAUDE_CODE_MCP_SERVER_NAME", "my-api")
    assert main(["auth", "headers", "--scheme", scheme]) == 0
    assert json.loads(capsys.readouterr().out) == expected


def test_headers_helper_without_a_key(monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_MCP_SERVER_NAME", "my-api")
    assert main(["auth", "headers"]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "bimai auth login my-api" in captured.err


# -- team ------------------------------------------------------------------------

def test_subagents_get_only_their_roles_servers(project, monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn.os.path, "exists", lambda p: "Read-Tools" in p)
    assert connect(project, "revit", "--yes") == 0
    assert front(project, "model-checker")["disallowedTools"] == "mcp__autodesk-help"
    assert front(project, "scribe")["disallowedTools"] == "mcp__autodesk-help, mcp__revit"


def test_mentor_uses_product_help(tmp_path):
    assert main(["init", str(tmp_path), "--person", "Anna", "--role", "bim modeller", "--new-to-vscode", "--yes"]) == 0
    assert "disallowedTools" not in front(tmp_path, "mentor")


def test_custom_servers_are_coordinator_only(project):
    connect(project, "--custom", "my-tool", "--url", "https://x/mcp", "--yes")
    for role in ("issue-manager", "model-checker", "scribe"):
        assert "mcp__my-tool" in front(project, role)["disallowedTools"]


def test_connections_section(project):
    text = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Connections" in text
    assert "| Autodesk Product Help (`autodesk-help`) | search Autodesk product help | no | Coordinator |" in text
    assert "Declared but not connected: ACC / Forma, Revit." in text


def test_connected_tool_is_no_longer_declared_only(project, monkeypatch):
    monkeypatch.setattr(conn, "PLATFORM", "windows")
    monkeypatch.setattr(conn.os.path, "exists", lambda p: "Read-Tools" in p)
    connect(project, "revit", "--yes")
    text = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Declared but not connected: ACC / Forma." in text
    assert "| Revit (read-only) (`revit`) | query models | no | Coordinator, Model Checker |" in text


def test_no_connections(project):
    assert main(["disconnect", "autodesk-help", "--path", str(project)]) == 0
    text = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "The team has no live connections yet." in text


# -- validate --------------------------------------------------------------------

def test_literal_secret_is_reported_without_its_value(project):
    data = mcp(project)
    data["mcpServers"]["leaky"] = {"type": "http", "url": "https://x/mcp",
                                   "headers": {"Authorization": "Bearer abc123", "X-Ok": "${OK_TOKEN}"},
                                   "env": {"TOKEN": "plain"}, "oauth": {"clientSecret": "zzz"}}
    (project / ".mcp.json").write_text(json.dumps(data), encoding="utf-8")
    problems = validate(project)
    assert {p.location for p in problems} == {"mcpServers.leaky.headers.Authorization", "mcpServers.leaky.env.TOKEN",
                                             "mcpServers.leaky.oauth.clientSecret"}
    assert all(secret not in str(p) for p in problems for secret in ("abc123", "plain", "zzz"))


def test_env_reference_with_default_is_fine(project):
    data = mcp(project)
    data["mcpServers"]["ok"] = {"type": "http", "url": "https://x/mcp", "headers": {"A": "${TOKEN:-none}"}}
    (project / ".mcp.json").write_text(json.dumps(data), encoding="utf-8")
    assert validate(project) == []


def test_invalid_mcp_json_is_a_problem(project):
    (project / ".mcp.json").write_text("{ nope", encoding="utf-8")
    assert [p.file for p in validate(project)] == [".mcp.json"]
