"""List what a folder already contains, so onboarding can pre-fill its answers.

Pure and read-only: `scan(path)` never writes anything.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

MAX_FILES = 20_000
EXAMPLES = 5
SKIP_DIRS = {"node_modules", "__pycache__", ".bimai"}
BEP_WORDS = ("bep", "eir", "execution plan", "uitvoeringsplan")

CATEGORIES = ("models", "issues", "requirements_checks", "bep", "planning", "relatics", "transcripts")
BY_EXTENSION = {
    ".ifc": "models", ".rvt": "models", ".nwd": "models", ".nwc": "models", ".dgn": "models", ".dwg": "models",
    ".bcf": "issues", ".bcfzip": "issues",
    ".ids": "requirements_checks",
    ".xer": "planning",
    ".vtt": "transcripts", ".srt": "transcripts",
}


@dataclass
class Found:
    count: int = 0
    examples: list[str] = field(default_factory=list)


@dataclass
class Scan:
    categories: dict[str, Found]
    suggestions: dict[str, str]     # suggestion key (see tools.yaml `suggests`) -> first file that suggested it
    is_git: bool
    has_claude_md: bool
    has_claude_dir: bool
    truncated: bool

    def as_dict(self) -> dict:
        return {
            "categories": {k: {"count": v.count, "examples": v.examples} for k, v in self.categories.items()},
            "suggestions": self.suggestions,
            "is_git": self.is_git,
            "has_claude_md": self.has_claude_md,
            "has_claude_dir": self.has_claude_dir,
            "truncated": self.truncated,
        }


def planning_format(path: Path) -> str | None:
    """'mspdi-xml' or 'p6-xml' from the XML root element only, so large files stay cheap."""
    try:
        for _, elem in ET.iterparse(path, events=("start",)):
            tag = elem.tag
            if tag.endswith("}Project") and "schemas.microsoft.com/project" in tag:
                return "mspdi-xml"
            if tag.split("}")[-1] == "APIBusinessObjects":
                return "p6-xml"
            return None
    except (ET.ParseError, OSError, UnicodeDecodeError):
        return None
    return None


def classify(path: Path) -> tuple[str, str] | None:
    """(category, suggestion key) for a file, or None when it is not relevant."""
    ext = path.suffix.lower()
    name = path.name.lower().replace("_", " ").replace("-", " ")
    if ext in (".pdf", ".docx") and any(w in name for w in BEP_WORDS):
        return "bep", "bep"
    if ext == ".json" and "relatics" in name:
        return "relatics", "relatics"
    if ext == ".xml":
        fmt = planning_format(path)
        return ("planning", fmt) if fmt else None
    if ext in BY_EXTENSION:
        return BY_EXTENSION[ext], ext
    return None


def scan(path: str | Path) -> Scan:
    root = Path(path).resolve()
    categories = {c: Found() for c in CATEGORIES}
    suggestions: dict[str, str] = {}
    seen = 0
    truncated = False
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            seen += 1
            if seen > MAX_FILES:
                truncated = True
                break
            file = Path(dirpath) / name
            hit = classify(file)
            if not hit:
                continue
            category, key = hit
            rel = file.relative_to(root).as_posix()
            found = categories[category]
            found.count += 1
            if len(found.examples) < EXAMPLES:
                found.examples.append(rel)
            suggestions.setdefault(key, rel)
        if truncated:
            break
    return Scan(
        categories=categories,
        suggestions=suggestions,
        is_git=(root / ".git").exists(),
        has_claude_md=(root / "CLAUDE.md").is_file(),
        has_claude_dir=(root / ".claude").is_dir(),
        truncated=truncated,
    )
