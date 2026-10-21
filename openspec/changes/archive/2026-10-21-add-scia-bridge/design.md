# Design

## Context

From SCIA's own MIT-licensed examples (github.com/scia-garage: open-api-adm-dotnet, open-api-adm-jupyter,
SciaOpenAPI_example_CSharp_simple_structure); help.scia.net blocks automated reading:

- The OpenAPI DLLs ship with SCIA Engineer (`<install>\OpenAPI_dll\SCIA.OpenAPI.dll` and dependencies); the
  install folder is in `HKCU\Software\SCIA\ESA\<version>\Admin\Dir` (`SYSTEM`, `Temp`). .NET Framework 4.8, x64.
- `new Environment(installPath, tempPath, "1.0.0.0")`, `env.RunSCIAEngineer(Environment.GuiMode.…)` starts a
  SCIA Engineer instance of its own; `env.OpenProject(file)` returns an `EsaProject`; `project.Model`
  (`Structure`); `project.RunCalculation()`; `project.CloseProject(SaveMode.SaveChangesNo)`.
- Results: `model.InitializeResultsAPI()` (null when nothing is calculated), a `ResultKey` (`CaseType`
  load case or combination, `CaseId = model.FindGuid(name)`, `EntityType`, `EntityName`, `Dimension`,
  `ResultType`, `CoordSystem`), `rapi.LoadResult(key)`; a `Result` has `GetMagnitudesCount`,
  `GetMagnitudeName(i)`, `GetSectionCount`, `GetSectionPosX(i)`, `GetMeshElementCount`, `GetValue(m, i)`,
  `GetTextOutput()`. Result types used in the samples: `eFemBeamInnerForces`, `eFemBeamDeformation`,
  `eFemBeamRelativeDeformation` (1D, beam), `eFemInnerForces`, `eFemDeformations`, `eFemStress`, `eFemStrains`,
  `eFemContactStress` (2D, slab), `eResultTypeReactionsSupport0D` (point support, `eDim_reactionsPoint`).
- The notebook loads the same API from Python with pythonnet (`clr.AddReference`).

## Decisions

- **Python, not a C# add-in:** the OpenAPI drives its own SCIA instance from outside, so the bridge is a
  separate process anyway; pythonnet loads SCIA's DLLs at run time from the user's installation, so nothing of
  SCIA is redistributed and there is no build step. **New dependency `pythonnet` (MIT), Windows only**
  (`sys_platform == "win32"`), justified because it is the documented way to call SCIA's .NET API from Python.
- **stdio MCP server** (`.mcp.json`: `bimai scia serve`): Claude Code starts and stops it with the session.
  SCIA starts lazily on the first tool call (hidden window where SCIA's `GuiMode` offers it) and closes when
  the session ends. One SCIA call at a time.
- **Read-only by construction:** `open_project` copies the `.esa` file to bimai's temp folder and opens the
  copy; the project is always closed with `SaveChangesNo`. `run_calculation` calculates the copy only.
- **Results as data:** 1D results per section (position and magnitudes), 2D results as per-magnitude minimum,
  maximum and the mesh element where they occur (the full mesh can be thousands of values); reactions per
  magnitude. Each result names the case, the entity and the units as the API reports them (SI values from the
  API; the response says so).
- **Load case or combination:** `case_type` `auto` tries the load case first, then the combination.
- **Detection** for onboarding: SCIA versions from the registry (newest with `OpenAPI_dll` first), else
  `Program Files\SCIA\Engineer*`. Not installed → status `needs-app` with SCIA's download page.
- **Role ranking in the interview:** presets whose typical tools the scan found come first; the question
  says that other roles can be typed under "Other".

## Risks / Trade-offs

- Unverified inside SCIA (no SCIA here) → beta, a test guide for a constructeur, clear errors that include
  SCIA's own messages.
- OpenAPI may need a specific SCIA license module → the error says so and the guide mentions it.
