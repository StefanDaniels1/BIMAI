# workspace-validation Specification

## Purpose
The `bimai` command-line entry point and `bimai validate`, which checks a project's `.bimai/`
workspace files against their schemas and against each other, so mistakes surface early and clearly.

## Requirements

### Requirement: bimai command
The system SHALL provide a `bimai` command, installable from the repository as a Python package, that
prints its version with `bimai --version` and lists its commands with `bimai --help`.

#### Scenario: Version
- **WHEN** the user runs `bimai --version`
- **THEN** the installed package version is printed and the exit code is 0

### Requirement: Workspace discovery
`bimai validate [PATH]` SHALL validate the `.bimai/` folder in PATH, defaulting to the current
directory. When PATH has no `.bimai/project.yaml`, it SHALL print an error naming PATH and exit with
code 2.

#### Scenario: No workspace
- **WHEN** the user runs `bimai validate` in a folder without `.bimai/project.yaml`
- **THEN** an error naming the folder is printed and the exit code is 2

### Requirement: Schema validation
The system SHALL validate `project.yaml`, `people.yaml`, `ownership.yaml`, every `seats/*/seat.yaml`,
every `workflows/*.yaml` and every `automations/*.yaml` against a JSON Schema. Files that are absent
and optional SHALL NOT be reported; `project.yaml` is required. Unparseable YAML SHALL be reported as
a problem for that file, not as a crash.

#### Scenario: Valid example project
- **WHEN** the user runs `bimai validate` on the repository's example project
- **THEN** it prints a success line and exits with code 0

#### Scenario: Missing required field
- **WHEN** `project.yaml` has no `id`
- **THEN** a problem is reported for `project.yaml` naming the missing `id` field

#### Scenario: Wrong type
- **WHEN** a workflow step's `needs` is a string instead of a list
- **THEN** a problem is reported for that workflow file at `steps.<step>.needs`

#### Scenario: Broken YAML
- **WHEN** `people.yaml` is not valid YAML
- **THEN** a problem is reported for `people.yaml` with the parser's line number, and other files are still checked

### Requirement: Cross-file references
The system SHALL report a problem when:
- a position's `held_by`, `lead`, or a cover entry's `by` names a person not in `people.yaml`;
- a seat's `person` is not in `people.yaml`;
- a seat's `positions`, or a cover entry's `position`, names a position not in `ownership.yaml`;
- an automation's `owner` is neither a position in `ownership.yaml` nor a seat.

#### Scenario: Unknown person in ownership
- **WHEN** a position lists `held_by: [jan]` and no person `jan` exists
- **THEN** a problem is reported for `ownership.yaml` at `positions.<id>.held_by` naming `jan`

### Requirement: Workflow graph checks
The system SHALL report a problem when a workflow step's `needs` names a step that does not exist in
that workflow, and when the steps' `needs` form a cycle, naming the steps in the cycle. Each step
SHALL have exactly one of `script`, `tool`, `agent`, `workflow` or `gate`.

#### Scenario: Unknown step
- **WHEN** a step declares `needs: [fetch]` and no step `fetch` exists
- **THEN** a problem is reported naming the step and `fetch`

#### Scenario: Cycle
- **WHEN** step `a` needs `b` and step `b` needs `a`
- **THEN** a problem is reported naming `a` and `b` as a cycle

#### Scenario: Two step types
- **WHEN** a step has both `script` and `agent`
- **THEN** a problem is reported for that step

### Requirement: Report format
Each problem SHALL be printed on its own line as `<path relative to the workspace>: <location>:
<message>`, sorted by file. After the problems, a summary line with the problem count SHALL be printed.
With `--json`, the output SHALL instead be a JSON object `{"valid": bool, "problems": [{"file",
"location", "message"}]}`. The exit code SHALL be 0 when there are no problems and 1 otherwise.

#### Scenario: Problems found
- **WHEN** the workspace has two problems
- **THEN** two problem lines and a summary line saying 2 problems are printed, and the exit code is 1

#### Scenario: JSON output
- **WHEN** the user runs `bimai validate --json` on a valid workspace
- **THEN** the output parses as JSON with `"valid": true` and an empty `problems` list
