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
  add-in source. bimai compiles it with `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe`
  (present on every Windows 10/11 PC, C# 5) against that PC's `Bentley.MstnPlatformNET.dll`, adding any
  assembly the compiler asks for (CS0012) from OpenRoads' own folders. One build per installed version.
- **Only `AddIn.cs` touches Bentley types at compile time.** Everything civil goes through reflection
  (`Reflect.cs`): the member names from Bentley's SDK examples (`Session.Instance.GetActiveDgnModel`,
  `ConsensusConnection`, `GetActiveGeometricModel`, `Alignments`, `LinearGeometry`,
  `GetPointAtDistanceOffset`, `ProjectPointOnPerpendicular`, `Profiles`/`ActiveProfile`,
  `ProfileGeometry.GetVerticalControlPoints`, `Corridors`, `TerrainSurfaces`, `DTM.DrapePoint`,
  `StationingFormatter`), so a member that differs in some version costs one value or one tool, not the
  build. Results also include each object's simple properties (`properties`), so a tester sees what
  OpenRoads offers where the bridge guessed wrong.
- **Own protocol layer** (`Json.cs`, `Http.cs`, `Mcp.cs`), a C# 5 port of the Civil 3D bridge's dual-era
  server without System.Text.Json: no assembly that could clash with OpenRoads' own versions inside
  .NET Framework. Synchronous, one background thread per connection.
- **Main thread** as in Civil 3D: a hidden WinForms control created in `Run`, work posted with
  `BeginInvoke`, 30 s timeout; reads only.
- **Where it goes:** `C:\ProgramData\bimai\openroads\<version>\BimaiOpenRoads.dll` (users may write there,
  so updates need no admin) and `<OpenRoads>\config\appl\bimai-openroads.cfg` (Bentley's documented
  autoload: `MS_ADDINPATH` and `MS_DGNAPPS` inside `%if exists`), written in one elevated step for all
  versions, skipped when already right.
- **Port 27185** (Civil 3D uses 27184), loopback only, Host/Origin checks.
- **CI without OpenRoads:** a stand-in `Bentley.MstnPlatformNET.dll` (`stubs/`) in a fake OpenRoads folder;
  CI runs the real `bimai bridge install openroads` (real csc, real elevation), then the bridge's real
  MCP server (`dev/DevHost.cs`) against the protocol tests, then uninstall.

## Open questions (for the first test inside OpenRoads, see bridges/openroads/TESTING.md)

1. Does OpenRoads Designer pump Windows messages on its main thread so `BeginInvoke` runs promptly?
2. Which per-user configuration file does OpenRoads process for `MS_DGNAPPS` (Personal.ucf, prefs)?
3. Are CifNET distances in metres in every version, and do the reflected member names match 2023–2026?
4. Where is `Bentley.MstnPlatformNET.dll` in each version (next to the executable or in a subfolder)?

## Risks / Trade-offs

- No CI with OpenRoads → a spike on a real PC comes first (task 1), and the guide says which versions
  were verified.
- Compiling on install adds a step that can fail (missing assemblies, API changes) → clear errors naming
  the OpenRoads version, and the source stays readable for IT.
