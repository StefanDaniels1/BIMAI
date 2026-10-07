"""`bimai init`: scan a folder, ask a short interview, propose a team, write the workspace.

`plan_files()` is pure and returns every file with its final content; `apply()` writes them.
The Claude Code files come from the shared generator in claude.py; the interview and printing
live in cli.py.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from bimai.claude import SeatContext, plan_claude_files
from bimai.connections import (Connection, McpJsonError, connections_from, json_text, load_servers, mcp_with,
                               read_json, server_config, settings_with_rules, tool_connections, write_rules)
from bimai.files import BLOCK_END, BLOCK_START, FileWrite, apply, plan_write  # noqa: F401 (re-exported)
from bimai.scan import Scan
from bimai.team import Catalogue, Team, load_catalogue

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


def _bimai_files(a: Answers, team: Team, cat: Catalogue) -> dict[str, str]:
    preset = cat.presets[team.preset]
    pid, me = a.project_id, a.person_id
    return {
        ".bimai/project.yaml": _yaml({
            "format_version": 1, "id": pid, "name": a.name, "language": a.language,
            "write_mode": "gated-write", "rule_owners": [me],
        }),
        ".bimai/people.yaml": _yaml({"people": [{"id": me, "name": a.person, "title": preset.label, "seat": me}]}),
        ".bimai/ownership.yaml": _yaml({"positions": {preset.id: {"role": preset.id, "held_by": [me]}}}),
        f".bimai/seats/{me}/seat.yaml": _yaml({
            "person": me, "role": a.role, "preset": preset.id, "goals": a.goals, "tools": a.tools,
            "positions": [preset.id], "team": [{"role": m.role, "why": m.why} for m in team.members],
        }),
    }


def seat_context(a: Answers, team: Team, cat: Catalogue, conns: list[Connection] | None = None) -> SeatContext:
    preset = cat.presets[team.preset]
    return SeatContext(project_name=a.name, language=a.language, person_name=a.person, seat=a.person_id,
                       title=preset.label, positions=[preset.id], goals=a.goals, team=team.members,
                       connections=conns or [], tools=a.tools)


def _plan_mcp(root: Path, tools: list[str]) -> tuple[FileWrite, list[Connection], list[str]]:
    """Every project gets the default servers (Autodesk Product Help) and the servers of chosen tools that are
    ready on this computer; servers already listed are kept. Also returns the deny rules for the write tools
    of the servers it adds (connected read-only)."""
    path = root / ".mcp.json"
    try:
        data = read_json(path)
    except McpJsonError as exc:
        return FileWrite(".mcp.json", "", "conflict", str(exc)), [], []
    new, deny = data, []
    for server in load_servers().values():
        if server.default and server.name not in (data.get("mcpServers") or {}):
            new = mcp_with(new, server.name, server_config(server))
    for c in tool_connections(tools):
        if c["status"] == "ready" and c["server"] not in (data.get("mcpServers") or {}):
            new = mcp_with(new, c["server"], c["config"])
            deny += write_rules(load_servers()[c["server"]])
    if new is data and path.exists():
        return FileWrite(".mcp.json", path.read_text(encoding="utf-8"), "unchanged"), connections_from(data), []
    return (plan_write(root, ".mcp.json", json_text(new), merge_note="bimai's servers added; other servers kept"),
            connections_from(new), deny)


def plan_files(root: str | Path, a: Answers, team: Team, cat: Catalogue | None = None) -> list[FileWrite]:
    root = Path(root).resolve()
    cat = cat or load_catalogue()
    plan = [plan_write(root, rel, content) for rel, content in _bimai_files(a, team, cat).items()]
    mcp, conns, deny = _plan_mcp(root, a.tools)
    plan += plan_claude_files(root, seat_context(a, team, cat, conns), cat)
    plan.append(mcp)

    settings = root / ".claude" / "settings.json"
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            plan.append(FileWrite(".claude/settings.json", "", "conflict", "not valid JSON; left as is"))
            data = None
        if isinstance(data, dict):
            notes = [f"model stays '{data['model']}'" if "model" in data else "model set to sonnet"]
            new = settings_with_rules({"model": "sonnet", **data}, "deny", deny) if deny else {"model": "sonnet", **data}
            if deny:
                notes.append("read-only rules added")
            if new == data:
                plan.append(FileWrite(".claude/settings.json", "", "unchanged", notes[0]))
            else:
                plan.append(FileWrite(".claude/settings.json", json.dumps(new, indent=2) + "\n", "update",
                                      "; ".join(notes) + "; other settings kept"))
        elif data is not None:
            plan.append(FileWrite(".claude/settings.json", "", "conflict", "not a JSON object; left as is"))
    else:
        new = settings_with_rules({"model": "sonnet"}, "deny", deny) if deny else {"model": "sonnet"}
        plan.append(FileWrite(".claude/settings.json", json.dumps(new, indent=2) + "\n", "create"))

    gitignore = root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    present = {line.strip() for line in current.splitlines()}
    missing = [line for line in GITIGNORE if line not in present]
    if missing:
        prefix = (current.rstrip("\n") + "\n\n") if current.strip() else ""
        plan.append(plan_write(root, ".gitignore", prefix + "# bimai\n" + "\n".join(missing) + "\n",
                          merge_note="bimai lines added"))
    else:
        plan.append(FileWrite(".gitignore", current, "unchanged"))
    return plan
