# Proposal

## Why

Three personas on one project (for example a BIM coordinator, a constructeur and a BIM modeller) can't work
together today: a second person can't join (`bimai init` refuses an existing project), and when a second seat
regenerates its team, it deletes the first seat's team members from the shared `.claude/agents/` and rewrites
the shared `CLAUDE.md` to "You work for <the other person>". There are also no handoffs, no decision records
and no catch-up. People shouldn't run commands for any of this: they say it, and Claude does it with bimai's
deterministic commands. The website needs a matching prompt to join a project.

## What Changes

- **Seats are safe in a shared project.** `.claude/agents/` holds the combined team of all seats (a member is
  removed only when no seat uses it); the shared `CLAUDE.md` block becomes the same for everyone (Coordinator,
  routing of the whole team, connections, collaboration rules). Everything about *you* comes from a **seat
  brief** printed by your personal session-start hook (`bimai brief`): who you work for, your positions and
  goals, your team, and what's new since your last session: decisions, handoffs to your positions, teammates'
  activity.
- **Joining is guided.** `bimai join --interview` gives Claude the questions (as for onboarding: options with
  explanations, recommended first, "Other"); `bimai join --person … --role … --yes` adds the person, a seat and a
  position (new, or shared with an existing holder), checked by `bimai validate`. `bimai init` in an existing
  project says to join instead, and the start prompt handles both: one prompt for starting and joining.
- **Handoffs.** `bimai handoff --to <position> --title … [--evidence …]` puts one file in that position's inbox;
  `bimai inbox` lists your open ones; `bimai handoff done <id>` closes one. The routing tells the Coordinator:
  work in another position's area becomes a handoff, never your own fix.
- **Decisions as records.** `bimai decide --title … --decision … [--source …] [--supersedes <id>]` writes one file
  per decision (date-based ids, so two people never collide; never edited afterwards). `bimai decisions` lists
  them. A superseded decision counts as reversed for the nap.
- **The team's log.** `bimai log --team` reads every seat's log that the project shares (`log.share`).
- **Website.** A "Join a project" page with a copy prompt in the same style as the start prompt; "Working
  together" describes what you can say and what bimai does.

## Non-goals

- Sharing through git without git commands (`bimai save` / `bimai sync`): the next change. Until then the files
  are laid out so two people normally never edit the same file.
- Cover and transfer of positions (later).

## Capabilities

### New Capabilities
- `collaboration`: seat brief, join, handoffs, decisions, team log.

## Impact

- `claude.py` (shared block, union of agents, brief hook), new `collab.py` (brief, join, handoffs, decisions),
  `cli.py`, `init.py` (existing project → join), `interview.py` (join interview), `nap.py` (supersedes), roles
  (Coordinator, Scribe: use `bimai decide`/`bimai handoff`), `docs/lib/prompts.ts` (join prompt), docs pages.
