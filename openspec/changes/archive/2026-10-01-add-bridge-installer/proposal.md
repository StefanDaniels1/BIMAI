# Proposal

## Why

The Civil 3D bridge works, but getting it onto a modeller's computer takes a GitHub login, an expiring
CI download, an administrator PowerShell with `-ExecutionPolicy Bypass`, and a second round of
`bimai connect`. A modeller won't do that, so today the bridge brings no value. Installing must be one
question and one Windows permission click, inside the flows people already use.

## What Changes

- **Published releases:** a workflow that, on a `civil3d-bridge-v*` tag, tests and builds the bridge on
  Windows and publishes the zip and its SHA-256 as a GitHub Release (public, no login, permanent).
- **`bimai bridge install civil3d`:** downloads the pinned release, checks its SHA-256 against the value
  pinned in bimai's catalogue, asks to close Civil 3D if it's running, and runs the verified installer
  with the normal Windows administrator prompt (one click). `--from <zip>` installs a local copy (for
  IT or offline use). Also `bimai bridge status civil3d` (installed version; running or not) and
  `bimai bridge uninstall civil3d`.
- **Seamless flows:** `bimai connect civil3d` offers to install when the bridge is missing, then connects;
  `bimai init` offers it when someone picks Civil 3D. Afterwards bimai checks that the bridge answers
  and says plainly what to do if Civil 3D isn't running.
- **Updates:** installing over an older version upgrades it; status shows when an update is available.
- Docs: the Civil 3D guide becomes "one command"; a section for IT departments (Intune/SCCM).

## Non-goals

- Code signing (would allow installing without administrator rights; later, needs a certificate).
- An MSI package; automatic background updates.
- Other bridges (the mechanism is generic, but only Civil 3D uses it now).

## Capabilities

### New Capabilities
- `bridge-installer`: releases, `bimai bridge install|status|uninstall`, and the install offers in `connect` and `init`.

### Modified Capabilities
<!-- none: mcp-connections' bridge entry gains release data, covered by the new capability -->

## Impact

- New `cli/bimai/bridges.py`, catalogue `release` data for `civil3d`, CLI wiring, tests.
- New `.github/workflows/release-civil3d-bridge.yml`.
- Docs: `guides/civil3d-bridge.mdx`, command reference.
- The first release must be published (and its hash pinned) before the one-command install works for
  everyone; until then `--from` works.
