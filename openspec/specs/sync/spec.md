# sync Specification

## Purpose
Save and share the team's work, and bring in colleagues' work, without git commands and without losing anything.

## Requirements

### Requirement: Save
`bimai save` SHALL commit only bimai's files and the team's outputs (skipping files over 25 MB, which it names)
with a plain message and the person's name, without changing git configuration, and SHALL do nothing when
nothing changed.

#### Scenario: A model file stays out
- **WHEN** a decision was recorded and the person also changed `Deck.rvt`
- **THEN** the commit contains the decision and not the model file

### Requirement: Sync
`bimai sync` SHALL save, bring in the team's changes and share the person's (rebase, then push, once more when
someone pushed meanwhile). On a conflict it SHALL keep the person's saved version, change nothing else, and name
the files; without a remote it SHALL only save; offline it SHALL say the work is saved and shared next time.

#### Scenario: Two people, different files
- **WHEN** Anna records a decision and Joris sends a handoff, and both sync
- **THEN** both have both files

#### Scenario: A real conflict
- **WHEN** both changed the same line of the same file
- **THEN** the person's version stays, nothing is lost, and the message names the file

### Requirement: Automatic sync
When the project hasn't switched it off (`sync.auto: false`), the session-start brief SHALL sync first and say
how many changes came in, and the end of each turn SHALL save and share in the background.

#### Scenario: Off
- **WHEN** `sync.auto` is false
- **THEN** neither the brief nor the end of a turn runs git

### Requirement: Join from a link
`bimai join <link>` SHALL clone the project into the person's Documents/bimai folder (or `--into`) and say where
it is, so the person can join there.

#### Scenario: Clone
- **WHEN** a person runs `bimai join <link>`
- **THEN** the project is cloned and the output names the folder to continue in

### Requirement: Safety rails
The project's shared settings SHALL deny the team's agents destructive git commands (force push, hard reset,
rebase, history rewrites, forced clean), and bimai's own sync SHALL never use them.

#### Scenario: Deny rules
- **WHEN** a project is set up
- **THEN** `.claude/settings.json` denies `Bash(git push --force*)` and `Bash(git reset --hard*)`
