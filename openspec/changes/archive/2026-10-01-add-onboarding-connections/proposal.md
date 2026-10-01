# Proposal

## Why

A user test on macOS showed a dead end: the interview offered Civil 3D, the person picked it, and the
final message told them to run `bimai connect civil3d`, which then failed with "only works on Windows".
Nothing said so up front. On Windows it isn't seamless either: the guided flow runs `bimai init --yes`,
which skips the bridge offer, so choosing Civil 3D never connects it. Choosing a tool should connect it
where that's possible, and say plainly where it isn't.

## What Changes

- **Connection plan for chosen tools.** For every chosen tool that matches a catalogue server, bimai
  works out its status on this computer: `ready` (can be connected now), `needs-install` (a bimai bridge
  that bimai can install), `needs-app` (an Autodesk add-on that isn't installed), `other-platform` (e.g.
  Civil 3D on macOS) or `unavailable` (no way for Claude Code to connect yet). The dry run (`--json`)
  includes this plan, with a plain sentence and the command for each.
- **Init connects what is ready**, also with `--yes`: those servers go into `.mcp.json` straight away. It
  never installs anything without a separate yes (a bridge install needs Windows' permission).
- **Honest options in the interview.** A tool whose connection can't work on this computer says so in
  its option description (e.g. "Windows only: your team connects to it on a Windows PC"). It can still be
  chosen: the project may be shared with Windows colleagues.
- **The final message** lists each chosen tool's connection status in plain words and gives commands only
  where they work on this computer.
- **The start prompt:** for a `needs-install` bridge, Claude asks with the question tool whether to
  install it now (explaining Windows' permission message) and runs `bimai connect <server> --install --yes`
  on yes.
- Docs: new-project page and the Civil 3D bridge guide.

## Non-goals

- Connecting sign-in servers (ACC, Fusion data) during onboarding; they stay with `bimai connect`.
- Running the bridge on macOS (Civil 3D is Windows-only).

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `workspace-init`: connection plan and connecting ready servers.
- `guided-onboarding`: platform notes on tool options; the prompt offers bridge installs.

## Impact

- `cli/bimai/init.py` (connection plan, `.mcp.json`), `cli.py` (init output, `--json`), `interview.py`
  (option descriptions), `connections.py` (status function); tests.
- `docs/lib/prompts.ts`, `docs/content/docs/start/new-project.mdx`, the Civil 3D bridge guide.
