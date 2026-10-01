# Proposal

## Why

The onboarding interview is rigid: people must type exact values ("bim coordinator", "model-checks",
"civil3d"), with no suggestions and no explanation of what each choice means. Claude Code has a built-in
way to ask people questions: clickable options with a short description, a recommended default, multiple
choice where several answers apply, and always an "Other" field for their own words. Onboarding should use
it, while the script keeps deciding what is valid (agents reason, scripts decide).

## What Changes

- **`bimai init --interview`** prints the interview as JSON, ready for Claude Code's question tool: steps
  of at most four questions, each with a short header, two to four options (label, description, value),
  the recommended option first, multi-select where it fits, the full list of allowed values for mapping
  a free-text answer, and whether the question is a choice or a text answer with suggestions.
  - Options come from the folder scan and the role: the four roles; for goals and tools the four most
    relevant to the chosen role (found tools first); suggested names from the folder and git.
  - Step 2 (goals, tools, VS Code) depends on the role: `--interview --role <role>`.
- **Forgiving role matching:** an unknown role suggests the closest roles instead of only listing all.
- **Labels and descriptions** for roles, goals and tools in the catalogue, so options explain themselves.
- **The start prompt** (install page and landing page) tells Claude to run the interview with its question
  tool, map "Other" answers to allowed values (asking when unsure), show the proposed team, and ask for a
  final yes before writing.
- Docs: the interview section describes the guided flow.

## Non-goals

- A different question flow in the terminal (`bimai init` without Claude keeps its prompts).
- Reading the BEP to pre-fill answers (BEP intake).
- Re-running onboarding on an existing project (team changes stay with `bimai team`).

## Capabilities

### New Capabilities
- `guided-onboarding`: the interview specification, forgiving role matching and the guided prompt.

### Modified Capabilities
<!-- none -->

## Impact

- New `cli/bimai/interview.py`; `cli.py` (`--interview`, `--role` for it); catalogue labels and
  descriptions (`presets/*.yaml`, `tools.yaml`); `team.py` (role suggestions); tests.
- `docs/lib/prompts.ts`, `docs/content/docs/start/install.mdx`, `new-project.mdx`.
