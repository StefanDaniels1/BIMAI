# Proposal

## Why

Testing `bimai init` showed three gaps. The Coordinator picks team members only from one-line
descriptions, so routing is vague. Agents forget everything between sessions, although
ARCHITECTURE.md §4 plans a history per position. And the team can't be changed after init: `team.md`
says "edit seat.yaml", but nothing picks that up. Squad (which inspired bimai) solves the first two
with a routing table and per-agent history; this change brings both in, in bimai's shape.

## What Changes

- **Routing table:** each catalogue role declares what work it handles, with examples. The
  `CLAUDE.md` block gets a generated routing table (work → member → examples) and fixed routing rules
  ("quick facts: answer directly", "exactly one accountable member per task", …). Same team, same table.
- **History per position** (§4, §8.7): `.bimai/positions/<position>/agents/<role>/history.md` for every
  member, created when missing and never overwritten or deleted. Every subagent file and the
  Coordinator block say which history to read first, and what may be written to it: confirmed,
  lasting learnings only (Squad's history-hygiene rules).
- **`bimai team`:** after you edit the `team` list in `seat.yaml`, regenerates the subagents, the
  `CLAUDE.md` block, `team.md` and missing history files. Files bimai generated carry a marker, so
  bimai updates its own files and never touches yours. Subagents of removed members are removed only
  if bimai generated them; their history stays.
- `bimai validate` reports unknown roles and teams over 5 members in `seat.yaml`.
- `bimai init` uses the same generator, so both commands always write the same thing.
- Docs: routing, history and `bimai team` on the "Your team" guide and in the command reference.

## Non-goals

- Enforcing that agents read or write history (a hook; belongs to the hooks change).
- `bimai nap` (compaction) and promoting learnings to shared rules.
- Project routing across repositories (desk, `bimai open`); needs `bimai new`/`join` first.
- Re-proposing a team from changed goals or tools; you edit the `team` list directly.
- Several seats per project (`bimai team` asks which seat when there is more than one).

## Capabilities

### New Capabilities
- `team-configuration`: generated routing, per-position history, `bimai team`, and the seat team checks in `bimai validate`.

### Modified Capabilities
<!-- none: builds on add-cli-validate and add-cli-init, which must be archived first -->

## Impact

- Depends on `add-cli-validate` and `add-cli-init`.
- Code: `cli/bimai/team.py`, `init.py` (generator moves to a shared module), `cli.py`, `validate.py`, role catalogue frontmatter.
- Docs: `docs/content/docs/guides/your-team.mdx`, `reference/commands.mdx`.
