---
name: meeting-intake
description: Turn a meeting transcript (Teams/Zoom .vtt, .srt, .docx or .txt) into minutes, decisions, tasks for the right people and handoffs to positions. Use when someone uploads or attaches a transcript of a coordination or design meeting, or asks to process meeting notes.
---

# Meeting intake

You turn a transcript into minutes and routed items. The workflow `meeting-intake` runs the
steps; the scripts parse, match names and route. **Your job is reading and classifying, never
deciding where things go and never guessing.**

## Your two steps

### 1. Extract (per chunk, haiku)

Read one chunk of speaker turns. Output candidate items as JSON following
`schemas/items.schema.json`. For every item:

- `type`: `summary`, `decision`, `action`, `risk`, `issue`, `agreement_change`,
  `open_question`, `availability` or `private`
- `text`: short and concrete, in the project language
- `evidence`: the turn's `start` time and the **exact quote** it came from
- `confidence`: how sure you are this item is real and correctly typed (0–1)

Rules:
- An **action** needs a verb and something to deliver. "We should look at it sometime" is an
  `open_question`, not an action.
- Put the owner **as said** in `owner` ("Jan", "the structural modellers", "the contractor")
  with `owner_kind`: `person`, `role`, `external` or `none`. For roles, add `role`
  (e.g. `bim-modeller`) and `scope` (e.g. `{discipline: structure}`) when stated. Do **not**
  resolve names to people; the script does that.
- `due`: an ISO date only if a date was said; `next_session`, `end_of_week` or `none` when
  those were said; otherwise leave it out. Never invent a date.
- A **decision** gets `status: decided` only if the transcript shows agreement ("agreed",
  "we go with", no objection after a proposal). Otherwise `status: proposed` or `unclear`.
- `level`: `project` for decisions, risks, rule changes and work for roles; `personal` for
  actions for one named person and availability; `unclear` when you can't tell.
- **Availability** ("I'm away next week") is `availability`. Health, family and other private
  remarks are `private` with the text "Personal remark" and nothing else. Never repeat them.

### 2. Consolidate (sonnet)

Merge the chunk outputs into one list:
- Remove duplicates from chunk overlap and repeated statements; keep the clearest quote.
- If a later statement changes an earlier one ("actually, let's make it Friday"), keep the final
  version and quote both.
- Check `decisions/` and `agreements.yaml`: if a decision conflicts with an earlier decision or
  the BEP, add `contradicts: [<decision id or agreements path>]`.
- Give items stable ids `i-01`, `i-02`, … in transcript order.
- Write 3–7 `summary` items that capture the meeting for someone who wasn't there.

## After routing

`route_items.py` returns either `ready` or questions for the **uploader**. Present the questions
in one message, numbered, each with its quote and timestamp and lettered options, exactly as
returned. Don't answer them yourself and don't apply anything while questions are open. Pass
the uploader's answers back as `answers.json` and route again.

When `ready`, the workflow applies the plan: minutes from `templates/minutes.md`, decisions,
tasks via `bimai tasks assign`, handoffs, change requests and cover suggestions. Finish with one
line per destination, e.g. "5 tasks for 3 people, 2 decisions, 1 handoff to modeller-structure,
1 question parked."
