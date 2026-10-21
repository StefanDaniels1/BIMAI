# Proposal

## Why

Several people can now work in one project, but they still share it with git themselves. Most BIM
professionals don't use git and shouldn't have to (ARCHITECTURE §8.6, "git without git"). bimai should save and
share their work, and bring in their colleagues' work, without them seeing a git command, and without ever
losing anything.

## What Changes

- **`bimai save`**: commits what bimai and the team produced (bimai's project files, the team's outputs) with a
  plain message ("Joris saved: 1 decision, 2 outputs"), under the person's name. Never the person's own model
  files or other files bimai doesn't own; large files are skipped and named.
- **`bimai sync`**: saves first, then brings in the team's changes and shares yours (pull with rebase, push).
  If a real conflict happens, nothing is lost: bimai stops the update, keeps your version and says in plain
  words which file and whose change it is. No remote: saved on this computer only. Offline: shared next time.
- **Automatic:** at the start of a session, the seat brief first syncs (so "what's new" includes your
  colleagues' latest work) and says how many changes came in; at the end of each turn, bimai saves and shares
  in the background. A project can switch this off (`sync: { auto: false }`).
- **`bimai join <link>`**: clones the project (into Documents/bimai/<name>) and continues with joining, so the
  join prompt no longer runs git itself.
- **Safety rails:** the team's agents may not run destructive git commands (force push, hard reset, history
  rewrites): `deny` rules in the project's shared settings. bimai itself never force-pushes or resets.
- **Docs:** "Saving and sharing" (available), join page and prompt updated.

## Non-goals

- Review of changes to shared rules (pull requests for ownership/project changes): later.
- `bimai restore` (bringing back an earlier version): later.

## Capabilities

### New Capabilities
- `sync`: save, sync, automatic sync, join from a link, safety rails.

## Impact

- New `cli/bimai/sync.py`; `cli.py`; `sessionlog.py` (hooks), `collab.py` (brief syncs first), `claude.py`
  (deny rules), join; tests with real git (a bare remote and two clones); docs and the join prompt.
