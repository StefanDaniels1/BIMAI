# Design

## Context

- Claude Code hooks (code.claude.com/docs/en/hooks): `Stop` input includes `last_assistant_message`;
  `Notification` has `type` (`permission_prompt`, `idle_prompt`, `agent_needs_input`, …) and `message`.
  Command hooks accept `"async": true` (background, timeout not enforced). Personal project settings live
  in `.claude/settings.local.json` (gitignored).
- ElevenLabs: `POST /v1/text-to-speech/{voice_id}?output_format=wav_22050` with header `xi-api-key`,
  body `{text, model_id}`; `GET /v2/voices` (filters, `labels.accent`); `eleven_flash_v2_5` is the
  low-latency model (~75 ms), Turbo is deprecated.

## Decisions

- **Hook command:** `bimai voice hook` (exec form, `async: true`). It reads the event from stdin, makes the
  spoken text, and does the network call and playback itself; a pid file lets a newer reply stop an older
  one still speaking.
- **Personal, per project:** hooks in `.claude/settings.local.json`, settings (voice, model, length) in the
  user's bimai config folder (`%APPDATA%\bimai\voice.json`, `~/.config/bimai/voice.json`), the key in the
  keychain (`bimai-voice`). Nothing voice-related is committed to the shared project.
- **Spoken text is deterministic Python** (agents reason, scripts decide): strip fenced code, tables,
  inline code, links (keep their text), headings and list markers; take whole sentences up to the limit.
- **Voices from the person's account**, not hard-coded IDs: `GET /v2/voices?voice_type=default` plus
  their own voices, British first (`labels.accent` contains "british"); the default suggestion is the first
  British male voice described as calm/deep if present, else the first British voice.
- **WAV** so playback needs nothing outside the standard library on Windows.

## Risks / Trade-offs

- Costs: every reply uses ElevenLabs characters → the length limit (400) keeps it low; `status` shows it.
- Privacy: reply text (which may contain project details) goes to ElevenLabs → explicit consent at setup,
  stated in the guide; off by default.
