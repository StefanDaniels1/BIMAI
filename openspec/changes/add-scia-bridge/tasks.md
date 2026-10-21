# Tasks

## 1. Persona

- [ ] 1.1 Catalogue: goal `calculations`, capability `analysis.results`, tool `scia` (+ `.esa`), role `structural-analyst`, preset `constructeur`. Verify: catalogue tests; team proposal test.
- [ ] 1.2 Interview: role options ranked by found tools. Verify: test with a `.esa` folder.

## 2. Bridge

- [ ] 2.1 `mcpstdio.py`: MCP over stdio (initialize, server/discover, tools/list, tools/call, ping). Verify: protocol tests.
- [ ] 2.2 `scia.py`: detection, pythonnet backend (lazy start, copy, results, calculation, close), tools. Verify: tests with a fake SCIA; original file untouched.
- [ ] 2.3 Catalogue server `scia`, connection status, `bimai scia serve|status`, pythonnet on Windows. Verify: tests; Windows CI loads pythonnet with .NET Framework.

## 3. Docs and checks

- [ ] 3.1 SCIA bridge guide (beta) with a test section for a constructeur; connections page. Verify: check_docs, site build.
- [ ] 3.2 Final check: pytest (strict), openspec validate --all --strict, CI green.
