# Proposal

## Why

The end goal: install bimai in a fresh or existing repo, let it look at the project, and get a
configured AI team. The build order (ARCHITECTURE.md §14) reaches that only after five other steps.
This change delivers a thin end-to-end version now; later changes (BEP intake, colleagues' seats,
connectors) deepen it.

Implements a first slice of ARCHITECTURE.md §5.5 (onboarding and team composition), §5.4 (model
tiers) and the `bimai init` path of §8.4. Adds a **repo scan**, which the architecture doesn't have yet.

## What Changes

- `bimai init [PATH]` in a fresh or existing folder:
  1. **Scan:** deterministically lists what the folder already contains (models, issues, IDS,
     BEP/EIR documents, planning exports, Relatics exports, transcripts) and whether it already has
     Claude Code configuration.
  2. **Interview:** asks role, goals, tools and data, VS Code familiarity, language and project
     name, pre-filled from the scan. Every answer is also a flag, so Claude Code can run it.
  3. **Propose:** picks a role preset, applies the team rules (goal served, data available,
     max 5) and shows each member with its reason.
  4. **Write, after confirmation:** a valid `.bimai/` workspace (project, person, position, seat,
     team) and the Claude Code configuration: one subagent per team member in `.claude/agents/`,
     the Coordinator's instructions in a marked block in `CLAUDE.md`, and `model: sonnet` in
     `.claude/settings.json`.
- `bimai init --dry-run` shows scan and proposal without writing anything.
- Existing files are never overwritten; settings are merged, `CLAUDE.md` and `.gitignore` only gain bimai lines.
- The role catalogue and four presets (§5.5) ship inside the package.
- ARCHITECTURE.md: repo scan added to §5.5; build order in §14 moves this slice forward.
- Docs: "Start a project" gets a section on `bimai init`, marked available.

## Non-goals

- Reading the BEP (only detected and reported; BEP intake is its own change).
- A second person on the project (`bimai join`, extra seats), `bimai new`, `bimai setup`, git hosting.
- Hooks, the gateway and connectors: "data available" means found or declared, not connected.
- Mentor and Builder beyond the Mentor joining for users new to VS Code.
- The conversational `/bimai:onboard` command (the plugin change adds it on top of these flags).

## Capabilities

### New Capabilities
- `workspace-init`: `bimai init`: repo scan, interview, team proposal and the files it writes.

### Modified Capabilities
<!-- none -->

## Impact

- Depends on `add-cli-validate` (the `bimai` package and `validate()`); apply that first.
- New: `cli/bimai/init.py`, `scan.py`, `team.py`, `cli/bimai/catalogue/` (roles, presets), tests.
- No new dependencies.
- Docs: `docs/content/docs/start/new-project.mdx`. ARCHITECTURE.md §5.5 and §14.
