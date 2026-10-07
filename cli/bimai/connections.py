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
    """Something bimai can install is missing: a bimai bridge (an add-in inside a desktop program), or a vendor
    app such as pyRevit (missing, too old, or its agent host switched off)."""


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
    builds: str = ""        # a bimai bridge built on the user's PC (openroads), see openroads.py
    program: str = ""       # the desktop program a local bridge runs in, for messages
    write_tools: tuple[str, ...] = ()   # tools that change data: denied unless the person allows changes
    app: dict = field(default_factory=dict)       # a vendor app bimai can install (pyRevit), see apps.py


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
            release=s.get("release") or {}, write_tools=tuple(s.get("write_tools") or ()), app=s.get("app") or {},
            builds=s.get("builds", ""), program=s.get("program", ""),
        )
    return servers


# ------------------------------------------------------------------ server configuration

def plugin_folders(environ) -> list[str]:
    """Where Autodesk products look for plug-in bundles (Autodesk: ApplicationPlugins locations)."""
    roots = [environ.get("ProgramFiles", r"C:\Program Files"), environ.get("ProgramData", r"C:\ProgramData"),
             environ.get("APPDATA", "")]
    return [f"{root}\\Autodesk\\ApplicationPlugins" for root in roots if root]


def expand(path: str, environ) -> str:
    """Fills in {ProgramFiles} and {APPDATA} from the environment."""
    return (path.replace("{ProgramFiles}", environ.get("ProgramFiles", r"C:\Program Files"))
                .replace("{APPDATA}", environ.get("APPDATA", "")))


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
        raise ConnectError(f"{server.label} only works on {_where(server)}.")
    if server.builds == "openroads":
        from bimai import openroads     # openroads imports this module
        if not openroads.installed(environ, exists):
            raise BridgeMissing(f"{server.label} isn't installed on this computer. It needs: {server.needs}. "
                                f"Install it with: bimai bridge install {server.name}  (guide: {server.docs})")
    if server.bundle and not any(exists(f"{folder}\\{server.bundle}") for folder in plugin_folders(environ)):
        raise BridgeMissing(f"{server.label} isn't installed on this computer. It needs: {server.needs}. "
                            f"Install it with: bimai bridge install {server.name}  (guide: {server.docs})")
    cfg = copy.deepcopy(server.config)
    if server.port and "url" in cfg:
        cfg["url"] = cfg["url"].replace("{port}", str(port or server.port))
    if "variants" in cfg:
        for variant in cfg.pop("variants"):
            command = expand(variant["command"], environ)
            if exists(command):
                if server.app:
                    from bimai import apps      # apps imports this module
                    problem = apps.problem(server, command)
                    if problem:
                        raise BridgeMissing(problem)
                return {"type": cfg["type"], "command": command, "args": list(variant.get("args", []))}
        if server.app:
            raise BridgeMissing(f"{server.app['name']} isn't installed on this computer. It needs: {server.needs}.")
        raise ConnectError(f"{server.label} isn't installed on this computer. It needs: {server.needs}. "
                           f"Setup: {server.docs}")
    if server.regions:
        if region not in server.regions:
            choices = ", ".join(server.regions)
            raise ConnectError(f"{server.label} has one endpoint per region; choose one with --region ({choices}). "
                               "Use the region your projects are hosted in.")
        cfg["url"] = server.regions[region]
    return cfg


def _where(server: Server) -> str:
    return " and ".join(p.capitalize() if p != "macos" else "macOS" for p in server.platforms)


def tool_connections(tools: list[str], *, platform: str | None = None, environ=None, exists=None) -> list[dict]:
    """For each chosen tool with a catalogue server (no sign-in needed): can it be connected on this computer?

    status: ready | needs-install | needs-app | other-platform | unavailable. `command` is only given
    where it works on this computer; `config` only when ready.
    """
    platform = platform or PLATFORM
    result = []
    for server in load_servers().values():
        matched = [t for t in tools if t in server.matches_tools]
        if not matched or server.default or server.auth != "none":
            continue
        entry = {"tools": matched, "server": server.name, "label": server.label, "command": None, "config": None}
        if server.unavailable:
            entry |= {"status": "unavailable", "message": f"No live connection from Claude Code yet (more: {server.docs})."}
        elif platform not in server.platforms:
            entry |= {"status": "other-platform",
                      "message": f"{_where(server)} only: your team connects to it on a {_where(server)} PC."}
        else:
            try:
                entry |= {"status": "ready", "config": server_config(server, platform=platform, environ=environ,
                                                                     exists=exists),
                          "message": "Connected read-only: your team can read it but not change it." if server.write_tools
                                     else "Connected: your team can use it."}
            except BridgeMissing as missing:
                if server.app:
                    entry |= {"status": "needs-install", "command": f"bimai connect {server.name} --install --yes",
                              "message": f"{missing} bimai can set it up for you."}
                elif server.release:
                    entry |= {"status": "needs-install", "command": f"bimai connect {server.name} --install --yes",
                              "message": f"The bimai bridge isn't installed yet. Installing it asks {_where(server)} "
                                         "for permission once, because it goes into the folder the program trusts."}
                else:
                    entry |= {"status": "needs-app", "message": f"Needs {server.needs}. Setup: {server.docs}"}
            except ConnectError:
                entry |= {"status": "needs-app", "command": f"bimai connect {server.name}",
                          "message": f"Needs {server.needs}. Set it up ({server.docs}), then connect it."}
        result.append(entry)
    return result


def option_note(connection: dict) -> str:
    """A short warning for an interview option whose connection can't work on this computer ('' if none)."""
    return {"other-platform": connection["message"],
            "needs-app": "Needs an add-on that isn't installed yet.",
            "unavailable": "No live connection from Claude Code yet."}.get(connection["status"], "")


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


def write_rules(server: Server) -> list[str]:
    return [f"mcp__{server.name}__{tool}" for tool in server.write_tools]


def settings_with_rules(data: dict, kind: str, rules: list[str]) -> dict:
    """Adds permission rules (kind: ask | deny), keeping all other settings."""
    out = copy.deepcopy(data)
    listed = out.setdefault("permissions", {}).setdefault(kind, [])
    listed.extend(r for r in rules if r not in listed)
    return out


def settings_without_rules(data: dict, rules: list[str]) -> dict:
    """Removes these rules from ask and deny; empty lists and an empty permissions block go too."""
    out = copy.deepcopy(data)
    perms = out.get("permissions")
    if not isinstance(perms, dict):
        return out
    for kind in ("ask", "deny"):
        if isinstance(perms.get(kind), list):
            perms[kind] = [r for r in perms[kind] if r not in rules]
            if not perms[kind]:
                del perms[kind]
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
