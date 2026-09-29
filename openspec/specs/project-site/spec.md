# project-site Specification

## Purpose
Generate a readable documentation site (Fumadocs MDX pages) from a project's shared `.bimai/` files,
for people who never open an editor. Deterministic, so the site always matches the project files.

## Requirements

### Requirement: Site generation
Given a project root containing `.bimai/project.yaml`, the system SHALL write an overview, people,
AI teams, how-we-work, agreements, decisions, this-week and one page per applied meeting, plus a
navigation file, into the output folder, replacing its previous contents. Pages SHALL be written in
the project language (`en` or `nl`, falling back to `en`).

#### Scenario: Demo project
- **WHEN** the generator runs on the example project
- **THEN** every page listed above exists in the output folder

#### Scenario: Missing project
- **WHEN** the project root has no `.bimai/project.yaml`
- **THEN** generation fails with a clear error naming the root

### Requirement: Only shared information is published
The system SHALL read only files the project shares with its whole team. It SHALL NOT read raw
transcripts, raw data exports or anyone's desk, SHALL NOT publish private journal sessions, and SHALL
NOT publish meetings that are not yet `applied`.

#### Scenario: Pending meeting
- **WHEN** a meeting folder has status other than `applied`
- **THEN** no page is generated for it

### Requirement: User text cannot inject markup
All text taken from project files SHALL be escaped so it renders as text, never as JSX, expressions
or broken tables.

#### Scenario: JSX in a decision title
- **WHEN** a decision title contains `<script>` or `{…}`
- **THEN** the generated page shows it as literal text

### Requirement: Shareable source documents
When a public directory is given, the system SHALL copy the project's declared source documents
(such as the BEP) there, so pages can link to them for download.

#### Scenario: BEP download
- **WHEN** the generator runs with `--public-dir`
- **THEN** the BEP file is copied there and the agreements page links to it
