# mcp-connections Specification

## Purpose
Connect a project's AI team to MCP servers, starting with Autodesk's official ones, through one list
(`.mcp.json`), one command (`bimai connect`) and one way to sign in (`bimai auth`), without anyone
handling a token and without a secret ever being written to a file.

## Requirements

### Requirement: Server catalogue
bimai SHALL ship a catalogue of MCP servers. Each entry SHALL state its name, label, vendor, a link to
its official documentation, its authentication model (`none`, `signin` or `key`), its access
(`read-only` or `read-write`), its platforms, its regional endpoints if any, the capabilities it
provides, and the Claude Code configuration to write. The catalogue SHALL contain only servers whose
connection details are confirmed in the vendor's documentation, and at least: Autodesk Product Help,
Revit Public MCP (read-only tools), Autodesk Fusion, Autodesk Fusion Data and InfoWorks Hydraulic
Modeling. A server that exists but that outside clients can't connect to SHALL be listed as
unavailable with the reason and no configuration; the catalogue SHALL list AutoCAD and Civil 3D this
way.

#### Scenario: Catalogue is complete and consistent
- **WHEN** the catalogue is loaded
- **THEN** every available entry has all fields above, every `signin` entry is an `http` server, every unavailable entry has a reason, and every capability provided is a known capability

#### Scenario: Unavailable server
- **WHEN** the user runs `bimai connect autocad-civil3d`
- **THEN** nothing is written, the output gives the reason (only reachable inside Autodesk Assistant), and the exit code is 2

### Requirement: One list in .mcp.json
bimai SHALL keep every server in the project's `.mcp.json`, in Claude Code's format, under
`mcpServers`. Adding or removing a server SHALL leave all other entries and keys in the file unchanged.
bimai SHALL refuse to change a `.mcp.json` that is not valid JSON, and report it.

#### Scenario: Existing servers are kept
- **WHEN** `.mcp.json` already lists a server `my-tool` and the user connects `autodesk-help`
- **THEN** `.mcp.json` lists both, and `my-tool`'s entry is unchanged

### Requirement: bimai connect
`bimai connect` without a server SHALL list every catalogue server with its label, whether it is in
`.mcp.json`, its access, and in plain language how you sign in ("no sign-in needed", "sign in with
your Autodesk account", "needs a key"). `bimai connect <server>` SHALL add the server to `.mcp.json`
and regenerate the team's Claude Code files. It SHALL refuse, with exit code 2 and an explanation, a
server not available on this platform, a local server whose application is not installed, and a
regional server without `--region` when it can't ask. An unknown server SHALL exit with code 2 and list
the catalogue.

#### Scenario: Public server
- **WHEN** the user runs `bimai connect autodesk-help`
- **THEN** `.mcp.json` gets an `http` entry with Autodesk's Product Help URL and no headers, and the output says no sign-in is needed

#### Scenario: Windows-only server on a Mac
- **WHEN** the user runs `bimai connect revit` on macOS
- **THEN** nothing is written, the output explains Revit only runs on Windows, and the exit code is 2

#### Scenario: Regional server
- **WHEN** the user runs `bimai connect hydraulic-modeling --region gbr`
- **THEN** the entry uses the GBR endpoint

### Requirement: Read by default
A `read-write` server SHALL be added only after explicit consent: an interactive yes, or
`--allow-writes`. Adding it SHALL add an `ask` rule `mcp__<server>` to the project's
`.claude/settings.json` permissions, keeping all other settings, so every tool call from that server
waits for the person's approval. Removing the server SHALL remove that rule. The Revit server SHALL
be configured with its read-only tools only.

#### Scenario: Write-capable server needs consent
- **WHEN** the user runs `bimai connect fusion-data --yes` without `--allow-writes`
- **THEN** nothing is written, the output says the server can change data and how to allow it, and the exit code is 2

#### Scenario: Ask rule
- **WHEN** the user runs `bimai connect fusion-data --allow-writes`
- **THEN** `.claude/settings.json` contains `mcp__fusion-data` under `permissions.ask`, and its other settings are unchanged

### Requirement: One way to sign in
`bimai auth login <server>` SHALL start the server's sign-in: for `signin` servers it runs Claude
Code's sign-in (`claude mcp login <server>`), which opens the browser and stores the token in Claude
Code's secure storage; for `key` servers it asks for the key with hidden input and stores it in the OS
keychain. `bimai connect` SHALL offer to sign in right away for `signin` and `key` servers.
`bimai auth logout <server>` SHALL remove the stored credential. `bimai auth status` SHALL list each
server in `.mcp.json` with how it signs in and, for `key` servers, whether a key is stored, never
showing a value. When the `claude` command is not available, sign-in SHALL print the in-session
alternative (`/mcp` in Claude Code) instead of failing.

#### Scenario: Autodesk sign-in
- **WHEN** the user runs `bimai auth login fusion-data`
- **THEN** bimai runs `claude mcp login fusion-data` and stores nothing itself

#### Scenario: Key server
- **WHEN** the user runs `bimai auth login my-api` for a `key` server and types a key
- **THEN** the key is stored in the OS keychain, the key is not echoed, and no file in the project contains it

#### Scenario: Status never shows secrets
- **WHEN** a key is stored and the user runs `bimai auth status`
- **THEN** the output says the key is stored, and does not contain the key

### Requirement: Keys reach the server without touching files
A `key` server's `.mcp.json` entry SHALL use a `headersHelper` that runs `bimai auth headers`, which
reads the key from the OS keychain for the server named in `CLAUDE_CODE_MCP_SERVER_NAME` and prints the
header JSON on stdout. It SHALL print nothing to stdout and exit non-zero when no key is stored.
`bimai connect --custom <name> --url <url> --auth key [--header <name>] [--scheme bearer|raw]` SHALL add
such a custom server.

#### Scenario: Header from the keychain
- **WHEN** a key `abc` is stored for `my-api` with scheme `bearer` and Claude Code runs the helper
- **THEN** stdout is `{"Authorization": "Bearer abc"}`

#### Scenario: Missing key
- **WHEN** no key is stored for `my-api`
- **THEN** the helper writes nothing to stdout and exits non-zero

### Requirement: bimai disconnect
`bimai disconnect <server>` SHALL remove the server from `.mcp.json`, remove its `ask` rule, remove its
stored credential, and regenerate the team's Claude Code files. A server not in `.mcp.json` SHALL exit
with code 2.

#### Scenario: Disconnect
- **WHEN** the user runs `bimai disconnect fusion-data`
- **THEN** `.mcp.json` no longer lists it and `permissions.ask` no longer contains `mcp__fusion-data`
