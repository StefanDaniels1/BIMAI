# Spec Delta

## ADDED Requirements

### Requirement: Connections for chosen tools
For every chosen tool that matches a server in the catalogue, `bimai init` SHALL determine the
connection status on this computer: `ready`, `needs-install` (a bimai bridge with a published release on a
supported platform), `needs-app` (a vendor add-on that isn't installed), `other-platform` or
`unavailable`, with a plain-language sentence and, only where it works on this computer, the command to
run. The dry run with `--json` SHALL include this plan. When writing, init SHALL add the `ready` servers
to `.mcp.json` (with or without `--yes`) and SHALL NOT install anything. The final output SHALL list the
status of every chosen tool's connection and SHALL NOT suggest a command that can't work on this computer.

#### Scenario: Civil 3D on macOS
- **WHEN** a modeller chooses Civil 3D on macOS
- **THEN** the plan says `other-platform` with "Windows only" and no command, nothing is added to `.mcp.json`, and the output doesn't suggest `bimai connect civil3d`

#### Scenario: Civil 3D bridge missing on Windows
- **WHEN** a modeller chooses Civil 3D on Windows without the bridge installed
- **THEN** the plan says `needs-install` with the command `bimai connect civil3d --install --yes`, and init installs nothing itself

#### Scenario: Ready server connected by init
- **WHEN** a chosen tool's server can be configured on this computer (e.g. the Civil 3D bridge is installed)
- **THEN** init adds it to `.mcp.json`, also with `--yes`
