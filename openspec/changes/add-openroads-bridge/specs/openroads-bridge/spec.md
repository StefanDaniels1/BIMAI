# Spec Delta

## ADDED Requirements

### Requirement: OpenRoads bridge server
The bridge SHALL run inside OpenRoads Designer 2023 or newer on Windows, start when OpenRoads loads it,
and serve MCP on `127.0.0.1:27185` (loopback only) with the protocol support of the Civil 3D bridge. It
SHALL never change the drawing. All model access SHALL happen on OpenRoads' main thread.

#### Scenario: Discover
- **WHEN** a client sends `server/discover` while OpenRoads runs with the bridge
- **THEN** the bridge answers with its name, version and read-only tools

### Requirement: Civil tools
The bridge SHALL offer `get_drawing_info`, `list_alignments`, `get_alignment`, `list_profiles`,
`get_profile`, `list_corridors`, `get_corridor`, `list_terrains`, `get_terrain_elevation` and
`list_drainage`, reading the active model's civil data through Bentley's CifNET SDK, with lengths and
stations in the drawing's units and the units named in every result.

#### Scenario: Alignments
- **WHEN** the open drawing has two alignments and the client calls `list_alignments`
- **THEN** both are returned with name, length, start and end station and feature definition

#### Scenario: No drawing
- **WHEN** no drawing is open
- **THEN** every tool returns an error saying to open a drawing

### Requirement: Built on the user's PC
`bimai bridge install openroads` SHALL download the pinned release (SHA-256 checked), find the installed
OpenRoads Designer versions, compile the add-in with the .NET Framework's C# compiler against each found
version's assemblies, install it per user, and register it to load automatically. A failed compile SHALL
name the OpenRoads version and install nothing for it.

#### Scenario: Two versions installed
- **WHEN** OpenRoads Designer 2024 and 2025 are installed
- **THEN** the add-in is compiled and registered for both

#### Scenario: Not installed
- **WHEN** no OpenRoads Designer is installed
- **THEN** the install stops with a message saying so, and nothing is written
