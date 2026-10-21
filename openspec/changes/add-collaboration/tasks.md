# Tasks

## 1. Shared seats

- [ ] 1.1 Shared CLAUDE.md block and union of agents; generic agent memory section. Verify: two-seat test (nothing of the first seat lost; same files from either seat).
- [ ] 1.2 `bimai brief` and its SessionStart hook; "since last session". Verify: tests.

## 2. Join

- [ ] 2.1 `bimai join --interview` and `bimai join`; init in an existing project points to join. Verify: tests (three personas join one project, validate, files of others unchanged).

## 3. Handoffs and decisions

- [ ] 3.1 `bimai handoff`, `bimai inbox`, `bimai handoff done`. Verify: tests.
- [ ] 3.2 `bimai decide`, `bimai decisions`; nap treats superseded as reversed; roles use the commands. Verify: tests.
- [ ] 3.3 `bimai log --team`. Verify: test.

## 4. Website and checks

- [ ] 4.1 Join prompt (copy button), start prompt handles an existing project, "Join a project" and "Working together" pages. Verify: prompt test, check_docs, site build.
- [ ] 4.2 A real run: three personas in one folder with Claude Code headless. Verify: notes in the PR.
- [ ] 4.3 Final check: pytest (strict), openspec validate --all --strict, CI green.
