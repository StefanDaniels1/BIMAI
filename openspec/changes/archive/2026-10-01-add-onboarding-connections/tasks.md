# Tasks

## 1. Connection status

- [x] 1.1 `connection_status` in `connections.py` and the plan for chosen tools. Verify: tests per status (macOS, Windows with and without bridge, unavailable server), with platform and bridge lookup faked.

## 2. Init

- [x] 2.1 Init adds `ready` servers to `.mcp.json` (also with `--yes`); `--json` includes the plan; final output lists statuses without impossible commands. Verify: tests for Civil 3D on macOS and Windows.
- [x] 2.2 Interview tool options carry platform notes. Verify: test for Civil 3D on macOS.

## 3. Prompt and docs

- [x] 3.1 Start prompt: `needs-install` question after writing; new-project page and Civil 3D guide. Verify: prompt test; site build.
- [x] 3.2 Final check: pytest (strict), openspec validate --all --strict, check_docs, CI green.
