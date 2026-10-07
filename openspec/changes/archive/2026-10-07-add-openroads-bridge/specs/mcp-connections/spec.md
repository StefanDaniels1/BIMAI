# Spec Delta

## ADDED Requirements

### Requirement: OpenRoads bridge in the catalogue
The catalogue SHALL contain `openroads` (bimai bridge, Windows, no sign-in, read-only, matches the
`openroads` tool, port 27185) with a pinned release, and Bentley's MicroStation MCP server as unavailable
(early access through Bentley). Onboarding SHALL report `openroads` with status `needs-install` when the
bridge isn't installed on Windows.

#### Scenario: Connect
- **WHEN** the bridge is installed and the user runs `bimai connect openroads --yes`
- **THEN** `.mcp.json` contains `openroads` with `http://127.0.0.1:27185/mcp`
