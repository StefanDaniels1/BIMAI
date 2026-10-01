# Contributing to bimai

Thanks for helping build bimai. At this stage the most useful contributions are real BIM workflows,
eval scenarios, and code for the next step in the [build order](ARCHITECTURE.md#14-mvp-and-build-order).

## Setup

```bash
pip install pyyaml jsonschema pytest python-docx
npm install -g @fission-ai/openspec@1.13.2
python -m pytest -q
```

Working on a bridge (`bridges/`)? You also need the .NET 8 and .NET 10 SDKs:
`dotnet test bridges/civil3d/tests/Bimai.Mcp.Tests`. The add-in compiles on macOS and Linux too, but only
runs inside Civil 3D on Windows.

## How changes are made: specs first

bimai uses [OpenSpec](https://github.com/Fission-AI/OpenSpec). Behavior is agreed in a short spec
before code is written, so reviewers discuss *what* before *how*.

1. Open an issue or discussion for anything larger than a bug fix.
2. Propose the change: `/opsx:propose <idea>` in Claude Code (or `openspec new change <name>` and
   fill in the files by hand). This creates `openspec/changes/<name>/`.
3. Open a draft pull request with only the proposal. Once it's agreed, implement it (`/opsx:apply`).
4. When CI is green, archive it (`/opsx:archive`) so `openspec/specs/` reflects what's built.

Bug fixes, refactors without behavior change, and documentation fixes can skip steps 2–4.

## Pull request checklist

- [ ] Tests added or updated, and `python -m pytest -q` passes
- [ ] `openspec validate --all --strict` passes
- [ ] User-facing change? Its page in `docs/` is updated, and `python scripts/check_docs.py` passes

See [AGENTS.md](AGENTS.md) for the project rules. Agents and humans follow the same ones.
