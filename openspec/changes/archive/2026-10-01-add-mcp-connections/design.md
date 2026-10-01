# Design

## Context

Autodesk documents three authentication models for its MCP servers (help.autodesk.com, ADSKMCP
"Authentication and Access"): **none** (local servers inside a desktop app, and public servers),
**Autodesk account sign-in** (cloud servers; MCP authorization spec with Client ID Metadata Documents,
supported by Claude Code) and **host-managed** (only inside an Autodesk product). Claude Code already
does the hard part for sign-in servers: browser sign-in, token storage in the OS keychain, refresh
(`/mcp`, `claude mcp login`). It also offers `headersHelper` for other schemes, `permissions.ask` rules,
per-subagent `mcpServers`, and an approval prompt for project `.mcp.json` servers.

ARCHITECTURE.md plans a gateway (§8.1) in front of all servers and a strict secrets rule (§11): secrets
only in the OS keychain, never in `.mcp.json`, never visible to the agent. This change delivers the
connections now, without the gateway, while keeping that rule.

## Verified servers (October 2026, from Autodesk's documentation)

| Server | Runs | Auth | Access | Connection |
|---|---|---|---|---|
| Product Help | Autodesk cloud | none | read-only | `https://developer.api.autodesk.com/knowledge/public/v1/mcp` |
| Revit Public MCP (Tech Preview) | local, Windows, Revit 2027.2 + add-on | none | read-only tools | stdio: `…\Revit 2027 MCP Server Read-Tools Technical Preview\Autodesk.RevitMcpServer.Stdio.exe --ManageConfigurationWithAutodeskRevitPluginInstaller=true`, or the Write-Tools install with `--tool-permission=StableReadOnly` |
| Fusion | local, inside Fusion | none | read-write | `http://127.0.0.1:27182/mcp` (port configurable in Fusion) |
| Fusion Data | Autodesk cloud | sign-in | read-write (project admin) | `https://developer.api.autodesk.com/fusion/mcp` |
| InfoWorks Hydraulic Modeling | Autodesk cloud, per region | sign-in | read-write (starts analyses) | `https://api.aps.{usa,gbr,aus}.autodesk.com/water/modeling-mcp/mcp` |

Listed as unavailable: AutoCAD and Civil 3D MCP (host-managed, Autodesk Assistant only; no connection
for outside clients is documented). The expected route for Civil 3D is bimai's own local bridge, a
`desktop-bridge` connector on the Civil 3D API (ARCHITECTURE.md §7.6, §9), as a separate change. Not
included: Fusion Compute (not reviewed yet). Re-check each entry against the vendor page during implementation.

## Decisions

- **`.mcp.json` is the one list,** not a bimai file that generates it. People already know it, Claude
  Code reads it natively, and a second source of truth would drift. bimai only edits the entries it is
  asked to add or remove. When the gateway comes, it becomes one more entry that fronts the others.
- **Authentication is delegated, never re-implemented.** Sign-in servers: Claude Code's OAuth (CIMD)
  stores tokens in its secure storage; bimai never sees them. Key servers: the key goes into the OS
  keychain via `keyring` (service `bimai-mcp`, username = server name) and reaches the server through
  `headersHelper: "bimai auth headers --header <name> --scheme <bearer|raw>"`. The options contain no
  spaces, so the same string works in the Windows and Unix shells Claude Code uses for helpers.
  Nothing secret is ever in `.mcp.json`, `.bimai/`, logs or output, which `bimai validate` enforces.
- **New dependency: `keyring`.** The standard cross-platform OS keychain library (Windows Credential
  Manager, macOS Keychain, Linux Secret Service), as §11.3 requires. Only imported when a key is used.
- **The human gate for write-capable servers is Claude Code's `permissions.ask`.** `mcp__<server>`
  matches every tool of that server and always prompts. It is coarse (read calls ask too), but it is a
  real gate today; the gateway later narrows it to write tools.
- **Least privilege via subagent `disallowedTools`,** derived from catalogue capabilities and role
  `requires`/`uses`: every server a role doesn't need is listed as `mcp__<server>`. Claude Code
  documents this; it doesn't define what an empty `mcpServers: []` means, so that field isn't used.
  The Coordinator, as the main session, sees all servers.
- **Local servers in the shared `.mcp.json`.** A teammate on a Mac sees the Revit entry fail to start
  in `/mcp`; that is visible and harmless, and keeps one list. The Revit path is detected on Windows
  at connect time (Read-Tools install first, then Write-Tools with the read-only flag).
- **The `claude` CLI is optional.** Sign-in calls `claude mcp login`; without the CLI, bimai prints the
  `/mcp` alternative. Login state is not parsed from Claude Code's output (not a stable interface).
- **Declared tools are stored** in `seat.yaml` (`tools:`) at init, so the Connections section can say
  what is declared but not connected after later regenerations.

## Risks / Trade-offs

- Autodesk servers are Technical Previews: endpoints and flags may change → the catalogue is data with
  doc links; a change is a one-line edit plus its test.
- Verified with Claude Code 2.1.286: the `claude mcp` CLI doesn't know project servers from `.mcp.json`
  until they are approved in an interactive session ("awaiting approval — run `claude` in this
  directory"). So right after `bimai connect`, sign-in goes through the session: approve the servers,
  then `/mcp` → Authenticate. `bimai auth login` tries the CLI first and prints exactly those steps
  when it can't.
- `ask` rules prompt on read calls of write-capable servers too → accepted until the gateway.
- Verified in Claude Code's permissions docs (October 2026): `mcp__<server>` matches every tool of a
  server; rules are evaluated deny → ask → allow, so an ask rule wins over any allow rule; ask rules
  still prompt in auto mode. `bypassPermissions` mode skips prompts, so the gate doesn't hold there:
  the docs tell people not to use that mode with read-write servers.
