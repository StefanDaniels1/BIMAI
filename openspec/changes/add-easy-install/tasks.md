# Tasks

## 1. Package and release

- [x] 1.1 `pyproject.toml` metadata for PyPI (classifiers, keywords, URLs), version 0.1.0, README with absolute image URLs. Verify: `uv build` produces a wheel with catalogue and schemas; `twine`-style metadata check passes.
- [x] 1.2 `.github/workflows/release-bimai.yml`: on `v*` tags, test, build, check tag = version and wheel contents, publish via Trusted Publishing, attach to a GitHub release. Verify: YAML valid; version check tested locally.

## 2. Install scripts

- [x] 2.1 `docs/public/install.sh` and `install.ps1` (uv if missing, `uv tool install --upgrade`, PATH, version, next step, `BIMAI_PACKAGE`, clear failures). Verify: install.sh run locally against the built wheel in a clean HOME.
- [ ] 2.2 CI `install` job on Windows, macOS and Linux with `BIMAI_PACKAGE=<wheel>`, then `bimai --version` and `bimai init` from a new shell. Verify: green on the PR.

## 3. bimai update

- [x] 3.1 `cli/bimai/update.py` (install method detection, update command, `--check` against PyPI) and CLI wiring. Verify: tests for uv, pipx, pip, editable, check newer/same/offline.

## 4. Docs

- [x] 4.1 Install page, landing prompt (`docs/lib/prompts.ts`), README quick start and command reference use the new commands; PyPI publisher setup documented for maintainers. Verify: check_docs, site build.
- [ ] 4.2 Final check: pytest (strict), openspec validate --all --strict, check_docs, CI green.
