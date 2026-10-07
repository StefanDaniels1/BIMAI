# Spec Delta

## Purpose
Let the team speak its replies and notifications aloud with a voice the person chooses (ElevenLabs, their
own key), through Claude Code hooks, without getting in the way or sharing anything with the team.

## ADDED Requirements

### Requirement: Voice setup
`bimai voice setup` SHALL ask for an ElevenLabs API key (or take it from `--key-stdin`), store it in the
operating system's keychain, verify it, list the voices available to that account with British voices
first, and save the chosen voice (or a voice ID the person gives). It SHALL state that spoken text is sent
to ElevenLabs and SHALL save nothing without the person's yes (or `--yes`).

#### Scenario: British voices first
- **WHEN** the account has British and American voices
- **THEN** the British voices are listed first and one of them is suggested

#### Scenario: Bad key
- **WHEN** ElevenLabs rejects the key
- **THEN** nothing is saved and the message says the key was not accepted

### Requirement: Voice hooks
`bimai voice on` SHALL add `Stop` and `Notification` command hooks running `bimai voice hook` in the
background (`async`) to the project's `.claude/settings.local.json`, keeping all other settings, and make
sure that file is gitignored. `bimai voice off` SHALL remove exactly those hooks.

#### Scenario: On and off
- **WHEN** the person runs `bimai voice on` and then `bimai voice off`
- **THEN** `.claude/settings.local.json` is as it was before

### Requirement: Spoken text
For a `Stop` event the hook SHALL speak the reply's first sentences without code blocks, tables, Markdown
markers (inline code keeps its words) and URLs, up to the configured limit (default 400 characters). For a
`Notification` it SHALL speak a short sentence for permission and input requests. Any failure SHALL be
logged and the hook SHALL exit 0.

#### Scenario: Reply with code
- **WHEN** the reply is a sentence, a code block and a table
- **THEN** only the sentence is spoken

#### Scenario: No key or no network
- **WHEN** the key is missing or ElevenLabs can't be reached
- **THEN** nothing is played, the reason is logged, and the hook exits 0

### Requirement: Playback
The hook SHALL request WAV from ElevenLabs and play it with `winsound` on Windows, `afplay` on macOS and
`paplay` or `aplay` on Linux, stopping speech from an earlier reply that is still playing.

#### Scenario: Newer reply
- **WHEN** a reply arrives while the previous one is still being spoken
- **THEN** the previous one stops and the new one plays
