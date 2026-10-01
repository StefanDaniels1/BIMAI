# workspace-init Specification

## Purpose
`bimai init` adds bimai to a fresh or existing folder: it scans what is there, asks a short
interview, proposes a lean AI team with reasons, and after confirmation writes a valid `.bimai/`
workspace plus the Claude Code configuration for that team.

## Requirements

### Requirement: Repo scan
The system SHALL scan the target folder recursively, skipping hidden folders, `node_modules` and
`.bimai`, and report per category the number of files found and up to five example paths:
`models` (`.ifc`, `.rvt`, `.nwd`, `.nwc`, `.dgn`, `.dwg`), `issues` (`.bcf`, `.bcfzip`),
`requirements_checks` (`.ids`), `bep` (`.pdf` or `.docx` whose name contains `bep`, `eir`,
`execution plan` or `uitvoeringsplan`, case-insensitive), `planning` (`.xer`, and `.xml` files whose
root element is an MS Project or Primavera P6 export), `relatics` (`.json` whose name contains
`relatics`) and `transcripts` (`.vtt`, `.srt`). It SHALL also report whether the folder is a git
repository and whether `CLAUDE.md` and `.claude/` already exist. The scan SHALL NOT modify anything.

#### Scenario: Existing project folder
- **WHEN** the folder contains `models/bridge.ifc`, `BEP-v3.pdf` and a P6 XML export
- **THEN** the scan reports 1 model, 1 BEP document and 1 planning file with their paths

#### Scenario: Unrelated XML
- **WHEN** the folder contains an `.xml` file that is not a planning export
- **THEN** it is not counted as planning

#### Scenario: Empty folder
- **WHEN** the folder is empty
- **THEN** every category reports 0 and init continues with the interview

### Requirement: Interview with pre-filled answers
The system SHALL ask for: project name, role, goals (one or more of `requirements`, `risks`,
`planning`, `reporting`, `issues`, `model-checks`, `delivery`, `meetings`), tools and data, whether
the user is new to VS Code, and output language (`en` or `nl`). Tools found by the scan SHALL be
pre-filled and shown with the file that suggested them. Each answer SHALL also be accepted as a
flag (`--name`, `--role`, `--goals`, `--tools`, `--new-to-vscode`, `--language`); with `--yes`, no
question is asked and missing answers use defaults (project name from the folder name, language
`en`, no goals beyond the preset's, tools from the scan). The user's name comes from `--person` or,
failing that, the git user name.

#### Scenario: Non-interactive
- **WHEN** the user runs `bimai init --role "bim coordinator" --goals issues,meetings --yes`
- **THEN** no question is asked and the workspace is written

#### Scenario: Scan pre-fills tools
- **WHEN** the scan found `.rvt` files
- **THEN** Revit is pre-selected among the tools, with the file that suggested it

#### Scenario: Unknown role
- **WHEN** the role matches no preset
- **THEN** init stops with exit code 2 and lists the available roles

### Requirement: Team proposal by preset and rules
The system SHALL select the preset whose match list contains the role (case-insensitive), take its
roles as candidates, and keep a candidate only if (1) it is the Coordinator or it serves at least
one chosen goal, and (2) every capability it requires is provided by a declared tool or scanned
data. The Mentor SHALL join only when the user is new to VS Code. The team SHALL NOT exceed 5
members including the Coordinator. Each member SHALL carry a reason naming the goals and data that
qualified it. The proposal SHALL be shown before anything is written and SHALL require confirmation
unless `--yes` is given.

#### Scenario: BIM modeller without requirements data
- **WHEN** the role is BIM modeller and no Relatics data is declared or found
- **THEN** the team has no Requirements & Risk Manager

#### Scenario: Missing data drops a role
- **WHEN** the role is design coordinator, goals include planning, and no planning data exists
- **THEN** the Planning Analyst is not on the team, and the proposal says which data would add it

#### Scenario: Reasons
- **WHEN** the Scribe joins because the user chose meetings
- **THEN** its reason reads `Goal: meetings`

#### Scenario: Declined proposal
- **WHEN** the user answers no to the proposal
- **THEN** nothing is written and the exit code is 1

### Requirement: Dry run
With `--dry-run`, the system SHALL print the scan, the answers and the proposed team, and the list of
files it would write, and SHALL NOT write anything. With `--json`, this output SHALL be a JSON object
with `scan`, `answers`, `team` and `files` keys.

#### Scenario: Dry run writes nothing
- **WHEN** the user runs `bimai init --dry-run --yes --role "bim modeller"`
- **THEN** the folder's contents are unchanged

### Requirement: Workspace written
After confirmation, the system SHALL write `.bimai/project.yaml`, `.bimai/people.yaml` (the user),
`.bimai/ownership.yaml` (one position for the user's role, held by the user),
`.bimai/seats/<person>/seat.yaml` (person, role, preset, goals, positions) and
`.bimai/seats/<person>/team.md` (a table of members and reasons). The written workspace SHALL pass
`bimai validate` with no problems. Init SHALL print every file it created or changed.

#### Scenario: Valid result
- **WHEN** init completes in an empty folder
- **THEN** `bimai validate` on that folder exits with code 0

### Requirement: Claude Code configured for the team
The system SHALL write one subagent file per team member except the Coordinator to
`.claude/agents/<role>.md`, with the role's model tier (§5.4) in its frontmatter. It SHALL put the
Coordinator's instructions, including the team list, between `<!-- bimai:start -->` and
`<!-- bimai:end -->` markers in `CLAUDE.md`, creating the file if needed and replacing only that block
if it exists. It SHALL set `"model": "sonnet"` in `.claude/settings.json` only when no model is set,
keeping all other settings.

#### Scenario: Existing CLAUDE.md is kept
- **WHEN** the folder has a `CLAUDE.md` with the user's own content
- **THEN** that content is unchanged and the bimai block is appended

#### Scenario: Existing settings are kept
- **WHEN** `.claude/settings.json` has permissions and `"model": "opus"`
- **THEN** permissions and model are unchanged

#### Scenario: Subagent models
- **WHEN** the team includes the Model Checker
- **THEN** `.claude/agents/model-checker.md` has `model: haiku`

### Requirement: Safe in existing repositories
The system SHALL NOT overwrite or delete any existing file other than replacing its own marked block
in `CLAUDE.md`, and SHALL only append missing bimai lines (`.bimai/state/`, `.bimai/site/`,
`.bimai/data/`) to `.gitignore`. It SHALL refuse to write a subagent file that already exists with
different content, and report it instead. When `.bimai/project.yaml` already exists, init SHALL stop
with exit code 2 and say the folder is already a bimai project.

#### Scenario: Already initialised
- **WHEN** the user runs `bimai init` in a folder that has `.bimai/project.yaml`
- **THEN** nothing is written and the exit code is 2

#### Scenario: Running twice on .gitignore
- **WHEN** `.gitignore` already contains `.bimai/state/`
- **THEN** that line is not added again

### Requirement: Product Help on every project
`bimai init` SHALL add Autodesk Product Help to `.mcp.json`, keeping any servers already listed, and
store the seat's declared tools in `seat.yaml` so later regenerations know what was declared. After
writing, it SHALL suggest `bimai connect <server>` for every catalogue server that matches a declared
tool.

#### Scenario: Fresh project
- **WHEN** `bimai init` completes in an empty folder
- **THEN** `.mcp.json` lists `autodesk-help`

#### Scenario: Suggestion for a declared tool
- **WHEN** the user declared Revit during init
- **THEN** the final output suggests `bimai connect revit`

### Requirement: Connections for chosen tools
For every chosen tool that matches a server in the catalogue, `bimai init` SHALL determine the
connection status on this computer: `ready`, `needs-install` (a bimai bridge with a published release on a
supported platform), `needs-app` (a vendor add-on that isn't installed), `other-platform` or
`unavailable`, with a plain-language sentence and, only where it works on this computer, the command to
run. The dry run with `--json` SHALL include this plan. When writing, init SHALL add the `ready` servers
to `.mcp.json` (with or without `--yes`) and SHALL NOT install anything. The final output SHALL list the
status of every chosen tool's connection and SHALL NOT suggest a command that can't work on this computer.

#### Scenario: Civil 3D on macOS
- **WHEN** a modeller chooses Civil 3D on macOS
- **THEN** the plan says `other-platform` with "Windows only" and no command, nothing is added to `.mcp.json`, and the output doesn't suggest `bimai connect civil3d`

#### Scenario: Civil 3D bridge missing on Windows
- **WHEN** a modeller chooses Civil 3D on Windows without the bridge installed
- **THEN** the plan says `needs-install` with the command `bimai connect civil3d --install --yes`, and init installs nothing itself

#### Scenario: Ready server connected by init
- **WHEN** a chosen tool's server can be configured on this computer (e.g. the Civil 3D bridge is installed)
- **THEN** init adds it to `.mcp.json`, also with `--yes`
