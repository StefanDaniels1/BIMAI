# Tasks

## 1. Voice

- [ ] 1.1 `voice.py`: config, keychain, ElevenLabs client (voices, speech), spoken-text rules, players, pid handling. Verify: tests with a fake ElevenLabs and player; spoken-text cases.
- [ ] 1.2 `bimai voice setup|on|off|status|test|hook`. Verify: CLI tests (on/off round trip, bad key, hook never fails).
- [ ] 1.3 Real test with an ElevenLabs key on macOS (and Windows CI for the winsound path with a fake API). Verify: notes in the PR.

## 2. Docs

- [ ] 2.1 `guides/voice.mdx` (setup, voices, privacy, costs), CLI reference. Verify: check_docs, site build.
- [ ] 2.2 Final check: pytest (strict), openspec validate --all --strict, CI green.
