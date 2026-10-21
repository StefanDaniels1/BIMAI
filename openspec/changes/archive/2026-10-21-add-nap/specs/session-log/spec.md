# Spec Delta

## Purpose
Let people ask what the team did yesterday or last week, from a log that costs nothing until it is read.

## ADDED Requirements

### Requirement: Session log
Hooks SHALL record every turn in `.bimai/log/<seat>/YYYY-MM-DD.md` without a model: the time, the question
(shortened), the team members that worked on it, the files written, and a short version of the answer
(no code, tables or links). The log SHALL be gitignored unless the project opts in. No team member SHALL
read it at the start of a task.

#### Scenario: One turn
- **WHEN** the person asks for a model check, the Model Checker runs and a report file is written
- **THEN** the day file gets one entry with the time, the question, "Model Checker", the report's path and the start of the answer

### Requirement: bimai log
`bimai log` SHALL print the entries and weekly digests for a period (`--since yesterday`, `--since 7d`,
`--since <date>`, optionally `--until`), newest last, and the Coordinator's routing SHALL say to use it for
questions about earlier work.

#### Scenario: Last week
- **WHEN** the person asks "what did we do last week?"
- **THEN** the Coordinator runs `bimai log --since 7d` and answers from its output

### Requirement: Weekly digests
The nap SHALL write a short digest per finished week from that week's log entries (with Haiku when
available), and SHALL remove day files older than 30 days only once their week has a digest.

#### Scenario: Old days
- **WHEN** a day file is 40 days old and its week has a digest
- **THEN** the day file is removed and `bimai log` for that week shows the digest
