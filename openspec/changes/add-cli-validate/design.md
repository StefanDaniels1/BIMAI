# Design

## Context

The repository has packs (plain scripts) but no Python package. ARCHITECTURE.md §4 reserves `cli/`
for the `bimai` package and §12.1 says every bimai file has a JSON Schema. The example project in
`packs/project-site/examples/knooppunt-oost/` is the only real workspace and must validate cleanly.

## Goals / Non-Goals

**Goals:** one installable command, readable problem messages, schemas that later commands reuse.

**Non-Goals:** a plugin system for validators, config options, auto-fixing.

## Decisions

- **Layout:** `cli/bimai/__init__.py` (version), `cli/bimai/__main__.py` + `cli.py` (argparse),
  `cli/bimai/validate.py` (checks, returns a list of problems), `cli/bimai/schemas/*.schema.json`.
  Root `pyproject.toml` with setuptools, `package-dir = {"" = "cli"}`, entry point `bimai = bimai.cli:main`.
  One package for now; split later only if the gateway needs its own.
- **argparse, not click/typer:** stdlib, enough for subcommands. No new dependency.
- **`jsonschema` Draft 2020-12**, with `iter_errors` so all problems are reported, not just the first.
  Location is the error's `absolute_path` joined with dots.
- **Schemas are permissive about extra keys** (`additionalProperties` allowed) except inside workflow
  steps, where an unknown key is usually a typo. This keeps early adopters' files from breaking as
  formats grow.
- **Validation is a pure function** `validate(workspace: Path) -> list[Problem]`; the CLI only
  formats. This is what later commands (`doctor`, the `SessionStart` hook) will call.
- **Cycle detection:** depth-first search over `needs`; report each cycle once.
- **Dates:** YAML parses `2026-09-28` as a date; convert to ISO strings before schema checks so
  schemas can use `"format": "date"` strings.

## Risks / Trade-offs

- Schemas written from one example project may be too strict for real projects → keep required
  fields minimal (ids and references) and loosen based on reports.
- Workflow expression syntax (`${{ }}`) is not checked yet; the engine change will add that.
