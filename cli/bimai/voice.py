"""Spoken replies: Claude Code hooks send a short version of each reply to ElevenLabs and play it.

Bring your own key: it lives in the computer's keychain. Settings (voice, model, length) are personal, in the
user's bimai config folder; the hooks go into the project's personal `.claude/settings.local.json`. Nothing
voice-related is shared with the team. The hook never fails a turn: problems are logged and it stays quiet.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Callable

from bimai import connections as conn
from bimai.text import spoken_text  # noqa: F401 (part of this module's interface)

API = "https://api.elevenlabs.io"
KEYRING_SERVICE = "bimai-voice"
KEYRING_USER = "elevenlabs"
DEFAULT_MODEL = "eleven_flash_v2_5"     # ElevenLabs' low-latency model (~75 ms); Turbo is deprecated
DEFAULT_MAX_CHARS = 400
OUTPUT_FORMAT = "wav_22050"             # WAV: Windows plays it with the standard library (winsound)
HOOK_ARGS = ["voice", "hook"]
NOTIFY_MATCHER = "permission_prompt|elicitation_dialog|agent_needs_input"
CONSENT = ("What the team says aloud is sent to ElevenLabs to be turned into speech: the first sentences of each "
           "reply, which can contain project details. ElevenLabs' terms and your plan apply; the key is yours.")


class VoiceError(Exception):
    """Something the person can fix, in plain language."""


class KeyRejected(VoiceError):
    pass


# ------------------------------------------------------------------ settings, key, log

def config_dir(environ=None) -> Path:
    environ = os.environ if environ is None else environ
    if sys.platform == "win32" and environ.get("APPDATA"):
        return Path(environ["APPDATA"]) / "bimai"
    return Path(environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "bimai"


def load_config(environ=None) -> dict:
    try:
        data = json.loads((config_dir(environ) / "voice.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(config: dict, environ=None) -> Path:
    path = config_dir(environ) / "voice.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return path


def get_key() -> str | None:
    try:
        return conn._keyring().get_password(KEYRING_SERVICE, KEYRING_USER)
    except Exception:   # a locked or missing keychain must not break the hook
        return None


def store_key(key: str) -> None:
    conn._keyring().set_password(KEYRING_SERVICE, KEYRING_USER, key)


def log(message: str, environ=None) -> None:
    try:
        path = config_dir(environ) / "voice.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 256 * 1024:
            path.write_text("", encoding="utf-8")
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
    except OSError:
        pass


# ------------------------------------------------------------------ ElevenLabs

def _request(url: str, key: str, opener: Callable, data: bytes | None = None, timeout: float = 30) -> bytes:
    headers = {"xi-api-key": key, "User-Agent": "bimai"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with opener(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", "")
            detail = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        except Exception:
            pass
        if exc.code == 401:
            raise KeyRejected("ElevenLabs didn't accept the key. Check it, and that it may use "
                              "Text to Speech (Access) and Voices (Read).") from exc
        if exc.code == 429:
            raise VoiceError("ElevenLabs says the usage limit is reached (credits or concurrent requests).") from exc
        raise VoiceError(f"ElevenLabs answered {exc.code}{': ' + detail if detail else ''}") from exc
    except OSError as exc:
        raise VoiceError(f"Couldn't reach ElevenLabs ({exc}). Check your internet connection or proxy.") from exc


def list_voices(key: str, opener: Callable | None = None) -> list[dict]:
    """The voices this account can use (default ones and its own), British first."""
    raw = _request(f"{API}/v2/voices?page_size=100", key, opener or urllib.request.urlopen)
    voices = []
    for v in json.loads(raw.decode("utf-8")).get("voices", []):
        labels = v.get("labels") or {}
        voices.append({
            "voice_id": v.get("voice_id", ""), "name": v.get("name", ""), "category": v.get("category", ""),
            "accent": str(labels.get("accent", "")), "gender": str(labels.get("gender", "")),
            "description": str(labels.get("description") or v.get("description") or labels.get("descriptive", "")),
        })
    return sorted(voices, key=lambda v: (not is_british(v), v["name"].lower()))


def is_british(voice: dict) -> bool:
    text = f"{voice.get('accent', '')} {voice.get('description', '')}".lower()
    return bool(re.search(r"\b(british|english|uk)\b", text))


def suggest(voices: list[dict]) -> dict | None:
    """A calm British male voice if there is one ("butler" feel), else the first British voice, else the first."""
    british = [v for v in voices if is_british(v)]
    calm = [v for v in british if v["gender"].lower() == "male"
            and any(w in v["description"].lower() for w in ("calm", "deep", "warm", "authoritative", "refined", "mature"))]
    for group in (calm, [v for v in british if v["gender"].lower() == "male"], british, voices):
        if group:
            return group[0]
    return None


def synthesize(text: str, key: str, voice_id: str, model: str = DEFAULT_MODEL, opener: Callable | None = None) -> bytes:
    body = json.dumps({"text": text, "model_id": model}).encode("utf-8")
    return _request(f"{API}/v1/text-to-speech/{voice_id}?output_format={OUTPUT_FORMAT}", key,
                    opener or urllib.request.urlopen, data=body, timeout=60)


# ------------------------------------------------------------------ what is said

def notification_text(event: dict) -> str:
    kind = event.get("type") or event.get("notification_type") or ""
    message = spoken_text(str(event.get("message") or ""), 160)
    if kind == "permission_prompt":
        return f"I need your approval. {message}".strip()
    if kind in ("elicitation_dialog", "agent_needs_input"):
        return "I need your input." + (f" {message}" if message else "")
    return ""


# ------------------------------------------------------------------ playback

def _current_file(environ=None) -> Path:
    return config_dir(environ) / "voice.current"


def _claim(environ=None) -> str:
    """Marks this utterance as the latest; an older one still playing notices and stops."""
    token = f"{os.getpid()}-{time.time_ns()}"
    path = _current_file(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    return token


def _still_current(token: str, environ=None) -> bool:
    try:
        return _current_file(environ).read_text(encoding="utf-8") == token
    except OSError:
        return False


def player_command(path: str, platform: str | None = None, which: Callable = shutil.which) -> list[str] | None:
    platform = platform or conn.PLATFORM
    if platform == "macos":
        return ["afplay", path]
    if platform == "linux":
        for player in (["paplay", path], ["aplay", "-q", path]):
            if which(player[0]):
                return player
    return None


def wav_seconds(audio: bytes) -> float:
    with wave.open(io.BytesIO(audio)) as w:
        return w.getnframes() / float(w.getframerate() or 1)


def play(audio: bytes, token: str, environ=None, platform: str | None = None, popen: Callable = subprocess.Popen,
         which: Callable = shutil.which) -> None:
    """Plays WAV audio; stops early when a newer utterance takes over."""
    platform = platform or conn.PLATFORM
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio)
        path = f.name
    try:
        if platform == "windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            end = time.monotonic() + wav_seconds(audio) + 0.3
            while time.monotonic() < end:
                if not _still_current(token, environ):
                    winsound.PlaySound(None, winsound.SND_PURGE)
                    return
                time.sleep(0.1)
            return
        command = player_command(path, platform, which)
        if command is None:
            raise VoiceError("No audio player found (Linux needs paplay or aplay).")
        proc = popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        while proc.poll() is None:
            if not _still_current(token, environ):
                proc.terminate()
                return
            time.sleep(0.1)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def say(text: str, *, environ=None, opener: Callable | None = None, player: Callable | None = None) -> bool:
    """Speaks the text with the configured voice. Raises VoiceError when it can't."""
    if not text:
        return False
    config = load_config(environ)
    if not config.get("voice_id"):
        raise VoiceError("No voice chosen yet. Run: bimai voice setup")
    key = get_key()
    if not key:
        raise VoiceError("No ElevenLabs key stored. Run: bimai voice setup")
    token = _claim(environ)
    audio = synthesize(text, key, config["voice_id"], config.get("model") or DEFAULT_MODEL, opener)
    if not _still_current(token, environ):
        return False            # a newer reply arrived while this one was being made
    (player or play)(audio, token, environ)
    return True


def hook(stdin_text: str, *, environ=None, opener: Callable | None = None, player: Callable | None = None) -> int:
    """Claude Code's Stop and Notification hook. Always returns 0: speech must never get in the way."""
    try:
        event = json.loads(stdin_text or "{}")
        name = event.get("hook_event_name")
        config = load_config(environ)
        if name == "Stop":
            if event.get("stop_hook_active"):
                return 0
            text = spoken_text(event.get("last_assistant_message") or "", int(config.get("max_chars") or DEFAULT_MAX_CHARS))
        elif name == "Notification":
            if config.get("notifications") is False:
                return 0
            text = notification_text(event)
        else:
            return 0
        if text:
            say(text, environ=environ, opener=opener, player=player)
    except VoiceError as exc:
        log(f"not spoken: {exc}", environ)
    except Exception as exc:    # never let a bug in speech break Claude's turn
        log(f"hook failed: {type(exc).__name__}: {exc}", environ)
    return 0


# ------------------------------------------------------------------ hooks in .claude/settings.local.json

def hook_command() -> str:
    found = shutil.which("bimai")
    return found or "bimai"


def _is_ours(entry: dict) -> bool:
    return isinstance(entry, dict) and entry.get("args") == HOOK_ARGS


def settings_with_hooks(data: dict, command: str) -> dict:
    out = json.loads(json.dumps(settings_without_hooks(data)))
    hooks = out.setdefault("hooks", {})
    ours = {"type": "command", "command": command, "args": list(HOOK_ARGS), "async": True}
    hooks.setdefault("Stop", []).append({"hooks": [dict(ours)]})
    hooks.setdefault("Notification", []).append({"matcher": NOTIFY_MATCHER, "hooks": [dict(ours)]})
    return out


def settings_without_hooks(data: dict) -> dict:
    out = json.loads(json.dumps(data or {}))
    hooks = out.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event in ("Stop", "Notification"):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                group = {**group, "hooks": [h for h in group["hooks"] if not _is_ours(h)]}
                if not group["hooks"]:
                    continue
            kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        del out["hooks"]
    return out


def is_on(data: dict) -> bool:
    for groups in (data.get("hooks") or {}).values():
        for group in groups if isinstance(groups, list) else []:
            if any(_is_ours(h) for h in (group.get("hooks") or []) if isinstance(group, dict)):
                return True
    return False
