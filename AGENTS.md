# Working on bimai

Instructions for AI coding agents (Claude Code, Codex, Copilot, …) and humans alike.

## Where things are

| Path | What |
|---|---|
| `ARCHITECTURE.md` | The long-term design. Read the relevant section before proposing a change. It is a target, not a spec. |
| `openspec/specs/` | What is **built and tested today**. The contract for current behavior. |
| `openspec/changes/` | Changes in progress: proposal, design, spec deltas, tasks. |
| `packs/` | Packs (skill + deterministic scripts + tests). `packs/meeting-intake/` is the reference layout. |
| `docs/` | Documentation site (Fumadocs). Documentation is part of done. |
| `scripts/check_docs.py` | CI check: every command and pack has a page. |

## Spec-driven workflow (OpenSpec)

Every change to behavior goes through OpenSpec:

1. **Propose:** `/opsx:propose <idea>` creates `openspec/changes/<name>/` with proposal, spec deltas, design and tasks. Stop here and get the proposal reviewed.
2. **Apply:** `/opsx:apply <name>` implements the tasks, with tests, one at a time.
3. **Archive:** `/opsx:archive <name>` merges the spec deltas into `openspec/specs/` once CI is green.

Use `/opsx:explore` to think something through before proposing. Typos, refactors without behavior change, and docs-only fixes don't need a change.

Pick changes from the build order in `ARCHITECTURE.md` §14, one small usable slice at a time.

## Rules

- **Keep it simple.** Smallest change that works on its own. No speculative abstractions or options.
- **Agents reason, scripts decide.** Anything checkable is deterministic Python: JSON in, JSON out.
- **Python 3.11+, stdlib first.** Allowed dependencies: `pyyaml`, `jsonschema`. Add others only with a justification in the change's `design.md`.
- **Cross-platform.** `pathlib` for paths; no shell scripts in the product; UTF-8 explicitly on every file read/write.
- **Never read or publish private data** (raw transcripts, desks, secrets) unless a spec says so.
- **Tests with every change.** Fixtures live next to the tests.
- **Docs with every user-facing change**, in the same pull request.

## Before you finish

```bash
python -m pytest -q                 # all tests
openspec validate --all --strict    # specs and changes are well-formed
python scripts/check_docs.py        # every command and pack has a page
```
