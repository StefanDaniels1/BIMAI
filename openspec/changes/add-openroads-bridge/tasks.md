# Tasks

## 1. Verification inside OpenRoads (handed over)

- [ ] 1.1 An OpenRoads user follows `bridges/openroads/TESTING.md` (install, autoload, every tool, values compared). Verify: their report; fixes in a follow-up change. Until then the bridge is labelled beta.

## 2. Bridge

- [x] 2.1 Protocol layer in C# 5 (`Json.cs`, `Http.cs`, `Mcp.cs`, `Tools.cs`), same behaviour as the Civil 3D bridge. Verify: protocol tests against the development host (locally and on Windows CI with csc.exe).
- [x] 2.2 Add-in (`AddIn.cs`), dispatcher, reflection helpers and the nine civil tools. Verify: compiles as C# 5 for .NET Framework 4.8 against the stand-in assembly (CI); tools answer clearly outside OpenRoads.
- [x] 2.3 Pack script and release workflow (`openroads-bridge-v*`). Verify: reproducible zip test; release run.

## 3. Install and connect

- [x] 3.1 `openroads.py`: find versions, build (CS0012 retries), ProgramData + config\appl in one prompt, status, uninstall; `bimai bridge … openroads`. Verify: tests with a simulated Windows; Windows CI with the real compiler and elevation.
- [x] 3.2 Catalogue `openroads` and Bentley MicroStation (unavailable); onboarding status; start prompt. Verify: tests.

## 4. Docs and checks

- [x] 4.1 `guides/openroads-bridge.mdx`, connections page, "beta" badge, TESTING.md. Verify: check_docs, site build.
- [ ] 4.2 Final check: pytest (strict), openspec validate --all --strict, CI green; pin the release hash.
