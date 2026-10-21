"""Short spoken or logged versions of a reply: no code, tables, links or Markdown. Standard library only,
so the hooks that use it (voice, session log) start fast."""
from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 400

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def spoken_text(text: str, limit: int = DEFAULT_MAX_CHARS) -> str:
    """A short spoken version of a reply: no code, tables, links or Markdown; whole sentences up to the limit."""
    if not text:
        return ""
    text = re.sub(r"```.*?(```|$)", " ", text, flags=re.S)                  # fenced code
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)                  # links and images: keep the words
    text = re.sub(r"https?://\S+", "", text)                                 # bare URLs
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") or re.fullmatch(r"[-=*_]{3,}", stripped):   # tables, rules
            continue
        marked = re.match(r"^(?:#{1,6}|[-*+]|\d+[.)])\s+", stripped)         # headings and list items
        stripped = re.sub(r"^(?:#{1,6}|[-*+]|\d+[.)])\s+", "", stripped)
        stripped = re.sub(r"^>\s?", "", stripped)                           # quotes
        if marked and stripped and stripped[-1] not in ".!?:;,":
            stripped += "."                                                   # a pause, as when read aloud
        lines.append(stripped)
    text = "\n".join(lines)
    text = re.sub(r"`([^`]*)`", r"\1", text)                                 # inline code: keep the words
    text = re.sub(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1", r"\2", text)     # emphasis
    text = re.sub(r"<[^>]+>", "", text)                                      # HTML tags
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    text = " ".join(p for p in paragraphs if p)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text).strip()
    if len(text) <= limit:
        return text
    spoken = ""
    for sentence in _SENTENCE_END.split(text):
        if len(spoken) + len(sentence) + 1 > limit:
            break
        spoken = f"{spoken} {sentence}".strip()
    if not spoken:                                                           # one long sentence: cut at a word
        spoken = text[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return spoken


