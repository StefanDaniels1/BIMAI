# Tasks

## 1. Catalogue

- [ ] 1.1 Add `handles` and two `examples` to every role's frontmatter, including the Coordinator; load them in `Role`. Verify: catalogue test checks every role has `handles` and exactly two examples.

## 2. Shared generator

- [ ] 2.1 Create `cli/bimai/claude.py` with `SeatContext` and the generator for subagents (marker + memory section), the `CLAUDE.md` block (Coordinator charter, memory, routing table, rules) and `team.md`; switch `init` to it. Verify: all existing init tests still pass.
- [ ] 2.2 Routing table and rules, deterministic per team. Verify: tests for the three-member table and for the Scribe rule appearing only with a Scribe.
- [ ] 2.3 History files per position and role, created only when missing, from a date-free template; memory section in subagents and the block. Verify: tests for creation on init, an existing history kept unchanged, and the subagent naming its history and rules.

## 3. bimai team

- [ ] 3.1 Load a `SeatContext` from disk: seat selection (`--seat`, exit 2 with a seat list when ambiguous, exit 2 without workspace), Coordinator first, "Added by hand" default, stop with exit 1 when `seat.yaml` is invalid. Verify: tests for two seats, missing Coordinator, missing `why`, invalid seat.
- [ ] 3.2 File plan with ownership: update marked subagents, conflict on unmarked, delete marked subagents of removed members, keep histories, `--dry-run`. Verify: tests for member added by hand, member removed, user's own agent file, dry run writes nothing.
- [ ] 3.3 Fix the `team.md` footer to "Edit the `team` list in seat.yaml, then run `bimai team`." Verify: test on the generated text.

## 4. Validate

- [ ] 4.1 Report unknown roles, duplicate roles and more than 5 members in a seat's `team`. Verify: tests for `clash-wizard`, a duplicate, and 6 members; the example project stays valid.

## 5. Documentation

- [ ] 5.1 Add routing, history and `bimai team` to `docs/content/docs/guides/your-team.mdx` (marked available) and `bimai team` to the command reference. Verify: `python scripts/check_docs.py` passes and the site builds.
- [ ] 5.2 Try it by hand on `test_BIMAI`-style output: init, add a Planning Analyst, remove the Mentor, run `bimai team`; check the files. Verify: workspace valid, files as specified.
- [ ] 5.3 Final check: `python -m pytest -q`, `openspec validate --all --strict` and `python scripts/check_docs.py` all pass.
