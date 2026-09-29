"""`bimai init`: scan a folder, ask a short interview, propose a team, write the workspace.

`plan_files()` is pure and returns every file with its final content; `apply()` writes them.
The interview and printing live in cli.py.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from bimai.scan import Scan
from bimai.team import Catalogue, Team, load_catalogue

BLOCK_START, BLOCK_END = "<!-- bimai:start -->", "<!-- bimai:end -->"
GITIGNORE = (".bimai/state/", ".bimai/site/", ".bimai/data/")


class AlreadyInitialised(Exception):
    pass


@dataclass
class Answers:
    name: str               # project name
    person: str             # the user's name
    role: str               # as typed, e.g. "BIM coordinator"
    goals: list[str]
    tools: list[str]
    new_to_vscode: bool = False
    language: str = "en"

    @property
    def project_id(self) -> str:
        return slug(self.name) or "project"

    @property
    def person_id(self) -> str:
        return slug(self.person.split()[0] if self.person.split() else "") or "me"

    def as_dict(self) -> dict:
        return dict(asdict(self), project_id=self.project_id, person_id=self.person_id)


@dataclass
class FileWrite:
    path: str               # relative to the project root, posix
    content: str
    action: str             # create | update | unchanged | conflict
    note: str = ""


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def check_not_initialised(root: Path) -> None:
    if (root / ".bimai" / "project.yaml").exists():
        raise AlreadyInitialised(f"{root} is already a bimai project (.bimai/project.yaml exists)")


def suggested_tools(scan: Scan, cat: Catalogue | None = None) -> dict[str, str]:
    """tool id -> the file that suggested it."""
    cat = cat or load_catalogue()
    tools: dict[str, str] = {}
    for key, file in scan.suggestions.items():
        tool = cat.suggests.get(key)
        if tool:
            tools.setdefault(tool, file)
    return tools


def _yaml(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def _plan(root: Path, rel: str, content: str, *, merge_note: str = "") -> FileWrite:
    """Only files we merge into (merge_note given) may be updated; anything else is never overwritten."""
    path = root / rel
    if not path.exists():
        return FileWrite(rel, content, "create")
    current = path.read_text(encoding="utf-8")
    if current == content:
        return FileWrite(rel, content, "unchanged")
    if not merge_note:
        return FileWrite(rel, content, "conflict", "exists with different content; left as is")
    return FileWrite(rel, content, "update", merge_note)


def _bimai_files(a: Answers, team: Team, cat: Catalogue) -> dict[str, str]:
    preset = cat.presets[team.preset]
    pid, me = a.project_id, a.person_id
    team_rows = "\n".join(f"| {cat.roles[m.role].label} | {m.why} |" for m in team.members)
    return {
        ".bimai/project.yaml": _yaml({
            "format_version": 1, "id": pid, "name": a.name, "language": a.language,
            "write_mode": "gated-write", "rule_owners": [me],
        }),
        ".bimai/people.yaml": _yaml({"people": [{"id": me, "name": a.person, "title": preset.label, "seat": me}]}),
        ".bimai/ownership.yaml": _yaml({"positions": {preset.id: {"role": preset.id, "held_by": [me]}}}),
        f".bimai/seats/{me}/seat.yaml": _yaml({
            "person": me, "role": a.role, "preset": preset.id, "goals": a.goals, "positions": [preset.id],
            "team": [{"role": m.role, "why": m.why} for m in team.members],
        }),
        f".bimai/seats/{me}/team.md": (
            f"# {a.person}'s team\n\n| Member | Why |\n|---|---|\n{team_rows}\n\n"
            "Change it by editing seat.yaml, or run `bimai init` again in a new project.\n"
        ),
    }


def _subagent(role) -> str:
    meta = yaml.safe_dump({"name": role.id, "description": role.description, "model": role.model},
                          sort_keys=False, allow_unicode=True, width=10_000)
    return f"---\n{meta}---\n{role.charter}"


def _claude_block(a: Answers, team: Team, cat: Catalogue) -> str:
    coordinator = cat.roles["coordinator"]
    members = [m for m in team.members if m.role != "coordinator"]
    rows = "\n".join(f"- **{cat.roles[m.role].label}** (subagent `{m.role}`): {cat.roles[m.role].description}"
                     for m in members) or "- (no other members yet)"
    return (
        f"{BLOCK_START}\n"
        "<!-- Written by `bimai init`. Edit outside this block; this block may be regenerated. -->\n"
        f"# bimai: {a.name}\n\n"
        f"{coordinator.charter}\n"
        f"## Your team\n\n{rows}\n\n"
        f"## This seat\n\n"
        f"You work for **{a.person}** ({cat.presets[team.preset].label}), seat `.bimai/seats/{a.person_id}/`. "
        f"Goals: {', '.join(a.goals) or 'none chosen'}. Write documents in "
        f"{'Dutch' if a.language == 'nl' else 'English'}.\n"
        f"{BLOCK_END}\n"
    )


def _with_block(current: str | None, block: str) -> str:
    if current is None:
        return block
    if BLOCK_START in current and BLOCK_END in current:
        before, rest = current.split(BLOCK_START, 1)
        after = rest.split(BLOCK_END, 1)[1].lstrip("\n")
        return before + block + (("\n" + after) if after else "")
    return current.rstrip("\n") + "\n\n" + block


def plan_files(root: str | Path, a: Answers, team: Team, cat: Catalogue | None = None) -> list[FileWrite]:
    root = Path(root).resolve()
    cat = cat or load_catalogue()
    plan = [_plan(root, rel, content) for rel, content in _bimai_files(a, team, cat).items()]

    for m in team.members:
        if m.role == "coordinator":
            continue
        plan.append(_plan(root, f".claude/agents/{m.role}.md", _subagent(cat.roles[m.role])))

    claude_md = root / "CLAUDE.md"
    current = claude_md.read_text(encoding="utf-8") if claude_md.exists() else None
    plan.append(_plan(root, "CLAUDE.md", _with_block(current, _claude_block(a, team, cat)),
                      merge_note="bimai block added or refreshed; your content is kept"))

    settings = root / ".claude" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            plan.append(FileWrite(".claude/settings.json", "", "conflict", "not valid JSON; left as is"))
            data = None
        if isinstance(data, dict):
            if "model" in data:
                plan.append(FileWrite(".claude/settings.json", "", "unchanged", f"model stays '{data['model']}'"))
            else:
                data["model"] = "sonnet"
                plan.append(FileWrite(".claude/settings.json", json.dumps(data, indent=2) + "\n", "update",
                                      "model set to sonnet; other settings kept"))
        elif data is not None:
            plan.append(FileWrite(".claude/settings.json", "", "conflict", "not a JSON object; left as is"))
    else:
        plan.append(FileWrite(".claude/settings.json", json.dumps({"model": "sonnet"}, indent=2) + "\n", "create"))

    gitignore = root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    present = {line.strip() for line in current.splitlines()}
    missing = [line for line in GITIGNORE if line not in present]
    if missing:
        prefix = (current.rstrip("\n") + "\n\n") if current.strip() else ""
        plan.append(_plan(root, ".gitignore", prefix + "# bimai\n" + "\n".join(missing) + "\n",
                          merge_note="bimai lines added"))
    else:
        plan.append(FileWrite(".gitignore", current, "unchanged"))
    return plan


def apply(root: str | Path, plan: list[FileWrite]) -> list[FileWrite]:
    """Write every create/update; returns what was written."""
    root = Path(root).resolve()
    written = []
    for fw in plan:
        if fw.action not in ("create", "update"):
            continue
        path = root / fw.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fw.content, encoding="utf-8", newline="\n")
        written.append(fw)
    return written
