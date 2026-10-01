# Design

## Context (verified October 2026)

From Autodesk's documentation (via the Product Help MCP server and help.autodesk.com) and Autodesk's
official NuGet packages:

- **Runtimes:** Civil 3D 2025 and 2026 run .NET 8; Civil 3D 2027 runs **.NET 10** ("New in 2027").
  Civil 3D 2027's `acdbmgd.runtimeconfig.json` lists only `Microsoft.NETCore.App` and
  `Microsoft.WindowsDesktop.App`; a plugin depending on `Microsoft.AspNetCore.App` "may prevent the
  plugin from running".
- **References:** a Civil 3D plugin references `AcDbMgd`, `AcMgd`, `AcCoreMgd`, `AecBaseMgd` and
  `AeccDbMgd`, not copied locally, x64. Autodesk publishes them on NuGet as `AutoCAD.NET` and
  `Civil3D.NET`. Pinned: `AutoCAD.NET` 25.0.1 (net8.0; depends on Core/Model 25.0.0) with `Civil3D.NET`
  13.7.1175 (2025.2, net8.0) for the .NET 8 build; `AutoCAD.NET` 26.0.0 with `Civil3D.NET` 13.9.628
  (net10.0) for the .NET 10 build. Note: `AutoCAD.NET` 25.0.2 and 25.1.1 were republished in 2026 for
  net10.0, so they are not used for the .NET 8 build; an assembly built against 2025's API also loads
  in 2026 and in any later runtime.
- **Bundles:** `PackageContents.xml` with one `Components` element per build, `RuntimeRequirements`
  `Platform="Civil3D"`, `SeriesMin`/`SeriesMax` (R25.0–R25.1 for 2025–2026, R26.0 for 2027), module
  paths with `/` relative to the bundle. .NET components load at startup by default; declaring
  commands in the manifest would switch to load-on-command, so none are declared. Autodesk's own
  Drainage Area Manager uses this per-framework layout (`Contents\net8.0-windows\` …).
- **Trust:** `C:\Program Files\` and subfolders are always trusted (TRUSTEDPATHS); elsewhere,
  SECURELOAD=1 warns and SECURELOAD=2 blocks. Install target:
  `C:\Program Files\Autodesk\ApplicationPlugins\bimai-civil3d.bundle` (administrator, once).
- **Threading and locking (AutoCAD .NET guide + API docs):** code running outside a command (like a
  modeless dialog) must lock the document. `LockDocument(mode, null, null, promptIfFails: false)` fails
  instead of prompting when a command is in progress. `Application.IsQuiescent` tells whether a
  command, LISP or ARX command is active.
- **Civil 3D API (checked against the assemblies):** `CivilApplication.ActiveDocument`;
  `CivilDocument.GetAlignmentIds/GetSurfaceIds/GetPipeNetworkIds/CorridorCollection/CogoPoints/Settings`;
  `Alignment` (`Length`, `StartingStation`, `EndingStation`, `AlignmentType`, `SiteName`, `StyleName`,
  `GetProfileIds`, `PointLocation`, `StationOffset`); `Profile` (`ElevationAt`, `ElevationMin/Max`,
  `ProfileType`); `Surface` (`GetGeneralProperties`, `FindElevationAtXY` throws outside the surface),
  `TinSurface.GetTinProperties`; `Corridor.Baselines` → `Baseline` (`AlignmentId`, `ProfileId`,
  `BaselineRegions` → `StartStation`, `EndStation`, `AssemblyId`); `Network.GetPipeIds/GetStructureIds`;
  `Pipe` (`InnerDiameterOrWidth`, `Length2D`, `Slope` (absolute), `MinimumCover`, `MaximumCover`,
  `StartPoint`, `EndPoint`, structure ids); `Structure` (`Location`, `RimElevation`, `SumpElevation`);
  `SettingsUnitZone` (`CoordinateSystemCode`, `DrawingUnits`, `AngularUnits`).
- **MCP:** Streamable HTTP; servers MUST validate `Origin` (403 if invalid) and SHOULD bind to
  localhost. Revision **2026-07-28** removed the `initialize` handshake and sessions: every request
  carries `_meta["io.modelcontextprotocol/protocolVersion"]`, POSTs carry `MCP-Protocol-Version`,
  `Mcp-Method` and (for `tools/call`) `Mcp-Name` headers that must match the body (else 400,
  `-32020`), unsupported versions get 400 `-32022` with the supported list, unknown methods 404
  `-32601`, `server/discover` is required, results carry `resultType`, and list results carry
  `ttlMs`/`cacheScope`. A **dual-era** server MAY also answer legacy `initialize` clients.

## Decisions

- **Three projects:**
  `Bimai.Mcp` (net8.0;net10.0, no Autodesk or third-party references): HTTP listener, dual-era MCP
  protocol, tool model, argument helpers, logging. Fully unit-tested on every OS.
  `Bimai.Mcp.Tests` (xUnit). `Bimai.Civil3D` (net8.0-windows;net10.0-windows): the add-in, the
  main-thread dispatcher and the Civil 3D tools. Compiled in CI against Autodesk's packages.
- **Own minimal HTTP/1.1 server on `TcpListener`** bound to `127.0.0.1` and `::1` instead of
  `HttpListener`: it truly binds loopback only (http.sys `localhost` prefixes accept other interfaces
  with a forged Host), needs no URL ACL or administrator rights, and behaves identically on Windows
  and in the macOS/Linux test runs. Supports Content-Length and chunked bodies, keep-alive, 4 MiB limit,
  30 s idle timeout. Responses are `application/json` only (no SSE), which the spec allows.
- **Dual-era protocol:** modern requests (with `_meta` protocol version) are validated and served
  statelessly; `initialize` selects legacy semantics (2025-03-26, 2025-06-18, 2025-11-25). All
  results include `resultType: "complete"` and server info in `_meta` (ignored by legacy clients).
  No sessions are minted; `Mcp-Session-Id` is ignored; GET/DELETE get 405.
- **No authentication token** (MCP "SHOULD"): loopback-only sockets plus Origin and Host checks stop
  remote access and DNS rebinding; the tools are read-only; Autodesk's own local Revit and Fusion
  servers work the same way. A token would add a failure point for non-technical users. Revisit when
  write tools arrive.
- **Main thread via a hidden WinForms control** created in `IExtensionApplication.Initialize` (which
  runs on the main thread): `BeginInvoke` posts a window message, so work runs promptly in the
  application context even when the user is idle (the `Idle` event does not fire without input).
  Each call: refuse unless `IsQuiescent`; take `MdiActiveDocument`; `LockDocument(Read, null, null,
  false)`; `StartOpenCloseTransaction()`; open everything `ForRead`; commit; 30 s timeout on the waiting
  side. Every exception becomes a tool error; nothing escapes into Civil 3D.
- **No invert levels:** the API doesn't document whether `Pipe.StartPoint` is the centreline or the
  invert, so the bridge reports points, slope, diameter and cover (defined by Autodesk) and never
  derives inverts.
- **Values in drawing units,** non-finite numbers as `null`, lists capped by `limit` (default 200,
  max 2000) with `truncated: true` when cut; per-point results for elevations and stations.
- **Port 27184** (Fusion uses 27182), overridable via `BIMAI_CIVIL3D_PORT`. A second Civil 3D instance
  finds the port taken, logs it and runs without the bridge.
- **Detection in bimai:** `bimai connect civil3d` checks for `bimai-civil3d.bundle` in the
  ApplicationPlugins folders (Program Files, ProgramData, %APPDATA%), and supports `--port`.

## Risks / Trade-offs

- I can't run Civil 3D here: correctness of Civil 3D calls is guaranteed only as far as compiling
  against both API versions and Autodesk's docs go. The first real run needs a manual test checklist
  (in the docs and the PR), on Windows with Civil 3D 2025, 2026 or 2027.
- Long reads (huge drawings) block Civil 3D's UI for their duration; limits and the timeout keep this
  bounded.
- Verified with Claude Code 2.1.286 against the development server (same protocol code and tool
  definitions, sample data): Claude Code speaks the **modern 2026-07-28** era. It calls
  `server/discover`, then `tools/list`, then `tools/call` with `MCP-Protocol-Version`, `Mcp-Method` and
  `Mcp-Name` headers; header validation passed, and a headless session answered from two tool results
  correctly. A legacy-only server would have depended on Claude Code's fallback. The legacy path stays
  for other clients (Claude Desktop via mcp-remote, VS Code, Cursor).
