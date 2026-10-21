"""Saving and sharing without git commands (ARCHITECTURE §8.6, "git without git").

`save` commits only what bimai and the team produced (never the person's models or other files) under the
person's name; `sync` saves, brings in the team's changes (rebase) and shares (push). Nothing is ever lost: on a
conflict bimai stops the update and keeps the person's saved version. bimai never force-pushes, resets or
rewrites history, and never changes git configuration.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

SAVE_PATHS = (".bimai", "CLAUDE.md", ".claude/agents", ".claude/settings.json", ".mcp.json", ".gitignore", "outputs")
MAX_BYTES = 25 * 1024 * 1024
LOCK_STALE = dt.timedelta(minutes=10)
GIT_RAILS = ["Bash(git push --force*)", "Bash(git push -f*)", "Bash(git push --force-with-lease*)",
             "Bash(git reset --hard*)", "Bash(git rebase*)", "Bash(git filter-branch*)", "Bash(git filter-repo*)",
             "Bash(git clean -f*)", "Bash(git checkout -- *)", "Bash(git branch -D*)"]


class SyncError(Exception):
    """Something the person can fix, in plain language."""


@dataclass
class Result:
    saved: str = ""                       # the commit message, or "" when nothing changed
    skipped: list[str] = field(default_factory=list)
    incoming: int = 0
    shared: bool = False
    conflict: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        lines = []
        if self.saved:
            lines.append(f"✓ Saved: {self.saved}")
        if self.skipped:
            lines.append("  Not saved (larger than 25 MB, share these yourself): " + ", ".join(self.skipped))
        if self.incoming:
            lines.append(f"✓ Updated from the team: {self.incoming} change{'s' if self.incoming != 1 else ''}")
        if self.shared:
            lines.append("✓ Shared with the team")
        if self.conflict:
            lines.append("! Not updated: a colleague changed the same part of " + ", ".join(self.conflict)
                         + ". Your version is kept and nothing is lost. Ask your team to sort it out together, "
                           "or ask the person who changed it.")
        lines += self.notes
        return "\n".join(lines) or "Everything is up to date."


# ------------------------------------------------------------------ git, carefully

def git(root: Path, *args: str, identity: tuple[str, str] | None = None, timeout: float = 60,
        run: Callable = subprocess.run) -> subprocess.CompletedProcess:
    cmd = ["git"]
    if identity:
        cmd += ["-c", f"user.name={identity[0]}", "-c", f"user.email={identity[1]}"]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}   # never wait for a prompt or an editor
    try:
        return run(cmd + list(args), cwd=root, capture_output=True, encoding="utf-8", errors="replace",
                   timeout=timeout, env=env)
    except FileNotFoundError as exc:
        raise SyncError("git isn't installed. bimai uses it underneath to save and share; "
                        + ("install Git for Windows: https://git-scm.com/download/win" if sys.platform == "win32"
                           else "install git with your system's package manager.")) from exc
    except subprocess.TimeoutExpired as exc:
        raise SyncError("Sharing took too long (the network may be slow); your work is saved here.") from exc


def is_repo(root: Path) -> bool:
    try:
        return git(root, "rev-parse", "--is-inside-work-tree", timeout=10).stdout.strip() == "true"
    except SyncError:
        return False


def auto_enabled(root: Path) -> bool:
    try:
        project = yaml.safe_load((root / ".bimai" / "project.yaml").read_text(encoding="utf-8")) or {}
        auto = (project.get("sync") or {}).get("auto", True)
    except (OSError, yaml.YAMLError, AttributeError):
        auto = True
    return bool(auto) and is_repo(root)


def identity(root: Path, seat: str) -> tuple[str, str]:
    try:
        people = yaml.safe_load((root / ".bimai" / "people.yaml").read_text(encoding="utf-8")) or {}
        name = next((p.get("name") for p in people.get("people") or [] if p.get("id") == seat), None)
    except (OSError, yaml.YAMLError):
        name = None
    return (name or seat), f"{seat}@users.bimai"


# ------------------------------------------------------------------ save

def changed_files(root: Path) -> list[tuple[str, str]]:
    """(status, path) for changes under bimai's paths, untracked included."""
    paths = [p for p in SAVE_PATHS if (root / p).exists() or _tracked(root, p)]
    if not paths:
        return []
    out = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *paths)
    if out.returncode != 0:
        raise SyncError(f"git status failed: {out.stderr.strip()[-200:]}")
    entries, items = out.stdout.split("\0"), []
    i = 0
    while i < len(entries):
        entry = entries[i]
        if len(entry) > 3:
            status, path = entry[:2], entry[3:]
            items.append((status, path))
            if status[0] in "RC":                    # renames carry the old path as the next entry
                i += 1
        i += 1
    return items


def _tracked(root: Path, path: str) -> bool:
    return bool(git(root, "ls-files", "--", path, timeout=10).stdout.strip())


def summary(paths: list[str], who: str) -> str:
    kinds = {"decision": 0, "handoff": 0, "learning": 0, "output": 0, "setup": 0}
    for p in paths:
        if p.startswith(".bimai/decisions/"):
            kinds["decision"] += 1
        elif "/inbox/" in p:
            kinds["handoff"] += 1
        elif p.endswith("history.md") or p.endswith("history-archive.md"):
            kinds["learning"] += 1
        elif p.startswith("outputs/"):
            kinds["output"] += 1
        else:
            kinds["setup"] += 1
    parts = [f"{n} {k if k == 'setup' else k + ('s' if n != 1 else '')}" for k, n in kinds.items() if n]
    parts = [p.replace("1 setup", "team setup").replace(" setup", " setup files") for p in parts]
    return f"{who} saved: " + ", ".join(parts)


def save(root: Path, seat: str, max_bytes: int = MAX_BYTES) -> Result:
    result = Result()
    if not is_repo(root):
        raise SyncError("This project folder isn't shared through git yet, so there is nothing to save to. "
                        "Ask the person who set it up, or IT, to put it in a shared repository.")
    changes = changed_files(root)
    files = []
    for status, path in changes:
        full = root / path
        if "D" not in status and full.is_file() and full.stat().st_size > max_bytes:
            result.skipped.append(path)
            continue
        files.append(path)
    if not files:
        return result
    who = identity(root, seat)
    add = git(root, "add", "-A", "--", *files)
    if add.returncode != 0:
        raise SyncError(f"Saving failed: {add.stderr.strip()[-300:]}")
    message = summary(files, who[0])
    commit = git(root, "commit", "-q", "--only", "-m", message, "--", *files, identity=who)
    if commit.returncode != 0:
        if "nothing to commit" in (commit.stdout + commit.stderr):
            return result
        raise SyncError(f"Saving failed: {(commit.stderr or commit.stdout).strip()[-300:]}")
    result.saved = message
    return result


# ------------------------------------------------------------------ sync

def _rebasing(root: Path) -> bool:
    gitdir = Path(git(root, "rev-parse", "--git-dir").stdout.strip())
    gitdir = gitdir if gitdir.is_absolute() else root / gitdir
    return (gitdir / "rebase-merge").exists() or (gitdir / "rebase-apply").exists()


def sync(root: Path, seat: str, timeout: float = 60) -> Result:
    result = save(root, seat)
    who = identity(root, seat)                     # rebasing re-creates our commits: they need a name too
    if not git(root, "remote").stdout.strip():
        result.notes.append("Saved on this computer only: this project has no shared repository yet.")
        return result
    upstream = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0
    fetch = git(root, "fetch", "-q", "origin", timeout=timeout)
    if fetch.returncode != 0:
        result.notes.append("Couldn't reach the shared repository (offline?). Your work is saved here and will be "
                            "shared next time.")
        return result
    if upstream:
        result.incoming = int(git(root, "rev-list", "--count", "HEAD..@{u}").stdout.strip() or 0)
        if result.incoming and not _update(root, result, timeout, who):
            return result
    for attempt in range(2):
        if upstream and int(git(root, "rev-list", "--count", "@{u}..HEAD").stdout.strip() or 0) == 0:
            return result                          # nothing new of ours to share
        push = git(root, "push", "-q", *([] if upstream else ["-u", "origin", "HEAD"]), timeout=timeout)
        if push.returncode == 0:
            result.shared = True
            return result
        text = push.stderr.lower()
        if attempt == 0 and upstream and ("rejected" in text or "fetch first" in text or "non-fast-forward" in text):
            git(root, "fetch", "-q", "origin", timeout=timeout)
            result.incoming += int(git(root, "rev-list", "--count", "HEAD..@{u}").stdout.strip() or 0)
            if not _update(root, result, timeout, who):
                return result
            continue
        last = push.stderr.strip().splitlines()[-1][:160] if push.stderr.strip() else "no details"
        result.notes.append(f"Couldn't share right now ({last}). Your work is saved here and will be shared next time.")
        return result
    return result


def _update(root: Path, result: Result, timeout: float, who: tuple[str, str] | None = None) -> bool:  # noqa: E501
    """Brings in the team's changes on top of ours. On a conflict: back to our saved state, nothing lost."""
    pull = git(root, "pull", "--rebase", "--autostash", "-q", identity=who, timeout=timeout)
    if pull.returncode == 0:
        return True
    if _rebasing(root):
        conflicted = [p for p in git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines() if p]
        git(root, "rebase", "--abort", identity=who)
        for path in conflicted:
            author = git(root, "log", "-1", "--format=%an", "@{u}", "--", path).stdout.strip()
            result.conflict.append(f"{path}" + (f" (changed by {author})" if author else ""))
        result.incoming = 0
        return False
    result.notes.append("Couldn't bring in the team's changes (" + (pull.stderr.strip().splitlines() or ["?"])[-1][:160]
                        + "). Your work is saved here.")
    result.incoming = 0
    return False


# ------------------------------------------------------------------ in the background (end of a turn)

def lock_path(root: Path) -> Path:
    return root / ".bimai" / "state" / "sync.lock"


def start_background(root: Path, seat: str, popen: Callable = subprocess.Popen) -> bool:
    lock = lock_path(root)
    if lock.exists():
        try:
            if dt.datetime.now() - dt.datetime.fromisoformat(lock.read_text(encoding="utf-8").strip()) < LOCK_STALE:
                return False                       # a sync is already running
        except ValueError:
            pass
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "cwd": str(root)}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    popen([sys.executable, "-m", "bimai", "sync", "--background", "--seat", seat, "--path", str(root)], **kwargs)
    return True


def release(root: Path) -> None:
    try:
        lock_path(root).unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ join from a link

def clone(link: str, into: Path | None = None) -> Path:
    parts = [p for p in re.split(r"[\\/:]", link.rstrip("/\\")) if p]       # https, ssh and Windows paths alike
    name = re.sub(r"\.git$", "", parts[-1] if parts else "") or "project"
    target = into or Path.home() / "Documents" / "bimai" / name
    if target.exists() and any(target.iterdir()):
        if (target / ".bimai" / "project.yaml").is_file():
            return target                             # already there
        raise SyncError(f"{target} already exists and isn't this project. Choose another folder with --into.")
    target.parent.mkdir(parents=True, exist_ok=True)
    out = git(target.parent, "clone", "-q", link, str(target), timeout=600)
    if out.returncode != 0:
        raise SyncError(f"Couldn't get the project from {link}: {out.stderr.strip()[-300:]} "
                        "(Check the link, and that you have access: sign in to your git host once.)")
    return target
