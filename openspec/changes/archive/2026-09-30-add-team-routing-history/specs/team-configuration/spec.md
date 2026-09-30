# Spec Delta

## Purpose
How a seat's team becomes Claude Code configuration: a routing table the Coordinator follows, a
history per position that agents learn in, and `bimai team` to regenerate it after the team changes.

## ADDED Requirements

### Requirement: Generated routing table
Whenever bimai writes a seat's Claude Code configuration (`bimai init` or `bimai team`), the
`CLAUDE.md` block SHALL contain a routing table with one row per team member, the Coordinator
included, giving the work it handles and two example requests, taken from the role catalogue. The
block SHALL also contain these routing rules: quick facts from the project files are answered by the
Coordinator directly; every task has exactly one accountable member, named to the person; work no
member covers is done by the Coordinator, which says so. When the Scribe is on the team, a rule SHALL
say that decisions and actions from meetings are recorded by the Scribe. The same team SHALL always
produce the same table and rules.

#### Scenario: Table matches the team
- **WHEN** the team is Coordinator, Model Checker and Scribe
- **THEN** the routing table has exactly those three rows, each with its work and two examples

#### Scenario: Scribe rule only with a Scribe
- **WHEN** the team has no Scribe
- **THEN** the block contains no rule about the Scribe

### Requirement: History per position
For every team member and every position the seat holds, bimai SHALL ensure
`.bimai/positions/<position>/agents/<role>/history.md` exists, creating it from a template naming the
project, position and role when missing. It SHALL NOT overwrite or delete an existing history file,
also not when a member is removed.

#### Scenario: Created on init
- **WHEN** `bimai init` writes a team with the Model Checker for position `bim-coordinator`
- **THEN** `.bimai/positions/bim-coordinator/agents/model-checker/history.md` exists

#### Scenario: Existing history is kept
- **WHEN** a history file already contains learnings and `bimai team` runs
- **THEN** the file is unchanged

### Requirement: Memory instructions
Every generated subagent file, and the Coordinator part of the `CLAUDE.md` block, SHALL name its
history file(s) and instruct the agent to read them before starting, and to append only confirmed,
lasting learnings as one dated line each with its source; never requests, intermediate states,
personal remarks or secrets; to correct a line that turns out wrong; and to record decisions in
`.bimai/decisions/` instead of history.

#### Scenario: Subagent names its history
- **WHEN** the Model Checker's subagent file is generated for position `bim-coordinator`
- **THEN** it names `.bimai/positions/bim-coordinator/agents/model-checker/history.md` and contains the rules above

### Requirement: bimai team regenerates from the seat
`bimai team [PATH]` SHALL read the seat's `team` list from `seat.yaml` and regenerate the subagent
files, the `CLAUDE.md` block and `team.md`, and create missing history files, printing every file it
creates, updates or removes. A member without a `why` SHALL get "Added by hand". The Coordinator
SHALL always be on the team, added first when missing. With more than one seat, `--seat <name>` SHALL
be required; without it, the command SHALL exit with code 2 and list the seats. With no workspace, it
SHALL exit with code 2. When `seat.yaml` fails validation, it SHALL print the problems, write nothing
and exit with code 1. `--dry-run` SHALL show the changes without writing.

#### Scenario: Member added by hand
- **WHEN** the user adds `{role: planning-analyst}` to the `team` list and runs `bimai team`
- **THEN** `.claude/agents/planning-analyst.md` is created, the routing table has a Planning Analyst row, and `team.md` shows "Added by hand"

#### Scenario: Two seats
- **WHEN** the project has seats `anna` and `jan` and the user runs `bimai team` without `--seat`
- **THEN** nothing is written, both seats are listed and the exit code is 2

### Requirement: bimai owns only the files it generated
Every generated subagent file SHALL contain the marker `<!-- bimai:generated -->`. `bimai team` SHALL
update a subagent file only if it carries the marker, and report any other existing file with the
same name as a conflict, leaving it unchanged. When a member is removed from the team, its subagent
file SHALL be deleted only if it carries the marker. Outside the `CLAUDE.md` block, nothing in
`CLAUDE.md` SHALL change.

#### Scenario: Removed member
- **WHEN** the Scribe is removed from the `team` list and `bimai team` runs
- **THEN** `.claude/agents/scribe.md` is deleted, its history file stays, and the routing table has no Scribe row

#### Scenario: User's own agent file
- **WHEN** `.claude/agents/scribe.md` exists without the marker and the Scribe is on the team
- **THEN** the file is unchanged and reported as a conflict

### Requirement: Team checks in validate
`bimai validate` SHALL report a problem for a `seat.yaml` whose `team` list names a role that is not in
the role catalogue, names a role twice, or has more than 5 members.

#### Scenario: Unknown role
- **WHEN** a seat's team contains `{role: clash-wizard}`
- **THEN** a problem is reported at `team.<index>.role` naming `clash-wizard` and listing the known roles

#### Scenario: Too many members
- **WHEN** a seat's team has 6 members
- **THEN** a problem is reported for that seat's `team`
