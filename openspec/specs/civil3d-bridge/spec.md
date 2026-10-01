# civil3d-bridge Specification

## Purpose
A bimai add-in inside the user's running Civil 3D that exposes the open drawing to AI tools through a
local, read-only MCP server, so the bimai team can query alignments, profiles, surfaces, corridors and
pipe networks with evidence.

## Requirements

### Requirement: Loads in supported Civil 3D versions
The add-in SHALL be delivered as one Autodesk plug-in bundle containing a .NET 8 build for Civil 3D
2025 and 2026 (series R25.0–R25.1) and a .NET 10 build for Civil 3D 2027 (series R26.0), each declared
for platform `Civil3D` only and loaded at startup. It SHALL depend only on the .NET runtime and the
Civil 3D/AutoCAD assemblies that Civil 3D provides (no ASP.NET Core, no third-party packages).

#### Scenario: Bundle manifest
- **WHEN** the bundle's PackageContents.xml is read
- **THEN** it declares one component per build with Platform `Civil3D`, the series ranges above, and module paths that exist in the bundle

### Requirement: Local MCP server
When Civil 3D loads the add-in, it SHALL start an MCP server using the Streamable HTTP transport at
`http://127.0.0.1:<port>/mcp` (default port 27184, overridable with the `BIMAI_CIVIL3D_PORT`
environment variable), listening on loopback addresses only. It SHALL serve both protocol eras: modern
stateless requests (2026-07-28: protocol version in `_meta`, `server/discover`, required
`MCP-Protocol-Version`/`Mcp-Method`/`Mcp-Name` headers that must match the body, else 400 with
`-32020`; unsupported versions 400 with `-32022` and the supported list) and legacy clients that send
`initialize` (2025-03-26, 2025-06-18, 2025-11-25, negotiated). It SHALL answer `tools/list` and
`tools/call` with `application/json` responses, notifications with 202, and GET and DELETE with 405. A failure to start
(for example a port in use) SHALL NOT disrupt Civil 3D; it SHALL be logged and shown by the status
command.

#### Scenario: Legacy initialize
- **WHEN** a client posts an `initialize` request for 2025-06-18
- **THEN** the server returns its name, version, protocol version 2025-06-18 and the tools capability

#### Scenario: Modern discovery
- **WHEN** a client posts `server/discover` with `_meta` protocol version 2026-07-28 and matching headers
- **THEN** the result lists the supported versions and the tools capability

#### Scenario: Header mismatch
- **WHEN** a modern `tools/call` has `Mcp-Name: list_layers` but calls `get_drawing`
- **THEN** the server answers 400 with error code -32020 and runs no tool

#### Scenario: Notification
- **WHEN** a client posts `notifications/initialized`
- **THEN** the server answers 202 with no body

#### Scenario: Port in use
- **WHEN** the port is already taken
- **THEN** Civil 3D keeps working and `BIMAIBRIDGE` reports that the server is not running and why

### Requirement: Local-only access
The server SHALL reject with 403 any request whose `Origin` header is present and is not a loopback
origin for its port, any request whose `Host` header is not `127.0.0.1`, `localhost` or `[::1]` with
its port, and any connection from a non-loopback address. Request bodies over 4 MiB SHALL be rejected
with 413.

#### Scenario: Browser on another site
- **WHEN** a request arrives with `Origin: https://evil.example`
- **THEN** it is rejected with 403 and no tool runs

#### Scenario: DNS rebinding
- **WHEN** a request arrives with `Host: evil.example:27184`
- **THEN** it is rejected with 403

### Requirement: Safe execution inside Civil 3D
Every tool SHALL run on Civil 3D's main thread, only when Civil 3D is quiescent (no command, script
or ARX command active), with the active document locked for reading without prompting, inside a
transaction, and SHALL NOT modify the drawing. When Civil 3D is busy, no drawing is open, or a call
takes longer than 30 seconds, the tool SHALL return an MCP tool error with a plain-language message
instead of waiting indefinitely. No exception SHALL escape into Civil 3D.

#### Scenario: Command running
- **WHEN** a tool is called while the user is in the middle of a command
- **THEN** the result is a tool error saying Civil 3D is busy and to finish the command first

#### Scenario: No drawing
- **WHEN** a tool is called with no drawing open
- **THEN** the result is a tool error saying no drawing is open

### Requirement: Read-only tools
The server SHALL offer these tools, each marked read-only, with JSON input schemas, numeric values in
drawing units, and results as JSON text plus structured content:
`get_drawing` (file, units, coordinate system, object counts), `list_layers`, `count_objects` (by
object type, optionally per layer), `list_alignments`, `get_alignment` (with its profiles),
`alignment_point` (station and offset to coordinates), `alignment_station` (coordinates to station and
offset), `profile_elevations`, `list_surfaces`, `surface_elevations`, `list_corridors`,
`list_pipe_networks` and `get_pipe_network`. Pipe results SHALL NOT include derived invert levels. Lists SHALL be capped with a `limit` and report when they are truncated. A name
that doesn't exist SHALL produce a tool error listing the available names. Points outside a surface or
stations outside an alignment SHALL be reported per point, not fail the whole call.

#### Scenario: Unknown alignment
- **WHEN** `get_alignment` is called with a name that doesn't exist
- **THEN** the tool error lists the alignments in the drawing

#### Scenario: Point outside a surface
- **WHEN** `surface_elevations` gets one point inside and one outside the surface
- **THEN** the first has an elevation and the second is marked outside

### Requirement: Status and troubleshooting
The add-in SHALL provide a `BIMAIBRIDGE` command that prints whether the server is running, its
address, the add-in version, and the last error; and SHALL log startup, errors and each tool call
(name and duration, never drawing contents) to `%LOCALAPPDATA%\bimai\civil3d-bridge.log`, keeping
the file under 1 MiB.

#### Scenario: Status
- **WHEN** the user types `BIMAIBRIDGE` while the server runs
- **THEN** the command line shows the address `http://127.0.0.1:27184/mcp` and the add-in version

### Requirement: Build and install
The repository SHALL contain a build script that produces the bundle with both builds, and an install
script that copies it to `C:\Program Files\Autodesk\ApplicationPlugins\bimai-civil3d.bundle` (which
Civil 3D always trusts), requiring administrator rights, plus an uninstall script. CI SHALL build the
add-in for both .NET versions and run the protocol tests.

#### Scenario: CI
- **WHEN** a pull request changes the bridge
- **THEN** CI compiles both builds against Autodesk's packages and runs the protocol tests
