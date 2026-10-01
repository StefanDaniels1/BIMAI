# Proposal

## Why

The team is configured, but it can't reach any tool: a test showed the Issue Manager correctly
reporting it has no data. Autodesk now ships official MCP servers, and Claude Code can connect to
them. Setting them up by hand means editing JSON, install paths and sign-ins: exactly what BIM
professionals shouldn't have to do. Autodesk's sign-in servers use the MCP
authorization flow (CIMD), which Claude Code supports: the token goes into the OS keychain and no
one ever handles a key.

Implements a first, gateway-less slice of ARCHITECTURE.md §7.6 (connector catalogue) and §11
(secrets), ahead of the gateway (§8.1).

## What Changes

- **One list:** the project's `.mcp.json` holds every MCP server, in Claude Code's own format. It's
  shared with the team and never contains a secret.
- **A catalogue of verified Autodesk servers** shipped with bimai, each with its authentication model
  (none, Autodesk sign-in or key), access (read-only or read-write), platforms, regions and the
  capabilities it provides: Product Help (public), Revit Public MCP read-only (local, Windows),
  Fusion (local), Fusion Data and InfoWorks Hydraulic Modeling (cloud, Autodesk sign-in).
- **Read by default:** a read-write server is added only after explicit consent, and gets a Claude
  Code `ask` rule, so every one of its tool calls waits for the person's approval.
- **`bimai connect`** lists the catalogue with status; `bimai connect <server>` adds it and, for
  sign-in servers, opens the Autodesk sign-in right away; `bimai disconnect <server>` removes it.
- **One way to sign in:** `bimai auth login|status|logout <server>`. Sign-in servers use Claude Code's
  browser sign-in; servers that need a key (custom servers) get it once through a hidden prompt into
  the OS keychain, and Claude Code fetches it at connect time through a helper. bimai never prints,
  logs or writes a secret.
- **The team uses its connections:** each subagent only gets the servers that serve its role (least
  privilege), and the `CLAUDE.md` block lists what the team can actually reach and what is only
  declared.
- `bimai init` adds Product Help for everyone; `bimai validate` rejects literal secrets in `.mcp.json`.
- Docs: a "Connections" guide and the command reference.

## Non-goals

- The gateway, evidence logging and write gates (§8.1, hooks change).
- Revit write tools (model changes need the evidence trail of the hooks change first).
- AutoCAD and Civil 3D MCP: it is only reachable inside Autodesk Assistant.
- Service identities for unattended runs (§11.5).

## Capabilities

### New Capabilities
- `mcp-connections`: the server catalogue, `.mcp.json` management, `bimai connect`/`disconnect`, `bimai auth`, and how connections feed the team.

### Modified Capabilities
- `team-configuration`: subagents get only their role's servers; the `CLAUDE.md` block gains a Connections section.
- `workspace-init`: `bimai init` adds Autodesk Product Help to `.mcp.json`.
- `workspace-validation`: `.mcp.json` is checked for literal secrets.

## Impact

- New `cli/bimai/connections.py`, catalogue `cli/bimai/catalogue/servers.yaml`, tests.
- New dependency `keyring` (OS keychain access on Windows, macOS, Linux).
- Calls the `claude` CLI for sign-in (`claude mcp login/logout`).
- Docs and ARCHITECTURE.md §7.6, §8.1, §11.3.
