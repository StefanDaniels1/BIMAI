#!/usr/bin/env python3
"""Route consolidated meeting items to where they belong, or ask the uploader.

Deterministic: the agent extracts and classifies items; this script decides
where each one goes and turns every uncertainty into a question for the
uploader. Nothing is guessed.

Usage:
  route_items.py <items.json> <people.yaml> <ownership.yaml> <meeting.yaml> [answers.json]

meeting.yaml (assembled by the bimai CLI from the meeting and project settings):
  id, date (YYYY-MM-DD), type, uploader (person id),
  settings: {ask_below: 0.8, rhythm_days: 14}   # rhythm from the BEP agreements, optional

answers.json: {"<question id>": "<option key>" | "skip" | {field: value, ...}}

Output: {"status": "needs_answers" | "ready", "actions": [...], "questions": [...],
         "pending_items": [...], "counts": {...}}
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
from resolve_speakers import resolve_name  # noqa: E402

ITEM_TYPES = {"summary", "decision", "action", "risk", "issue", "agreement_change",
              "open_question", "availability", "private"}
DEFAULT_ASK_BELOW = 0.8
MAX_ROUNDS = 10


# ---------------------------------------------------------------- context
class Context:
    def __init__(self, people: list[dict], ownership: dict, meeting: dict):
        self.people = people
        self.by_id = {p["id"]: p for p in people}
        self.positions: dict = (ownership or {}).get("positions", {}) or {}
        self.meeting = meeting
        self.date = dt.date.fromisoformat(str(meeting["date"]))
        settings = meeting.get("settings", {}) or {}
        self.ask_below = float(settings.get("ask_below", DEFAULT_ASK_BELOW))
        self.rhythm_days = settings.get("rhythm_days")
        self.uploader = meeting["uploader"]

    def label(self, person_id: str) -> str:
        p = self.by_id.get(person_id, {"name": person_id})
        extra = ", ".join(self.positions_of(person_id)) or p.get("organization") or ""
        return f"{p['name']}, {extra}" if extra else p["name"]

    def positions_of(self, person_id: str) -> list[str]:
        seat = self.by_id.get(person_id, {}).get("seat")
        return [pid for pid, pos in self.positions.items() if seat and seat in pos.get("held_by", [])]

    def leads_of(self, position_id: str) -> list[str]:
        pos = self.positions.get(position_id, {})
        lead = pos.get("lead") or (pos.get("held_by") or [None])[0]
        return [p["id"] for p in self.people if lead and p.get("seat") == lead]


def scope_matches(position_scope: dict | None, item_scope: dict | None) -> bool:
    if not item_scope:
        return True
    position_scope = position_scope or {}
    return all(str(position_scope.get(k, "")).casefold() == str(v).casefold() for k, v in item_scope.items())


# ---------------------------------------------------------------- questions
def question(item: dict, reason: str, text: str, options: list[dict]) -> dict:
    options = options + [{"key": "skip", "label": "Skip this item", "set": {"_skip": True}}]
    return {
        "id": f"{item['id']}:{reason}",
        "item": item["id"],
        "reason": reason,
        "text": text,
        "quote": (item.get("evidence") or {}).get("quote"),
        "at": (item.get("evidence") or {}).get("start"),
        "options": options,
    }


def owner_questions(item: dict, ctx: Context) -> tuple[dict | None, list[dict]]:
    """Resolve the owner of an action/availability item. Returns (resolution, questions)."""
    if item.get("owner_id"):
        return {"person": item["owner_id"]}, []
    if item.get("position"):
        return {"position": item["position"]}, []

    kind = item.get("owner_kind") or ("person" if item.get("owner") else "none")
    raw = item.get("owner") or ""
    me = {"key": "me", "label": f"Me ({ctx.label(ctx.uploader)})",
          "set": {"owner_id": ctx.uploader, "owner_kind": "person"}}
    external = {"key": "external", "label": "An external party (not on bimai)",
                "set": {"owner_kind": "external"}}

    if kind == "external":
        return {"external": raw or "external party"}, []

    if kind == "role":
        candidates = [pid for pid, pos in ctx.positions.items()
                      if (not item.get("role") or pos.get("role") == item["role"])
                      and scope_matches(pos.get("scope"), item.get("scope"))]
        if len(candidates) == 1:
            return {"position": candidates[0]}, []
        options = [{"key": chr(97 + n), "label": pid, "set": {"position": pid}} for n, pid in enumerate(candidates)]
        text = (f'Which position should "{item["text"]}" go to?' if candidates
                else f'No position matches "{raw or item.get("role")}". Who should do "{item["text"]}"?')
        return None, [question(item, "owner", text, options + [me])]

    if kind == "person" and raw:
        match = resolve_name(raw, ctx.people)
        if match["status"] == "matched":
            return {"person": match["person"]}, []
        options = [{"key": chr(97 + n), "label": ctx.label(pid), "set": {"owner_id": pid, "owner_kind": "person"}}
                   for n, pid in enumerate(match["candidates"])]
        text = (f'Who is "{raw}"?' if match["status"] == "ambiguous"
                else f'"{raw}" isn\'t a known project member. Who should do "{item["text"]}"?')
        return None, [question(item, "owner", text, options + [me, external])]

    return None, [question(item, "owner", f'Nobody was named for "{item["text"]}". Who should do it?', [me, external])]


def due_date(item: dict, ctx: Context) -> tuple[str | None, list[dict]]:
    due = item.get("due")
    if due in ("none", "no_deadline"):
        return None, []
    if due == "next_session" and ctx.rhythm_days:
        return (ctx.date + dt.timedelta(days=int(ctx.rhythm_days))).isoformat(), []
    if due == "end_of_week":
        return (ctx.date + dt.timedelta(days=(4 - ctx.date.weekday()) % 7)).isoformat(), []
    if isinstance(due, str):
        try:
            return dt.date.fromisoformat(due).isoformat(), []
        except ValueError:
            pass
    options = []
    if ctx.rhythm_days:
        options.append({"key": "next", "label": "Before the next session", "set": {"due": "next_session"}})
    options += [
        {"key": "week", "label": "End of this week", "set": {"due": "end_of_week"}},
        {"key": "none", "label": "No deadline", "set": {"due": "none"}},
    ]
    return None, [question(item, "due", f'When is "{item["text"]}" due?', options)]


# ---------------------------------------------------------------- routing
def route_item(item: dict, ctx: Context) -> tuple[list[dict], list[dict]]:
    """Return (actions, questions) for one item. Questions block the item's actions."""
    base = {
        "item": item["id"],
        "text": item["text"],
        "source": f"meeting:{ctx.meeting['id']}",
        "evidence": item.get("evidence"),
    }
    kind = item.get("type")
    if item.get("_skip"):
        return [dict(base, kind="skipped")], []
    if kind not in ITEM_TYPES:
        return [], [question(item, "type", f'What is "{item["text"]}"?', [
            {"key": "a", "label": "An action", "set": {"type": "action"}},
            {"key": "b", "label": "A decision", "set": {"type": "decision"}},
            {"key": "c", "label": "Just a summary point", "set": {"type": "summary"}},
        ])]
    if kind == "private":
        return [dict(base, kind="dropped", text="(private remark left out)")], []

    # Level first: the answer changes where the item goes, so ask it on its own.
    if item.get("level") == "unclear":
        who = ctx.label(item["owner_id"]) if item.get("owner_id") else (item.get("owner") or "the person named")
        return [], [question(item, "level", f'Is "{item["text"]}" a project matter or a personal action?', [
            {"key": "project", "label": "Project: a rule or agreement change for everyone",
             "set": {"level": "project", "type": "agreement_change"}},
            {"key": "personal", "label": f"Personal: an action for {who}",
             "set": {"level": "personal", "type": "action"}},
        ])]

    questions: list[dict] = []
    if kind == "decision":
        if item.get("status") != "decided":
            questions.append(question(item, "decided", f'Was "{item["text"]}" decided, or only discussed?', [
                {"key": "decided", "label": "Decided", "set": {"status": "decided"}},
                {"key": "later", "label": "Only proposed: park it for a later decision",
                 "set": {"type": "open_question"}},
            ]))
        if item.get("contradicts") and not item.get("supersedes_confirmed"):
            earlier = ", ".join(item["contradicts"])
            questions.append(question(item, "contradicts", f'"{item["text"]}" conflicts with {earlier}. What applies?', [
                {"key": "replace", "label": "The new decision replaces the earlier one",
                 "set": {"supersedes_confirmed": True, "supersedes": item["contradicts"]}},
                {"key": "keep", "label": "Keep the earlier one; record this as discussed only",
                 "set": {"type": "summary"}},
            ]))
        if not questions:
            actions = [dict(base, kind="decision", level="project", supersedes=item.get("supersedes", []))]
            return actions, []

    elif kind in ("action", "availability"):
        owner, owner_q = owner_questions(item, ctx)
        questions += owner_q
        due, due_q = (None, []) if kind == "availability" else due_date(item, ctx)
        questions += due_q
        if not questions and owner:
            if kind == "availability":
                person = owner.get("person")
                positions = ctx.positions_of(person) if person else []
                notify = sorted({lead for pos in positions for lead in ctx.leads_of(pos)} - {person}) or [ctx.uploader]
                return [dict(base, kind="cover_suggestion", person=person, positions=positions, notify=notify,
                             note="Suggestion only; nothing is stored about the person")], []
            if "external" in owner:
                return [
                    dict(base, kind="external_action", party=owner["external"], due=due),
                    dict(base, kind="task", person=ctx.uploader, due=due, assigned_by=ctx.uploader,
                         text=f"Follow up with {owner['external']}: {item['text']}"),
                ], []
            if "position" in owner:
                return [dict(base, kind="handoff", position=owner["position"], due=due, level="project")], []
            person = owner["person"]
            if ctx.by_id.get(person, {}).get("external"):
                name = ctx.by_id[person]["name"]
                return [
                    dict(base, kind="external_action", party=name, due=due),
                    dict(base, kind="task", person=ctx.uploader, due=due, assigned_by=ctx.uploader,
                         text=f"Follow up with {name}: {item['text']}"),
                ], []
            held = ctx.positions_of(person)
            matching = [p for p in held if scope_matches(ctx.positions[p].get("scope"), item.get("scope"))]
            position = matching[0] if len(matching) == 1 else (held[0] if len(held) == 1 else None)
            return [dict(base, kind="task", person=person, position=position, due=due,
                         assigned_by=ctx.uploader, level="personal")], []

    elif kind in ("risk", "issue"):
        return [dict(base, kind="risk_review", level="project")], []
    elif kind == "agreement_change":
        return [dict(base, kind="change_request", level="project")], []
    elif kind == "open_question":
        return [dict(base, kind="parking_lot", level="project", proposed_owner=item.get("owner"))], []
    elif kind == "summary":
        return [dict(base, kind="minutes")], []

    return [], questions


def route(items: list[dict], ctx: Context, answers: dict | None = None) -> dict:
    items = [dict(i) for i in items]
    answers = answers or {}
    applied: set[str] = set()

    def pass_once():
        actions, questions = [], []
        for item in items:
            a, q = route_item(item, ctx)
            # A low-confidence item is never applied unconfirmed. Its other questions
            # are asked in the same batch, so the uploader answers everything at once.
            if (not item.get("_skip") and item.get("type") not in ("summary", "private")
                    and float(item.get("confidence", 1.0)) < ctx.ask_below):
                questions.append(question(item, "confirm", f'Is this right? "{item["text"]}"', [
                    {"key": "yes", "label": "Yes, keep it", "set": {"confidence": 1.0}},
                ]))
                questions += q
                continue
            actions += a
            questions += q
        return actions, questions

    for _ in range(MAX_ROUNDS):
        actions, questions = pass_once()
        progressed = False
        for q in questions:
            if q["id"] in applied or q["id"] not in answers:
                continue
            answer = answers[q["id"]]
            item = next(i for i in items if i["id"] == q["item"])
            if answer == "skip":
                item["_skip"] = True
            elif isinstance(answer, dict):
                item.update(answer)
            else:
                option = next((o for o in q["options"] if o["key"] == answer), None)
                if option is None:
                    continue
                item.update(option["set"])
            applied.add(q["id"])
            progressed = True
        if not progressed:
            break

    pending = sorted({q["item"] for q in questions})
    counts: dict[str, int] = {}
    for a in actions:
        counts[a["kind"]] = counts.get(a["kind"], 0) + 1
    return {
        "meeting_id": ctx.meeting["id"],
        "status": "needs_answers" if questions else "ready",
        "actions": actions,
        "questions": questions,
        "pending_items": pending,
        "counts": counts,
    }


def load_yaml(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def main(argv: list[str]) -> int:
    if len(argv) not in (5, 6):
        print(__doc__, file=sys.stderr)
        return 2
    items = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    items = items.get("items", items) if isinstance(items, dict) else items
    ctx = Context(load_yaml(argv[2]).get("people", []), load_yaml(argv[3]), load_yaml(argv[4]))
    answers = json.loads(Path(argv[5]).read_text(encoding="utf-8")) if len(argv) == 6 else {}
    print(json.dumps(route(items, ctx, answers), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
