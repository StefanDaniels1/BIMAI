# documentation Specification

## Purpose
Keep documentation part of done: CI fails when something user-facing has no page or the published
site has broken links.

## Requirements

### Requirement: Command coverage
The docs check SHALL fail when any `/bimai:<command>` or top-level `` `bimai <command>` `` mentioned in
ARCHITECTURE.md is missing from the command reference page.

#### Scenario: Undocumented command
- **WHEN** ARCHITECTURE.md mentions `bimai foo` and the command reference does not
- **THEN** the check exits non-zero and names `bimai foo`

### Requirement: Pack coverage
The docs check SHALL fail when a folder in `packs/` is not mentioned in any documentation page.

#### Scenario: New pack without a page
- **WHEN** a new pack folder is added without documentation
- **THEN** the check exits non-zero and names the pack

### Requirement: Internal links resolve
With `--links`, the docs check SHALL fail for any internal link in the built site that does not
resolve to a page or file.

#### Scenario: Broken link
- **WHEN** a built page links to a path that does not exist
- **THEN** the check exits non-zero and names the link and the page it was first seen on
