# Proposal

## Why

Every team member reads its whole history at the start of every task, and nothing limits its size. After
a few months that costs tokens on every call, and old conventions sit next to their corrections. Squad
solves this with `squad nap`: a script that archives by size and age (15 KB histories, keep the last 5
entries, logs pruned after 7 days). It is safe but blunt: a key convention from month one goes because it
is old. People also want to ask "what did we do yesterday?" or "last week?", which needs a session log
that costs nothing until someone asks.

## What Changes

- **Budgets.** Each history has a budget (default 2,000 tokens, about 8 KB); `bimai nap --dry-run` shows
  what every team member reads at the start, in tokens. CI keeps every role charter under a budget.
- **`bimai nap`: the script part (always, free).** Checks the line format (date, source), removes exact
  duplicates and lines tied to reversed decisions, and moves what is over budget to
  `history-archive.md` next to the history (not read by default; nothing is deleted).
- **`bimai nap`: the Haiku part (when a history is over budget, or weekly).** Claude Code in headless mode
  (`claude -p --model haiku --effort high`, structured JSON output, no tools, a cost cap) *proposes*
  merges, contradictions and stale lines with a reason each. The script *decides*: a merged line must name
  the lines it replaces and keep their sources, so no new facts appear; personal remarks are always
  removed; the result is shown as a diff and the archive keeps everything.
- **Daily, without a scheduler.** A `SessionStart` hook runs `bimai nap --if-due`: it checks in
  milliseconds whether a nap is due (24 hours since the last one) and, if so, starts it in the background.
  Nothing runs on days nobody works.
- **Session log.** Hooks record each turn deterministically, without a model: time, the question, the
  team members who worked on it, the files written, and a short version of the answer, in
  `.bimai/log/<seat>/YYYY-MM-DD.md`. Agents don't read it at the start; it is read only when asked.
- **`bimai log [--since yesterday|7d|<date>]`** prints the log (and weekly digests) for a period; the
  Coordinator's routing says to use it for questions about earlier work. The nap writes a short weekly
  digest with Haiku; daily files older than 30 days are folded into the digests.

## Non-goals

- Reading or summarizing Claude Code's own transcripts (they stay where Claude Code keeps them).
- A scheduler (cron, Task Scheduler) or a background service.

## Capabilities

### New Capabilities
- `memory-hygiene`: budgets, nap (script and Haiku), daily trigger.
- `session-log`: logging hooks, `bimai log`, digests.

## Impact

- New `cli/bimai/nap.py`, `cli/bimai/sessionlog.py`; `cli.py`; `claude.py` (routing rule, hooks in the
  project settings written by `bimai init`/`bimai team`); tests with a fake `claude`.
- Docs: a "Memory and history" guide; commands reference.
