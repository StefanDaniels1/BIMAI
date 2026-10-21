"""The nap: keeps what team members read at the start small and current, without losing anything.

Script part (always): duplicates and lines tied to reversed decisions go to history-archive.md; what is still
over budget is archived oldest first. Haiku part (when over budget, or weekly): Claude Code headless proposes
merges and drops; this script applies only what passes its checks (agents reason, scripts decide).
Also writes weekly digests of the session log. Every removed line lands in the archive with a reason.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

from bimai import sessionlog

DEFAULT_BUDGET = 2000            # tokens per history
DEFAULT_MODEL = "haiku"          # Claude Code's alias for its newest Haiku
DEFAULT_EFFORT = "high"
MAX_BUDGET_USD = "0.25"          # per Claude Code call
DUE_AFTER = dt.timedelta(hours=24)
HAIKU_EVERY = dt.timedelta(days=7)
LOCK_STALE = dt.timedelta(hours=2)
KEEP_DAYS = 30
SOURCE = re.compile(r"\(source:\s*([^)]*)\)")
DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "merges": {"type": "array", "items": {"type": "object", "properties": {
            "replace": {"type": "array", "items": {"type": "integer"}},
            "line": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["replace", "line", "reason"]}},
        "drops": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "integer"},
            "reason": {"type": "string", "enum": ["stale", "contradicted", "personal", "duplicate"]},
            "explain": {"type": "string"}},
            "required": ["id", "reason", "explain"]}},
    },
    "required": ["merges", "drops"],
}

INSTRUCTIONS = """You tidy the memory of one member of a BIM project team. Below are its history lines, numbered.
Each line is a lasting learning: "- YYYY-MM-DD: <learning> (source: <where>)".

Propose, as JSON matching the schema:
- merges: lines that say the same thing or belong together. Give the ids they replace and ONE new line in the
  same format, with the newest date of the replaced lines and ALL their sources in its (source: ...).
  Never add a fact that isn't in the replaced lines.
- drops: lines that are stale (about a finished phase or a one-off), contradicted by a newer line (name it in
  explain), duplicates, or personal remarks (health, family, absence, opinions about people) — always drop those.
Keep everything else: conventions, preferences, where things are, what worked. When unsure, keep.
Return empty lists when nothing should change."""


def tokens(text: str) -> int:
    return (len(text) + 3) // 4


# ------------------------------------------------------------------ histories

@dataclass
class History:
    path: Path
    head: list[str]                      # everything up to and including "## Learnings" (and comments)
    lines: list[str]                     # the learning lines ("- ...")
    tail: list[str] = field(default_factory=list)   # anything after the learnings we don't touch

    @property
    def archive_path(self) -> Path:
        return self.path.with_name("history-archive.md")

    def text(self) -> str:
        body = "\n".join(self.head + self.lines + ([""] + self.tail if self.tail else [])).rstrip("\n")
        return body + "\n"

    @property
    def tokens(self) -> int:
        return tokens(self.text())


def read_history(path: Path) -> History:
    head, lines, tail = [], [], []
    mode = "head"
    for line in path.read_text(encoding="utf-8").splitlines():
        if mode == "head":
            head.append(line)
            if line.strip().lower().startswith("## learnings"):
                mode = "learnings"
        elif mode == "learnings":
            stripped = line.strip()
            if line.startswith("## "):
                mode = "tail"
                tail.append(line)
            elif not stripped:
                if not lines:
                    head.append(line)              # spacing above the first learning stays as written
            elif stripped.startswith("<!--") and not lines:
                head.append(line)                  # the template's format comment stays above the lines
            else:
                lines.append(line.rstrip())         # learnings (malformed ones too: kept and counted)
        else:
            tail.append(line)
    return History(path, head, lines, tail)


def histories(root: Path) -> list[Path]:
    return sorted((root / ".bimai" / "positions").glob("*/agents/*/history.md"))


def budget(root: Path) -> int:
    try:
        project = yaml.safe_load((root / ".bimai" / "project.yaml").read_text(encoding="utf-8")) or {}
        return int((project.get("memory") or {}).get("history_tokens") or DEFAULT_BUDGET)
    except (OSError, ValueError, yaml.YAMLError, AttributeError):
        return DEFAULT_BUDGET


def model_settings(root: Path) -> tuple[str, str]:
    try:
        memory = (yaml.safe_load((root / ".bimai" / "project.yaml").read_text(encoding="utf-8")) or {}).get("memory") or {}
        return str(memory.get("model") or DEFAULT_MODEL), str(memory.get("effort") or DEFAULT_EFFORT)
    except (OSError, yaml.YAMLError, AttributeError):
        return DEFAULT_MODEL, DEFAULT_EFFORT


def _date(line: str) -> str:
    m = DATE.search(line)
    return m.group(1) if m else "0000-00-00"


def _norm(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip().lower())


def reversed_decisions(root: Path) -> set[str]:
    """Decision files marked `status: reversed` or `status: superseded` (relative paths)."""
    found = set()
    for path in sorted((root / ".bimai" / "decisions").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            try:
                meta = yaml.safe_load(text.split("---", 2)[1]) or {}
            except yaml.YAMLError:
                continue
            if str(meta.get("status", "")).lower() in ("reversed", "superseded"):
                found.add(path.relative_to(root).as_posix())
    return found


# ------------------------------------------------------------------ the plan for one history

@dataclass
class Change:
    removed: list[str]
    reason: str
    added: str | None = None             # a merged line that replaces `removed`


def script_changes(h: History, limit: int, reversed_: set[str]) -> list[Change]:
    """Duplicates and reversed decisions; then the oldest lines while over budget."""
    changes, seen, kept = [], set(), []
    for line in h.lines:
        key = _norm(line)
        if key in seen:
            changes.append(Change([line], "duplicate"))
            continue
        seen.add(key)
        sources = " ".join(SOURCE.findall(line))
        hit = next((d for d in reversed_ if d in sources or Path(d).stem in sources), None)
        if hit:
            changes.append(Change([line], f"decision reversed ({hit})"))
            continue
        kept.append(line)
    return changes + budget_changes(h, kept, limit)


def budget_changes(h: History, kept: list[str], limit: int) -> list[Change]:
    changes = []
    trial = History(h.path, h.head, list(kept), h.tail)
    for line in sorted(kept, key=_date):                 # oldest first; undated lines count as oldest
        if trial.tokens <= limit:
            break
        trial.lines.remove(line)
        changes.append(Change([line], "over budget"))
    return changes


def apply_changes(h: History, changes: list[Change]) -> History:
    lines = list(h.lines)
    for c in changes:
        positions = [lines.index(r) for r in c.removed if r in lines]
        for r in c.removed:
            if r in lines:
                lines.remove(r)
        if c.added:
            lines.insert(min(positions) if positions else len(lines), c.added)
    return History(h.path, h.head, lines, h.tail)


def write_archive(h: History, changes: list[Change], today: dt.date) -> None:
    if not changes:
        return
    path = h.archive_path
    current = path.read_text(encoding="utf-8") if path.exists() else (
        f"# Archive of {h.path.parent.name} · {h.path.parent.parent.parent.name}\n\n"
        "Lines the nap moved out of history.md (not read by the team at the start; nothing is deleted).\n")
    block = [f"\n## Nap {today.isoformat()}\n"]
    for c in changes:
        for r in c.removed:
            block.append(f"{r}  ⟵ {c.reason}" + (" → merged into the line below" if c.added else ""))
        if c.added:
            block.append(f"  merged: {c.added}")
    path.write_text(current.rstrip("\n") + "\n" + "\n".join(block) + "\n", encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ Haiku (Claude Code headless)

def claude_cli() -> str | None:
    return shutil.which("claude")


def ask_claude(prompt: str, schema: dict | None, model: str, effort: str, *, run: Callable = subprocess.run,
               cli: str | None = None) -> tuple[object, str]:
    """Runs `claude -p` once (no tools, no saved session, a cost cap). Returns (result, model used)."""
    cli = cli or claude_cli()
    if not cli:
        raise RuntimeError("Claude Code (claude) isn't installed or not on PATH")
    base = [cli, "-p", "--model", model, "--output-format", "json", "--tools", "", "--no-session-persistence",
            "--max-budget-usd", MAX_BUDGET_USD]
    if schema:
        base += ["--json-schema", json.dumps(schema)]
    attempts = [base + ["--effort", effort], base] if effort else [base]
    last = ""
    for cmd in attempts:                 # effort levels depend on the model: retry without when refused
        out = run(cmd, input=prompt, capture_output=True, encoding="utf-8", errors="replace", timeout=300)
        if out.returncode == 0:
            try:
                data = json.loads(out.stdout)
            except ValueError as exc:
                raise RuntimeError(f"Claude Code returned no JSON: {out.stdout[:200]}") from exc
            used = ", ".join((data.get("modelUsage") or {}).keys()) or model
            if schema:
                result = data.get("structured_output")
                if result is None:
                    result = json.loads(data.get("result") or "{}")
                return result, used
            return str(data.get("result") or "").strip(), used
        last = (out.stderr or out.stdout or "").strip()
    raise RuntimeError(f"Claude Code failed: {last[-300:]}")


def model_changes(h: History, proposal: dict) -> tuple[list[Change], list[str]]:
    """Turns Haiku's proposal into changes, keeping only what passes the checks. Returns (changes, refused)."""
    numbered = dict(enumerate(h.lines, 1))
    used: set[int] = set()
    changes, refused = [], []
    for m in proposal.get("merges") or []:
        ids = [i for i in m.get("replace") or [] if isinstance(i, int)]
        line = str(m.get("line") or "").strip()
        if len(ids) < 2 or any(i not in numbered or i in used for i in ids):
            refused.append(f"merge {ids}: unknown or reused lines")
            continue
        replaced = [numbered[i] for i in ids]
        sources = [s.strip() for r in replaced for s in SOURCE.findall(r)]
        merged_sources = " ".join(SOURCE.findall(line))
        if not line.startswith("- "):
            line = "- " + line
        if not all(s and s in merged_sources for s in sources):
            refused.append(f"merge {ids}: the new line doesn't keep all sources")
            continue
        if len(line) >= sum(len(r) for r in replaced):
            refused.append(f"merge {ids}: the new line isn't shorter")
            continue
        used.update(ids)
        changes.append(Change(replaced, f"merged: {m.get('reason') or ''}".strip(), added=line))
    for d in proposal.get("drops") or []:
        i = d.get("id")
        if i not in numbered or i in used or d.get("reason") not in ("stale", "contradicted", "personal", "duplicate"):
            refused.append(f"drop {i}: unknown line or reason")
            continue
        used.add(i)
        reason = d["reason"] if d["reason"] == "personal" else f"{d['reason']}: {d.get('explain') or ''}".strip()
        changes.append(Change([numbered[i]], reason))
    return changes, refused


def prompt_for(h: History) -> str:
    numbered = "\n".join(f"{i}. {line}" for i, line in enumerate(h.lines, 1))
    return f"{INSTRUCTIONS}\n\nHistory of {h.path.parent.name}:\n{numbered}\n"


# ------------------------------------------------------------------ the nap

@dataclass
class Report:
    rows: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def nap(root: Path, *, dry_run: bool = False, use_model: bool = True, force_model: bool = False,
        today: dt.date | None = None, ask: Callable | None = None) -> Report:
    today = today or dt.date.today()
    limit = budget(root)
    model, effort = model_settings(root)
    state = load_state(root)
    weekly = _older_than(state.get("last_model"), HAIKU_EVERY)
    have_claude = use_model and (ask is not None or claude_cli() is not None)
    ask = ask or (lambda prompt, schema: ask_claude(prompt, schema, model, effort))
    reversed_ = reversed_decisions(root)
    report = Report()
    model_ran = False
    for path in histories(root):
        h = read_history(path)
        before = h.tokens
        changes = script_changes(h, 10 ** 9, reversed_)          # duplicates and reversed decisions first
        h2 = apply_changes(h, changes)
        if have_claude and not dry_run and h2.lines and (force_model or h2.tokens > limit or (weekly and len(h2.lines) >= 8)):
            try:
                proposal, used = ask(prompt_for(h2), PROPOSAL_SCHEMA)
                more, refused = model_changes(h2, proposal if isinstance(proposal, dict) else {})
                model_ran = True
                report.notes += [f"{path.relative_to(root).as_posix()}: refused {r}" for r in refused]
                report.notes.append(f"model: {used}")
                changes += more
                h2 = apply_changes(h2, more)
            except Exception as exc:
                report.notes.append(f"{path.relative_to(root).as_posix()}: Haiku step skipped ({exc})")
        over = budget_changes(h2, h2.lines, limit)
        changes += over
        h2 = apply_changes(h2, over)
        report.rows.append({"history": path.relative_to(root).as_posix(), "tokens": before, "after": h2.tokens,
                            "budget": limit, "changes": [(c.reason, c.removed, c.added) for c in changes]})
        if changes and not dry_run:
            write_archive(h, changes, today)
            path.write_text(h2.text(), encoding="utf-8", newline="\n")
    if use_model and not have_claude:
        report.notes.append("Claude Code isn't available: only the script part ran.")
    if not dry_run:
        report.notes += digest_weeks(root, today, ask if have_claude else None)
        state["last_run"] = dt.datetime.now().isoformat(timespec="seconds")
        if model_ran:
            state["last_model"] = state["last_run"]
        save_state(root, state)
    return report


# ------------------------------------------------------------------ weekly digests of the session log

def digest_weeks(root: Path, today: dt.date, ask: Callable | None) -> list[str]:
    notes = []
    this_week = sessionlog.week_id(today)
    for seat_dir in sorted((root / ".bimai" / "log").glob("*/")):
        days = sorted(p for p in seat_dir.glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem))
        weeks: dict[str, list[Path]] = {}
        for p in days:
            weeks.setdefault(sessionlog.week_id(dt.date.fromisoformat(p.stem)), []).append(p)
        for wid, files in weeks.items():
            digest = seat_dir / "weeks" / f"{wid}.md"
            if wid < this_week and not digest.exists():
                text = "\n\n".join(f.read_text(encoding="utf-8") for f in files)
                body = None
                if ask:
                    try:
                        body, _ = ask("Summarize this week of a BIM project team's session log for the person, in a "
                                      "few short lines per day: what was asked, what was done, which files. Only "
                                      "facts from the log. Plain Markdown, no preamble.\n\n" + text, None)
                    except Exception as exc:
                        notes.append(f"digest {wid}: Haiku skipped ({exc})")
                if not body:
                    body = _plain_digest(files)
                digest.parent.mkdir(parents=True, exist_ok=True)
                digest.write_text(f"# Week {wid} · {seat_dir.name}\n\n{str(body).strip()}\n", encoding="utf-8", newline="\n")
                notes.append(f"digest written: {digest.relative_to(root).as_posix()}")
            if digest.exists():
                for f in files:
                    if (today - dt.date.fromisoformat(f.stem)).days > KEEP_DAYS:
                        f.unlink()
    return notes


def _plain_digest(files: list[Path]) -> str:
    out = []
    for f in files:
        asked = [line[len("- Asked: "):] for line in f.read_text(encoding="utf-8").splitlines() if line.startswith("- Asked: ")]
        out.append(f"- {f.stem}: {len(asked)} request(s)" + (": " + "; ".join(asked[:3]) if asked else ""))
    return "\n".join(out)


# ------------------------------------------------------------------ daily trigger

def _state_file(root: Path) -> Path:
    return root / ".bimai" / "state" / "nap.json"


def load_state(root: Path) -> dict:
    try:
        return json.loads(_state_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(root: Path, state: dict) -> None:
    path = _state_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _older_than(stamp: str | None, delta: dt.timedelta) -> bool:
    if not stamp:
        return True
    try:
        return dt.datetime.now() - dt.datetime.fromisoformat(stamp) >= delta
    except ValueError:
        return True


def lock_path(root: Path) -> Path:
    return root / ".bimai" / "state" / "nap.lock"


def is_due(root: Path) -> bool:
    lock = lock_path(root)
    if lock.exists() and not _older_than(lock.read_text(encoding="utf-8").strip() or None, LOCK_STALE):
        return False
    return _older_than(load_state(root).get("last_run"), DUE_AFTER)


def start_background(root: Path, popen: Callable = subprocess.Popen) -> None:
    """Starts `bimai nap --background` detached, so the session never waits for it."""
    lock = lock_path(root)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    cmd = [sys.executable, "-m", "bimai", "nap", "--background", "--path", str(root)]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": str(root)}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    popen(cmd, **kwargs)


def release(root: Path) -> None:
    try:
        lock_path(root).unlink()
    except OSError:
        pass
