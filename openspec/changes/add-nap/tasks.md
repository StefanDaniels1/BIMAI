# Tasks

## 1. Session log

- [x] 1.1 `sessionlog.py`: hook handler (UserPromptSubmit, PostToolUse, Stop), per-session state, day files, gitignore. Verify: tests with recorded hook inputs, concurrent sessions.
- [x] 1.2 `bimai log --since/--until`; routing rule in the CLAUDE.md block; hooks written by `bimai init`/`bimai team`. Verify: tests.

## 2. Nap

- [x] 2.1 Budgets and `bimai nap --dry-run`; charter budget test. Verify: tests.
- [x] 2.2 Script part (duplicates, reversed decisions, archive over budget). Verify: "nothing lost" property test.
- [x] 2.3 Haiku part via `claude -p` (schema, checks, effort fallback, cost cap); weekly digests. Verify: tests with a fake `claude`; one real run.
- [x] 2.4 `SessionStart` hook and `--if-due` (lock, detached start). Verify: tests.

## 3. Docs and checks

- [x] 3.1 "Memory and history" guide; commands reference. Verify: check_docs, site build.
- [ ] 3.2 Final check: pytest (strict), openspec validate --all --strict, CI green.
