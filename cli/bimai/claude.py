"""Generate a seat's Claude Code configuration: subagents, the CLAUDE.md block, team.md and histories.

Used by both `bimai init` (from the interview) and `bimai team` (from the files on disk), so both
always write the same thing. Pure: returns a plan, never writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from bimai.files import BLOCK_END, BLOCK_START, GENERATED, FileWrite, plan_create_only, plan_write, with_block
from bimai.team import Catalogue, Member, load_catalogue

COORDINATOR = "coordinator"


@dataclass
class SeatContext:
    project_name: str
    language: str
    person_name: str
    seat: str                   # seat folder name
    title: str                  # e.g. "BIM coordinator"
    positions: list[str]
    goals: list[str]
    team: list[Member]


def history_path(position: str, role: str) -> str:
    return f".bimai/positions/{position}/agents/{role}/history.md"


def history_template(ctx: SeatContext, position: str, role: str, cat: Catalogue) -> str:
    return (
        f"# {cat.roles[role].label} · {position}\n\n"
        f"What the {cat.roles[role].label} learned in the `{position}` position on {ctx.project_name}.\n"
        "Kept per position, so it stays with the job when people change.\n\n"
        "## Learnings\n\n"
        "<!-- One line per confirmed, lasting learning: - YYYY-MM-DD: <learning> (source: <where>) -->\n"
    )


def memory_section(ctx: SeatContext, role: str) -> str:
    files = "\n".join(f"- `{history_path(p, role)}`" for p in ctx.positions) or "- (this seat holds no position yet)"
    which = " of the position the work belongs to" if len(ctx.positions) > 1 else ""
    return (
        "## Your memory\n\n"
        f"Read your history before you start:\n\n{files}\n\n"
        f"When you learn something lasting about this project, add it to the history{which}:\n\n"
        "- Only confirmed outcomes: conventions, preferences, where things are, what worked. "
        "Not requests, intermediate steps or guesses.\n"
        "- One line per learning: `- YYYY-MM-DD: <learning> (source: <file, meeting or message>)`.\n"
        "- Never write personal remarks (health, family, reasons for absence) or secrets.\n"
        "- If a line turns out wrong or a decision is reversed, correct that line instead of adding "
        "a contradicting one.\n"
        "- Decisions belong in `.bimai/decisions/` (one file per decision), not in history.\n"
    )


def subagent(ctx: SeatContext, role: str, cat: Catalogue) -> str:
    r = cat.roles[role]
    meta = yaml.safe_dump({"name": r.id, "description": r.description, "model": r.model},
                          sort_keys=False, allow_unicode=True, width=10_000)
    return f"---\n{meta}---\n{GENERATED}\n{r.charter}\n{memory_section(ctx, role)}"


def routing_section(ctx: SeatContext, cat: Catalogue) -> str:
    rows = []
    for m in ctx.team:
        r = cat.roles[m.role]
        who = f"{r.label} (you)" if m.role == COORDINATOR else f"{r.label} (`{m.role}`)"
        examples = ", ".join(f'"{e}"' for e in r.examples)
        rows.append(f"| {r.handles} | {who} | {examples} |")
    rules = [
        "Quick facts from the project files: answer them yourself; don't hand them to a team member.",
        "Every task has exactly one accountable team member. Tell the person who is handling it.",
        "Work no team member covers: do it yourself, and say that no team member covers it.",
    ]
    if any(m.role == "scribe" for m in ctx.team):
        rules.append("Decisions and actions from meetings are recorded by the Scribe.")
    numbered = "\n".join(f"{i}. {rule}" for i, rule in enumerate(rules, 1))
    return (
        "## Routing\n\n| Work | Who | For example |\n|---|---|---|\n" + "\n".join(rows)
        + f"\n\n{numbered}\n"
    )


def claude_block(ctx: SeatContext, cat: Catalogue) -> str:
    return (
        f"{BLOCK_START}\n"
        "<!-- Written by bimai. Edit outside this block; `bimai team` regenerates it. -->\n"
        f"# bimai: {ctx.project_name}\n\n"
        f"{cat.roles[COORDINATOR].charter}\n"
        f"{routing_section(ctx, cat)}\n"
        f"{memory_section(ctx, COORDINATOR)}\n"
        "## This seat\n\n"
        f"You work for **{ctx.person_name}** ({ctx.title}), seat `.bimai/seats/{ctx.seat}/`. "
        f"Goals: {', '.join(ctx.goals) or 'none chosen'}. Write documents in "
        f"{'Dutch' if ctx.language == 'nl' else 'English'}.\n"
        f"{BLOCK_END}\n"
    )


def team_md(ctx: SeatContext, cat: Catalogue) -> str:
    rows = "\n".join(f"| {cat.roles[m.role].label} | {m.why} |" for m in ctx.team)
    return (
        f"{GENERATED}\n# {ctx.person_name}'s team\n\n| Member | Why |\n|---|---|\n{rows}\n\n"
        "Edit the `team` list in seat.yaml, then run `bimai team`.\n"
    )


def plan_claude_files(root: str | Path, ctx: SeatContext, cat: Catalogue | None = None) -> list[FileWrite]:
    root = Path(root).resolve()
    cat = cat or load_catalogue()
    members = {m.role for m in ctx.team}
    plan = [plan_write(root, f".bimai/seats/{ctx.seat}/team.md", team_md(ctx, cat), owned=True)]

    for m in ctx.team:
        if m.role != COORDINATOR:
            plan.append(plan_write(root, f".claude/agents/{m.role}.md", subagent(ctx, m.role, cat), owned=True))
    agents = root / ".claude" / "agents"
    for f in sorted(agents.glob("*.md")) if agents.is_dir() else []:
        if f.stem not in members and GENERATED in f.read_text(encoding="utf-8"):
            plan.append(FileWrite(f".claude/agents/{f.name}", "", "delete", "no longer on the team; history kept"))

    claude_md = root / "CLAUDE.md"
    current = claude_md.read_text(encoding="utf-8") if claude_md.exists() else None
    plan.append(plan_write(root, "CLAUDE.md", with_block(current, claude_block(ctx, cat)),
                           merge_note="bimai block added or refreshed; your content is kept"))

    for position in ctx.positions:
        for m in ctx.team:
            rel = history_path(position, m.role)
            plan.append(plan_create_only(root, rel, history_template(ctx, position, m.role, cat)))
    return plan


class SeatError(Exception):
    """No seat, an unknown seat, or several seats and none chosen (exit 2)."""


def find_seat(root: Path, seat: str | None) -> str:
    seats = sorted(d.name for d in (root / ".bimai" / "seats").glob("*/") if (d / "seat.yaml").is_file())
    if seat:
        if seat not in seats:
            raise SeatError(f"no seat '{seat}'. Seats: {', '.join(seats) or 'none'}")
        return seat
    if not seats:
        raise SeatError("this project has no seats yet; run `bimai init` first")
    if len(seats) > 1:
        raise SeatError(f"this project has several seats; choose one with --seat: {', '.join(seats)}")
    return seats[0]


def load_seat_context(root: str | Path, seat: str, cat: Catalogue | None = None) -> SeatContext:
    """Build the context from the files on disk. Call validate() first: this assumes valid files."""
    root = Path(root).resolve()
    cat = cat or load_catalogue()
    b = root / ".bimai"

    def load(path: Path) -> dict:
        return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.is_file() else {}

    project = load(b / "project.yaml")
    data = load(b / "seats" / seat / "seat.yaml")
    people = {p.get("id"): p for p in load(b / "people.yaml").get("people") or [] if isinstance(p, dict)}
    person = people.get(data.get("person"), {})
    preset = cat.presets.get(data.get("preset"))
    team = [Member(m["role"], m.get("why") or "Added by hand") for m in data.get("team") or []]
    if not any(m.role == COORDINATOR for m in team):
        team.insert(0, Member(COORDINATOR, "Always"))
    return SeatContext(
        project_name=project.get("name") or project.get("id", root.name),
        language=project.get("language", "en"),
        person_name=person.get("name") or data.get("person", seat),
        seat=seat,
        title=preset.label if preset else (data.get("role") or person.get("title") or "team member"),
        positions=list(data.get("positions") or []),
        goals=list(data.get("goals") or []),
        team=team,
    )
