"""Check a project's .bimai/ workspace against its schemas and against itself.

Pure: `validate(path)` reads files and returns problems; it never writes or prints.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass
from functools import cache
from importlib import resources
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from bimai.team import load_catalogue

STEP_TYPES = ("script", "tool", "agent", "workflow", "gate")
ENV_REF = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}$")


class NoWorkspace(Exception):
    pass


@dataclass(frozen=True, order=True)
class Problem:
    file: str
    location: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.location}: {self.message}" if self.location else f"{self.file}: {self.message}"

    def as_dict(self) -> dict:
        return asdict(self)


@cache
def _validator(name: str) -> Draft202012Validator:
    text = resources.files("bimai").joinpath("schemas", f"{name}.schema.json").read_text(encoding="utf-8")
    return Draft202012Validator(json.loads(text), format_checker=FormatChecker())


def _plain(value):
    """YAML turns 2026-09-28 into a date; schemas expect ISO strings."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _dotted(path) -> str:
    return ".".join(str(p) for p in path)


class _Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.bimai = root / ".bimai"
        self.problems: list[Problem] = []

    def rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def report(self, path: Path, location: str, message: str) -> None:
        self.problems.append(Problem(self.rel(path), location, message))

    def load(self, path: Path, schema: str) -> dict | None:
        """Parse and schema-check one file. Returns its data only if it is a mapping."""
        try:
            data = _plain(yaml.safe_load(path.read_text(encoding="utf-8")))
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f"line {mark.line + 1}" if mark else ""
            self.report(path, where, f"not valid YAML ({getattr(exc, 'problem', None) or exc})")
            return None
        except (OSError, UnicodeDecodeError) as exc:
            self.report(path, "", f"cannot be read ({exc})")
            return None
        if data is None:
            data = {}
        for err in _validator(schema).iter_errors(data):
            self.report(path, _dotted(err.absolute_path), err.message)
        return data if isinstance(data, dict) else None


def validate(path: str | Path = ".") -> list[Problem]:
    root = Path(path).resolve()
    if not (root / ".bimai" / "project.yaml").is_file():
        raise NoWorkspace(f"no bimai project in {root} (.bimai/project.yaml not found)")
    ws = _Workspace(root)
    b = ws.bimai

    ws.load(b / "project.yaml", "project")
    people_file, ownership_file = b / "people.yaml", b / "ownership.yaml"
    people_data = ws.load(people_file, "people") if people_file.is_file() else None
    ownership = (ws.load(ownership_file, "ownership") if ownership_file.is_file() else None) or {}
    seats = {d.name: ws.load(d / "seat.yaml", "seat")
             for d in sorted(b.glob("seats/*/")) if (d / "seat.yaml").is_file()}
    workflows = {p: ws.load(p, "workflow") for p in sorted(b.glob("workflows/*.yaml"))}
    automations = {p: ws.load(p, "automation") for p in sorted(b.glob("automations/*.yaml"))}

    # Only check references against a file that exists and parsed; otherwise every
    # reference would be reported on top of the real problem.
    people = _ids(people_data.get("people")) if isinstance(people_data, dict) else None
    positions = ownership.get("positions") if isinstance(ownership.get("positions"), dict) else {}

    _check_ownership(ws, ownership_file, ownership, positions, people)
    for name, seat in seats.items():
        if seat:
            _check_seat(ws, b / "seats" / name / "seat.yaml", seat, positions, people, ownership_file.is_file())
    for p, wf in workflows.items():
        if wf and isinstance(wf.get("steps"), dict):
            _check_workflow(ws, p, wf["steps"])
    for p, auto in automations.items():
        owner = (auto or {}).get("owner")
        if isinstance(owner, str) and owner not in positions and owner not in seats:
            ws.report(p, "owner", f"'{owner}' is neither a position in ownership.yaml nor a seat")

    _check_mcp_json(ws, root / ".mcp.json")
    return sorted(set(ws.problems))


def _check_mcp_json(ws: _Workspace, path: Path) -> None:
    """.mcp.json is shared with the team: it may hold references to secrets, never the secrets."""
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        ws.report(path, f"line {getattr(exc, 'lineno', '?')}", "not valid JSON")
        return
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return
    advice = ("looks like a secret written into a shared file; use `bimai connect --custom <name> --url <url> "
              "--auth key` (key in your keychain) or a ${VARIABLE} reference")
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            continue
        for key in ("headers", "env"):
            values = entry.get(key)
            for k, v in (values.items() if isinstance(values, dict) else []):
                if not (isinstance(v, str) and ENV_REF.match(v)):
                    ws.report(path, f"mcpServers.{name}.{key}.{k}", advice)
        oauth = entry.get("oauth")
        if isinstance(oauth, dict) and "clientSecret" in oauth:
            ws.report(path, f"mcpServers.{name}.oauth.clientSecret", advice)


def _ids(items) -> set[str] | None:
    if not isinstance(items, list):
        return None
    return {i["id"] for i in items if isinstance(i, dict) and isinstance(i.get("id"), str)}


def _check_ownership(ws: _Workspace, path: Path, ownership: dict, positions: dict, people: set | None) -> None:
    if people is not None:
        for pid, pos in positions.items():
            if not isinstance(pos, dict):
                continue
            for person in pos.get("held_by") or []:
                if isinstance(person, str) and person not in people:
                    ws.report(path, f"positions.{pid}.held_by", f"'{person}' is not in people.yaml")
            lead = pos.get("lead")
            if isinstance(lead, str) and lead not in people:
                ws.report(path, f"positions.{pid}.lead", f"'{lead}' is not in people.yaml")
    cover = ownership.get("cover") if isinstance(ownership.get("cover"), list) else []
    for i, entry in enumerate(cover):
        if not isinstance(entry, dict):
            continue
        by, pos = entry.get("by"), entry.get("position")
        if people is not None and isinstance(by, str) and by not in people:
            ws.report(path, f"cover.{i}.by", f"'{by}' is not in people.yaml")
        if isinstance(pos, str) and pos not in positions:
            ws.report(path, f"cover.{i}.position", f"'{pos}' is not a position in ownership.yaml")


MAX_TEAM = 5


def _check_team(ws: _Workspace, path: Path, team) -> None:
    if not isinstance(team, list):
        return
    known = load_catalogue().roles  # the roles this bimai version knows
    seen: set[str] = set()
    for i, member in enumerate(team):
        role = member.get("role") if isinstance(member, dict) else None
        if not isinstance(role, str):
            continue
        if role not in known:
            ws.report(path, f"team.{i}.role", f"'{role}' is not a known role (known: {', '.join(sorted(known))})")
        elif role in seen:
            ws.report(path, f"team.{i}.role", f"'{role}' is on the team twice")
        seen.add(role)
    if len(team) > MAX_TEAM:
        ws.report(path, "team", f"has {len(team)} members; the maximum is {MAX_TEAM}")


def _check_seat(ws: _Workspace, path: Path, seat: dict, positions: dict, people: set | None,
                has_ownership: bool) -> None:
    _check_team(ws, path, seat.get("team"))
    person = seat.get("person")
    if people is not None and isinstance(person, str) and person not in people:
        ws.report(path, "person", f"'{person}' is not in people.yaml")
    if not has_ownership:
        return
    for i, pos in enumerate(seat.get("positions") or []):
        if isinstance(pos, str) and pos not in positions:
            ws.report(path, f"positions.{i}", f"'{pos}' is not a position in ownership.yaml")


def _check_workflow(ws: _Workspace, path: Path, steps: dict) -> None:
    graph: dict[str, list[str]] = {}
    for sid, step in steps.items():
        if not isinstance(step, dict):
            continue
        kinds = [k for k in STEP_TYPES if k in step]
        if len(kinds) != 1:
            found = ", ".join(kinds) if kinds else "none"
            ws.report(path, f"steps.{sid}", f"needs exactly one of {', '.join(STEP_TYPES)} (found: {found})")
        needs = step.get("needs") if isinstance(step.get("needs"), list) else []
        graph[sid] = [n for n in needs if isinstance(n, str)]
        for n in graph[sid]:
            if n not in steps:
                ws.report(path, f"steps.{sid}.needs", f"step '{n}' does not exist")
    for cycle in _cycles(graph):
        ws.report(path, "steps", f"cycle: {' -> '.join(cycle + [cycle[0]])}")


def _cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """Each distinct cycle once, rotated to start at its smallest step for stable output."""
    found: set[tuple[str, ...]] = set()
    state: dict[str, int] = {}  # 1 = on the current path, 2 = done
    path: list[str] = []

    def visit(node: str) -> None:
        state[node] = 1
        path.append(node)
        for nxt in graph.get(node, []):
            if nxt not in graph:
                continue
            if state.get(nxt) == 1:
                cycle = path[path.index(nxt):]
                i = cycle.index(min(cycle))
                found.add(tuple(cycle[i:] + cycle[:i]))
            elif state.get(nxt) is None:
                visit(nxt)
        path.pop()
        state[node] = 2

    for node in graph:
        if node not in state:
            visit(node)
    return [list(c) for c in sorted(found)]
