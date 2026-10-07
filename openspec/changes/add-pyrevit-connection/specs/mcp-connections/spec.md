# Spec Delta

## ADDED Requirements

### Requirement: pyRevit agent runtime in the catalogue
The catalogue SHALL contain `pyrevit` (Windows, no sign-in, matches the `revit` tool) with the stdio
command `pyrevit.exe mcp`, using the per-user install (`%APPDATA%\pyRevit-Master\bin`) and otherwise the
all-users install (`%ProgramFiles%\pyRevit-Master\bin`). It SHALL need pyRevit 7.0 or newer; an older
version SHALL be reported as needing an update.

#### Scenario: Per-user pyRevit
- **WHEN** pyRevit 7.0 is installed per user and the user runs `bimai connect pyrevit --yes`
- **THEN** `.mcp.json` contains `pyrevit` with type `stdio`, the `%APPDATA%` command and args `["mcp"]`

#### Scenario: Old pyRevit
- **WHEN** only pyRevit 6.5 is installed
- **THEN** connecting says pyRevit 7.0 or newer is needed and offers the update

### Requirement: Per-tool write rules
A catalogue server MAY list `write_tools`. Connected without write consent, bimai SHALL add a `deny`
rule `mcp__<server>__<tool>` for each to `.claude/settings.json`; with consent (`--allow-writes` or an
interactive yes) it SHALL add `ask` rules instead. Other settings SHALL be kept, and disconnecting SHALL
remove the rules.

#### Scenario: pyRevit read-only by default
- **WHEN** the user runs `bimai connect pyrevit --yes`
- **THEN** `permissions.deny` contains `mcp__pyrevit__run_modify` and the read tools are not restricted

#### Scenario: Changes with approval
- **WHEN** the user runs `bimai connect pyrevit --allow-writes --yes`
- **THEN** `permissions.ask` contains `mcp__pyrevit__run_modify` and `permissions.deny` doesn't

### Requirement: Installing pyRevit
When pyRevit 7.0+ is missing on Windows, `bimai connect pyrevit` SHALL offer (interactive) or perform
(`--install`) the installation of the pinned pyRevit release: download the signed per-user installer,
refuse it unless its SHA-256 matches the pin, refuse while Revit is running, and run it silently without
administrator rights; it SHALL refuse, with an explanation, when bimai itself runs as administrator
(pyRevit's per-user installer then ends in a dialog that can't be suppressed). When pyRevit's agent host is off, it SHALL offer (or with `--install` perform)
`pyrevit configs agent enable` and say that Revit must be restarted. Onboarding SHALL report the
`pyrevit` connection with status `needs-install` and the command `bimai connect pyrevit --install --yes`.

#### Scenario: Verified install
- **WHEN** the downloaded installer's SHA-256 differs from the pin
- **THEN** nothing is installed and the error says the download didn't match

#### Scenario: Running as administrator
- **WHEN** bimai runs elevated and pyRevit has to be installed
- **THEN** nothing is installed and the error says to use a normal terminal

#### Scenario: Revit running
- **WHEN** Revit is running during the install
- **THEN** bimai asks to close Revit first and installs nothing until it is closed

### Requirement: pyRevit prerequisites in one step
Before installing pyRevit, bimai SHALL check for the .NET 8 and .NET 10 Desktop Runtimes at the minimum
versions pyRevit's installer requires. Missing runtimes SHALL be installed from Microsoft's official
installers pinned in the catalogue (version, URL, SHA-512), all in one elevated step, after saying that
Windows asks permission once and why. A download whose SHA-512 differs SHALL be refused. When nothing is
missing, no permission is asked.

#### Scenario: Both runtimes missing
- **WHEN** neither .NET 8 nor .NET 10 Desktop Runtime is installed and the user agrees
- **THEN** both are installed in one elevated step, and then pyRevit is installed without elevation

#### Scenario: Runtimes present
- **WHEN** both runtimes are installed at the required versions
- **THEN** pyRevit is installed without any permission prompt
