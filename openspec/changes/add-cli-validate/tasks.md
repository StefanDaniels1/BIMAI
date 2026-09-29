# Tasks

## 1. Package skeleton

- [x] 1.1 Add `[project]` metadata, dependencies (`pyyaml`, `jsonschema`), `bimai` entry point and `cli` package dir to `pyproject.toml`; add `cli/tests` to pytest `testpaths`. Verify: `pip install -e .` succeeds.
- [x] 1.2 Create `cli/bimai/` with `__init__.py` (`__version__`), `__main__.py` and `cli.py` (argparse with `--version` and a `validate` subcommand). Verify: test that `bimai --version` prints the version and exits 0.

## 2. Schema validation

- [x] 2.1 Write schemas for `project`, `people`, `ownership`, `seat`, `workflow`, `automation` in `cli/bimai/schemas/`. Verify: the example project validates against each.
- [x] 2.2 Implement `validate(workspace) -> list[Problem]`: workspace discovery (exit 2 case), YAML loading with parse errors as problems, date normalization, schema checks with dotted locations. Verify: tests for valid example, missing `id`, wrong `needs` type, broken YAML, no workspace.

## 3. Cross-file and workflow checks

- [x] 3.1 Add reference checks (people, positions, seats, automation owners). Verify: test with an unknown person in `held_by` and an unknown position in a seat.
- [x] 3.2 Add workflow graph checks (unknown `needs`, cycles, exactly one step type). Verify: tests for unknown step, two-step cycle, step with two types.

## 4. Output, CI and docs

- [x] 4.1 Implement text and `--json` output and exit codes 0/1/2. Verify: tests for the problem lines + summary, and JSON on a valid workspace.
- [x] 4.2 In `ci.yml`, install the package and run `bimai validate packs/project-site/examples/knooppunt-oost`. Verify: the command passes locally.
- [x] 4.3 Mark `bimai validate` as available in `docs/content/docs/reference/commands.mdx` and add a short "Checking your files" note with example output. Verify: `python scripts/check_docs.py` passes.
- [x] 4.4 Final check: `python -m pytest -q`, `openspec validate --all --strict` and `python scripts/check_docs.py` all pass.
