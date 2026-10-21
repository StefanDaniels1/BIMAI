# scia-bridge Specification

## Purpose
Let a constructeur's team read calculation results from SCIA Engineer, without ever changing the model.

## Requirements

### Requirement: SCIA bridge server
`bimai scia serve` SHALL be an MCP server over stdio (both protocol eras, like the other bimai bridges) with the
tools `open_project`, `get_member_results`, `get_surface_results`, `get_support_reactions` and
`run_calculation`, all read-only for the person's files. It SHALL start SCIA Engineer only on the first tool
call that needs it, and close it when the session ends.

#### Scenario: Tools listed without SCIA
- **WHEN** a client lists the tools
- **THEN** the five tools are returned, without starting SCIA Engineer

### Requirement: Never touch the project file
`open_project` SHALL copy the given `.esa` file and open the copy; the bridge SHALL close projects without
saving and SHALL never write to the original file.

#### Scenario: Original untouched
- **WHEN** a project is opened, calculated and closed through the bridge
- **THEN** the original `.esa` file's bytes are unchanged

### Requirement: Results
Result tools SHALL take the case name (load case or combination; `auto` tries both) and the entity name as SCIA
shows them, and SHALL return the magnitudes with their names: per section for members, minimum and maximum per
magnitude (with the mesh element) for surfaces, and per magnitude for supports, naming the case, the entity and
that values are in the units of SCIA's API. When nothing is calculated, they SHALL say so and point to `run_calculation`.

#### Scenario: Member internal forces
- **WHEN** the client asks for internal forces of member B3 in load case LC1
- **THEN** the result lists each section's position with N, Vy, Vz, Mx, My, Mz (as SCIA names them)

### Requirement: Detection
bimai SHALL find installed SCIA Engineer versions (registry, then Program Files) and report the `scia`
connection as `ready` when one with the OpenAPI is installed on Windows, `needs-app` otherwise.

#### Scenario: No SCIA
- **WHEN** SCIA Engineer isn't installed
- **THEN** onboarding reports the SCIA connection as needing SCIA Engineer, with no command
