# Tasks

## 1. Catalogue

- [x] 1.1 Role descriptions, `goal_options` and `typical_tools` in each preset; goal labels and descriptions in `tools.yaml`; tool descriptions. Verify: catalogue test (4 goal options per preset, defaults included, tools exist).

## 2. Interview

- [x] 2.1 `cli/bimai/interview.py`: steps, questions, options (scan first), recommended values, allowed values, text suggestions, tool limits. Verify: tests for step 1, step 2 per role, found tools first, limits for every role with and without scan results.
- [x] 2.2 `bimai init --interview [--role]` (JSON, writes nothing, exit 2 when already initialised or role unknown). Verify: CLI tests.
- [x] 2.3 Forgiving role matching with suggestions. Verify: tests for typos and Dutch terms.

## 3. Prompt and docs

- [x] 3.1 Rewrite the start prompt for the guided flow; update the install and new-project pages. Verify: test on the prompt text (names `--interview`, the question tool, "Other" mapping, final yes); site build.
- [x] 3.2 Try the guided flow with the real Claude Code on a scratch folder (headless where possible). Verify: notes in the PR.
- [x] 3.3 Final check: pytest (strict), openspec validate --all --strict, check_docs, CI green.
