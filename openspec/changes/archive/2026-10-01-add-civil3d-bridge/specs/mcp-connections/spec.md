# Spec Delta

## ADDED Requirements

### Requirement: Civil 3D bridge in the catalogue
The catalogue SHALL contain `civil3d`: bimai's own Civil 3D bridge, local, no sign-in, read-only,
Windows only, providing model, drawing, alignment, surface, corridor and pipe queries, with the
`.mcp.json` entry `http://127.0.0.1:27184/mcp`. `bimai connect civil3d` SHALL succeed only when the
bundle is installed in an ApplicationPlugins folder, and otherwise explain how to install it.
`--port` SHALL override the port for servers that support it.

#### Scenario: Bridge not installed
- **WHEN** the user runs `bimai connect civil3d` on Windows without the bundle installed
- **THEN** nothing is written and the output explains how to install the bridge

#### Scenario: Bridge installed
- **WHEN** the bundle is installed and the user runs `bimai connect civil3d`
- **THEN** `.mcp.json` gets `civil3d` with URL `http://127.0.0.1:27184/mcp`, and the Model Checker may use it
