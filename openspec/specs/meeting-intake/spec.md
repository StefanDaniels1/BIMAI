# meeting-intake Specification

## Purpose
Turn a meeting transcript into speaker turns, match speakers to project people, chunk turns for
extraction, and route extracted items to their destination. Every uncertainty becomes a question for
the uploader instead of a guess. All steps here are deterministic scripts (JSON in, JSON out).

## Requirements

### Requirement: Transcript parsing
The system SHALL parse WebVTT (Teams and Zoom styles), SubRip, Word (.docx Teams download) and plain
text transcripts into an ordered list of speaker turns, each with index, speaker, start time
(normalized `HH:MM:SS`, or null when absent) and text. Consecutive turns by the same speaker SHALL be
merged. The output SHALL include a meeting id that is stable for identical content.

#### Scenario: Teams VTT
- **WHEN** a Teams `.vtt` file with `<v Name>` cues is parsed
- **THEN** each turn carries the speaker name and a normalized start time, and consecutive cues by the same speaker are one turn

#### Scenario: Same content, same id
- **WHEN** the same transcript is parsed twice
- **THEN** both results have the same meeting id

#### Scenario: No turns
- **WHEN** a transcript contains no recognizable speaker turns
- **THEN** parsing fails with an error naming the file

### Requirement: Speaker resolution never guesses
The system SHALL match raw speaker names to people in `people.yaml` in the order: exact name or alias,
unique first name, close spelling. A name with more than one candidate SHALL be reported as
`ambiguous` with its candidates, and a name with none as `unknown`; neither is assigned to a person.

#### Scenario: Two people share a first name
- **WHEN** the speaker is "Jan" and two people are named Jan
- **THEN** the speaker is `ambiguous` with both as candidates and appears in `unresolved`

### Requirement: Chunking with overlap
The system SHALL split turns into chunks under a character budget, overlapping by a configurable
number of turns, such that every turn is in at least one chunk and chunking always progresses even
when a single turn exceeds the budget.

#### Scenario: Huge single turn
- **WHEN** one turn is larger than the budget
- **THEN** chunking terminates and that turn is in its own chunk

### Requirement: Routing asks instead of guessing
The system SHALL route each item to exactly one destination (minutes, decision, task, handoff,
external action with a follow-up task for the uploader, risk review, change request, parking lot,
cover suggestion, dropped or skipped), or produce questions for the uploader. Questions SHALL be
raised for: unknown item type, unclear level, undecided decisions, decisions that contradict earlier
decisions, unresolved or ambiguous owners, relative due dates that cannot be computed, and any
non-summary item with confidence below the `ask_below` setting. Each question SHALL include the
transcript quote and lettered options. The result status SHALL be `needs_answers` while any question
remains and `ready` otherwise.

#### Scenario: First pass on an uncertain meeting
- **WHEN** items include an ambiguous owner and a low-confidence action
- **THEN** status is `needs_answers` and those items have no actions yet

#### Scenario: Answers complete routing
- **WHEN** routing is rerun with an answer for every question
- **THEN** status is `ready`

#### Scenario: External owner
- **WHEN** an action's owner is an external party
- **THEN** it becomes an external action plus a follow-up task for the uploader

### Requirement: Private remarks are never stored
The system SHALL drop items of type `private` with a placeholder text, and availability items SHALL
produce only a cover suggestion to the relevant position leads, storing nothing about the person.

#### Scenario: Availability
- **WHEN** someone says they are away next week
- **THEN** the only output is a cover suggestion notifying the lead of their positions
