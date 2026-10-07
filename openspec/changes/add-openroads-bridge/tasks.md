# Tasks

## 1. Spike on a real PC (needs OpenRoads Designer)

- [ ] 1.1 Minimal add-in (compiled with csc.exe on the PC) that starts the HTTP server, answers `server/discover` and `list_alignments` on the main thread. Verify: answers the open questions in design.md; notes in the PR.

## 2. Bridge

- [ ] 2.1 `Bimai.Mcp` multi-targets net48 (or built-in JSON). Verify: protocol tests on net48 and net8.
- [ ] 2.2 Add-in source (C# 5): AddIn, dispatcher, tools. Verify: CI compiles it with csc flags against stubs; real PC test of every tool.
- [ ] 2.3 Release workflow (`openroads-bridge-v*`): zip with source, Bimai.Mcp, scripts; SHA-256 pin. Verify: release run.

## 3. Install and connect

- [ ] 3.1 `bridges.py`: detect OpenRoads versions, compile, install per user, autoload, uninstall, status. Verify: tests with a fake Windows; real PC.
- [ ] 3.2 Catalogue `openroads` and Bentley MicroStation (unavailable); onboarding status. Verify: tests.

## 4. Docs and checks

- [ ] 4.1 `guides/openroads-bridge.mdx`, connections page. Verify: check_docs, site build.
- [ ] 4.2 Final check: pytest (strict), openspec validate --all --strict, dotnet test, CI green.
