"""The `bimai` command. Each subcommand formats the result of a pure function."""
from __future__ import annotations

import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

from bimai import __version__
from bimai.claude import SeatError, find_seat, load_seat_context, plan_claude_files
from bimai.files import apply as apply_plan
from bimai.init import AlreadyInitialised, Answers, apply, check_not_initialised, plan_files, suggested_tools
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
        out = subprocess.run(["git", "config", "user.name"], cwd=cwd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


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
    default_person = _git_user(root) or getpass.getuser()
    person = args.person or (_ask("Your name", default_person) if interactive else default_person)

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
    print("✓ workspace is valid\n\nNext: open Claude Code in this folder (`claude`) and say hello to your team.")
    return 0


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
