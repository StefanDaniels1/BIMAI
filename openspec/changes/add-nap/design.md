# Design

## Context

- Claude Code (code.claude.com/docs): `claude -p` with `--model haiku`, `--effort` (levels depend on the
  model), `--json-schema` (validated structured output), `--tools ""`, `--no-session-persistence`,
  `--max-budget-usd`, `--permission-prompts none`. Hooks: `UserPromptSubmit` (`prompt`), `PostToolUse`
  (`tool_name`, `tool_input.file_path`, Agent `subagent_type`), `Stop` (`last_assistant_message`),
  `SessionStart` (blocks the first response; no `async`).
- Squad's nap (`packages/squad-cli/src/cli/core/nap.ts`): thresholds 15 KB / 20 KB, keep 5 entries,
  logs 7 days, decisions 30 days, journal file; no model.

## Decisions

- **Agents reason, scripts decide.** Haiku only returns a proposal (JSON: `merge`, `drop`, `keep` with line
  ids and reasons). The script applies only what passes its checks: ids exist, merged lines cite the
  replaced lines' sources, nothing outside the history changes, size goes down. Anything else is ignored.
- **Nothing is lost.** Every removed or replaced line goes to `history-archive.md` with the date of the nap
  and the reason. A history line that is in neither file is a bug (tested).
- **Token estimate** = characters / 4 (no tokenizer dependency); budgets are configurable in
  `.bimai/project.yaml` (`memory.history_tokens`).
- **Daily trigger:** the `SessionStart` hook exits immediately; when due it starts `bimai nap --background`
  as a detached process (Windows: `DETACHED_PROCESS`; elsewhere a new session). A `.bimai/state/nap.json`
  keeps the last run and a lock so two sessions don't nap at once.
- **Session log without a model:** per-session state in `.bimai/state/log/<session>.json` collects the
  turn (question, members, files); `Stop` appends one entry to the day file and clears it. Text is cut with
  the same rules as the voice's spoken text (no code, tables, links).
- **Where the log lives:** `.bimai/log/<seat>/`, **gitignored by default** (questions can contain personal
  remarks); a project can opt in to sharing it (`log.share: true` in `project.yaml`) later.
- **Digests:** weekly (`.bimai/log/<seat>/weeks/2026-W41.md`), a few lines per day, written by Haiku from the
  log entries only; day files older than 30 days are removed once their week has a digest.

- **Log hooks are synchronous** (found in a real run): background hooks can finish out of order on a quick
  turn, and Claude Code cancels them when a headless run ends. `bimai._entry` loads only the log module for
  hook calls, so one takes about 0.06 s instead of 0.35 s.
- **Model:** Claude Code's `haiku` alias with `--effort high`; in the real run it resolved to
  `claude-haiku-5-5` and accepted high effort (one tidy of an 8-line history: about 12 s, cents).

## Risks / Trade-offs

- Haiku's proposal can be poor → it can only shrink and merge with sources, never invent; the diff is shown;
  the archive has everything.
- Headless Claude uses the person's subscription → `--max-budget-usd` cap per nap and only when needed.
