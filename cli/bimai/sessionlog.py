"""The session log: what the team did, per seat and day, recorded by Claude Code hooks without a model.

Hooks (`bimai log hook --seat <seat>`, in the project's personal .claude/settings.local.json):
UserPromptSubmit starts a turn, PostToolUse adds files written and team members used, Stop writes one
entry to .bimai/log/<seat>/YYYY-MM-DD.md. Nobody reads the log at the start of a task; `bimai log`
prints it when someone asks what was done. Gitignored unless the project shares it (log.share).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from bimai.text import spoken_text

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
AGENT_TOOLS = {"Agent", "Task"}
HOOK_MATCHER = "Edit|Write|MultiEdit|NotebookEdit|Agent|Task"


def project_root(start: str | Path) -> Path | None:
    p = Path(start).resolve()
    for candidate in (p, *p.parents):
        if (candidate / ".bimai" / "project.yaml").is_file():
            return candidate
    return None


def log_dir(root: Path, seat: str) -> Path:
    return root / ".bimai" / "log" / seat


def _state_path(root: Path, session: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session)[:64] or "session"
    return root / ".bimai" / "state" / "log" / f"{safe}.json"


def _one_line(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _labels(root: Path) -> dict[str, str]:
    try:
        from bimai.team import load_catalogue
        return {rid: r.label for rid, r in load_catalogue().roles.items()}
    except Exception:
        return {}


def _relative(root: Path, path: str) -> str | None:
    try:
        rel = Path(path).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return Path(path).name or None
    if rel.startswith((".bimai/log/", ".bimai/state/")):
        return None
    return rel


def handle(event: dict, seat: str, now: dt.datetime | None = None) -> None:
    """One hook event. Never raises into Claude Code (the CLI catches everything)."""
    root = project_root(event.get("cwd") or ".")
    if root is None:
        return
    name = event.get("hook_event_name")
    session = str(event.get("session_id") or "session")
    state_path = _state_path(root, session)
    now = now or dt.datetime.now()

    def load() -> dict | None:
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save(state: dict) -> None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    if name == "UserPromptSubmit":
        pending = load()
        if pending:                                  # a turn that never reached Stop (interrupted)
            write_entry(root, seat, pending, answer="(interrupted)")
        save({"time": now.isoformat(timespec="minutes"), "asked": _one_line(event.get("prompt", ""), 300),
              "members": [], "files": []})
    elif name == "PostToolUse":
        state = load()
        if state is None:
            return
        tool, data = event.get("tool_name"), event.get("tool_input") or {}
        if tool in WRITE_TOOLS and data.get("file_path"):
            rel = _relative(root, data["file_path"])
            if rel and rel not in state["files"]:
                state["files"].append(rel)
        elif tool in AGENT_TOOLS and data.get("subagent_type"):
            if data["subagent_type"] not in state["members"]:
                state["members"].append(data["subagent_type"])
        save(state)
    elif name == "Stop" and not event.get("stop_hook_active"):
        state = load() or {"time": now.isoformat(timespec="minutes"), "asked": "", "members": [], "files": []}
        write_entry(root, seat, state, answer=spoken_text(event.get("last_assistant_message") or "", 400))
        try:
            state_path.unlink()
        except OSError:
            pass


def write_entry(root: Path, seat: str, state: dict, answer: str) -> Path:
    when = dt.datetime.fromisoformat(state["time"])
    path = log_dir(root, seat) / f"{when.date().isoformat()}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    labels = _labels(root)
    lines = [f"## {when.strftime('%H:%M')}"]
    if state.get("asked"):
        lines.append(f"- Asked: {state['asked']}")
    if state.get("members"):
        lines.append("- Team: " + ", ".join(labels.get(m, m) for m in state["members"]))
    if state.get("files"):
        lines.append("- Files: " + ", ".join(state["files"][:20]) + (" …" if len(state["files"]) > 20 else ""))
    if answer:
        lines.append(f"- Answer: {answer}")
    header = "" if path.exists() else f"# {when.date().isoformat()} · {seat}\n\n"
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n".join(lines) + "\n\n")    # one write: concurrent sessions don't interleave lines
    return path


# ------------------------------------------------------------------ reading

def parse_period(since: str | None, until: str | None, today: dt.date | None = None) -> tuple[dt.date, dt.date]:
    today = today or dt.date.today()

    def one(value: str, default: dt.date) -> dt.date:
        if not value:
            return default
        v = value.strip().lower()
        if v == "today":
            return today
        if v == "yesterday":
            return today - dt.timedelta(days=1)
        m = re.fullmatch(r"(\d+)\s*([dw])", v)
        if m:
            return today - dt.timedelta(days=int(m.group(1)) * (7 if m.group(2) == "w" else 1))
        try:
            return dt.date.fromisoformat(v)
        except ValueError as exc:
            raise ValueError(f"'{value}' is not a date: use today, yesterday, 7d, 2w or YYYY-MM-DD") from exc

    start = one(since or "", today - dt.timedelta(days=6))
    end = one(until or "", today)
    if end < start:
        start, end = end, start
    return start, end


def week_id(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def read(root: Path, seat: str, start: dt.date, end: dt.date) -> str:
    """The day files in the period; weeks whose days are gone appear as their digest."""
    folder = log_dir(root, seat)
    parts, digests_shown = [], set()
    day = start
    while day <= end:
        path = folder / f"{day.isoformat()}.md"
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8").strip())
        else:
            wid = week_id(day)
            digest = folder / "weeks" / f"{wid}.md"
            if wid not in digests_shown and digest.is_file():
                parts.append(digest.read_text(encoding="utf-8").strip())
                digests_shown.add(wid)
        day += dt.timedelta(days=1)
    return "\n\n".join(parts)


def shared(root: Path) -> bool:
    import yaml                                  # only here: the hooks shouldn't pay for it
    try:
        project = yaml.safe_load((root / ".bimai" / "project.yaml").read_text(encoding="utf-8")) or {}
        return bool((project.get("log") or {}).get("share"))
    except (OSError, yaml.YAMLError, AttributeError):
        return False


# ------------------------------------------------------------------ hooks in .claude/settings.local.json

def _ours(entry: dict) -> bool:
    args = entry.get("args") if isinstance(entry, dict) else None
    return isinstance(args, list) and args[:2] in (["log", "hook"], ["nap", "--if-due"])


def without_team_hooks(data: dict) -> dict:
    out = json.loads(json.dumps(data or {}))
    hooks = out.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event in list(hooks):
        groups = hooks[event] if isinstance(hooks[event], list) else []
        kept = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                group = {**group, "hooks": [h for h in group["hooks"] if not _ours(h)]}
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


def with_team_hooks(data: dict, command: str, seat: str) -> dict:
    """The session log (UserPromptSubmit, PostToolUse, Stop) and the daily nap check.

    Synchronous on purpose: background hooks can finish out of order on a quick turn, and Claude Code cancels
    them when a headless run ends. A log hook takes about 0.06 s (bimai._entry loads only this module)."""
    out = without_team_hooks(data)
    hooks = out.setdefault("hooks", {})
    log = {"type": "command", "command": command, "args": ["log", "hook", "--seat", seat], "timeout": 10}
    hooks.setdefault("SessionStart", []).append(
        {"matcher": "startup", "hooks": [{"type": "command", "command": command, "args": ["nap", "--if-due"]}]})
    hooks.setdefault("UserPromptSubmit", []).append({"hooks": [dict(log)]})
    hooks.setdefault("PostToolUse", []).append({"matcher": HOOK_MATCHER, "hooks": [dict(log)]})
    hooks.setdefault("Stop", []).append({"hooks": [dict(log)]})
    return out
