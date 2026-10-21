# Spec Delta

## ADDED Requirements

### Requirement: Constructeur
The catalogue SHALL contain the preset `constructeur` (label "Constructeur") matching Dutch and English names
for a structural engineer, with the goal `calculations` ("Structural results") and the role
`structural-analyst`, which requires the capability `analysis.results` (provided by the `scia` tool). The
interview SHALL put the presets whose typical tools the folder scan found first among its four role options.

#### Scenario: A SCIA project folder
- **WHEN** the folder contains a `.esa` file
- **THEN** "Constructeur" is the first role option and SCIA Engineer is suggested as a tool

#### Scenario: Constructeur team
- **WHEN** a constructeur chooses Structural results and SCIA Engineer
- **THEN** the team includes the Structural Analyst
