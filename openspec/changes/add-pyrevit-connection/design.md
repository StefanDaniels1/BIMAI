# Design

## Context

pyRevit 7.0's agent runtime: an in-Revit host (off by default, `[agent] enabled`) plus `pyrevit mcp`, an
MCP server over stdio. Its own registration for Claude Code is `claude mcp add --scope project pyrevit
-- "<pyrevit.exe>" mcp`, i.e. `{"type":"stdio","command":"<pyrevit.exe>","args":["mcp"]}`. Installers:
`pyRevit_<v>_signed.exe` (per user, `%APPDATA%\pyRevit-Master`, no admin, adds `bin` to the user PATH)
and `..._admin_signed.exe` (all users, `%ProgramFiles%\pyRevit-Master`). Both are Inno Setup. pyRevit's
host enforces its own contract (queries roll back; changes need approval in Revit by default).

## Decisions

- **bimai's `.mcp.json` entry equals pyRevit's own**, so `pyrevit mcp uninstall` and bimai agree.
- **Deny `run_modify` by default** instead of an `ask` rule on the whole server: reading stays smooth
  (no approval per query), and changing the model needs two explicit consents (bimai, then Revit).
- **Pinned per-user installer** (version, URL, SHA-256 from GitHub's release digest) in `servers.yaml`,
  like the Civil 3D bridge: no admin prompt at all, silent (`/VERYSILENT /SUPPRESSMSGBOXES
  /NORESTART`). A new pyRevit release means a bimai patch release with a new pin.
- **Version check** by running `pyrevit.exe --version` (stdlib `subprocess`, 10 s timeout); 7.0+ needed.
- **Enabling the host** changes pyRevit's user config, so it is asked separately and explained.

- **Prerequisites first, in one prompt.** pyRevit's installer (Inno Setup + CodeDependencies) installs
  missing .NET 8/10 Desktop Runtimes itself, each triggering its own UAC prompt, and requires at least
  8.0.23 and 10.0.2. bimai detects them via `%ProgramFiles%\dotnet\shared\Microsoft.WindowsDesktop.App\<v>`
  (the desktop runtime installer also installs `Microsoft.NETCore.App`), downloads Microsoft's installers
  (pinned: 8.0.31, 10.0.12, SHA-512 from Microsoft's releases.json), and runs them `/install /quiet
  /norestart` from one elevated PowerShell, like the Civil 3D bridge install. Then pyRevit's checks pass
  and its installer runs unelevated without prompts.

## Risks / Trade-offs

- pyRevit's agent runtime is experimental (validated on Revit 2024 and 2025) → the guide says so, and
  bimai connects it read-only by default.
- Silent install flags are untested on a real PC → Windows CI runs the installer for real
  (as for the Civil 3D bridge), then `pyrevit --version` and `pyrevit configs agent enable`.
