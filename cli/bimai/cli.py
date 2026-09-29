"""The `bimai` command. Each subcommand formats the result of a pure function."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bimai import __version__
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bimai", description="An open-source BIM team that lives in your editor.")
    parser.add_argument("--version", action="version", version=f"bimai {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    p = sub.add_parser("validate", help="check every bimai file in a project")
    p.add_argument("path", nargs="?", type=Path, default=Path("."), help="project folder (default: current folder)")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    p.set_defaults(func=cmd_validate)
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
