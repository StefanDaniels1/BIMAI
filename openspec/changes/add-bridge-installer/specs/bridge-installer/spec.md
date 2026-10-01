# Spec Delta

## Purpose
Get a bimai bridge onto a user's computer with one question and one Windows permission click, from
verified, published releases, inside the commands people already use.

## ADDED Requirements

### Requirement: Published releases
The repository SHALL contain a workflow that, when a tag `civil3d-bridge-v<version>` is pushed, runs the
bridge tests, builds the bundle on Windows, checks that the tag version equals the bridge version, and
publishes a GitHub Release with `bimai-civil3d-bridge.zip` and `SHA256SUMS.txt`.

#### Scenario: Version mismatch
- **WHEN** the tag says 0.2.0 but the bridge version is 0.1.0
- **THEN** the workflow fails and publishes nothing

### Requirement: Verified download
For a catalogue server with release data (repository, tag, asset, SHA-256), `bimai bridge install
<server>` SHALL download the asset from the GitHub release and SHALL refuse to install it unless its
SHA-256 equals the hash pinned in the catalogue. Without a pinned hash, it SHALL refuse and point to
`--from`. `--from <zip>` SHALL install a local zip without a download (its hash is shown, not required).
The zip SHALL contain the bundle with its manifest and the installer script, or be refused.

#### Scenario: Tampered download
- **WHEN** the downloaded file's SHA-256 differs from the pinned hash
- **THEN** nothing is installed and the error says the download could not be verified

#### Scenario: No release yet
- **WHEN** the catalogue has no pinned hash
- **THEN** the command explains that no release is published yet and how to use `--from`

### Requirement: One-click installation
On Windows, installation SHALL run the verified installer from the zip through the Windows administrator
prompt (UAC) and wait for it to finish. When Civil 3D is running, it SHALL ask the user to close it
first and stop if it is still running. A declined prompt or a failed installer SHALL leave nothing
half-installed and SHALL explain the result, including how IT can install it. On other platforms the
command SHALL explain that the bridge needs Windows. Success SHALL be confirmed by finding the
installed bundle.

#### Scenario: Declined permission
- **WHEN** the user declines the Windows administrator prompt
- **THEN** the command says the bridge was not installed and how to ask IT, and exits with code 1

#### Scenario: Civil 3D running
- **WHEN** Civil 3D is running and the user doesn't close it
- **THEN** nothing is installed and the command asks to close Civil 3D and try again

### Requirement: Status and uninstall
`bimai bridge status <server>` SHALL show whether the bridge is installed and which version, whether a
newer catalogued version exists, and whether it currently answers on its port. `bimai bridge uninstall
<server>` SHALL remove the installed bundle through the administrator prompt.

#### Scenario: Installed and running
- **WHEN** the bridge is installed and Civil 3D is running with it
- **THEN** status shows the installed version and "running"

### Requirement: Install offered where people already are
When `bimai connect <server>` finds a release-based bridge missing on Windows, it SHALL, if interactive,
ask to install it now and, after a successful install, continue connecting; non-interactively it SHALL
print the install command. When `bimai init` writes a workspace whose declared tools match a
release-based bridge that isn't installed (on Windows, interactive), it SHALL offer to install and
connect it. After connecting a local bridge, bimai SHALL check whether it answers and say plainly
whether to start Civil 3D.

#### Scenario: Connect installs first
- **WHEN** the bridge is missing and the user answers yes to "Install the Civil 3D bridge now?"
- **THEN** the bridge is installed and `civil3d` is added to `.mcp.json` in the same command

#### Scenario: Init offers the bridge
- **WHEN** a modeller declares Civil 3D during `bimai init` on Windows without the bridge
- **THEN** init asks whether to install and connect the Civil 3D bridge
