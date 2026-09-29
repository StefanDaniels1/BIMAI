# Proposal

## Why

Every later building block (workflow engine, onboarding, sites, automations) reads `.bimai/` YAML
files, and today nothing checks them. A typo in `ownership.yaml` or a workflow with a missing step
only shows up as a confusing failure later. An installable `bimai` command with `bimai validate` is
the smallest usable first slice of build step 1 (ARCHITECTURE.md §14), and it gives the project a
home for every CLI command that follows.

## What Changes

- A `bimai` Python package in `cli/`, installable with `pip install -e .` or `uv tool install .`,
  providing a `bimai` command with `--version`.
- `bimai validate [PATH]`: checks the `.bimai/` workspace at PATH (default: current directory)
  and prints one line per problem as `<file>: <location>: <message>`. Exit code 0 when valid,
  1 when problems are found, 2 when no workspace is found.
- JSON Schemas (shipped inside the package) for `project.yaml`, `people.yaml`, `ownership.yaml`,
  `seats/*/seat.yaml`, `workflows/*.yaml` and `automations/*.yaml`.
- Cross-file checks that a schema can't express: people referenced in ownership and seats exist,
  positions referenced in seats and cover exist, workflow `needs` refer to existing steps, and
  workflows have no cycles.
- The example project and CI both run `bimai validate`, so the example can't drift from the schemas.
- Docs: `bimai validate` marked available in the command reference.

## Non-goals

- Schemas for the other files named in §12.1 (agreements, tasks, team, preset, pack, connector,
  mapping, connectors, projects). Each gets added when the feature that reads it is built.
- Checking that capabilities, packs or sub-workflows referenced by a workflow are installed
  (needs the gateway and pack registry, not built yet).
- Registering schemas in `.vscode/settings.json` (belongs to `bimai init`).
- Any other command (`init`, `graph`, `workflow run`, …).

## Capabilities

### New Capabilities
- `workspace-validation`: the `bimai` command and `bimai validate`, what it checks and how it reports problems.

### Modified Capabilities
<!-- none -->

## Impact

- New: `cli/bimai/` package, `cli/tests/`, `[project]` metadata and a `bimai` entry point in `pyproject.toml`.
- Dependencies: `pyyaml`, `jsonschema` (both already used by the packs and CI).
- CI: `ci.yml` installs the package and validates the example project.
- Docs: `docs/content/docs/reference/commands.mdx`.
