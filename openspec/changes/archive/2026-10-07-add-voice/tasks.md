# Tasks

## 1. Voice

- [x] 1.1 `voice.py`: config, keychain, ElevenLabs client (voices, speech), spoken-text rules, players, pid handling. Verify: tests with a fake ElevenLabs and player; spoken-text cases.
- [x] 1.2 `bimai voice setup|on|off|status|test|hook`. Verify: CLI tests (on/off round trip, bad key, hook never fails).
- [ ] 1.3 (Open: released before a real-key test, at the owner's request; verify on first real use.) Real test with an ElevenLabs key on macOS (and Windows CI for the winsound path with a fake API). Verify: notes in the PR.

## 2. Docs

- [x] 2.1 `guides/voice.mdx` (setup, voices, privacy, costs), CLI reference. Verify: check_docs, site build.
- [x] 2.2 Final check: pytest (strict), openspec validate --all --strict, CI green.
