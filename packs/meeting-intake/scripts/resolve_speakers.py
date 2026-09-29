#!/usr/bin/env python3
"""Match transcript speakers (and action owners) to project people.

Deterministic. Matching order: exact name or alias -> unique first name ->
close spelling (difflib). More than one candidate is never guessed: it becomes
a question for the uploader.

Usage:
  resolve_speakers.py <parsed.json> <people.yaml>   -> JSON on stdout
Output:
  {"speakers": {"<raw name>": {"status": "matched|ambiguous|unknown", "person": id|null,
                               "candidates": [ids]}},
   "turns": [... each turn with "person" added ...],
   "unresolved": ["<raw name>", ...]}
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

PARENS = re.compile(r"\s*[\(\[].*?[\)\]]\s*")
FUZZY_CUTOFF = 0.85


def normalize(name: str) -> str:
    """Casefold, strip accents, drop '(Company)' suffixes and extra spaces."""
    name = PARENS.sub(" ", name)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(name.casefold().replace(",", " ").split())


def load_people(path: str | Path) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data.get("people", [])


def _keys(person: dict) -> set[str]:
    keys = {normalize(person["name"])}
    keys |= {normalize(a) for a in person.get("aliases", [])}
    # "de Vries, Jan" style display names
    parts = person["name"].split()
    if len(parts) > 1:
        keys.add(normalize(f"{' '.join(parts[1:])} {parts[0]}"))
    return keys


def resolve_name(raw: str, people: list[dict]) -> dict:
    """Return {"status", "person", "candidates"} for one raw name."""
    key = normalize(raw)
    if not key or key in {"unknown", "speaker"}:
        return {"status": "unknown", "person": None, "candidates": []}

    exact = [p["id"] for p in people if key in _keys(p)]
    if len(exact) == 1:
        return {"status": "matched", "person": exact[0], "candidates": exact}
    if len(exact) > 1:
        return {"status": "ambiguous", "person": None, "candidates": exact}

    first = key.split()[0]
    by_first = [p["id"] for p in people if normalize(p["name"]).split()[0] == first]
    if len(key.split()) == 1 and by_first:
        if len(by_first) == 1:
            return {"status": "matched", "person": by_first[0], "candidates": by_first}
        return {"status": "ambiguous", "person": None, "candidates": by_first}

    lookup = {k: p["id"] for p in people for k in _keys(p)}
    close = difflib.get_close_matches(key, list(lookup), n=3, cutoff=FUZZY_CUTOFF)
    ids = sorted({lookup[c] for c in close})
    if len(ids) == 1:
        return {"status": "matched", "person": ids[0], "candidates": ids}
    if len(ids) > 1:
        return {"status": "ambiguous", "person": None, "candidates": ids}
    return {"status": "unknown", "person": None, "candidates": []}


def resolve(parsed: dict, people: list[dict]) -> dict:
    speakers = {raw: resolve_name(raw, people) for raw in sorted({t["speaker"] for t in parsed["turns"]})}
    turns = [dict(t, person=speakers[t["speaker"]]["person"]) for t in parsed["turns"]]
    unresolved = [raw for raw, r in speakers.items() if r["status"] != "matched"]
    return dict(parsed, speakers=speakers, turns=turns, unresolved=unresolved)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    parsed = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(resolve(parsed, load_people(argv[2])), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
