#!/usr/bin/env python3
"""Documentation is part of done: fail CI when something user-facing has no page.

Checks:
  1. every slash command and every top-level `bimai` command in ARCHITECTURE.md
     appears in docs/content/docs/reference/commands.mdx
  2. every pack in packs/ is mentioned somewhere in the docs content
  3. (with --links) every internal link in the built site (docs/out) resolves

Usage: check_docs.py [--links]
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "docs" / "content" / "docs"
OUT = ROOT / "docs" / "out"


def check_commands() -> list[str]:
    arch = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    reference = (CONTENT / "reference" / "commands.mdx").read_text(encoding="utf-8")
    problems = []
    for cmd in sorted(set(re.findall(r"/bimai:([a-z-]+)", arch))):
        if cmd not in reference:
            problems.append(f"/bimai:{cmd} is not in reference/commands.mdx")
    for cmd in sorted(set(re.findall(r"`bimai ([a-z][a-z-]*)", arch))):
        if f"bimai {cmd}" not in reference:
            problems.append(f"`bimai {cmd}` is not in reference/commands.mdx")
    return problems


def check_packs() -> list[str]:
    docs_text = "\n".join(p.read_text(encoding="utf-8") for p in CONTENT.rglob("*.mdx"))
    return [f"pack {p.name} has no documentation page" for p in sorted((ROOT / "packs").iterdir())
            if p.is_dir() and p.name not in docs_text]


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.startswith("/") and not href.startswith("//"):
                self.links.append(href.split("#")[0].split("?")[0])


def check_links() -> list[str]:
    if not OUT.exists():
        return ["docs/out does not exist: run `npm run build` in docs/ first"]
    problems, seen = [], set()
    for html in OUT.rglob("*.html"):
        parser = _Links()
        parser.feed(html.read_text(encoding="utf-8", errors="replace"))
        for link in parser.links:
            if link in seen or link == "/":
                continue
            seen.add(link)
            target = OUT / link.lstrip("/")
            if not (target.exists() or target.with_suffix(".html").exists() or (target / "index.html").exists()):
                problems.append(f"broken link {link} (first seen in {html.relative_to(OUT)})")
    return problems


def main(argv: list[str]) -> int:
    problems = check_commands() + check_packs()
    if "--links" in argv:
        problems += check_links()
    for p in problems:
        print(f"✗ {p}")
    print("✓ documentation complete" if not problems else f"{len(problems)} documentation problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
