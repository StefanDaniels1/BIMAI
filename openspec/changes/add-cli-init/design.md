# Design

## Context

`add-cli-validate` provides the `bimai` package and `validate()`. ARCHITECTURE.md §5.1 defines the
role catalogue (with `requires`, `serves` and default model), §5.5 the presets and team rules.
Connectors don't exist yet, so "data available" can only mean "found by the scan or declared".

## Goals / Non-Goals

**Goals:** one command from an empty or existing folder to a working Claude Code team; every step
deterministic except the free-text interpretation the user (or Claude) does before calling it.

**Non-Goals:** a plugin/marketplace install, hooks, multi-seat, BEP parsing.

## Decisions

- **Three pure functions, one thin command.** `scan(path) -> Scan`, `propose(answers, scan,
  catalogue) -> Team`, `plan_files(...) -> list[FileWrite]`; `init.py` only asks questions, prints and
  applies the file plan. `--dry-run` prints the plan instead of applying it. This makes every rule
  unit-testable without touching disk, and `/bimai:onboard` can later reuse the same functions.
- **Catalogue as data inside the package:** `catalogue/roles/<id>.md` (frontmatter: `model`,
  `requires`, `serves`, `description`; body: the charter) and `catalogue/presets/<id>.yaml` (`matches`,
  `team`). `catalogue/tools.yaml` maps tools to capabilities (e.g. `revit: [model.query]`,
  `acc: [issues.read, documents.read]`, `relatics: [requirements.read, risks.read]`,
  `primavera: [schedule.read]`) and scan categories to tools. Adding a role or tool is editing data.
- **Written subagents contain only what Claude Code reads** (`name`, `description`, `model`, body);
  bimai's composition fields stay in the catalogue, so a Claude Code frontmatter change can't break
  composition.
- **The Coordinator is the main session**, not a subagent (§5.2: it runs workflows and talks to the
  human), so its charter goes into the `CLAUDE.md` block.
- **Free-text role matching is exact against `matches`** (case-insensitive, both English and Dutch
  terms). Fuzzy interpretation is the agent's job, and the script decides (principle 3).
- **Planning XML detection** reads only the root element with `xml.etree.ElementTree.iterparse`
  (MSPDI `Project` namespace, P6 `APIBusinessObjects`), stopping after the first element, so large
  files stay cheap.
- **Scan limits:** stop after 20,000 files and say so, to keep init fast on huge shares.
- **Interactive prompts use `input()`** with defaults in brackets; no TUI library.

## Risks / Trade-offs

- Subagents in `.claude/agents/` are shared by everyone in the repo, while the architecture gives
  each person their own team. That's fine with one seat; the `join` change must resolve it (e.g.
  prefix per seat or a union of teams).
- Filename-based BEP and Relatics detection will miss files → the interview always lets the user
  declare tools and data by hand.
- Presets from one document may not match real roles → both English and Dutch match terms; unknown
  roles fail loudly with the list of options.
