# Proposal

## Why

Civil 3D is central to infrastructure work, but Autodesk's own AutoCAD and Civil 3D MCP server is only
reachable inside Autodesk Assistant. bimai's team can't see a single alignment, surface or pipe today.
ARCHITECTURE.md §7.6 and §9 plan a local `desktop-bridge` for exactly this: an add-in inside the user's
running Civil 3D that exposes an MCP server on the user's own machine, the same pattern Autodesk uses
for Revit and Fusion.

## What Changes

- **`bridges/civil3d/`**: a C# add-in, loaded automatically by Civil 3D from an Autodesk plug-in bundle,
  that starts a local MCP server (Streamable HTTP, loopback only) inside the running session.
  - Civil 3D 2025 and 2026 (.NET 8) and Civil 3D 2027 (.NET 10), one bundle, built against Autodesk's
    official `AutoCAD.NET` and `Civil3D.NET` NuGet packages.
  - **Read-only tools** on the open drawing: drawing info (units, coordinate system), layers, object
    counts, alignments (with station ↔ coordinate conversion), profiles and profile elevations,
    surfaces and surface elevations, corridors, pipe networks.
  - Safe by construction: work runs on Civil 3D's main thread, never while a command is running, under
    a read lock and a transaction; clear errors instead of crashes; a `BIMAIBRIDGE` status command and
    a log file.
  - A protocol library with automated tests that run in CI on every platform.
- **bimai side:** `civil3d` in the server catalogue (local, read-only, Windows), detected through the
  installed bundle; the Model Checker gets it automatically.
- **Install and build:** a build script producing the bundle, and an install script for
  `C:\Program Files\Autodesk\ApplicationPlugins` (a location Civil 3D always trusts).
- CI builds the add-in for both .NET versions and runs the protocol tests.
- Docs: a Civil 3D bridge guide (install, connect, tools, troubleshooting).

## Non-goals

- Write tools (styles, properties): later, behind the approval gate.
- AutoCAD-only (non-Civil) drawings, Civil 3D 2024 and older (.NET Framework 4.8), OpenRoads.
- A signed installer or MSI; code signing.
- Authentication tokens: like Autodesk's local servers, the bridge relies on loopback-only binding
  and Origin/Host checks (see design).

## Capabilities

### New Capabilities
- `civil3d-bridge`: the add-in, its MCP server, its tools, packaging and installation.

### Modified Capabilities
- `mcp-connections`: the catalogue gains `civil3d` (detected via the installed bundle).

## Impact

- New `bridges/civil3d/` (.NET solution: protocol library + tests, Civil 3D add-in, bundle, scripts).
- `cli/bimai/catalogue/servers.yaml`, `connections.py` (bundle detection), tests.
- `.github/workflows/ci.yml`: a .NET job. Docs and ARCHITECTURE.md §7.6/§9.
