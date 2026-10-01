# Spec Delta

## ADDED Requirements

### Requirement: Subagents get only their role's servers
Every generated subagent SHALL be able to use exactly the servers in `.mcp.json` that provide a
capability its role requires or uses, so each member reaches only the tools its job needs. Every other
server in `.mcp.json` SHALL be listed in the subagent's frontmatter `disallowedTools` as
`mcp__<server>`. Servers bimai doesn't know (custom servers without capabilities) SHALL be available to
the Coordinator only. When the servers in `.mcp.json` change, the next regeneration SHALL update the
lists.

#### Scenario: Model Checker gets Revit
- **WHEN** `.mcp.json` lists `revit` and `autodesk-help`, and the team has the Model Checker and the Scribe
- **THEN** the Model Checker's subagent disallows `mcp__autodesk-help` but not `mcp__revit`, and the Scribe's disallows both

### Requirement: Connections section
The `CLAUDE.md` block SHALL contain a Connections section listing each server in `.mcp.json` with what
it provides, whether it can change data, and which members use it; and listing the tools and data the
seat declared that no connected server provides, saying they are declared but not connected. With no
servers, it SHALL say the team has no connections and that exports can be placed in the project.

#### Scenario: Declared but not connected
- **WHEN** the seat declared ACC and no server in `.mcp.json` provides issues
- **THEN** the Connections section says ACC is declared but not connected
