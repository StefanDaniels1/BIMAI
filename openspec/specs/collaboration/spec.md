# collaboration Specification

## Purpose
Let several people, each with their own team, work on one project: join, hand work over, record decisions and
catch up, by saying it, with bimai doing it deterministically.

## Requirements

### Requirement: Shared files are the same for every seat
`bimai team` and `bimai init`/`bimai join` SHALL write a `CLAUDE.md` block and `.claude/agents/` that don't depend
on which seat ran them: the agents are the union of all seats' teams, and an agent is removed only when no seat
has it on its team.

#### Scenario: A second seat
- **WHEN** a constructeur's seat regenerates its team in a project with a BIM coordinator's seat
- **THEN** the coordinator's team members stay in `.claude/agents/` and `CLAUDE.md` names no person

### Requirement: Seat brief
`bimai brief --seat <seat>` SHALL print, within about 400 tokens, who the seat works for, its positions, goals,
language and team, and since the seat's last brief: new decisions, open handoffs to its positions and, when the
log is shared, teammates' entries. Each person's `SessionStart` hook SHALL run it.

#### Scenario: New since last session
- **WHEN** a decision was recorded and a handoff was sent to Joris's position after his last session
- **THEN** Joris's next brief lists both, and the one after that doesn't list them as new

### Requirement: Join
`bimai join --interview` SHALL print the joining questions in the onboarding interview format (person, role,
position, goals, tools, VS Code), and `bimai join` with the answers SHALL add the person, a seat and a position
(new or shared, with a lead when shared) and set up the seat, refusing a person who already has a seat. `bimai
init` in an existing project SHALL point to `bimai join`.

#### Scenario: Join as constructeur
- **WHEN** Joris joins a project as constructeur with SCIA Engineer
- **THEN** people.yaml, ownership.yaml (position `constructeur`, held by joris) and his seat exist, the workspace validates, and the existing seats' files are unchanged

### Requirement: Handoffs
`bimai handoff --to <position>` SHALL create one file in that position's inbox with the sender, title, body and
evidence; `bimai inbox` SHALL list the open handoffs for a seat's positions; `bimai handoff done <id>` SHALL close
one of the seat's own. An unknown position SHALL be refused with the list of positions.

#### Scenario: Clash handed to the modeller
- **WHEN** Anna's team hands "Clash between slab and duct at grid C4" to `bim-modeller`
- **THEN** Fatima's inbox and her next brief show it, with Anna as the sender

### Requirement: Decisions
`bimai decide` SHALL write one decision file with title, decision, date, author seat, status and optional source
and superseded decision, never overwriting a file; `bimai decisions` SHALL list them, newest first, showing which
are superseded.

#### Scenario: Superseded
- **WHEN** a decision supersedes an earlier one
- **THEN** both files exist, the list marks the earlier one as superseded, and the nap treats it as reversed

### Requirement: Join prompt
The website SHALL offer a copy prompt to join a project, in the style of the start prompt, that has Claude install
bimai, run the join interview with its question tool, and set up the seat after a final yes.

#### Scenario: Prompt content
- **WHEN** the join prompt is published
- **THEN** it names `bimai join --interview`, the question tool and the final confirmation
