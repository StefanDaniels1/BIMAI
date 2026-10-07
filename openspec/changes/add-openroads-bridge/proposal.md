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
  - Tools: `get_drawing_info`, `list_alignments`, `get_alignment` (elements, points with stations),
    `locate_on_alignment` (station and offset of a point), `list_profiles`, `get_profile` (control
    points with station and elevation), `list_corridors` (alignment and station range), `list_terrains`,
    `get_terrain_elevation` (at x,y).
  - Built on Bentley's civil API (CifNET, as documented in the OpenRoads Designer SDK), on OpenRoads'
    main thread, never changing the drawing.
- **Built on the user's PC.** Bentley's API assemblies aren't redistributable and aren't on NuGet, so
  bimai can't ship a compiled add-in. The release contains the add-in's source (C# 5, no dependencies);
  `bimai bridge install openroads` compiles it with the C# compiler that ships with Windows' .NET
  Framework 4.8, against each OpenRoads Designer installed on that PC. The release zip is pinned by SHA-256.
- **Seamless install:** detects installed OpenRoads Designer versions, puts the bridge in
  `C:\ProgramData\bimai\openroads`, registers it with one `config\appl` file (Bentley's documented way,
  one explained Windows permission prompt), and is offered during onboarding when someone picks
  OpenRoads (status `needs-install`, like Civil 3D).
- **Beta:** written from Bentley's documentation and tested in CI with the real compiler, the real
  permission step and the bridge's real MCP server, but not yet inside OpenRoads Designer. A test guide
  (`bridges/openroads/TESTING.md`) lets an OpenRoads user verify it in about 20 minutes.
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

- New `bridges/openroads/` (C# 5 sources, a stand-in Bentley assembly and a development host for CI,
  pack script, test guide), `openroads.py` (find, build, register, remove), catalogue, CLI, CI, release
  workflow, docs (new "beta" status badge).
- Needs a real Windows PC with OpenRoads Designer for verification (CI has no OpenRoads).
