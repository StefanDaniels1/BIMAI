# Design

## Context

From Bentley's OpenRoads Designer SDK documentation (docs.bentley.com, SDK Help v1/v2 and 2025):

- Add-ins are .NET Framework 4.8 assemblies with a class inheriting `Bentley.MstnPlatformNET.AddIn`
  (an `MdlTaskID`, a constructor, `Run`), loaded with `mdl load <dll>` or automatically through a
  configuration file: `MS_ADDINPATH < <folder>` and `MS_DGNAPPS < <dll>`.
- Civil data: `new Bentley.CifNET.SDK.ConsensusConnection(activeModel).GetActiveGeometricModel()` gives
  alignments, profiles, corridors, terrain surfaces (`Bentley.CifNET.GeometryModel.SDK`). Create/modify is
  supported for alignment, profile, corridor and superelevation; drainage and utilities are read-only.
- The CifNET assemblies are installed with OpenRoads (`…\OpenRoadsDesigner\Cif`); the platform
  assemblies (`Bentley.DgnPlatformNET`, `Bentley.MstnPlatformNET`) next to the executable.
- No public NuGet packages from Bentley (only unofficial repackagings by third parties).
- MicroStation Python (2024+) has modules for DGN, geometry, EC properties and the platform, but no
  civil module; Bentley's MicroStation MCP server is early access, without civil tools.

## Decisions

- **C# add-in on CifNET**, not Python: only CifNET reaches alignments, profiles, corridors and terrains.
- **Compile on the user's PC.** Bentley's assemblies can't be redistributed, so the release carries the
  add-in source plus `Bimai.Mcp.dll` built for net48 in CI. bimai compiles the add-in with
  `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe` (present on every Windows 10/11 PC, C# 5)
  against that PC's OpenRoads assemblies. The Bentley-facing code stays small and C# 5; the protocol and
  tool logic live in `Bimai.Mcp` (modern C#, multi-targeted to net48). CI compiles the add-in with the
  same compiler flags against stub assemblies that mirror the Bentley types we use, so syntax and C# 5
  limits are checked on every push; the real API is checked on a real PC.
- **Protocol library shared with Civil 3D:** `Bimai.Mcp` gets a `net48` target (System.Text.Json from
  NuGet, MIT, shipped next to the add-in through `MS_ADDIN_DEPENDENCYPATH`).
- **Main thread** as in Civil 3D: a hidden WinForms control created in `Run`, requests marshalled with
  `BeginInvoke`; reads only, no transactions.
- **Per-user install, autoload:** files under `%LOCALAPPDATA%\bimai\openroads\<OpenRoads version>`; the
  autoload lines go into the per-user configuration if OpenRoads reads it (to verify), otherwise into
  `…\OpenRoadsDesigner\config\appl\bimai.cfg` (Bentley's documented location; needs Windows' permission,
  explained as for Civil 3D).
- **Port 27185** (Civil 3D uses 27184), loopback only.

## Open questions (verified on a real PC before building the tools)

1. Does OpenRoads Designer pump Windows messages on its main thread so `BeginInvoke` runs promptly?
2. Which per-user configuration file does OpenRoads process for `MS_DGNAPPS` (Personal.ucf, prefs)?
3. Does System.Text.Json (and its dependencies) load inside OpenRoads without binding conflicts? If not,
   `Bimai.Mcp` uses a small built-in JSON writer/reader for net48.
4. Exact CifNET members for stations, profile VPIs and corridor templates across 2023–2026.

## Risks / Trade-offs

- No CI with OpenRoads → a spike on a real PC comes first (task 1), and the guide says which versions
  were verified.
- Compiling on install adds a step that can fail (missing assemblies, API changes) → clear errors naming
  the OpenRoads version, and the source stays readable for IT.
