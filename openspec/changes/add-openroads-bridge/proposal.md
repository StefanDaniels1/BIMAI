# Proposal

## Why

Road designers on Bentley OpenRoads Designer (common at Dutch and European infrastructure clients) have no
way to let Claude Code read their design. Bentley's MicroStation MCP server is early access through sales
only, has no civil (OpenRoads) tools, and Bentley Copilot (2026, technology preview) only answers how-to
questions. A bimai bridge inside OpenRoads Designer, like the Civil 3D bridge, gives a modeller's team
read-only access to alignments, profiles, corridors and terrains in the open drawing.

## What Changes

- **OpenRoads bridge** (`bridges/openroads`): an add-in that runs inside OpenRoads Designer (2023 and
  newer, Windows) and serves MCP on `127.0.0.1:27185`, read-only, with the same protocol support as the
  Civil 3D bridge (2026-07-28 stateless and the older handshake).
  - Tools: `get_drawing_info`, `list_alignments`, `get_alignment` (horizontal elements, stations),
    `list_profiles`, `get_profile` (vertical intersection points, grades), `list_corridors`,
    `get_corridor` (templates and station ranges), `list_terrains`, `get_terrain_elevation` (at x,y),
    `list_drainage` (nodes and conduits, read-only in Bentley's SDK).
  - Built on Bentley's civil API (CifNET, as documented in the OpenRoads Designer SDK), on OpenRoads'
    main thread, never changing the drawing.
- **Built on the user's PC.** Bentley's API assemblies aren't redistributable and aren't on NuGet, so
  bimai can't ship a compiled add-in. The release contains the add-in's source (small, C# 5) and the
  prebuilt protocol library; `bimai bridge install openroads` compiles the source with the C# compiler
  that ships with Windows' .NET Framework 4.8, against the OpenRoads Designer installed on that PC. This
  also matches each OpenRoads version automatically. The release zip is pinned by SHA-256 as usual.
- **Seamless install:** detects installed OpenRoads Designer versions, installs per user (no administrator
  rights where the per-user configuration allows it), registers autoloading, and is offered during
  onboarding when someone picks OpenRoads (status `needs-install`, like Civil 3D).
- **Catalogue:** `openroads` (bimai bridge, Windows, matches the `openroads` tool) and Bentley's
  MicroStation MCP server as unavailable (early access through Bentley).
- **Docs:** an OpenRoads bridge guide.

## Non-goals

- Changing the design (read-only, like the Civil 3D bridge).
- OpenRail, OpenSite and OpenBridge Designer (the same SDK loads there; a later change).
- MicroStation without OpenRoads (no civil model).

## Capabilities

### New Capabilities
- `openroads-bridge`: the add-in, its tools and its build-on-install.

### Modified Capabilities
- `mcp-connections`: `openroads` and Bentley's MicroStation server in the catalogue.

## Impact

- New `bridges/openroads/` (C# add-in source, net48 build of the protocol library, install scripts,
  stub assemblies for compiling in CI), `bridges.py` (compile step, OpenRoads detection), catalogue, CI,
  release workflow, docs.
- Needs a real Windows PC with OpenRoads Designer for verification (CI has no OpenRoads).
