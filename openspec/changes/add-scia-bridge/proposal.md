# Proposal

## Why

The **constructeur** (structural engineer) is a key member of Dutch infrastructure and building projects and
has no bimai persona or connection yet. Most of them calculate in SCIA Engineer (Nemetschek). SCIA has no MCP
server; its OpenAPI (shipped with SCIA Engineer, .NET Framework 4.8) can open a project and read calculation
results, and SCIA documents using it from Python through pythonnet (scia-garage/open-api-adm-jupyter).

## What Changes

- **Persona `Constructeur`** (preset): matches "constructeur", "constructief ontwerper", "structural engineer",
  "rekenaar" and similar; goals **Structural results** (new), model checks, deliveries, meetings; typical tools
  SCIA Engineer, IFC, Revit. The interview shows the roles that fit the folder first (a `.esa` file puts the
  Constructeur in the four role options).
- **Team member `Structural Analyst`:** answers questions about internal forces, deformations and reactions with
  the numbers from SCIA, names the load case or combination and the units, never changes the model.
- **SCIA bridge** (`bimai scia serve`, a stdio MCP server in bimai, Windows): starts its own SCIA Engineer in the
  background on first use, opens a **copy** of the project file (the engineer's file is never touched), and
  offers read-only tools: `open_project`, `get_member_results` (internal forces, deformations),
  `get_surface_results` (internal forces, deformations, stresses, strains, contact stresses),
  `get_support_reactions`, and `run_calculation` (linear, on the copy, when results are missing).
- **Catalogue:** tool `scia` (`.esa` files suggest it), capability `analysis.results`, server `scia` (stdio,
  no sign-in, read-only, needs SCIA Engineer 21+ with a license), detected from SCIA's registry entries.
- **Docs:** SCIA bridge guide (beta), connections page, persona in the interview docs.

## Non-goals

- Changing the SCIA model or saving the project (read-only; the copy is closed without saving).
- Code checks (unity checks) and design (beyond the result types SCIA's samples document).
- Other structural programs (Technosoft, Robot, ETABS): later, through the same persona.

## Capabilities

### New Capabilities
- `scia-bridge`: the stdio MCP server, its tools and SCIA detection.

### Modified Capabilities
- `team-configuration`: the Constructeur preset and the Structural Analyst role.

## Impact

- New `cli/bimai/scia.py` (detection, pythonnet backend, results) and `cli/bimai/mcpstdio.py` (a small
  dual-era MCP server over stdio); catalogue (`tools.yaml`, `servers.yaml`, `presets/constructeur.yaml`,
  `roles/structural-analyst.md`); `scan.py` (`.esa`); `interview.py` (role ranking); `connections.py`
  (detection); `pyproject.toml` (pythonnet on Windows only); tests with a fake SCIA; docs.
