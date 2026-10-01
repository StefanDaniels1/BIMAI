"""MCP connections: the server catalogue, the project's .mcp.json, sign-in and keys.

One list (`.mcp.json`, Claude Code's format), one command (`bimai connect`) and one way to sign in
(`bimai auth`). Secrets never touch a file: Autodesk sign-in tokens are stored by Claude Code, and keys
for custom servers live in the OS keychain and reach the server through a `headersHelper`.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from pathlib import Path

import yaml

PLATFORM = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
KEYRING_SERVICE = "bimai-mcp"
HELPER = "bimai auth headers"
SIGN_IN_TEXT = {
    "none": "no sign-in needed",
    "signin": "sign in with your Autodesk account",
    "key": "needs a key (stored in your computer's keychain)",
    "unknown": "set up by hand",
}


class ConnectError(Exception):
    """A server can't be connected here, with the reason in plain language (exit 2)."""


class BridgeMissing(ConnectError):
    """A bimai bridge (an add-in inside a desktop program) isn't installed; it can be installed."""


class McpJsonError(Exception):
    """.mcp.json exists but isn't valid JSON (or not a JSON object)."""


@dataclass(frozen=True)
class Server:
    name: str
    label: str
    vendor: str
    docs: str
    auth: str = "none"
    access: str = "read-only"
    platforms: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    matches_tools: tuple[str, ...] = ()
    config: dict = field(default_factory=dict)
    regions: dict = field(default_factory=dict)
    needs: str = ""
    unavailable: str = ""
    default: bool = False
    bundle: str = ""        # an Autodesk plug-in bundle that must be installed (bimai bridges)
    port: int = 0           # default port for local servers whose port can be changed (--port)
    release: dict = field(default_factory=dict)   # published bridge release: repo, tag, asset, version, sha256


@dataclass(frozen=True)
class Connection:
    """A server listed in .mcp.json, with what bimai knows about it."""
    name: str
    label: str
    provides: tuple[str, ...]
    access: str          # read-only | read-write | unknown
    auth: str            # none | signin | key | unknown
    known: bool          # in bimai's catalogue


@cache
def load_servers() -> dict[str, Server]:
    text = resources.files("bimai").joinpath("catalogue", "servers.yaml").read_text(encoding="utf-8")
    servers = {}
    for name, s in yaml.safe_load(text).items():
        servers[name] = Server(
            name=name, label=s["label"], vendor=s["vendor"], docs=s["docs"],
            auth=s.get("auth", "none"), access=s.get("access", "read-only"),
            platforms=tuple(s.get("platforms") or ()), provides=tuple(s.get("provides") or ()),
            matches_tools=tuple(s.get("matches_tools") or ()), config=s.get("config") or {},
            regions=s.get("regions") or {}, needs=s.get("needs", ""), unavailable=s.get("unavailable", ""),
            default=bool(s.get("default")), bundle=s.get("bundle", ""), port=int(s.get("port") or 0),
            release=s.get("release") or {},
        )
    return servers


# ------------------------------------------------------------------ server configuration

def plugin_folders(environ) -> list[str]:
    """Where Autodesk products look for plug-in bundles (Autodesk: ApplicationPlugins locations)."""
    roots = [environ.get("ProgramFiles", r"C:\Program Files"), environ.get("ProgramData", r"C:\ProgramData"),
             environ.get("APPDATA", "")]
    return [f"{root}\\Autodesk\\ApplicationPlugins" for root in roots if root]


def server_config(server: Server, *, region: str | None = None, port: int | None = None, platform: str | None = None,
                  environ=None, exists=None) -> dict:
    """The .mcp.json entry for a catalogue server on this machine, or ConnectError explaining why not."""
    platform = platform or PLATFORM
    environ = os.environ if environ is None else environ
    exists = exists or os.path.exists
    if port is not None and not server.port:
        raise ConnectError(f"{server.label} has no port to choose; leave out --port.")
    if port is not None and not 0 < port < 65536:
        raise ConnectError("--port must be between 1 and 65535.")
    if server.unavailable:
        raise ConnectError(server.unavailable)
    if platform not in server.platforms:
        where = " and ".join(p.capitalize() if p != "macos" else "macOS" for p in server.platforms)
        raise ConnectError(f"{server.label} only works on {where}.")
    if server.bundle and not any(exists(f"{folder}\\{server.bundle}") for folder in plugin_folders(environ)):
        raise BridgeMissing(f"{server.label} isn't installed on this computer. It needs: {server.needs}. "
                            f"Install it with: bimai bridge install {server.name}  (guide: {server.docs})")
    cfg = copy.deepcopy(server.config)
    if server.port and "url" in cfg:
        cfg["url"] = cfg["url"].replace("{port}", str(port or server.port))
    if "variants" in cfg:
        program_files = environ.get("ProgramFiles", r"C:\Program Files")
        for variant in cfg.pop("variants"):
            command = variant["command"].replace("{ProgramFiles}", program_files)
            if exists(command):
                return {"type": cfg["type"], "command": command, "args": list(variant.get("args", []))}
        raise ConnectError(f"{server.label} isn't installed on this computer. It needs: {server.needs}. "
                           f"Setup: {server.docs}")
    if server.regions:
        if region not in server.regions:
            choices = ", ".join(server.regions)
            raise ConnectError(f"{server.label} has one endpoint per region; choose one with --region ({choices}). "
                               "Use the region your projects are hosted in.")
        cfg["url"] = server.regions[region]
    return cfg


def custom_config(url: str, auth: str = "none", header: str = "Authorization", scheme: str = "bearer") -> dict:
    if auth not in ("none", "key"):
        raise ConnectError("--auth must be 'none' or 'key'")
    if scheme not in ("bearer", "raw"):
        raise ConnectError("--scheme must be 'bearer' or 'raw'")
    if not header.replace("-", "").isalnum():
        raise ConnectError("--header may only contain letters, digits and dashes")
    cfg = {"type": "http", "url": url}
    if auth == "key":
        cfg["headersHelper"] = f"{HELPER} --header {header} --scheme {scheme}"
    return cfg


# ------------------------------------------------------------------ .mcp.json and settings

def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise McpJsonError(f"{path.name} is not valid JSON (line {exc.lineno}); fix it first") from exc
    if not isinstance(data, dict):
        raise McpJsonError(f"{path.name} is not a JSON object; fix it first")
    return data


def json_text(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def mcp_with(data: dict, name: str, entry: dict) -> dict:
    out = copy.deepcopy(data)
    out.setdefault("mcpServers", {})[name] = entry
    return out


def mcp_without(data: dict, name: str) -> dict:
    out = copy.deepcopy(data)
    out.get("mcpServers", {}).pop(name, None)
    return out


def ask_rule(name: str) -> str:
    return f"mcp__{name}"


def settings_with_ask(data: dict, name: str) -> dict:
    out = copy.deepcopy(data)
    ask = out.setdefault("permissions", {}).setdefault("ask", [])
    if ask_rule(name) not in ask:
        ask.append(ask_rule(name))
    return out


def settings_without_ask(data: dict, name: str) -> dict:
    out = copy.deepcopy(data)
    perms = out.get("permissions")
    ask = perms.get("ask") if isinstance(perms, dict) else None
    if isinstance(ask, list) and ask_rule(name) in ask:
        ask.remove(ask_rule(name))
        if not ask:
            del perms["ask"]
        if not perms:
            del out["permissions"]
    return out


def auth_of(name: str, entry: dict) -> str:
    server = load_servers().get(name)
    if server and not server.unavailable:
        return server.auth
    if HELPER in str(entry.get("headersHelper", "")):
        return "key"
    return "unknown"


def connections(root: Path) -> list[Connection]:
    """The servers in the project's .mcp.json; an invalid file counts as none (validate reports it)."""
    try:
        return connections_from(read_json(root / ".mcp.json"))
    except McpJsonError:
        return []


def connections_from(data: dict) -> list[Connection]:
    servers = load_servers()
    result = []
    for name, entry in (data.get("mcpServers") or {}).items():
        s = servers.get(name)
        if s and not s.unavailable:
            result.append(Connection(name, s.label, s.provides, s.access, s.auth, True))
        else:
            result.append(Connection(name, name, (), "unknown", auth_of(name, entry or {}), False))
    return result


# ------------------------------------------------------------------ keys and sign-in

def _keyring():
    import keyring  # imported only when a key is used

    return keyring


def store_key(name: str, key: str) -> None:
    _keyring().set_password(KEYRING_SERVICE, name, key)


def has_key(name: str) -> bool:
    return _keyring().get_password(KEYRING_SERVICE, name) is not None


def delete_key(name: str) -> bool:
    kr = _keyring()
    if kr.get_password(KEYRING_SERVICE, name) is None:
        return False
    kr.delete_password(KEYRING_SERVICE, name)
    return True


def headers_for(name: str, header: str = "Authorization", scheme: str = "bearer") -> dict | None:
    key = _keyring().get_password(KEYRING_SERVICE, name)
    if key is None:
        return None
    return {header: f"Bearer {key}" if scheme == "bearer" else key}


def claude_cli() -> str | None:
    return shutil.which("claude")


def claude_mcp(action: str, name: str, quiet: bool = False) -> bool:
    """Run `claude mcp login|logout <name>`. False without the CLI, or when Claude Code doesn't know the
    server yet: project servers in .mcp.json only exist for the CLI after they are approved in a session."""
    cli = claude_cli()
    if not cli:
        return False
    out = subprocess.run([cli, "mcp", action, name], capture_output=quiet, encoding="utf-8", errors="replace")
    return out.returncode == 0


def in_session_hint(name: str) -> str:
    return (f"Start Claude Code in this project (`claude`) and approve the project's servers when asked. "
            f"Then type /mcp, choose '{name}' and select Authenticate, and sign in with your Autodesk "
            "account in the browser that opens.")
