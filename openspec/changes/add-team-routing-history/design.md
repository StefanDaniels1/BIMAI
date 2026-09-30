# Design

## Context

`add-cli-init` generates the Claude Code files straight from the interview answers. `bimai team` must
produce the same files from what's on disk (`project.yaml`, `people.yaml`, `seat.yaml`). Squad's
routing (`routing.md` + rules) and history (`agents/<name>/history.md` + hygiene rules) are the
reference; ARCHITECTURE.md §4 places bimai's history under positions so it survives replacement.

## Decisions

- **One generator, two callers.** A new `cli/bimai/claude.py` builds the Claude Code files from a
  `SeatContext` (project name, language, person, preset label, positions, goals, team). `init` writes
  the `.bimai/` files, then calls it; `team` loads a `SeatContext` from disk and calls it. `init.py`
  keeps the file-plan and apply mechanics (`FileWrite`, `apply`), extended with a `delete` action.
- **Routing lives in the `CLAUDE.md` block, not a separate `routing.md`.** The block is loaded into
  every session, so the table is always in context; a separate file would need the Coordinator to
  remember to read it. It is generated, so it can't drift from the team.
- **Catalogue fields:** each role gets `handles` (one line) and `examples` (exactly two). Tested.
- **Ownership marker in the body** (`<!-- bimai:generated -->`, right after the frontmatter), not in
  the frontmatter, so Claude Code's frontmatter stays exactly `name`, `description`, `model`.
  Claude Code strips HTML comments from `CLAUDE.md`; in subagent bodies the comment is harmless.
- **Histories per (position, role)**, one per position the seat holds. The memory section lists all
  of them and says: write to the one for the position the work belongs to.
- **History template** has no date, so regenerating is deterministic; the agent dates its own lines.
- **`seat.yaml` is the source of truth after init.** Its `team` list is edited by hand. No re-proposal
  from goals: that needs the tools, which aren't stored, and is a separate feature.
- **Role checks in `validate`** load the catalogue from the installed package, so a project is checked
  against the roles its bimai version knows.

## Risks / Trade-offs

- Agents may ignore memory instructions → accepted for now; a Stop hook in the hooks change can check
  that history was considered.
- `.claude/agents/` is still shared per repo, not per seat → unchanged from init; resolved with `join`.
- History files grow → `bimai nap` (later) compacts them; the template asks for one line per learning.
