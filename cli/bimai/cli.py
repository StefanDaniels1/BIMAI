"""The `bimai` command. Each subcommand formats the result of a pure function."""
from __future__ import annotations

import argparse
import getpass
import os
import re
import json
import subprocess
import sys
from pathlib import Path

from bimai import __version__
from bimai import bridges
from bimai import connections as conn
from bimai.claude import SeatError, find_seat, load_seat_context, plan_claude_files
from bimai.files import apply as apply_plan
from bimai.init import (AlreadyInitialised, Answers, apply, check_not_initialised, connect_suggestions,
                        plan_files, suggested_tools)
from bimai.scan import scan
from bimai.team import UnknownRole, load_catalogue, match_preset, propose
from bimai.validate import NoWorkspace, validate


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        problems = validate(args.path)
    except NoWorkspace as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"valid": not problems, "problems": [p.as_dict() for p in problems]},
                         indent=2, ensure_ascii=False))
    else:
        for p in problems:
            print(p)
        if problems:
            print(f"{len(problems)} problem{'s' if len(problems) != 1 else ''} found")
        else:
            print("✓ workspace is valid")
    return 1 if problems else 0


class InitError(Exception):
    """Bad answer given as a flag: exit code 2."""


def _ask(question: str, default: str = "") -> str:
    try:
        answer = input(f"{question}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def _split(value: str) -> list[str]:
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def _git_user(root: Path) -> str:
    try:
        cwd = root if root.exists() else Path.cwd()
        out = subprocess.run(["git", "config", "user.name"], cwd=cwd, capture_output=True, timeout=5,
                             encoding="utf-8", errors="replace")
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _default_person(root: Path) -> str:
    """The git user name, else the login name; never fails (getpass.getuser can raise on Windows)."""
    name = _git_user(root)
    if name:
        return name
    try:
        return getpass.getuser()
    except Exception:
        return "me"


def _check_list(kind: str, values: list[str], allowed) -> list[str]:
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise InitError(f"unknown {kind}: {', '.join(unknown)}. Choose from: {', '.join(allowed)}")
    return values


def _interview(args: argparse.Namespace, root: Path, found: dict[str, str]) -> Answers:
    """Flags win; with --yes nothing is asked; otherwise ask, with defaults pre-filled."""
    cat = load_catalogue()
    interactive = not args.yes

    name = args.name or (_ask("Project name", root.name) if interactive else root.name)
    person = args.person or (_ask("Your name", _default_person(root)) if interactive else _default_person(root))

    if args.role:
        role = args.role
        match_preset(role, cat)               # UnknownRole -> exit 2
    elif not interactive:
        raise InitError("--role is required with --yes. Roles: " + ", ".join(p.label for p in cat.presets.values()))
    else:
        roles = ", ".join(p.label for p in cat.presets.values())
        while True:
            role = _ask(f"Your role on this project ({roles})")
            try:
                match_preset(role, cat)
                break
            except UnknownRole as exc:
                print(f"  {exc}")
    preset = match_preset(role, cat)

    def choose(kind: str, flag: str | None, default: list[str], allowed, prompt: str) -> list[str]:
        if flag is not None:
            return _check_list(kind, _split(flag), allowed)
        if not interactive:
            return default
        while True:
            try:
                return _check_list(kind, _split(_ask(prompt, ",".join(default))), allowed)
            except InitError as exc:
                print(f"  {exc}")

    goals = choose("goals", args.goals, list(preset.goals), cat.goals,
                   f"What do you want help with? ({', '.join(cat.goals)})")
    if interactive and found and args.tools is None:
        print("  Found in this folder:")
        for tool, file in found.items():
            print(f"    {cat.tools[tool]['label']:<24} {file}")
    tools = choose("tools", args.tools, list(found), list(cat.tools),
                   f"Tools and data used ({', '.join(cat.tools)})")

    if args.new_to_vscode or not interactive:
        new = bool(args.new_to_vscode)
    else:
        new = _ask("Are you new to VS Code? (y/N)", "n").lower().startswith("y")
    language = args.language or (_ask("Output language (en/nl)", "en") if interactive else "en")
    _check_list("language", [language], ("en", "nl"))
    return Answers(name=name, person=person, role=role, goals=goals, tools=tools,
                   new_to_vscode=new, language=language)


def _print_scan(s) -> None:
    hits = {k: v for k, v in s.categories.items() if v.count}
    if not hits:
        print("  Nothing BIM-related found yet (fine for a new project).")
    for cat_name, f in hits.items():
        more = f", +{f.count - len(f.examples)} more" if f.count > len(f.examples) else ""
        print(f"  {cat_name.replace('_', ' '):<20} {f.count:>4}  {', '.join(f.examples)}{more}")
    if s.truncated:
        print("  (stopped after 20,000 files)")
    extras = [label for ok, label in ((s.is_git, "git repository"), (s.has_claude_md, "CLAUDE.md"),
                                      (s.has_claude_dir, ".claude/")) if ok]
    if extras:
        print(f"  Already here: {', '.join(extras)}")


def _print_proposal(team, plan) -> None:
    cat = load_catalogue()
    print(f"Proposed team ({len(team.members)} of max 5):")
    for m in team.members:
        r = cat.roles[m.role]
        print(f"  {r.label:<28} {m.why}   [{r.model}]")
    for hint in team.hints:
        print(f"  · {hint}")
    print("\nFiles:")
    _print_files(plan)


def cmd_init(args: argparse.Namespace) -> int:
    root = args.path.resolve()
    if args.json and not args.dry_run:
        print("error: --json only works with --dry-run", file=sys.stderr)
        return 2
    try:
        check_not_initialised(root)
        s = scan(root)
        found = suggested_tools(s)
        if not args.json:
            print(f"Looking at {root}")
            _print_scan(s)
            print()
        answers = _interview(args, root, found)
        team = propose(answers.role, answers.goals, answers.tools, answers.new_to_vscode)
    except (AlreadyInitialised, UnknownRole, InitError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    plan = plan_files(root, answers, team)

    if args.json:
        print(json.dumps({"scan": s.as_dict(), "answers": answers.as_dict(), "team": team.as_dict(),
                          "files": [{"path": f.path, "action": f.action, "note": f.note} for f in plan]},
                         indent=2, ensure_ascii=False))
        return 0
    _print_proposal(team, plan)
    if args.dry_run:
        print("\nDry run: nothing was written.")
        return 0
    if not args.yes and not _ask("\nWrite these files? (Y/n)", "y").lower().startswith("y"):
        print("Nothing written.")
        return 1

    root.mkdir(parents=True, exist_ok=True)
    written = apply(root, plan)
    print(f"\nWrote {len(written)} file{'s' if len(written) != 1 else ''}.")
    conflicts = [f for f in plan if f.action == "conflict"]
    for f in conflicts:
        print(f"  ! {f.path}: {f.note}")
    problems = validate(root)
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        return 1
    print("✓ workspace is valid")
    offered = _offer_bridges(root, answers.tools, interactive=not args.yes)
    hints = [h for h in connect_suggestions(answers.tools) if not any(h.endswith(" " + n) for n in offered)]
    if hints:
        print("\nConnect the tools you use:")
        for hint in hints:
            print(f"  {hint}")
    print("\nNext: open Claude Code in this folder (`claude`) and say hello to your team.")
    return 0


def _offer_bridges(root: Path, tools: list[str], interactive: bool) -> list[str]:
    """After init on Windows: offer to set up the bimai bridges for the tools someone declared."""
    if not interactive or conn.PLATFORM != "windows":
        return []
    offered = []
    for server in conn.load_servers().values():
        if not (server.bundle and server.release and set(server.matches_tools) & set(tools)):
            continue
        offered.append(server.name)
        question = (f"\nYou use {', '.join(t for t in server.matches_tools if t in tools)}. Connect your team to it now "
                    f"with {server.label}? (installs it if needed; Windows asks permission once) (Y/n)")
        if _ask(question, "y").lower().startswith("y"):
            ns = build_parser().parse_args(["connect", server.name, "--path", str(root), "--install"])
            if cmd_connect(ns) != 0:
                print(f"  You can try again later with: bimai connect {server.name}")
        else:
            print(f"  Later: bimai connect {server.name}")
    return offered


def _print_files(plan) -> None:
    for fw in plan:
        print(f"  {fw.action:<9} {fw.path}{f'  ({fw.note})' if fw.note else ''}")


def cmd_team(args: argparse.Namespace) -> int:
    root = args.path.resolve()
    try:
        problems = validate(root)
        seat = find_seat(root, args.seat)
    except (NoWorkspace, SeatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    seat_file = f".bimai/seats/{seat}/seat.yaml"
    seat_problems = [p for p in problems if p.file == seat_file]
    if seat_problems:
        for p in seat_problems:
            print(p)
        print("Fix seat.yaml first; nothing was written.")
        return 1
    ctx = load_seat_context(root, seat)
    plan = plan_claude_files(root, ctx)
    changes = [f for f in plan if f.action != "unchanged"]
    print(f"Team for seat {seat}: " + ", ".join(m.role for m in ctx.team))
    _print_files(changes or [])
    if not changes:
        print("  Everything is up to date.")
    if args.dry_run:
        print("Dry run: nothing was written.")
        return 0
    changed = apply_plan(root, plan)
    print(f"Changed {len(changed)} file{'s' if len(changed) != 1 else ''}.")
    remaining = validate(root)
    for p in remaining:
        print(f"  ✗ {p}")
    if not remaining:
        print("✓ workspace is valid")
    return 1 if remaining else 0


def _regenerate_team(root: Path, seat: str | None) -> None:
    """After the server list changes, every member's access and the Connections section follow."""
    try:
        name = find_seat(root, seat)
    except SeatError:
        return
    changed = apply_plan(root, plan_claude_files(root, load_seat_context(root, name)))
    if changed:
        print(f"Updated your team ({len(changed)} file{'s' if len(changed) != 1 else ''}).")


def _sign_in(name: str, kind: str, interactive: bool) -> None:
    if kind == "signin":
        if interactive and _ask("Sign in with your Autodesk account now? (Y/n)", "y").lower().startswith("y"):
            if conn.claude_mcp("login", name):
                print("✓ Signed in. Claude Code keeps the sign-in safely in your computer's keychain.")
                return
            print("Claude Code can't sign in to this server yet: it has to approve the project's servers first.")
        print(f"To sign in: {conn.in_session_hint(name)}")
    elif kind == "key":
        if interactive:
            key = getpass.getpass(f"Paste the key for {name} (it won't be shown): ").strip()
            if key:
                conn.store_key(name, key)
                print("✓ Key stored in your computer's keychain. It is never written to a file.")
                return
        print(f"To add the key later: bimai auth login {name}")


def _connect_list(root: Path) -> int:
    listed = {c.name for c in conn.connections(root)}
    print("Servers you can connect (bimai connect <name>):\n")
    for s in conn.load_servers().values():
        if s.unavailable:
            print(f"  {s.name:<20} {s.label:<28} not connectable yet: {s.unavailable.split(';')[0]}")
            continue
        status = "connected" if s.name in listed else ""
        access = "can change data" if s.access == "read-write" else "read-only"
        print(f"  {s.name:<20} {s.label:<28} {access:<16} {conn.SIGN_IN_TEXT[s.auth]:<38} {status}")
    custom = [n for n in listed if n not in conn.load_servers()]
    if custom:
        print(f"\nAlso in .mcp.json: {', '.join(sorted(custom))}")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    root = args.path.resolve()
    if not (root / ".bimai" / "project.yaml").is_file():
        print(f"error: no bimai project in {root}; run `bimai init` first", file=sys.stderr)
        return 2
    if not args.server and not args.custom:
        return _connect_list(root)
    interactive = not args.yes
    servers = conn.load_servers()
    try:
        mcp = conn.read_json(root / ".mcp.json")
        settings = conn.read_json(root / ".claude" / "settings.json")
        if args.custom:
            name = args.custom
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or name in servers:
                raise conn.ConnectError(f"'{name}' can't be used as a custom name (use lowercase letters, digits "
                                        "and dashes, and not a catalogue name)")
            if not args.url:
                raise conn.ConnectError("--custom needs --url")
            entry, kind, access, label = (conn.custom_config(args.url, args.auth, args.header, args.scheme),
                                          args.auth, "unknown", name)
        else:
            name = args.server
            if name not in servers:
                raise conn.ConnectError(f"no server '{name}'. Choose from: {', '.join(servers)}")
            server = servers[name]
            region = args.region
            if server.regions and not region and interactive and not server.unavailable:
                region = _ask(f"Which region are your projects in? ({', '.join(server.regions)})").lower()
            try:
                entry = conn.server_config(server, region=region, port=args.port)
            except conn.BridgeMissing:
                if not _offer_bridge_install(server, interactive, args.install):
                    raise
                entry = conn.server_config(server, region=region, port=args.port)
            kind, access, label = server.auth, server.access, server.label
            if access == "read-write" and not args.allow_writes:
                question = (f"{label} can change data. Every call will ask for your approval first. "
                            "Connect it? (y/N)")
                if not (interactive and _ask(question, "n").lower().startswith("y")):
                    raise conn.ConnectError(f"{label} can change data, so it needs your explicit consent: "
                                            f"bimai connect {name} --allow-writes")
    except bridges.BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (conn.ConnectError, conn.McpJsonError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    (root / ".mcp.json").write_text(conn.json_text(conn.mcp_with(mcp, name, entry)), encoding="utf-8")
    print(f"✓ {label} added to .mcp.json")
    if access == "read-write":
        path = root / ".claude" / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(conn.json_text(conn.settings_with_ask(settings, name)), encoding="utf-8")
        print("  Every call to it asks for your approval (rule in .claude/settings.json).")
    if kind == "none":
        print("  No sign-in needed.")
    _sign_in(name, kind, interactive)
    _regenerate_team(root, args.seat)
    server = servers.get(name)
    if server and server.bundle and server.port:
        port = args.port or server.port
        if bridges.probe(port) is not None:
            print(f"✓ {server.label} answers: Civil 3D is running with the bridge.")
        else:
            print(f"  {server.label} starts together with Civil 3D: open Civil 3D with a drawing to use it.")
    print("Start a new Claude Code session to use it. Claude Code asks once to approve servers in .mcp.json.")
    return 0


def _offer_bridge_install(server, interactive: bool, install: bool) -> bool:
    """A bimai bridge is missing: install it now (one Windows permission click) if the person agrees."""
    if not server.release or conn.PLATFORM != "windows":
        return False
    if not install:
        if not interactive:
            return False
        question = (f"{server.label} isn't installed yet. Install it now? Windows will ask for permission once, "
                    "because it is installed in the folder Civil 3D trusts. (Y/n)")
        if not _ask(question, "y").lower().startswith("y"):
            return False
    bridges.install(server, ask=lambda q: _ask(q, "y").lower().startswith("y"), say=print)
    return True


def cmd_disconnect(args: argparse.Namespace) -> int:
    root = args.path.resolve()
    try:
        mcp = conn.read_json(root / ".mcp.json")
        settings = conn.read_json(root / ".claude" / "settings.json")
    except conn.McpJsonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    entry = (mcp.get("mcpServers") or {}).get(args.server)
    if entry is None:
        print(f"error: '{args.server}' is not in .mcp.json", file=sys.stderr)
        return 2
    kind = conn.auth_of(args.server, entry)
    if kind == "signin":
        conn.claude_mcp("logout", args.server, quiet=True)   # before removing: the CLI must still know it
    (root / ".mcp.json").write_text(conn.json_text(conn.mcp_without(mcp, args.server)), encoding="utf-8")
    if conn.ask_rule(args.server) in (settings.get("permissions") or {}).get("ask", []):
        (root / ".claude" / "settings.json").write_text(
            conn.json_text(conn.settings_without_ask(settings, args.server)), encoding="utf-8")
    if kind == "key":
        conn.delete_key(args.server)
    print(f"✓ {args.server} removed")
    _regenerate_team(root, args.seat)
    return 0


def _listed(root: Path) -> dict:
    return conn.read_json(root / ".mcp.json").get("mcpServers") or {}


def cmd_auth(args: argparse.Namespace) -> int:
    if args.action == "headers":
        # Called by Claude Code (headersHelper) at connect time. stdout carries the header, nothing else.
        name = args.server or os.environ.get("CLAUDE_CODE_MCP_SERVER_NAME", "")
        headers = conn.headers_for(name, args.header, args.scheme) if name else None
        if headers is None:
            print(f"bimai: no key stored for '{name}'. Run: bimai auth login {name}", file=sys.stderr)
            return 1
        print(json.dumps(headers))
        return 0
    root = args.path.resolve()
    try:
        listed = _listed(root)
    except conn.McpJsonError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.action == "status":
        if not listed:
            print("No servers in .mcp.json yet. See: bimai connect")
        for name, entry in listed.items():
            kind = conn.auth_of(name, entry)
            extra = (" · key stored ✓" if conn.has_key(name) else " · no key yet ✗") if kind == "key" else ""
            if kind == "signin":
                extra = " · check with /mcp in Claude Code"
            print(f"  {name:<20} {conn.SIGN_IN_TEXT[kind]}{extra}")
        return 0
    if not args.server or args.server not in listed:
        print(f"error: '{args.server}' is not in .mcp.json. Servers: {', '.join(listed) or 'none'}", file=sys.stderr)
        return 2
    kind = conn.auth_of(args.server, listed[args.server])
    if args.action == "login":
        if kind == "none":
            print(f"{args.server} needs no sign-in.")
        elif kind == "unknown":
            print(conn.in_session_hint(args.server))
        else:
            _sign_in(args.server, kind, interactive=True)
        return 0
    # logout
    if kind == "key":
        print("✓ Key removed from your keychain." if conn.delete_key(args.server) else "No key was stored.")
    elif kind == "signin":
        if not conn.claude_mcp("logout", args.server):
            print(f"In Claude Code, type /mcp, choose '{args.server}' and clear its authentication.")
    else:
        print(f"{args.server} has no stored sign-in.")
    return 0


def cmd_bridge(args: argparse.Namespace) -> int:
    servers = conn.load_servers()
    server = servers.get(args.server)
    if server is None or not server.bundle:
        names = ", ".join(s.name for s in servers.values() if s.bundle)
        print(f"error: '{args.server}' is not a bimai bridge. Bridges: {names}", file=sys.stderr)
        return 2
    ask = (lambda q: True) if args.yes else (lambda q: _ask(q, "y").lower().startswith("y"))
    try:
        if args.action == "install":
            bridges.install(server, zip_path=args.from_zip, ask=ask, say=print)
            print(f"Next, in your project folder: bimai connect {server.name}")
        elif args.action == "uninstall":
            bridges.uninstall(server, say=print)
        else:
            st = bridges.status(server)
            if not st["installed"]:
                print(f"{server.label}: not installed. Install it with: bimai bridge install {server.name}")
            else:
                update = f" (version {st['latest']} is available: bimai bridge install {server.name})" if st["update_available"] else ""
                print(f"{server.label}: installed, version {st['version']}{update}")
                print(f"  {st['path']}")
                print("  running: yes" if st["running"] else "  running: no (it starts with Civil 3D)")
    except bridges.BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bimai", description="An open-source BIM team that lives in your editor.")
    parser.add_argument("--version", action="version", version=f"bimai {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("validate", help="check every bimai file in a project")
    p.add_argument("path", nargs="?", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("init", help="add bimai to a folder: scan it, ask a few questions, set up your team")
    p.add_argument("path", nargs="?", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--name", help="project name (default: folder name)")
    p.add_argument("--person", help="your name (default: your git user name)")
    p.add_argument("--role", help='your role, e.g. "BIM coordinator"')
    p.add_argument("--goals", help="comma-separated: requirements,risks,planning,reporting,issues,model-checks,"
                                   "delivery,meetings (default: your role's)")
    p.add_argument("--tools", help="comma-separated tools and data, e.g. revit,acc,relatics (default: found in folder)")
    p.add_argument("--new-to-vscode", action="store_true", help="add the Mentor to your team")
    p.add_argument("--language", choices=["en", "nl"], help="output language (default: en)")
    p.add_argument("--yes", "-y", action="store_true", help="ask nothing; accept defaults and the proposal")
    p.add_argument("--dry-run", action="store_true", help="show what would happen; write nothing")
    p.add_argument("--json", action="store_true", help="with --dry-run: print the result as JSON")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("team", help="update your Claude Code team after editing the team list in seat.yaml")
    p.add_argument("path", nargs="?", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--seat", help="whose team (needed when the project has several seats)")
    p.add_argument("--dry-run", action="store_true", help="show what would change; write nothing")
    p.set_defaults(func=cmd_team)

    p = sub.add_parser("connect", help="connect your team to a tool (an MCP server); without a name: list them")
    p.add_argument("server", nargs="?", help="server name, e.g. autodesk-help or revit")
    p.add_argument("--path", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--region", help="for servers with one endpoint per region, e.g. usa, gbr, aus")
    p.add_argument("--allow-writes", action="store_true", help="consent to a server that can change data")
    p.add_argument("--port", type=int, help="for local servers with a configurable port, e.g. civil3d")
    p.add_argument("--install", action="store_true", help="install a missing bimai bridge without asking first")
    p.add_argument("--custom", metavar="NAME", help="add your own server under this name (needs --url)")
    p.add_argument("--url", help="with --custom: the server's https address")
    p.add_argument("--auth", choices=["none", "key"], default="none", help="with --custom: does it need a key?")
    p.add_argument("--header", default="Authorization", help="with --auth key: header that carries the key")
    p.add_argument("--scheme", choices=["bearer", "raw"], default="bearer", help="with --auth key: 'Bearer <key>' or the key alone")
    p.add_argument("--seat", help="whose team to update (needed when the project has several seats)")
    p.add_argument("--yes", "-y", action="store_true", help="ask nothing")
    p.set_defaults(func=cmd_connect)

    p = sub.add_parser("disconnect", help="remove a server, its approval rule and its stored sign-in or key")
    p.add_argument("server")
    p.add_argument("--path", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--seat", help="whose team to update (needed when the project has several seats)")
    p.set_defaults(func=cmd_disconnect)

    p = sub.add_parser("bridge", help="install, check or remove a bimai bridge (e.g. civil3d)")
    p.add_argument("action", choices=["install", "status", "uninstall"])
    p.add_argument("server", help="the bridge, e.g. civil3d")
    p.add_argument("--from", dest="from_zip", type=Path, help="install from a zip you have instead of downloading")
    p.add_argument("--yes", "-y", action="store_true", help="don't ask bimai's questions (Windows still asks for permission)")
    p.set_defaults(func=cmd_bridge)

    p = sub.add_parser("auth", help="sign in to servers: login, status, logout")
    p.add_argument("action", choices=["login", "status", "logout", "headers"],
                   help="headers is used by Claude Code itself, not by people")
    p.add_argument("server", nargs="?")
    p.add_argument("--path", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--header", default="Authorization", help=argparse.SUPPRESS)
    p.add_argument("--scheme", choices=["bearer", "raw"], default="bearer", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_auth)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows consoles may not be UTF-8; never crash on printing a ✓ or a Dutch name.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)
