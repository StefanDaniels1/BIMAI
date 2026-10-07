# Proposal

## Why

A team that speaks back makes bimai feel like a personal assistant on site or at the desk: hands busy in
Revit or Civil 3D, eyes on the model, and the team says what it found or that it needs an approval.
Claude Code's hooks make this possible without changing how Claude works: a hook gets every finished
reply (`Stop`, with `last_assistant_message`) and every "I need you" moment (`Notification`), and can run
in the background (`async`). ElevenLabs turns text into natural speech; the person brings their own key.

## What Changes

- **`bimai voice setup`** (bring your own ElevenLabs key): stores the key in the computer's keychain (like
  other bimai keys), checks it, lists the **British voices** available in the person's ElevenLabs account
  (from ElevenLabs' voice list, filtered on accent) and lets them pick one, or take any voice ID from their
  own library (for example an original voice made with ElevenLabs' Voice Design). Says plainly that the
  spoken text is sent to ElevenLabs, and only continues after a yes.
- **`bimai voice on` / `off` / `status` / `test`:** `on` adds two background hooks to the project's
  personal `.claude/settings.local.json` (not shared with the team): `Stop` speaks a short spoken version
  of each reply; `Notification` says when the team needs an approval or input. `off` removes them.
- **What is spoken:** the first sentences of the reply, without code, tables, links and Markdown, at most
  about 400 characters (configurable), so it sounds like a briefing rather than a document being read out.
  A new reply stops the previous one.
- **Playback without extra software:** ElevenLabs returns WAV; Windows plays it with Python's built-in
  `winsound`, macOS with `afplay`, Linux with `paplay` or `aplay`.
- **Never in the way:** the hooks run in the background; any problem (no key, no network, quota) is logged
  and Claude carries on silently.
- **Docs:** a "Voice" guide: setup, choosing a British voice, privacy, costs, and why bimai doesn't offer
  a copy of a film character's voice.

## Non-goals

- Speaking to the team (voice input). Windows (Win+H) and macOS dictation already work in Claude Code.
- Cloning or recommending voices of real people or characters (ElevenLabs' policy and their rights).
- Other text-to-speech providers (one well-supported provider first).

## Capabilities

### New Capabilities
- `voice`: setup, hooks, spoken text, playback.

## Impact

- New `cli/bimai/voice.py`; `cli.py` (`bimai voice …`); tests with a fake ElevenLabs and player.
- `.gitignore` lines for `.claude/settings.local.json` (if missing). Docs: `guides/voice.mdx`, CLI page.
- Dependencies: none new (urllib, wave/winsound from the standard library; keyring already used).
