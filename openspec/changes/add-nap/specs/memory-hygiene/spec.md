# Spec Delta

## Purpose
Keep what every team member reads at the start of a task small and current, without losing anything.

## ADDED Requirements

### Requirement: Budgets
`bimai nap --dry-run` SHALL report, per team member and position, the estimated tokens of what it reads at
the start (its history) and the budget (default 2,000 tokens, `memory.history_tokens` in project.yaml), and
what a nap would change. CI SHALL keep every role charter within a fixed token budget.

#### Scenario: Over budget
- **WHEN** a history is 3,000 tokens and the budget is 2,000
- **THEN** the dry run marks it over budget and lists the lines a nap would archive

### Requirement: Nap, script part
`bimai nap` SHALL remove exact duplicate lines and lines tied to reversed decisions, and move the oldest
lines over budget to `history-archive.md` next to the history, with the date and the reason. Every line
SHALL end up in the history or the archive.

#### Scenario: Nothing lost
- **WHEN** a nap runs on a history over budget
- **THEN** every original line is in the history or in the archive

### Requirement: Nap, Haiku part
When a history is still over budget, or weekly, the nap SHALL ask Claude Code headless with Haiku (high
effort where supported, structured output, no tools, a cost cap) for a proposal of merges, drops and stale
lines with reasons, and SHALL apply only proposals that pass its checks: the lines exist, a merged line
cites the sources of the lines it replaces, and the history gets smaller. Personal remarks SHALL be removed.
Without Claude Code, the nap SHALL do the script part only and say so.

#### Scenario: Invented fact refused
- **WHEN** Haiku proposes a merged line without the sources of the lines it replaces
- **THEN** that proposal is not applied and the original lines stay

### Requirement: Daily nap
`bimai init` and `bimai team` SHALL add a `SessionStart` hook running `bimai nap --if-due`, which SHALL
return immediately and, when 24 hours have passed since the last nap and no nap is running, start one in
the background.

#### Scenario: Not due
- **WHEN** the last nap was two hours ago
- **THEN** `bimai nap --if-due` exits at once without starting anything
