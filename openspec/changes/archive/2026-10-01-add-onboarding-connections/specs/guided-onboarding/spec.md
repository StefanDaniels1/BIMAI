# Spec Delta

## ADDED Requirements

### Requirement: Platform notes on tool options
A tool option whose connection can't work on this computer (status `other-platform`, `needs-app` or
`unavailable`) SHALL say so in its description, in plain words, and SHALL stay selectable.

#### Scenario: Civil 3D offered on macOS
- **WHEN** the interview's tool options include Civil 3D on macOS
- **THEN** its description starts with "Windows only"

## MODIFIED Requirements

### Requirement: Guided start prompt
The start prompt published on the install page and the landing page SHALL instruct Claude to get the
interview from `bimai init --interview`, ask each step with Claude Code's question tool using the given
headers, options, multi-select and recommended order, map "Other" answers to the allowed values (and ask
when unsure), request step 2 with the chosen role, show the proposed team from a dry run, and only write
after a final yes. After writing, for each connection with status `needs-install`, it SHALL ask with the
question tool whether to install it now, explain that Windows asks permission once, and run the given
command only on yes; it SHALL report the other statuses in plain words without suggesting commands that
don't work on this computer.

#### Scenario: Prompt content
- **WHEN** the start prompt is published
- **THEN** it names `bimai init --interview`, the question tool, mapping of "Other" answers, the final confirmation, and the `needs-install` question
