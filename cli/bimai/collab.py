"""Working together: joining a project, the seat brief, handoffs and decisions.

People say what they want ("join this project", "hand this to the modeller", "record that decision"); Claude
runs these commands. Every record is one file that only its author (or, for a handoff, its receiver) changes, so
two people never edit the same file. Shared files (CLAUDE.md, .claude/agents) are the same for every seat; what
is personal comes from the seat brief, printed by each person's own session-start hook.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from bimai.init import slug
from bimai.team import Catalogue, UnknownRole, load_catalogue, match_preset, propose

BRIEF_CHARS = 1800              # about 450 tokens: the brief is read at every session start
LIST_MAX = 5


class CollabError(Exception):
    """Something the person (or Claude) can fix, in plain language (exit 2)."""


# ------------------------------------------------------------------ small file helpers

def _load(path: Path) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}


def _dump(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8", newline="\n")


def read_record(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---\n") and "\n---" in text[4:]:
        head, body = text[4:].split("\n---", 1)
        try:
            return (yaml.safe_load(head) or {}), body.lstrip("\n")
        except yaml.YAMLError:
            pass
    return {}, text


def write_record(path: Path, meta: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    head = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(f"---\n{head}---\n\n{body.strip()}\n", encoding="utf-8", newline="\n")


def _unique(folder: Path, stem: str) -> Path:
    path, n = folder / f"{stem}.md", 2
    while path.exists():
        path, n = folder / f"{stem}-{n}.md", n + 1
    return path


def _now() -> dt.datetime:
    return dt.datetime.now().replace(microsecond=0)


def positions(root: Path) -> dict:
    return (_load(root / ".bimai" / "ownership.yaml").get("positions") or {})


def people(root: Path) -> dict:
    return {p["id"]: p for p in _load(root / ".bimai" / "people.yaml").get("people") or [] if isinstance(p, dict) and "id" in p}


def seat_positions(root: Path, seat: str) -> list[str]:
    return list(_load(root / ".bimai" / "seats" / seat / "seat.yaml").get("positions") or [])


def my_seat(root: Path) -> str | None:
    """The seat of the person on this computer: the one their own hooks name (.claude/settings.local.json)."""
    try:
        data = json.loads((root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    found = []
    for event, groups in (data.get("hooks") or {}).items():
        for group in groups if isinstance(groups, list) else []:
            for h in (group.get("hooks") or []) if isinstance(group, dict) else []:
                args = h.get("args") if isinstance(h, dict) else None
                if isinstance(args, list) and "--seat" in args[:-1]:
                    found.append((args[:1] != ["brief"], args[args.index("--seat") + 1]))   # the brief hook first
    return sorted(found)[0][1] if found else None


def resolve_seat(root: Path, seat: str | None) -> str:
    seats = sorted(d.name for d in (root / ".bimai" / "seats").glob("*/") if (d / "seat.yaml").is_file())
    chosen = seat or my_seat(root) or (seats[0] if len(seats) == 1 else None)
    if not chosen:
        raise CollabError(f"Which seat? This project has several: {', '.join(seats)}. Use --seat.")
    if chosen not in seats:
        raise CollabError(f"No seat '{chosen}'. Seats: {', '.join(seats) or 'none'}")
    return chosen


# ------------------------------------------------------------------ join

@dataclass
class Joined:
    seat: str
    name: str
    preset: str
    position: str
    shared_with: list[str]
    team: object                                   # team.Team


def plan_join(root: Path, person: str, role: str, goals: list[str], tools: list[str], new_to_vscode: bool = False,
              position: str | None = None, cat: Catalogue | None = None) -> Joined:
    """What joining would do, without writing anything."""
    cat = cat or load_catalogue()
    if not (root / ".bimai" / "project.yaml").is_file():
        raise CollabError(f"{root} isn't a bimai project yet. To start one: bimai init")
    pid = slug(person.split()[0] if person.split() else "") or "me"
    if (root / ".bimai" / "seats" / pid).exists() or pid in people(root):
        raise CollabError(f"'{person}' already has a seat in this project (.bimai/seats/{pid}/). To change the team: "
                          f"bimai team --seat {pid}")
    preset = match_preset(role, cat)                                  # UnknownRole with suggestions
    unknown = [g for g in goals if g not in cat.goals] + [t for t in tools if t not in cat.tools]
    if unknown:
        raise CollabError(f"Unknown goals or tools: {', '.join(unknown)}")
    existing = positions(root)
    if position and position in existing:
        chosen, shared_with = position, list(existing[position].get("held_by") or [])
    else:
        chosen = position or (preset.id if preset.id not in existing else f"{preset.id}-{pid}")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", chosen):
            raise CollabError("A position id uses lowercase letters, digits and dashes, e.g. modeller-structure")
        shared_with = []
    team = propose(preset.id, goals, tools, new_to_vscode, cat)
    return Joined(pid, person, preset.id, chosen, shared_with, team)


def join(root: Path, person: str, role: str, goals: list[str], tools: list[str], new_to_vscode: bool = False,
         position: str | None = None, cat: Catalogue | None = None) -> Joined:
    """Adds a person, their seat and a position to an existing project. Other seats' files aren't touched."""
    j = plan_join(root, person, role, goals, tools, new_to_vscode, position, cat)
    own_path = root / ".bimai" / "ownership.yaml"
    ownership = _load(own_path)
    all_positions = ownership.setdefault("positions", {})
    if j.position in all_positions:                                    # share an existing position
        pos = all_positions[j.position]
        pos["held_by"] = list(pos.get("held_by") or []) + [j.seat]
        pos.setdefault("lead", (pos["held_by"] or [j.seat])[0])         # several holders need a lead (§8.7)
    else:
        all_positions[j.position] = {"role": j.preset, "held_by": [j.seat]}
    _dump(own_path, ownership)
    people_path = root / ".bimai" / "people.yaml"
    data = _load(people_path)
    label = (cat or load_catalogue()).presets[j.preset].label
    data.setdefault("people", []).append({"id": j.seat, "name": person, "title": label, "seat": j.seat})
    _dump(people_path, data)
    _dump(root / ".bimai" / "seats" / j.seat / "seat.yaml", {
        "person": j.seat, "role": role, "preset": j.preset, "goals": goals, "tools": tools, "positions": [j.position],
        "team": [{"role": m.role, "why": m.why} for m in j.team.members]})
    return j


def join_interview(root: Path, git_user: str | None = None, role: str | None = None, cat: Catalogue | None = None) -> dict:
    """The joining questions, in the onboarding interview format, for Claude Code's question tool."""
    from bimai import interview
    cat = cat or load_catalogue()
    if not (root / ".bimai" / "project.yaml").is_file():
        raise CollabError(f"{root} isn't a bimai project yet. To start one: bimai init --interview")
    project = _load(root / ".bimai" / "project.yaml")
    base = {"for": "Claude Code's AskUserQuestion tool: one call per step; options in the given order (recommended "
                   "first); multi_select as given. Map an 'Other' answer to the closest allowed value and confirm it "
                   "when unsure.",
            "project": project.get("name") or project.get("id"),
            "people": [f"{p.get('name')} ({p.get('title')})" for p in people(root).values()],
            "init_command": "bimai join --person <person> --role <role> --goals <goal,goal> --tools <tool,tool> "
                            "[--position <id>] [--new-to-vscode] --yes"}
    if role is None:
        step = interview.step_one(root, git_user, cat)
        step["questions"] = [q for q in step["questions"] if q["id"] in ("person", "role")]
        return {**base, "steps": [step], "next": 'After step 1, run: bimai join --interview --role "<role>"  (for step 2)'}
    preset = match_preset(role, cat)
    step = interview.step_two(root, preset.label, cat)
    same = {pid: p for pid, p in positions(root).items() if p.get("role") == preset.id}
    if same:
        options = [{"label": "A position of my own", "description": f"New position for you ({preset.id} or similar)",
                    "value": None}]
        for pid, p in list(same.items())[:3]:
            holders = ", ".join(people(root).get(h, {}).get("name", h) for h in p.get("held_by") or [])
            options.append({"label": f"Share {pid}"[:60], "description": f"Work together with {holders} in this job",
                            "value": pid})
        step["questions"].append({
            "id": "position", "header": "Position", "kind": "choice", "multi_select": False,
            "question": f"There is already a {preset.label} position here. Take a position of your own (another part "
                        "of the work, e.g. a zone or discipline) or share it?",
            "options": options, "recommended": None,
            "allowed": [{"value": None, "label": "A position of my own"}] + [{"value": k, "label": k} for k in same]})
    return {**base, "steps": [step],
            "next": "After step 2, show who joins and their team with the join command and --dry-run, then ask for a final yes."}


# ------------------------------------------------------------------ handoffs

def handoff(root: Path, seat: str, to: str, title: str, body: str = "", evidence: list[str] | None = None) -> Path:
    known = positions(root)
    if to not in known:
        raise CollabError(f"No position '{to}'. Positions: {_position_list(root)}")
    if not title.strip():
        raise CollabError("A handoff needs a title")
    mine = seat_positions(root, seat)
    now = _now()
    path = _unique(root / ".bimai" / "positions" / to / "inbox", f"{now:%Y%m%d-%H%M}-{slug(title)[:40] or 'handoff'}")
    write_record(path, {"title": title.strip(), "from": seat, "from_position": mine[0] if mine else None, "to": to,
                        "created": now.isoformat(), "status": "open", "evidence": list(evidence or [])}, body or title)
    return path


def inbox(root: Path, seat: str, include_done: bool = False) -> list[dict]:
    items = []
    for pos in seat_positions(root, seat):
        for path in sorted((root / ".bimai" / "positions" / pos / "inbox").glob("*.md")):
            meta, body = read_record(path)
            if include_done or meta.get("status", "open") == "open":
                items.append({"id": path.stem, "position": pos, "path": path.relative_to(root).as_posix(),
                              "body": body.strip(), **meta})
    return sorted(items, key=lambda i: str(i.get("created", "")))


def handoff_done(root: Path, seat: str, hid: str, note: str = "") -> Path:
    for pos in seat_positions(root, seat):
        path = root / ".bimai" / "positions" / pos / "inbox" / f"{hid}.md"
        if path.is_file():
            meta, body = read_record(path)
            meta.update(status="done", closed=_now().isoformat(), closed_by=seat)
            if note:
                meta["note"] = note
            write_record(path, meta, body)
            return path
    raise CollabError(f"No handoff '{hid}' in your inbox (bimai inbox lists them). Only the receiving position "
                      "closes a handoff.")


def _position_list(root: Path) -> str:
    who = people(root)
    out = []
    for pid, p in positions(root).items():
        holders = ", ".join(who.get(h, {}).get("name", h) for h in p.get("held_by") or []) or "unstaffed"
        out.append(f"{pid} ({holders})")
    return "; ".join(out) or "none"


# ------------------------------------------------------------------ decisions

def decide(root: Path, seat: str, title: str, decision: str, source: str = "", supersedes: str | None = None) -> Path:
    if not title.strip() or not decision.strip():
        raise CollabError("A decision needs a title and the decision itself")
    folder = root / ".bimai" / "decisions"
    if supersedes and not (folder / f"{supersedes}.md").is_file():
        known = ", ".join(d["id"] for d in decisions(root)[:10]) or "none yet"
        raise CollabError(f"No decision '{supersedes}' to supersede. Recent: {known}")
    now = _now()
    path = _unique(folder, f"{now:%Y-%m-%d}-{slug(title)[:50] or 'decision'}")
    meta = {"title": title.strip(), "date": now.date().isoformat(), "recorded": now.isoformat(), "by": seat,
            "status": "active", "source": source or None}
    if supersedes:
        meta["supersedes"] = supersedes
    write_record(path, meta, decision)
    return path


def decisions(root: Path) -> list[dict]:
    items = []
    for path in sorted((root / ".bimai" / "decisions").glob("*.md")):
        meta, body = read_record(path)
        items.append({"id": path.stem, "path": path.relative_to(root).as_posix(), "decision": body.strip(), **meta})
    superseded = {d.get("supersedes") for d in items if d.get("supersedes")}
    for d in items:
        if d["id"] in superseded or str(d.get("status", "")).lower() in ("reversed", "superseded"):
            d["status"] = "superseded"
    return sorted(items, key=lambda d: str(d.get("recorded") or d.get("date") or d["id"]), reverse=True)


# ------------------------------------------------------------------ the seat brief

def brief(root: Path, seat: str, *, advance: bool = True, now: dt.datetime | None = None,
          cat: Catalogue | None = None) -> str:
    """Who you work for and what's new since your last session, short enough to read at every session start."""
    cat = cat or load_catalogue()
    now = now or _now()
    state_path = root / ".bimai" / "state" / f"brief-{seat}.json"
    try:
        last = dt.datetime.fromisoformat(json.loads(state_path.read_text(encoding="utf-8"))["last"])
    except (OSError, ValueError, KeyError):
        last = None
    data = _load(root / ".bimai" / "seats" / seat / "seat.yaml")
    who = people(root)
    me = who.get(data.get("person"), {})
    preset = cat.presets.get(data.get("preset"))
    my_positions = list(data.get("positions") or [])
    lines = [f"## Your seat (bimai)",
             f"You work for **{me.get('name') or seat}** ({preset.label if preset else data.get('role', '')}), seat "
             f"`.bimai/seats/{seat}/`. Positions: {', '.join(my_positions) or 'none'}. "
             f"Goals: {', '.join(data.get('goals') or []) or 'none chosen'}."]
    team = [m.get("role") for m in data.get("team") or [] if isinstance(m, dict) and m.get("role") in cat.roles]
    members = [f"{cat.roles[r].label} (`{r}`): {cat.roles[r].handles}" for r in team if r != "coordinator"]
    if members:
        lines.append("Your team: " + "; ".join(members) + ". When you hand them work, name the position "
                     f"({my_positions[0] if my_positions else 'yours'}).")
    others = [f"{p.get('name')} ({', '.join(pid for pid, pos in positions(root).items() if p['id'] in (pos.get('held_by') or []))})"
              for p in who.values() if p.get("id") != data.get("person")]
    if others:
        lines.append("Others on this project: " + "; ".join(others) + ". Work in their area → `bimai handoff --to <position>`.")

    since = f" since your last session ({last:%Y-%m-%d %H:%M})" if last else ""
    new = []
    open_items = inbox(root, seat)
    if open_items:
        shown = [f"- Handoff to you ({i['position']}) from {_name(who, i.get('from'))}"
                 f"{' (' + i['from_position'] + ')' if i.get('from_position') else ''}: {i.get('title')} (`{i['id']}`)"
                 for i in open_items[:LIST_MAX]]
        more = len(open_items) - LIST_MAX
        new += shown + ([f"- … and {more} more: `bimai inbox`"] if more > 0 else [])
    recent = [d for d in decisions(root) if last is None or str(d.get("recorded") or "") > last.isoformat()]
    if last is None:
        recent = recent[:3]
    for d in recent[:LIST_MAX]:
        new.append(f"- Decision {d['id']}: {d.get('title')}: {d['decision'][:120]} (by {_name(who, d.get('by'))}"
                   f"{', superseded' if d['status'] == 'superseded' else ''})")
    if len(recent) > LIST_MAX:
        new.append(f"- … and {len(recent) - LIST_MAX} more decisions: `bimai decisions`")
    activity = _team_activity(root, seat, last)
    if activity:
        new.append("- Team log: " + activity + " (`bimai log --team`)")
    if new:
        lines.append(f"### Open and new{since}")
        lines += new
    else:
        lines.append(f"Nothing new{since}: no open handoffs or new decisions.")
    text = "\n".join(lines)
    if len(text) > BRIEF_CHARS:
        text = text[:BRIEF_CHARS].rsplit("\n", 1)[0] + "\n- … (cut to keep it short: `bimai inbox`, `bimai decisions`)"
    if advance:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({"last": now.isoformat()}), encoding="utf-8")
    return text


def _name(who: dict, seat: str | None) -> str:
    return who.get(seat, {}).get("name") or seat or "?"


def _team_activity(root: Path, seat: str, last: dt.datetime | None) -> str:
    from bimai import sessionlog
    if not sessionlog.shared(root) or last is None:
        return ""
    counts = []
    for folder in sorted((root / ".bimai" / "log").glob("*/")):
        if folder.name == seat:
            continue
        n = 0
        for day in folder.glob("*.md"):
            try:
                if dt.date.fromisoformat(day.stem) >= last.date():
                    n += day.read_text(encoding="utf-8").count("\n## ")
            except ValueError:
                continue
        if n:
            counts.append(f"{n} entries by {folder.name}")
    return ", ".join(counts)
