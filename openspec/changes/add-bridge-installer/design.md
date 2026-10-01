# Design

## Decisions

- **Trust chain:** the bimai package pins the release's SHA-256 in `servers.yaml`. A download is only
  installed when it matches, so a compromised release or network can't swap the add-in. Pinning
  happens in a commit after the release is published (the hash only exists then); until then the
  installer refuses downloads and supports `--from`.
- **Reuse the verified `install.ps1` from the zip** instead of a second install path: the same script IT
  can run, already checks for a running Civil 3D, copies to `C:\Program Files\Autodesk\ApplicationPlugins`
  (always trusted) and unblocks files. Elevation: `powershell Start-Process -Verb RunAs -Wait -PassThru`
  runs it with the normal UAC prompt; the exit code is passed back. Success is confirmed independently
  by checking the installed bundle.
- **Download with the standard library** (`urllib`): on Windows Python uses the system certificate store
  and honours proxy environment variables, which covers most company networks. Size cap 50 MB, timeout.
- **Process check** with `tasklist` (always present on Windows); no new dependency.
- **Version and health:** installed version from the bundle's `PackageContents.xml` (`AppVersion`);
  "running" by posting a `server/discover` request to `127.0.0.1:<port>` with a 2-second timeout.
- **Interactivity:** `--yes` never installs software silently (installing is a different decision from
  "accept defaults"); it prints the command instead. `bimai bridge install --yes` skips bimai's own
  questions but Windows still shows its permission prompt.
- **Generic by data:** any catalogue server with `bundle` + `release` gets the same flow.

## Risks / Trade-offs

- Users without administrator rights can't click through the prompt → the message explains what to send
  to IT (the zip and the one-line install command); code signing would remove this, later.
- Group policies that force PowerShell `AllSigned` block the installer script → same IT route.
- The release workflow can only be fully exercised by pushing a tag (a public, outward action), so the
  first release is published only with the maintainer's go-ahead.
