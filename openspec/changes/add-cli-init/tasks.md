# Tasks

## 1. Catalogue

- [ ] 1.1 Add `cli/bimai/catalogue/roles/` charters for coordinator, requirements-risk-manager, planning-analyst, information-manager, model-checker, issue-manager, scribe and mentor, with `model`, `requires`, `serves`, `description` frontmatter per ARCHITECTURE.md §5.1/§5.4. Verify: test that loads every role and checks its model tier.
- [ ] 1.2 Add the four presets (§5.5, English and Dutch match terms) and `tools.yaml` (tools → capabilities, scan categories → tools). Verify: test that every role named in a preset exists and every capability a role requires is provided by some tool.

## 2. Repo scan

- [ ] 2.1 Implement `scan(path)` with the categories, skip rules, 5 example paths and the 20,000-file limit. Verify: tests with a temp folder for each category, including an unrelated `.xml` and an empty folder, and a check that the folder is unchanged afterwards.
- [ ] 2.2 Detect git repo, `CLAUDE.md` and `.claude/`. Verify: test.

## 3. Team proposal

- [ ] 3.1 Implement `propose(answers, scan, catalogue)`: preset match, goal and data rules, Mentor rule, max 5, reasons, and the "would join with <data>" hints. Verify: tests for the modeller, missing planning data, Scribe reason and unknown role scenarios.

## 4. File plan and writing

- [ ] 4.1 Implement `plan_files(...)` for the `.bimai/` files, subagents, `CLAUDE.md` block, settings merge and `.gitignore` lines. Verify: test that a workspace written to a temp folder passes `validate()` with no problems.
- [ ] 4.2 Apply the safety rules: never overwrite, refuse changed subagents, replace only the marked block, no duplicate `.gitignore` lines, exit 2 when already initialised. Verify: tests for existing `CLAUDE.md`, existing settings with `opus`, repeated `.gitignore`, and an existing `.bimai/project.yaml`.

## 5. Command

- [ ] 5.1 Add `bimai init` to the CLI: interactive prompts with scan pre-fills, all flags, `--yes`, `--dry-run`, `--json`, confirmation, printed file list, exit codes. Verify: tests for non-interactive run, dry run writes nothing, declined proposal exits 1.
- [ ] 5.2 Try it by hand on an empty folder and on a copy of the example project with its `.bimai/` removed; paste the output into the PR. Verify: both produce a valid workspace and a sensible team.

## 6. Documentation

- [ ] 6.1 Add a "Already have a project folder?" section with `bimai init` and sample output to `docs/content/docs/start/new-project.mdx`, marked available. Verify: `python scripts/check_docs.py` passes.
- [ ] 6.2 Add the repo scan to ARCHITECTURE.md §5.5 and move this slice forward in the §14 build order. Verify: the docs check still passes.
- [ ] 6.3 Final check: `python -m pytest -q`, `openspec validate --all --strict` and `python scripts/check_docs.py` all pass.
