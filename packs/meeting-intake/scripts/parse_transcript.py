#!/usr/bin/env python3
"""Parse a meeting transcript into speaker turns.

Deterministic, no model involved. Supported formats:
  - WebVTT (.vtt): Teams (<v Name>text</v>) and Zoom ("Name: text") styles
  - SubRip (.srt)
  - Word (.docx): Teams transcript download (needs python-docx)
  - Plain text (.txt/.md): "Name: text", "[00:03:12] Name: text",
    or Teams-style header lines "Name   0:03:12" followed by text lines

Usage:
  parse_transcript.py <file>            -> JSON on stdout
Output:
  {"meeting_id", "source_format", "turn_count", "turns": [{"i", "speaker", "start", "text"}]}
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

CUE_TIME = re.compile(r"^(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->\s*")
VTT_VOICE = re.compile(r"^<v(?:\.[^ >]+)?\s+([^>]+)>(.*?)(?:</v>)?$")
NAME_TEXT = re.compile(r"^([^:\[\]\d][^:]{0,60}?):\s+(.+)$")
STAMP_NAME_TEXT = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s+([^:]{1,60}?):\s+(.+)$")
NAME_STAMP = re.compile(r"^(.{1,60}?)\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*$")
TAG = re.compile(r"<[^>]+>")


class TranscriptError(ValueError):
    """Raised when a transcript can't be parsed into turns."""


def norm_time(value: str | None) -> str | None:
    """Normalize '0:03:12', '03:12', '00:03:12.500' to 'HH:MM:SS'."""
    if not value:
        return None
    value = value.replace(",", ".").split(".")[0]
    parts = [int(p) for p in value.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    return f"{h:02d}:{m:02d}:{s:02d}"


def looks_like_name(name: str) -> bool:
    words = name.split()
    return 0 < len(words) <= 6 and not name.strip().endswith((".", "?", "!"))


def _cues(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split VTT/SRT lines into (start_time, text_lines) cues."""
    cues: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for raw in lines:
        line = raw.strip()
        if CUE_TIME.match(line):
            if current:
                cues.append(current)
            current = (line.split("-->")[0].strip(), [])
        elif not line:
            if current:
                cues.append(current)
                current = None
        elif current is not None:
            current[1].append(line)
    if current:
        cues.append(current)
    return cues


def parse_cues(text: str) -> list[dict]:
    turns = []
    for start, body in _cues(text.splitlines()):
        speaker, parts = None, []
        for line in body:
            voice = VTT_VOICE.match(line)
            if voice:
                speaker = voice.group(1).strip()
                parts.append(TAG.sub("", voice.group(2)).strip())
                continue
            clean = TAG.sub("", line).strip()
            named = NAME_TEXT.match(clean)
            if named and speaker is None and not parts and looks_like_name(named.group(1)):
                speaker, clean = named.group(1).strip(), named.group(2).strip()
            parts.append(clean)
        content = " ".join(p for p in parts if p)
        if content:
            turns.append({"speaker": speaker or "Unknown", "start": norm_time(start), "text": content})
    return turns


def parse_plain(text: str) -> list[dict]:
    turns: list[dict] = []
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = STAMP_NAME_TEXT.match(line)
        if m and looks_like_name(m.group(2)):
            current = {"speaker": m.group(2).strip(), "start": norm_time(m.group(1)), "text": m.group(3).strip()}
            turns.append(current)
            continue
        m = NAME_STAMP.match(line)
        if m and looks_like_name(m.group(1)):
            current = {"speaker": m.group(1).strip(), "start": norm_time(m.group(2)), "text": ""}
            turns.append(current)
            continue
        m = NAME_TEXT.match(line)
        if m and looks_like_name(m.group(1)):
            current = {"speaker": m.group(1).strip(), "start": None, "text": m.group(2).strip()}
            turns.append(current)
            continue
        if current is None:
            current = {"speaker": "Unknown", "start": None, "text": ""}
            turns.append(current)
        current["text"] = f"{current['text']} {line}".strip()
    return [t for t in turns if t["text"]]


def read_docx(path: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise TranscriptError("Reading .docx needs the python-docx package") from exc
    return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)


def merge_consecutive(turns: list[dict]) -> list[dict]:
    """Merge consecutive turns by the same speaker (VTT splits sentences into many cues)."""
    merged: list[dict] = []
    for turn in turns:
        if merged and merged[-1]["speaker"] == turn["speaker"]:
            merged[-1]["text"] = f"{merged[-1]['text']} {turn['text']}".strip()
        else:
            merged.append(dict(turn))
    for i, turn in enumerate(merged):
        turn["i"] = i
    return merged


def meeting_id(turns: list[dict]) -> str:
    digest = hashlib.sha256()
    for t in turns:
        digest.update(f"{t['speaker']}\x1f{t['text']}\n".encode("utf-8"))
    return digest.hexdigest()[:12]


def parse_file(path: str | Path) -> dict:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        text, fmt = read_docx(path), "docx"
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        fmt = {".vtt": "vtt", ".srt": "srt"}.get(suffix, "text")
        if fmt == "text" and text.lstrip().startswith("WEBVTT"):
            fmt = "vtt"
    turns = parse_cues(text) if fmt in ("vtt", "srt") else parse_plain(text)
    turns = merge_consecutive(turns)
    if not turns:
        raise TranscriptError(f"No speaker turns found in {path.name}")
    return {
        "meeting_id": meeting_id(turns),
        "source_format": fmt,
        "source_file": path.name,
        "turn_count": len(turns),
        "turns": turns,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        result = parse_file(argv[1])
    except (OSError, TranscriptError) as exc:
        print(json.dumps({"ok": False, "error": "invalid_input", "message": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
