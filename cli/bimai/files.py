"""Planning and applying file writes, with bimai's ownership rules.

A plan is a list of `FileWrite`s with their final content; `apply()` carries it out. Nothing that
bimai doesn't own is ever overwritten or deleted.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

GENERATED = "<!-- bimai:generated -->"
BLOCK_START, BLOCK_END = "<!-- bimai:start -->", "<!-- bimai:end -->"


@dataclass
class FileWrite:
    path: str               # relative to the project root, posix
    content: str
    action: str             # create | update | unchanged | conflict | delete
    note: str = ""


def plan_write(root: Path, rel: str, content: str, *, merge_note: str = "", owned: bool = False) -> FileWrite:
    """Plan one file. An existing file is only updated when it is a file we merge into (merge_note)
    or a file bimai generated (owned, and it carries the GENERATED marker)."""
    path = root / rel
    if not path.exists():
        return FileWrite(rel, content, "create")
    current = path.read_text(encoding="utf-8")
    if current == content:
        return FileWrite(rel, content, "unchanged")
    if merge_note:
        return FileWrite(rel, content, "update", merge_note)
    if owned and GENERATED in current:
        return FileWrite(rel, content, "update", "regenerated")
    return FileWrite(rel, content, "conflict", "exists with different content; left as is")


def plan_create_only(root: Path, rel: str, content: str) -> FileWrite:
    return FileWrite(rel, content, "unchanged" if (root / rel).exists() else "create")


def with_block(current: str | None, block: str) -> str:
    """Put bimai's marked block into a file, replacing only an earlier block."""
    if current is None:
        return block
    if BLOCK_START in current and BLOCK_END in current:
        before, rest = current.split(BLOCK_START, 1)
        after = rest.split(BLOCK_END, 1)[1].lstrip("\n")
        return before + block + (("\n" + after) if after else "")
    return current.rstrip("\n") + "\n\n" + block


def apply(root: str | Path, plan: list[FileWrite]) -> list[FileWrite]:
    """Carry out every create, update and delete; returns what changed."""
    root = Path(root).resolve()
    changed = []
    for fw in plan:
        path = root / fw.path
        if fw.action in ("create", "update"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fw.content, encoding="utf-8", newline="\n")
        elif fw.action == "delete":
            path.unlink()
        else:
            continue
        changed.append(fw)
    return changed
