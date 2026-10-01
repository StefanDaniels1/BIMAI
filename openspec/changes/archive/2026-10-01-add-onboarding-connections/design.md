# Design

## Decisions

- **One status function** in `connections.py`: `connection_status(server, platform)` reuses
  `server_config` and maps its outcome (config → `ready`, `BridgeMissing` with a release → `needs-install`,
  "only works on" → `other-platform`, `unavailable` → `unavailable`, otherwise `needs-app`). No second set
  of platform rules.
- **Only servers without sign-in** (`auth: none`) are connected by init; sign-in servers need a browser and
  stay with `bimai connect`. Today that means Civil 3D and Revit.
- **No installs in init.** Installing a bridge triggers Windows' permission prompt; that deserves its own
  explicit yes, asked by Claude (guided) or by init's existing interactive offer (terminal).
- **Choosable everywhere.** A Mac user can still pick Civil 3D: the team (Model Checker) and the shared
  project are right for Windows colleagues; only the connection waits.

## Risks / Trade-offs

- A `ready` server in `.mcp.json` that isn't running (Civil 3D closed) shows as failed in Claude Code
  → the final message says the bridge starts with Civil 3D, as `bimai connect` already does.
