# Tasks

## 1. Releases

- [x] 1.1 `.github/workflows/release-civil3d-bridge.yml`: on `civil3d-bridge-v*` tags, test, build on Windows, check tag = bridge version, publish zip + SHA256SUMS.txt as a (pre-)release. Verify: YAML valid; version check script tested locally.
- [x] 1.2 Catalogue `release` data for `civil3d` (repo, tag, asset, sha256 or null). Verify: catalogue test.

## 2. Installer (cli/bimai/bridges.py)

- [x] 2.1 Download with size cap and SHA-256 verification; `--from`; zip validation and extraction. Verify: tests with a local zip, a tampered download and no pinned hash.
- [x] 2.2 Windows install: Civil 3D running check, elevated run of the zip's install.ps1, exit codes, confirmation via the installed bundle; clear messages for declined prompt, failure and non-Windows. Verify: tests with mocked processes.
- [x] 2.3 Status (installed version, update available, running via server/discover) and uninstall. Verify: tests, including status against a local fake bridge server.

## 3. Flows

- [x] 3.1 `bimai bridge install|status|uninstall` commands. Verify: CLI tests.
- [x] 3.2 `bimai connect` offers install when the bundle is missing, then connects; health check after connecting local bridges. Verify: tests.
- [x] 3.3 `bimai init` offers install + connect for declared bridge tools. Verify: tests.

## 4. Docs and checks

- [x] 4.1 Civil 3D guide rewritten around one command; IT section; command reference. Verify: check_docs, site build.
- [ ] 4.2 Final check: pytest (strict), openspec validate --all --strict, check_docs; CI green.
