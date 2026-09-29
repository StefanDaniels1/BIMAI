"""Tests for the meeting-intake pack scripts. Run: python -m pytest packs/meeting-intake/tests"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
FIX = HERE / "fixtures"
sys.path.insert(0, str(HERE.parent / "scripts"))

from chunk import chunk_turns  # noqa: E402
from parse_transcript import TranscriptError, parse_file  # noqa: E402
from resolve_speakers import load_people, resolve, resolve_name  # noqa: E402
from route_items import Context, route  # noqa: E402


@pytest.fixture
def people():
    return load_people(FIX / "people.yaml")


@pytest.fixture
def ctx(people):
    ownership = yaml.safe_load((FIX / "ownership.yaml").read_text(encoding="utf-8"))
    meeting = yaml.safe_load((FIX / "meeting.yaml").read_text(encoding="utf-8"))
    return Context(people, ownership, meeting)


@pytest.fixture
def items():
    return json.loads((FIX / "items.json").read_text(encoding="utf-8"))["items"]


def by_item(result, item_id):
    return [a for a in result["actions"] if a["item"] == item_id]


def questions_for(result, item_id):
    return [q for q in result["questions"] if q["item"] == item_id]


# ---------------------------------------------------------------- parsing
def test_teams_vtt_merges_consecutive_turns_and_normalizes_time():
    parsed = parse_file(FIX / "coordination-teams.vtt")
    assert parsed["source_format"] == "vtt"
    first = parsed["turns"][0]
    assert first["speaker"] == "Steve Daniëls"
    assert first["start"] == "00:00:03"
    assert "twelve new ones" in first["text"]  # two cues merged into one turn
    assert [t["speaker"] for t in parsed["turns"]] == [
        "Steve Daniëls", "Jan Bakker (Installatiebedrijf)", "Anna de Wit", "Steve Daniëls"]


def test_meeting_id_is_stable_for_the_same_content():
    assert parse_file(FIX / "coordination-teams.vtt")["meeting_id"] == parse_file(FIX / "coordination-teams.vtt")["meeting_id"]


def test_zoom_vtt_and_srt_use_name_prefix():
    zoom = parse_file(FIX / "coordination-zoom.vtt")
    assert [t["speaker"] for t in zoom["turns"]] == ["Steve Daniëls", "Anna de Wit"]
    srt = parse_file(FIX / "coordination.srt")
    assert srt["source_format"] == "srt"
    assert srt["turn_count"] == 1 and srt["turns"][0]["speaker"] == "Sam Jansen"


def test_plain_text_formats(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text(
        "[00:01:05] Steve: Let's begin.\n"
        "Anna de Wit   0:02:10\n"
        "The model is uploaded.\n"
        "It has the new zones.\n"
        "Sam: Requirements next.\n",
        encoding="utf-8",
    )
    turns = parse_file(f)["turns"]
    assert [(t["speaker"], t["start"]) for t in turns] == [
        ("Steve", "00:01:05"), ("Anna de Wit", "00:02:10"), ("Sam", None)]
    assert turns[1]["text"] == "The model is uploaded. It has the new zones."


def test_docx_teams_download(tmp_path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    for line in ["Steve Daniëls   0:00:03", "Good morning.", "Anna de Wit   0:00:09", "Model is uploaded."]:
        doc.add_paragraph(line)
    path = tmp_path / "meeting.docx"
    doc.save(path)
    parsed = parse_file(path)
    assert parsed["source_format"] == "docx"
    assert [t["speaker"] for t in parsed["turns"]] == ["Steve Daniëls", "Anna de Wit"]


def test_empty_transcript_is_an_error(tmp_path):
    f = tmp_path / "empty.vtt"
    f.write_text("WEBVTT\n\n", encoding="utf-8")
    with pytest.raises(TranscriptError):
        parse_file(f)


# ---------------------------------------------------------------- speakers
@pytest.mark.parametrize("raw, expected", [
    ("Steve Daniëls", "steve"),
    ("steve daniels", "steve"),                    # accents and case ignored
    ("Daniëls, Steve", "steve"),                   # surname-first display name
    ("Jan Bakker (Installatiebedrijf)", "jan-bakker"),  # company suffix dropped
    ("Anna", "anna"),                              # alias
    ("Fatima", "fatima"),                          # unique first name
    ("Anna de With", "anna"),                      # close spelling
])
def test_resolve_name_matches(people, raw, expected):
    result = resolve_name(raw, people)
    assert result["status"] == "matched" and result["person"] == expected


def test_resolve_name_never_guesses_between_two_jans(people):
    result = resolve_name("Jan", people)
    assert result["status"] == "ambiguous"
    assert set(result["candidates"]) == {"jan-devries", "jan-bakker"}


def test_resolve_name_unknown(people):
    assert resolve_name("Piet Pieters", people)["status"] == "unknown"


def test_resolve_marks_turns_and_lists_unresolved(people):
    resolved = resolve(parse_file(FIX / "coordination-teams.vtt"), people)
    assert resolved["turns"][0]["person"] == "steve"
    assert resolved["unresolved"] == []


# ---------------------------------------------------------------- chunking
def test_chunks_cover_all_turns_with_overlap():
    turns = [{"i": n, "speaker": "S", "text": "x" * 100} for n in range(50)]
    chunks = chunk_turns(turns, max_chars=1000, overlap=2)
    assert chunks[0]["first_turn"] == 0 and chunks[-1]["last_turn"] == 49
    for prev, nxt in zip(chunks, chunks[1:]):
        assert nxt["first_turn"] == prev["last_turn"] - 1  # two turns of overlap
    assert all(sum(len(t["text"]) + 17 for t in c["turns"]) <= 1000 for c in chunks)


def test_chunking_always_progresses_on_huge_turns():
    turns = [{"i": n, "speaker": "S", "text": "x" * 5000} for n in range(3)]
    chunks = chunk_turns(turns, max_chars=1000, overlap=2)
    assert [c["first_turn"] for c in chunks] == [0, 1, 2]


# ---------------------------------------------------------------- routing
def test_first_pass_asks_instead_of_guessing(ctx, items):
    result = route(items, ctx)
    assert result["status"] == "needs_answers"
    reasons = {(q["item"], q["reason"]) for q in result["questions"]}
    assert ("i-02", "owner") in reasons       # two people called Jan
    assert ("i-03", "decided") in reasons     # decided or only discussed?
    assert ("i-04", "level") in reasons       # project rule or personal action?
    assert ("i-09", "confirm") in reasons     # low confidence
    assert ("i-11", "due") in reasons         # no deadline given
    assert set(result["pending_items"]) == {"i-02", "i-03", "i-04", "i-09", "i-11"}


def test_clear_items_are_routed_on_the_first_pass(ctx, items):
    result = route(items, ctx)
    assert by_item(result, "i-01")[0]["kind"] == "minutes"
    handoff = by_item(result, "i-05")[0]
    assert handoff["kind"] == "handoff" and handoff["position"] == "modeller-structure"
    assert by_item(result, "i-06")[0]["kind"] == "risk_review"
    assert by_item(result, "i-08")[0]["kind"] == "dropped"
    assert "Personal remark" not in json.dumps(result)


def test_external_owner_becomes_external_action_plus_follow_up(ctx, items):
    result = route(items, ctx)
    kinds = {a["kind"]: a for a in by_item(result, "i-10")}
    assert kinds["external_action"]["party"] == "Jan Bakker"
    assert kinds["task"]["person"] == "steve"  # the uploader follows up
    assert kinds["task"]["text"].startswith("Follow up with Jan Bakker")


def test_availability_suggests_cover_to_the_lead_and_stores_nothing_about_the_person(ctx, items):
    suggestion = by_item(route(items, ctx), "i-07")[0]
    assert suggestion["kind"] == "cover_suggestion"
    assert suggestion["positions"] == ["modeller-structure"]
    assert "anna" not in suggestion["notify"]  # the person herself is lead, so the uploader is told
    assert suggestion["notify"] == ["steve"]


def test_questions_include_the_transcript_quote(ctx, items):
    q = questions_for(route(items, ctx), "i-02")[0]
    assert q["at"] == "00:14:32" and "abutment" in q["quote"]
    labels = [o["label"] for o in q["options"]]
    assert any("Jan de Vries" in label for label in labels)
    assert labels[-1] == "Skip this item"


def test_answers_make_everything_ready(ctx, items):
    first = route(items, ctx)
    answers = {
        "i-02:owner": next(o["key"] for o in questions_for(first, "i-02")[0]["options"] if "Jan de Vries" in o["label"]),
        "i-03:decided": "decided",
        "i-04:level": "project",
        "i-09:confirm": "yes",
        "i-11:due": "week",
    }
    result = route(items, ctx, answers)
    assert result["status"] == "ready", result["questions"]

    task = by_item(result, "i-02")[0]
    assert (task["kind"], task["person"], task["position"]) == ("task", "jan-devries", "modeller-structure")
    assert task["due"] == "2026-10-08"            # next session = meeting date + 14 days
    assert task["source"] == "meeting:3f9a1c2b7d10" and task["assigned_by"] == "steve"

    assert by_item(result, "i-03")[0]["kind"] == "decision"
    assert by_item(result, "i-04")[0]["kind"] == "change_request"
    sam = by_item(result, "i-09")[0]
    assert (sam["person"], sam["due"]) == ("sam", "2026-09-25")  # end of the meeting's week (Friday)
    assert by_item(result, "i-11")[0]["due"] == "2026-09-25"


def test_personal_answer_turns_item_into_a_task_for_the_named_person(ctx, items):
    result = route(items, ctx, {"i-04:level": "personal"})
    task = by_item(result, "i-04")[0]
    assert (task["kind"], task["person"]) == ("task", "steve")


def test_skip_and_park(ctx, items):
    result = route(items, ctx, {"i-02:owner": "skip", "i-03:decided": "later"})
    assert by_item(result, "i-02")[0]["kind"] == "skipped"
    assert by_item(result, "i-03")[0]["kind"] == "parking_lot"


def test_contradiction_with_an_earlier_decision_is_asked(ctx):
    item = {"id": "c-1", "type": "decision", "status": "decided", "confidence": 0.95,
            "text": "Deck slab 400 mm", "contradicts": ["decision:2026-09-10-deck-slab"]}
    first = route([item], ctx)
    assert questions_for(first, "c-1")[0]["reason"] == "contradicts"
    result = route([item], ctx, {"c-1:contradicts": "replace"})
    decision = by_item(result, "c-1")[0]
    assert decision["kind"] == "decision" and decision["supersedes"] == ["decision:2026-09-10-deck-slab"]


def test_unknown_owner_offers_me_external_or_skip(ctx):
    item = {"id": "u-1", "type": "action", "confidence": 0.9, "text": "Order samples",
            "owner": "Piet", "owner_kind": "person", "due": "2026-10-01"}
    q = questions_for(route([item], ctx), "u-1")[0]
    assert [o["key"] for o in q["options"]] == ["me", "external", "skip"]


def test_unknown_item_type_is_asked(ctx):
    item = {"id": "t-1", "type": "brainstorm", "confidence": 0.9, "text": "Ideas for the entrance"}
    assert questions_for(route([item], ctx), "t-1")[0]["reason"] == "type"


def test_next_session_without_a_rhythm_is_asked(people):
    ownership = yaml.safe_load((FIX / "ownership.yaml").read_text(encoding="utf-8"))
    meeting = {"id": "m", "date": "2026-09-24", "uploader": "steve", "settings": {}}
    ctx = Context(people, ownership, meeting)
    item = {"id": "n-1", "type": "action", "confidence": 0.9, "text": "Check levels",
            "owner": "Fatima", "owner_kind": "person", "due": "next_session"}
    q = questions_for(route([item], ctx), "n-1")[0]
    assert q["reason"] == "due" and "next" not in [o["key"] for o in q["options"]]
