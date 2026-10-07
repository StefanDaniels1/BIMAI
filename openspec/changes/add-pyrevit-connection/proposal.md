# Proposal

## Why

Most Revit users today run Revit 2024–2026, where Autodesk's Revit MCP server (Revit 2027.2, Tech
Preview) isn't available. pyRevit 7.0 (released 2026-10-06), free and widely used, ships an agent
runtime: an MCP server over stdio (`pyrevit mcp`) that lets Claude Code read a live Revit model
(`get_context`, `inspect_elements`, `run_query`, `capture_view`, …) and, after approval in Revit,
change it (`run_modify`). Revit users should get it with the same one-step connection as Civil 3D.

## What Changes

- **Catalogue server `pyrevit`** (vendor pyRevit Labs, Windows, no sign-in, matches the `revit` tool):
  `pyrevit.exe mcp` from the per-user install (`%APPDATA%\pyRevit-Master\bin`) or the all-users install
  (`%ProgramFiles%\pyRevit-Master\bin`), needing pyRevit 7.0 or newer.
- **Read by default, per tool.** A server can name its `write_tools`. Connected read-only (the default),
  bimai adds a `deny` rule for each (`mcp__pyrevit__run_modify`), so the team can read but never change
  the model. With `--allow-writes` (explicit consent) they become `ask` rules instead, on top of
  pyRevit's own approval inside Revit. Removing the server removes the rules.
- **One-step install of the newest pyRevit.** `bimai connect pyrevit` offers to install the pinned
  pyRevit release (7.0.0, the signed per-user installer, SHA-256 checked, silent, no administrator
  rights for pyRevit itself, Revit must be closed), and to switch on pyRevit's agent host (`pyrevit configs agent
  enable`, off by default), each after a yes. An older pyRevit (< 7.0) is reported with the update offer.
- **Prerequisites in one permission prompt.** pyRevit needs Microsoft's .NET 8 and .NET 10 Desktop
  Runtimes (machine-wide; its installer would otherwise ask Windows' permission once per runtime, without
  explanation). bimai checks which are missing and installs them first, from Microsoft's official
  installers with pinned SHA-512, in one elevated step it explains beforehand. pyRevit's own installer
  then runs without any prompt. WebView2 (per user) is left to pyRevit's installer.
- **Onboarding:** choosing Revit gives the pyRevit connection a status like Civil 3D (`ready`,
  `needs-install`, `other-platform`), so the guided flow offers it.
- **Docs:** a pyRevit guide (what it can do, read-only vs. changes, why Revit must be closed, how to
  update), and the connections page.

## Non-goals

- pyRevit's own `pyrevit mcp install claude` (it writes to user or project scope directly); bimai keeps
  one list, `.mcp.json`, with the same entry.
- Changing pyRevit's agent policy (it stays `ask`, pyRevit's default).
- Following new pyRevit releases automatically: the pin moves with bimai releases.

## Capabilities

### Modified Capabilities
- `mcp-connections`: pyRevit server, per-tool read/write rules, installer for a vendor app.

## Impact

- `catalogue/servers.yaml`, `connections.py` (`{APPDATA}` in variants, `write_tools`, version check),
  a small `apps.py` (download, verify, silent install, enable host), `cli.py`; tests with a fake Windows.
- Docs: new `guides/pyrevit.mdx`, `guides/connections.mdx`.
