# Design

## Decisions

- **Shared files are identical for every seat.** `bimai team` (any seat) writes the same `CLAUDE.md` block and the
  same `.claude/agents/` for everyone: the union of all seats' teams. Agents' memory section names no seat: the
  Coordinator passes the position when it delegates, and the agent reads that position's history.
- **Your seat comes from your own hook.** The personal `.claude/settings.local.json` gets a `SessionStart` hook
  (matchers startup, resume, clear and compact, so it survives compaction): `bimai brief --seat <you>`. Its
  output goes into Claude's context (Claude Code adds SessionStart output to the context). It is short and
  deterministic: seat, positions, goals, language, your team and routing, and since your last session (a
  timestamp in `.bimai/state/brief-<seat>.json`): new decisions, open handoffs to your positions, teammates'
  log entries if the log is shared. At most about 400 tokens; lists are cut with a count.
- **Join is the init interview for an existing project:** no project questions (name, language, BEP); a position
  question offers the existing positions of the chosen role (to share) and a new one (default
  `<preset>`; `<preset>-<person>` when that exists). Sharing a position with a holder sets a `lead` (the first
  holder) as ARCHITECTURE §8.7 requires.
- **Records are one file each, never edited by someone else.** Handoffs: `.bimai/positions/<to>/inbox/<id>.md`
  (`<id>` = `YYYYMMDD-HHMM-<slug>`), frontmatter `from`, `to`, `created`, `status` (open/done), `evidence`;
  only the receiving position closes it. Decisions: `.bimai/decisions/<YYYY-MM-DD>-<slug>.md`, frontmatter
  `title`, `date`, `by`, `status: active`, `source`, `supersedes`; superseding is recorded in the new file only.
- **Agents call commands, people talk.** The Coordinator's routing and the Scribe's charter say to use
  `bimai handoff`, `bimai decide` and `bimai inbox`; the seat brief reminds the Coordinator once per session.

## Risks / Trade-offs

- Without sync, people still share with git themselves → the join page says so, and the next change adds
  `bimai save`/`bimai sync`.
- The brief costs tokens every session → hard cap and counts instead of full lists.
