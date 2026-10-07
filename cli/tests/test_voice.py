"""Spoken replies (voice.py): ElevenLabs is simulated, the keychain and the audio player are fakes.

No real key is ever used in tests or stored in the repository: people bring their own.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import urllib.error
import wave
from pathlib import Path

import pytest

from bimai import connections as conn
from bimai import voice
from bimai.cli import main

ROOT = Path(__file__).resolve().parents[2]
FAKE_KEY = "test-key-not-real"

VOICES = {"voices": [
    {"voice_id": "us1", "name": "Adam", "category": "premade", "labels": {"accent": "american", "gender": "male", "description": "deep"}},
    {"voice_id": "uk2", "name": "Lily", "category": "premade", "labels": {"accent": "british", "gender": "female", "description": "warm"}},
    {"voice_id": "uk1", "name": "Daniel", "category": "premade", "labels": {"accent": "british", "gender": "male", "description": "deep, authoritative"}},
    {"voice_id": "ua1", "name": "Oksana", "category": "premade", "labels": {"accent": "ukrainian", "gender": "female", "description": "calm"}},
]}


def silence(seconds=0.05) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\0\0" * int(22050 * seconds))
    return buffer.getvalue()


class FakeElevenLabs:
    def __init__(self):
        self.spoken: list[dict] = []
        self.offline = False

    def __call__(self, request, timeout=None):
        if self.offline:
            raise urllib.error.URLError("no network")
        if request.headers.get("Xi-api-key") != FAKE_KEY:
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail": "bad key"}'))
        if request.full_url.startswith(f"{voice.API}/v2/voices"):
            return io.BytesIO(json.dumps(VOICES).encode())
        assert request.full_url.endswith(f"?output_format={voice.OUTPUT_FORMAT}")
        self.spoken.append({"voice": request.full_url.split("/text-to-speech/")[1].split("?")[0], **json.loads(request.data)})
        return io.BytesIO(silence())


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, user, password):
        self.store[(service, user)] = password

    def get_password(self, service, user):
        return self.store.get((service, user))


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    keyring = FakeKeyring()
    monkeypatch.setattr(conn, "_keyring", lambda: keyring)
    return keyring


@pytest.fixture
def api(monkeypatch):
    fake = FakeElevenLabs()
    monkeypatch.setattr(voice.urllib.request, "urlopen", fake)
    return fake


@pytest.fixture
def played(monkeypatch):
    heard = []
    monkeypatch.setattr(voice, "play", lambda audio, token, environ=None: heard.append(audio))
    return heard


def set_up(monkeypatch, *extra):
    monkeypatch.setattr("sys.stdin", io.StringIO(FAKE_KEY + "\n"))
    return main(["voice", "setup", "--key-stdin", "--yes", *extra])


# -- what is said ----------------------------------------------------------------

def test_spoken_text_leaves_out_code_tables_and_markdown():
    reply = ("**Done.** The model check found `3` issues, see [the report](https://x.example/r).\n\n"
             "```python\nprint('hello')\n```\n\n| Issue | Level |\n|---|---|\n| Clash | high |\n\n"
             "## Next\n- Fix the clash at https://example.com/a\n")
    assert voice.spoken_text(reply) == "Done. The model check found 3 issues, see the report. Next. Fix the clash at."


def test_spoken_text_keeps_whole_sentences_within_the_limit():
    reply = "First sentence here. Second one is a bit longer. Third would be too much."
    assert voice.spoken_text(reply, 50) == "First sentence here. Second one is a bit longer."
    long = "word " * 200
    cut = voice.spoken_text(long, 60)
    assert cut.endswith("…") and len(cut) <= 61
    assert voice.spoken_text("") == "" and voice.spoken_text("```\nonly code\n```") == ""


def test_notification_text():
    assert voice.notification_text({"type": "permission_prompt", "message": "Bash requires permission to run: npm test"}) == \
        "I need your approval. Bash requires permission to run: npm test"
    assert voice.notification_text({"type": "agent_needs_input", "message": ""}) == "I need your input."
    assert voice.notification_text({"type": "idle_prompt", "message": "Claude is waiting"}) == ""


# -- voices ----------------------------------------------------------------------

def test_british_voices_first_and_a_calm_british_suggestion(api):
    voices = voice.list_voices(FAKE_KEY)
    assert [v["name"] for v in voices] == ["Daniel", "Lily", "Adam", "Oksana"]      # Ukrainian isn't "uk"
    assert voice.suggest(voices)["name"] == "Daniel"


def test_bad_key(api):
    with pytest.raises(voice.KeyRejected, match="didn't accept the key"):
        voice.list_voices("wrong")


# -- setup -----------------------------------------------------------------------

def test_setup_stores_key_in_the_keychain_and_settings_outside_the_project(api, home, monkeypatch, capsys, tmp_path):
    assert set_up(monkeypatch) == 0
    assert home.store[(voice.KEYRING_SERVICE, voice.KEYRING_USER)] == FAKE_KEY
    config = voice.load_config()
    assert config["voice_id"] == "uk1" and config["voice_name"] == "Daniel" and config["model"] == "eleven_flash_v2_5"
    assert FAKE_KEY not in (voice.config_dir() / "voice.json").read_text(encoding="utf-8")
    assert "sent to ElevenLabs" in capsys.readouterr().out


def test_setup_with_a_chosen_voice(api, monkeypatch):
    assert set_up(monkeypatch, "--voice", "lily") == 0
    assert voice.load_config()["voice_id"] == "uk2"
    assert set_up(monkeypatch, "--voice", "MyDesignedVoiceId") == 0                 # any ID from their own library
    assert voice.load_config()["voice_id"] == "MyDesignedVoiceId"


def test_setup_with_a_rejected_key_saves_nothing(api, home, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("wrong\n"))
    assert main(["voice", "setup", "--key-stdin", "--yes"]) == 2
    assert home.store == {} and voice.load_config() == {}
    assert "Nothing was saved" in capsys.readouterr().err


# -- hooks in the project ----------------------------------------------------------

def test_on_off_round_trip_keeps_other_settings(api, monkeypatch, tmp_path):
    set_up(monkeypatch)
    project = tmp_path / "project"
    (project / ".claude").mkdir(parents=True)
    original = {"permissions": {"allow": ["Bash(ls)"]},
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "my-own-hook"}]}]}}
    path = project / ".claude" / "settings.local.json"
    path.write_text(json.dumps(original), encoding="utf-8")

    assert main(["voice", "on", "--path", str(project)]) == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    ours = [h for g in data["hooks"]["Stop"] for h in g["hooks"] if h.get("args") == ["voice", "hook"]]
    assert ours and ours[0]["async"] is True
    assert data["hooks"]["Notification"][0]["matcher"] == voice.NOTIFY_MATCHER
    assert data["permissions"] == original["permissions"]
    assert ".claude/settings.local.json" in (project / ".gitignore").read_text(encoding="utf-8")
    assert main(["voice", "on", "--path", str(project)]) == 0                        # twice: still one of each
    data = json.loads(path.read_text(encoding="utf-8"))
    assert sum(h.get("args") == ["voice", "hook"] for g in data["hooks"]["Stop"] for h in g["hooks"]) == 1

    assert main(["voice", "off", "--path", str(project)]) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == original


def test_on_needs_setup_first(tmp_path, capsys):
    assert main(["voice", "on", "--path", str(tmp_path)]) == 2
    assert "bimai voice setup" in capsys.readouterr().err


# -- the hook --------------------------------------------------------------------

def stop_event(text, **extra):
    return json.dumps({"hook_event_name": "Stop", "last_assistant_message": text, **extra})


def test_hook_speaks_a_short_version_of_the_reply(api, played, monkeypatch):
    set_up(monkeypatch)
    assert voice.hook(stop_event("All **three** checks passed.\n\n```\nlog\n```")) == 0
    assert api.spoken == [{"voice": "uk1", "text": "All three checks passed.", "model_id": "eleven_flash_v2_5"}]
    assert len(played) == 1
    assert voice.hook(json.dumps({"hook_event_name": "Notification", "type": "permission_prompt", "message": "Edit a file"})) == 0
    assert api.spoken[-1]["text"] == "I need your approval. Edit a file"


def test_hook_never_fails(api, played, monkeypatch):
    assert voice.hook(stop_event("Hello.")) == 0                                     # not set up: logged, quiet
    assert "No voice chosen" in (voice.config_dir() / "voice.log").read_text(encoding="utf-8")
    set_up(monkeypatch)
    api.offline = True
    assert voice.hook(stop_event("Hello.")) == 0
    assert "Couldn't reach ElevenLabs" in (voice.config_dir() / "voice.log").read_text(encoding="utf-8")
    assert voice.hook("not json") == 0
    assert voice.hook(stop_event("Hello.", stop_hook_active=True)) == 0
    assert played == []


def test_cli_hook_reads_stdin(api, played, monkeypatch):
    set_up(monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(stop_event("Ready.")))
    assert main(["voice", "hook"]) == 0
    assert api.spoken[-1]["text"] == "Ready."


# -- playback ----------------------------------------------------------------------

class FakeProcess:
    def __init__(self, polls):
        self.polls = list(polls)
        self.terminated = False

    def poll(self):
        return self.polls.pop(0) if self.polls else 0

    def terminate(self):
        self.terminated = True


def test_players():
    assert voice.player_command("a.wav", "macos") == ["afplay", "a.wav"]
    assert voice.player_command("a.wav", "linux", which=lambda n: n == "aplay") == ["aplay", "-q", "a.wav"]
    assert voice.player_command("a.wav", "linux", which=lambda n: None) is None


def test_a_newer_reply_stops_the_older_one(monkeypatch):
    older = voice._claim()
    voice._claim()                                                                   # a newer reply arrives
    proc = FakeProcess([None, None, None])
    voice.play(silence(), older, platform="macos", popen=lambda cmd, **kw: proc)
    assert proc.terminated


def test_playing_to_the_end(monkeypatch):
    token = voice._claim()
    commands = []
    proc = FakeProcess([None, 0])
    voice.play(silence(), token, platform="macos", popen=lambda cmd, **kw: commands.append(cmd) or proc)
    assert not proc.terminated and commands[0][0] == "afplay" and commands[0][1].endswith(".wav")
    assert not Path(commands[0][1]).exists()                                         # temporary file removed


def test_wav_length():
    assert abs(voice.wav_seconds(silence(0.5)) - 0.5) < 0.01


# -- no real keys in the repository ----------------------------------------------------

def test_no_elevenlabs_key_is_committed():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, encoding="utf-8").stdout.split()
    pattern = re.compile(r"sk_[0-9a-f]{32,}")
    for name in tracked:
        path = ROOT / name
        if path.suffix in {".png", ".ico", ".zip", ".dll", ".exe", ".bmp"} or not path.is_file():
            continue
        assert not pattern.search(path.read_text(encoding="utf-8", errors="ignore")), f"an API key in {name}"
