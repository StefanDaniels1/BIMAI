# Tasks

## 1. Protocol library (Bimai.Mcp)

- [x] 1.1 Solution layout in `bridges/civil3d/` (Directory.Build.props, solution, three projects, pinned packages). Verify: `dotnet build` succeeds for all target frameworks on macOS.
- [x] 1.2 Minimal HTTP/1.1 server on loopback (Content-Length, chunked, keep-alive, 4 MiB limit, timeouts, Origin/Host/remote checks, 403/404/405/413). Verify: tests for each.
- [x] 1.3 Dual-era MCP protocol: initialize (legacy negotiation), server/discover, ping, tools/list, tools/call, notifications (202), modern header validation (-32020), unsupported version (-32022), unknown method (404/-32601 modern), parse errors. Verify: tests for each.
- [x] 1.4 Tool model and argument helpers (typed args, defaults, limits, per-item errors, non-finite numbers), dispatcher interface with timeout, logger with size cap. Verify: tests.

## 2. Civil 3D add-in (Bimai.Civil3D)

- [x] 2.1 Plugin entry (Initialize/Terminate, never throws), main-thread dispatcher (hidden control, quiescence, read lock, transaction, timeout), `BIMAIBRIDGE` status command. Verify: builds for net8.0-windows and net10.0-windows against the pinned packages.
- [x] 2.2 Tools: get_drawing, list_layers, count_objects, list_alignments, get_alignment, alignment_point, alignment_station, profile_elevations, list_surfaces, surface_elevations, list_corridors, list_pipe_networks, get_pipe_network. Verify: both builds compile; tool definitions validated by a test that loads their schemas without Civil 3D.
- [x] 2.3 Bundle (PackageContents.xml), `build.ps1`/`build.sh`, `install.ps1`, `uninstall.ps1`. Verify: build script produces the bundle layout; manifest test checks module paths exist.

## 3. End-to-end without Civil 3D

- [x] 3.1 A development server (same protocol, sample data) and a test with the real Claude Code CLI (`claude mcp` health check) to confirm the protocol era Claude Code uses. Verify: Claude Code reports the server connected; result noted in design.md.

## 4. bimai side

- [x] 4.1 `civil3d` catalogue entry, bundle detection, `--port`. Verify: tests for not installed, installed (mocked), port override, Model Checker access.

## 5. CI and docs

- [x] 5.1 CI job (windows-latest): build both add-in targets, run protocol tests; also run protocol tests on ubuntu. Verify: green on the PR.
- [x] 5.2 Docs: `docs/content/docs/guides/civil3d-bridge.mdx` (install, connect, tools, troubleshooting, manual test checklist), Connections guide, command reference, ARCHITECTURE.md §7.6/§9. Verify: check_docs and site build pass.
- [ ] 5.3 Final check: pytest (strict), dotnet test, openspec validate --all --strict, check_docs.
