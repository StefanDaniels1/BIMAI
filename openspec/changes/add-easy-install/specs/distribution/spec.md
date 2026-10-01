# Spec Delta

## Purpose
How people get bimai onto their computer and keep it up to date: one command, no Python, git or
administrator rights required, from verified public releases.

## ADDED Requirements

### Requirement: Published to PyPI
The repository SHALL contain a workflow that, when a tag `v<version>` is pushed, runs the tests, builds
the wheel and source distribution, checks that the tag equals the package version and that the built
package contains the catalogue and schemas, and publishes it to PyPI as `bimai` through Trusted
Publishing, without stored credentials.

#### Scenario: Version mismatch
- **WHEN** the tag is v0.2.0 and the package version is 0.1.0
- **THEN** the workflow fails and nothing is published

### Requirement: One-line install
`docs.bimai.nl/install.ps1` (Windows PowerShell) and `docs.bimai.nl/install.sh` (macOS and Linux) SHALL
install bimai for the current user without administrator rights and without Python or git present:
install uv into the user's folder if it is missing, run `uv tool install --upgrade bimai` (uv downloads
a suitable Python when none is found), make sure the tool folder is on the PATH, and print the version
and the next step (`bimai init`). Running a script again SHALL update bimai. The environment variable
`BIMAI_PACKAGE` SHALL override what is installed (a wheel path or a version), for testing and pinning.
A failure SHALL stop the script with a plain-language message.

#### Scenario: Fresh computer
- **WHEN** the script runs on a computer without uv or bimai
- **THEN** uv and bimai are installed in the user's folder and `bimai --version` works in a new terminal

#### Scenario: Run again
- **WHEN** the script runs while bimai is already installed
- **THEN** bimai is updated to the latest version, not reinstalled from scratch or duplicated

### Requirement: bimai update
`bimai update` SHALL update bimai using the tool it was installed with: `uv tool upgrade bimai` for uv
tool installs, `pipx upgrade bimai` for pipx, and `python -m pip install --upgrade bimai` otherwise, and
SHALL refuse with an explanation for editable installs from source. `bimai update --check` SHALL report
the installed and the latest published version without changing anything, and SHALL say so plainly
when PyPI can't be reached.

#### Scenario: Installed with uv
- **WHEN** bimai runs from a uv tool environment and the user runs `bimai update`
- **THEN** bimai runs `uv tool upgrade bimai`

#### Scenario: Check
- **WHEN** PyPI's latest version is newer than the installed one
- **THEN** `bimai update --check` shows both versions and the command to update
