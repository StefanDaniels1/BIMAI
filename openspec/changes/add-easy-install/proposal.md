# Proposal

## Why

Installing bimai today means `pip install "git+https://github.com/…"`, which needs both Python and git
on the user's computer. Many BIM professionals have neither, and installing them is an IT ticket. Squad
installs with one command from package registries and a standalone script; bimai should too. The name
`bimai` is still free on PyPI. ARCHITECTURE.md §12.5 already plans "pipx or uv everywhere".

## What Changes

- **PyPI:** bimai is published to PyPI as `bimai` by a release workflow on `v*` tags, using PyPI Trusted
  Publishing (no stored tokens), after building, checking the version and running the tests.
- **One-line install, nothing required:** `install.ps1` (Windows) and `install.sh` (macOS, Linux) on
  docs.bimai.nl install uv into the user's folder if needed (no administrator rights), then
  `uv tool install bimai`; uv downloads a suitable Python by itself. No Python, git or admin needed.
  Re-running the script updates bimai.
- **`bimai update`:** updates bimai itself with the tool it was installed with (uv, pipx or pip), and
  `--check` tells whether a newer version exists. (`bimai upgrade` stays reserved for project files.)
- CI runs the install scripts on Windows, macOS and Linux against the freshly built package, then
  `bimai --version` and `bimai init`.
- Docs: the install page, the landing-page prompt and the README use the new commands; the package
  page on PyPI shows the README.

## Non-goals

- WinGet and Homebrew packages, standalone executables (later, once releases are regular).
- `bimai upgrade` (project file migrations) and automatic update checks on every run.

## Capabilities

### New Capabilities
- `distribution`: PyPI releases, the install scripts, and `bimai update`.

### Modified Capabilities
<!-- none -->

## Impact

- `.github/workflows/release-bimai.yml`, `ci.yml` (install test job), `pyproject.toml` metadata,
  `cli/bimai/__init__.py` version 0.1.0, `cli/bimai/update.py`, CLI wiring, tests.
- `docs/public/install.ps1`, `docs/public/install.sh`, install docs, `docs/lib/prompts.ts`, README.
- The maintainer must register a PyPI "pending publisher" once (a web form) before the first release.
