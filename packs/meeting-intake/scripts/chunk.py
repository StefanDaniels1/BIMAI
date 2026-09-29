#!/usr/bin/env python3
"""Split speaker turns into chunks for parallel extraction.

Deterministic. Chunks stay under a character budget (~4 characters per token)
and overlap by a few turns, so an action agreed across a chunk boundary is
still seen whole. Consolidation removes the duplicates the overlap creates.

Usage:
  chunk.py <resolved.json> [max_chars] [overlap_turns]   -> JSON list on stdout
Output:
  [{"chunk": n, "first_turn": i, "last_turn": j, "turns": [...]}, ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_MAX_CHARS = 12_000  # about 3k tokens per chunk: cheap and fast on the haiku tier
DEFAULT_OVERLAP = 2


def turn_size(turn: dict) -> int:
    return len(turn["text"]) + len(turn.get("speaker", "")) + 16


def chunk_turns(turns: list[dict], max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[dict]:
    if max_chars <= 0 or overlap < 0:
        raise ValueError("max_chars must be positive and overlap non-negative")
    chunks: list[dict] = []
    start = 0
    while start < len(turns):
        size, end = 0, start
        while end < len(turns) and (end == start or size + turn_size(turns[end]) <= max_chars):
            size += turn_size(turns[end])
            end += 1
        chunks.append({
            "chunk": len(chunks),
            "first_turn": turns[start]["i"],
            "last_turn": turns[end - 1]["i"],
            "turns": turns[start:end],
        })
        if end >= len(turns):
            break
        start = max(end - overlap, start + 1)  # always move forward
    return chunks


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3, 4):
        print(__doc__, file=sys.stderr)
        return 2
    resolved = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    max_chars = int(argv[2]) if len(argv) > 2 else DEFAULT_MAX_CHARS
    overlap = int(argv[3]) if len(argv) > 3 else DEFAULT_OVERLAP
    print(json.dumps(chunk_turns(resolved["turns"], max_chars, overlap), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
