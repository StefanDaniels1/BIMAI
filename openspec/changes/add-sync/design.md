# Design

## Decisions

- **What is saved:** `.bimai/` (bimai's records; state, log, data and site are gitignored already), `CLAUDE.md`,
  `.claude/agents/`, `.claude/settings.json`, `.mcp.json`, `.gitignore`, and the team's `outputs/`. Files over
  25 MB are skipped and named. Nothing else: models, drawings and the person's own files are theirs to share.
- **Identity:** commits use the person's name from `people.yaml` and `<seat>@users.bimai`, passed per command
  (`git -c user.name=… -c user.email=…`), so bimai never changes git configuration.
- **Sync = save, `pull --rebase`, push.** On a rebase conflict: `rebase --abort` (back to the saved local state,
  nothing lost), report the files and the other author from the remote's last commit on them, exit 1. Push
  rejected because someone pushed meanwhile: pull and push once more. No remote: save only. Network failure:
  "saved here; shared next time".
- **Automatic sync:** the brief hook runs `bimai brief --sync` (sync with a 20-second limit, then the brief, with
  "Updated from the team: N changes" or why not); the `Stop` hook runs `bimai save --share`, which commits
  (fast) and starts the push in a detached background process. `sync.auto: false` turns both off.
- **Safety rails:** `.claude/settings.json` gets `permissions.deny` for `Bash(git push --force*)`,
  `Bash(git push -f*)`, `Bash(git reset --hard*)`, `Bash(git rebase*)`, `Bash(git filter-branch*)`,
  `Bash(git clean -f*)`, `Bash(git checkout -- *)`; bimai's own sync uses only commit, pull --rebase, rebase
  --abort and push.
- **Join from a link:** `bimai join <link>` runs `git clone` into `~/Documents/bimai/<repo>` (or `--into`), then
  prints the folder; the join prompt continues there.

## Risks / Trade-offs

- Commits on every turn make a long history → messages are plain and grouped by kind; history is cheap.
- A person without git installed → a clear message; on Windows bimai points to Git for Windows.
