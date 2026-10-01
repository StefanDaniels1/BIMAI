# Spec Delta

## ADDED Requirements

### Requirement: Product Help on every project
`bimai init` SHALL add Autodesk Product Help to `.mcp.json`, keeping any servers already listed, and
store the seat's declared tools in `seat.yaml` so later regenerations know what was declared. After
writing, it SHALL suggest `bimai connect <server>` for every catalogue server that matches a declared
tool.

#### Scenario: Fresh project
- **WHEN** `bimai init` completes in an empty folder
- **THEN** `.mcp.json` lists `autodesk-help`

#### Scenario: Suggestion for a declared tool
- **WHEN** the user declared Revit during init
- **THEN** the final output suggests `bimai connect revit`
