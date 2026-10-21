# Tasks

## 1. Save and sync

- [x] 1.1 `sync.py`: what is saved, identity, message, save, sync (rebase, push retry, conflict, no remote, offline). Verify: tests with a bare remote and two clones.
- [x] 1.2 `bimai save`, `bimai sync`; automatic: brief syncs first, Stop saves and shares in the background; `sync.auto`. Verify: tests.
- [x] 1.3 Safety rails (deny rules). Verify: test.

## 2. Join from a link

- [x] 2.1 `bimai join <link>` clones. Verify: test with a local remote.

## 3. Docs and checks

- [x] 3.1 "Saving and sharing" page, join page and prompt. Verify: prompt test, check_docs, build.
- [x] 3.2 Final check: pytest (strict), openspec validate --all --strict, CI green (Windows git included).
