# Design

## Decisions

- **uv as the installer engine** (verified with uv 0.9): `uv tool install` puts bimai in an isolated
  environment and its command in `~/.local/bin` (Windows: `%USERPROFILE%\.local\bin`), and "will download
  Python if a version cannot be found". Astral's own installer (`astral.sh/uv/install.ps1|.sh`, redirecting
  to releases.astral.sh) installs uv per user, without administrator rights. `uv tool update-shell` adds
  the folder to the PATH. This mirrors Squad's standalone script without bundling a runtime ourselves.
- **Scripts hosted on docs.bimai.nl** (`docs/public/`), so the URL is short and under our control; they
  are plain, readable files and the docs show how to read one before running it.
- **Version 0.1.0** for the first PyPI release, not an alpha: `uv tool install` and `pipx` skip
  pre-releases by default, which would break the one-liner. Pre-alpha status is stated in the trove
  classifier and the README.
- **`bimai update`** detects the install method from the running interpreter: `uv/tools/bimai` in
  `sys.prefix` → uv; `pipx/venvs/bimai` → pipx; a direct-URL editable install → refuse; otherwise pip
  for that interpreter. `--check` reads `https://pypi.org/pypi/bimai/json` with a short timeout.
- **Trusted Publishing:** the workflow's `publish` job runs in the `pypi` environment with
  `id-token: write` and `pypa/gh-action-pypi-publish`. The maintainer registers a pending publisher on
  PyPI (owner StefanDaniels1, repository BIMAI, workflow `release-bimai.yml`, environment `pypi`).
- **README on PyPI:** image links become absolute URLs so the PyPI page renders the logo.
- **CI:** an `install` job on all three platforms builds the wheel, runs the platform's install script
  with `BIMAI_PACKAGE=<wheel>`, then runs `bimai --version` and `bimai init` in a temporary folder from a
  new shell, proving the PATH setup.

## Risks / Trade-offs

- Company networks may block astral.sh, github.com or pypi.org → the script stops with a message naming
  what it tried; docs give the manual route (`pipx install bimai`).
- `irm … | iex` is a pattern some IT policies distrust → the docs explain what the script does and how to
  download and read it first.
