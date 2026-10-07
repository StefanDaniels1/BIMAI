# Tasks

## 1. Catalogue and connection

- [x] 1.1 `pyrevit` in `servers.yaml` (variants with `{APPDATA}` and `{ProgramFiles}`, `write_tools`, release pin); `{APPDATA}` in `server_config`; version check (7.0+). Verify: tests for per-user, all-users, old and missing pyRevit.
- [x] 1.2 Per-tool write rules (deny by default, ask with consent, removed on disconnect). Verify: tests.

## 2. Install

- [x] 2.1 `apps.py`: download, SHA-256 check, Revit-running check, silent per-user install, enable the agent host; offered by `bimai connect pyrevit` and `--install`. Verify: tests with a fake Windows; Windows CI installs the real pyRevit and checks `pyrevit --version` and agent enable.
- [x] 2.2 Prerequisites: detect .NET 8/10 Desktop Runtimes, install missing ones from pinned Microsoft installers (SHA-512) in one elevated step. Verify: tests with a fake Windows (none, one, both missing; bad hash); Windows CI.
- [x] 2.3 Onboarding status `needs-install` for pyRevit. Verify: test.

## 3. Docs and checks

- [x] 3.1 `guides/pyrevit.mdx`, connections page. Verify: check_docs, site build.
- [ ] 3.2 Final check: pytest (strict), openspec validate --all --strict, CI green.
