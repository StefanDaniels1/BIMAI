# Tasks

## 1. Catalogue

- [ ] 1.1 Re-check each server against its Autodesk documentation page and write `cli/bimai/catalogue/servers.yaml` (Product Help, Revit read-only, Fusion, Fusion Data, Hydraulic Modeling) with auth, access, platforms, regions, provides, docs link and config; add `docs.search` and the new capabilities to `tools.yaml` where roles need them. Verify: catalogue test for completeness and consistency.

## 2. .mcp.json and settings

- [ ] 2.1 Read, add and remove entries in `.mcp.json` without touching others; refuse invalid JSON. Verify: tests for keeping an existing server, invalid JSON, removing.
- [ ] 2.2 Add and remove the `mcp__<server>` ask rule in `.claude/settings.json`, keeping other settings. Verify: tests for adding, removing, existing permissions kept.
- [ ] 2.3 Confirm with Claude Code docs or a real session that `permissions.ask: ["mcp__<server>"]` prompts for every tool of that server. Verify: note the result in design.md.

## 3. bimai connect / disconnect

- [ ] 3.1 `bimai connect` listing with status, access and plain-language sign-in text. Verify: test on the output.
- [ ] 3.2 `bimai connect <server>`: platform check, Revit detection on Windows, `--region` (ask when interactive), read-write consent (`--allow-writes`), unknown server, then team regeneration. Verify: tests for public server, Revit on macOS, Revit not installed on Windows (mocked), region, consent refused, ask rule added.
- [ ] 3.3 `bimai connect --custom <name> --url <url> --auth key|none [--header] [--scheme]`. Verify: test for the generated entry with `headersHelper`.
- [ ] 3.4 `bimai disconnect <server>`: removes entry, ask rule and credential, regenerates the team. Verify: tests.

## 4. bimai auth

- [ ] 4.1 `bimai auth login`: `claude mcp login <server>` for sign-in servers (fallback text without the CLI); hidden key prompt into the keychain for key servers; offered by `connect`. Verify: tests with a mocked `claude` and an in-memory keyring backend.
- [ ] 4.2 `bimai auth headers` (helper): reads the key for `CLAUDE_CODE_MCP_SERVER_NAME`, prints header JSON, nothing on stdout and non-zero without a key. Verify: tests for bearer, raw, missing key.
- [ ] 4.3 `bimai auth status` and `bimai auth logout`. Verify: tests that status never contains the key, logout removes it.
- [ ] 4.4 Confirm `claude mcp login` works for a project `.mcp.json` server (trust/approval), in a real session. Verify: note the result in design.md; adjust the fallback text if needed.

## 5. Team integration

- [ ] 5.1 Subagent `mcpServers` from capabilities; confirm `mcpServers: []` semantics in Claude Code docs. Verify: test for the Model Checker / Scribe scenario.
- [ ] 5.2 Connections section in the `CLAUDE.md` block, with declared-but-not-connected tools from `seat.yaml` `tools`. Verify: tests for connected, declared-not-connected and no connections.
- [ ] 5.3 `bimai init`: store `tools` in `seat.yaml` (schema updated), add Product Help to `.mcp.json`, suggest `bimai connect` for declared tools. Verify: tests; existing init tests still pass.

## 6. Validate

- [ ] 6.1 `.mcp.json` secret checks (literal header/env values, `clientSecret`, invalid JSON), never printing values. Verify: tests for a literal token, a `${VAR}` reference, invalid JSON.

## 7. Documentation

- [ ] 7.1 New guide `docs/content/docs/guides/connections.mdx`: the servers, how sign-in works, read-only vs read-write, what is never stored where; commands in the reference; update ARCHITECTURE.md §7.6, §8.1 (interim without gateway) and §11.3 (sign-in via the harness, `headersHelper`). Verify: `check_docs.py` passes and the site builds.
- [ ] 7.2 Hand test on macOS: init, `bimai connect`, `autodesk-help` in a real Claude Code session ("search Revit help for worksharing"), a custom key server with the helper. Verify: notes in the PR.
- [ ] 7.3 Final check: `pytest` (strict encoding mode), `openspec validate --all --strict`, `check_docs.py`.
