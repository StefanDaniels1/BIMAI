"""Saving and sharing (sync.py) with real git: a shared remote and two people's clones."""
from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from bimai import collab, sync
from bimai.cli import main


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, encoding="utf-8", check=True).stdout.strip()


@pytest.fixture(autouse=True)
def no_git_identity(tmp_path, monkeypatch):
    """Like a fresh laptop: no global git settings, so bimai must bring its own name for commits."""
    empty = tmp_path / "gitconfig"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setattr("bimai.connections.claude_cli", lambda: None)


@pytest.fixture
def team(tmp_path):
    """Anna starts the project and shares it; Joris clones it with `bimai join <link>` and joins."""
    remote = tmp_path / "viaduct.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    anna = tmp_path / "anna" / "viaduct"
    subprocess.run(["git", "clone", "-q", str(remote), str(anna)], check=True, capture_output=True)
    (anna / "Deck.rvt").write_bytes(b"model")
    assert main(["init", str(anna), "--person", "Anna", "--role", "BIM coordinator", "--goals", "issues,meetings",
                 "--tools", "acc,revit", "--yes"]) == 0
    assert main(["sync", "--path", str(anna), "--seat", "anna"]) == 0                 # first share: sets upstream
    joris = tmp_path / "joris" / "viaduct"
    assert main(["join", str(remote), "--into", str(joris)]) == 0
    assert main(["join", str(joris), "--person", "Joris", "--role", "constructeur", "--tools", "scia", "--yes"]) == 0
    assert main(["sync", "--path", str(joris), "--seat", "joris"]) == 0
    assert main(["sync", "--path", str(anna), "--seat", "anna"]) == 0
    return remote, anna, joris


def test_two_people_share_their_work(team, capsys):
    remote, anna, joris = team
    assert (anna / ".bimai" / "seats" / "joris" / "seat.yaml").exists()              # Anna has Joris's seat
    collab.decide(anna, "anna", "Deck slab thickness", "300 mm", "coordination meeting")
    collab.handoff(joris, "joris", "bim-coordinator", "Opening in the deck for the duct needs a check")
    r1 = sync.sync(anna, "anna")
    r2 = sync.sync(joris, "joris")
    assert r1.shared and r2.shared and r2.incoming == 1
    sync.sync(anna, "anna")
    for root in (anna, joris):
        assert len(list((root / ".bimai" / "decisions").glob("*.md"))) == 1
        assert len(list((root / ".bimai" / "positions" / "bim-coordinator" / "inbox").glob("*.md"))) == 1
    log = git(anna, "log", "--format=%an|%s", "-3")
    assert "Joris|Joris saved: 1 handoff" in log and "Anna|Anna saved: 1 decision" in log


def test_models_and_personal_files_are_never_saved(team):
    remote, anna, joris = team
    (anna / "Deck.rvt").write_bytes(b"changed model")
    (anna / "notes.txt").write_text("my own notes", encoding="utf-8")
    (anna / "outputs").mkdir(exist_ok=True)
    (anna / "outputs" / "clash-report.md").write_text("# Clashes", encoding="utf-8")
    (anna / "outputs" / "huge.ifc").write_bytes(b"0" * 2048)
    result = sync.save(anna, "anna", max_bytes=1024)
    files = git(anna, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert files == ["outputs/clash-report.md"] and result.skipped == ["outputs/huge.ifc"]
    assert "Anna saved: 1 output" == result.saved
    status = git(anna, "status", "--porcelain")
    assert "Deck.rvt" in status and "notes.txt" in status                           # still the person's to share


def test_a_real_conflict_loses_nothing(team):
    remote, anna, joris = team
    rel = ".bimai/positions/bim-coordinator/agents/coordinator/history.md"
    for root, text in ((anna, "- 2026-10-21: drawings in folder A (source: Anna)"), (joris, "- 2026-10-21: drawings in folder B (source: Joris)")):
        path = root / rel
        path.write_text(path.read_text(encoding="utf-8") + text + "\n", encoding="utf-8")
    assert sync.sync(anna, "anna").shared
    result = sync.sync(joris, "joris")
    assert result.conflict and rel in result.conflict[0] and "Anna" in result.conflict[0]
    assert "folder B" in (joris / rel).read_text(encoding="utf-8")                    # Joris's version is kept
    assert not (joris / ".git" / "rebase-merge").exists()                             # no half-done update
    assert "folder B" in git(joris, "show", f"HEAD:{rel}")                             # and it is saved
    assert main(["sync", "--path", str(joris), "--seat", "joris"]) == 1               # the command says so


def test_no_remote_and_offline(tmp_path):
    root = tmp_path / "solo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    main(["init", str(root), "--person", "Anna", "--role", "BIM coordinator", "--yes"])
    result = sync.sync(root, "anna")
    assert result.saved and "this project has no shared repository" in result.notes[0]
    git(root, "remote", "add", "origin", str(tmp_path / "nowhere.git"))
    collab.decide(root, "anna", "Something", "decided")
    result = sync.sync(root, "anna")
    assert result.saved and "Couldn't reach the shared repository" in result.notes[0]


def test_not_a_git_folder(tmp_path, capsys):
    main(["init", str(tmp_path), "--person", "Anna", "--role", "BIM coordinator", "--yes"])
    assert main(["save", "--path", str(tmp_path)]) == 1
    assert "isn't shared through git yet" in capsys.readouterr().err
    assert main(["save", "--share", "--path", str(tmp_path)]) == 0                   # the hook stays silent


def test_brief_brings_in_the_team_first(team, monkeypatch, capsys):
    remote, anna, joris = team
    collab.handoff(anna, "anna", "constructeur", "Check the deck for the new duct opening")
    sync.sync(anna, "anna")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart", "source": "startup"})))
    assert main(["brief", "--path", str(joris), "--seat", "joris", "--sync"]) == 0
    out = capsys.readouterr().out
    assert "(bimai sync) Updated from the team: 1 change." in out
    assert "Handoff to you (constructeur) from Anna" in out                           # what's new includes it


def test_end_of_turn_saves_and_shares_in_the_background(team, monkeypatch):
    remote, anna, joris = team
    started = []
    monkeypatch.setattr(sync, "start_background", lambda root, seat, popen=None: started.append(seat) or True)
    collab.decide(anna, "anna", "Load model", "Eurocode")
    assert main(["save", "--share", "--path", str(anna), "--seat", "anna"]) == 0
    assert started == ["anna"] and "Anna saved: 1 decision" in git(anna, "log", "-1", "--format=%s")
    project = anna / ".bimai" / "project.yaml"
    data = yaml.safe_load(project.read_text(encoding="utf-8"))
    data["sync"] = {"auto": False}
    project.write_text(yaml.safe_dump(data), encoding="utf-8")
    collab.decide(anna, "anna", "Another", "x")
    assert main(["save", "--share", "--path", str(anna), "--seat", "anna"]) == 0
    assert started == ["anna"] and "Another" not in git(anna, "log", "-1", "--format=%s")   # off: nothing ran


def test_background_lock(team):
    remote, anna, joris = team
    calls = []
    assert sync.start_background(anna, "anna", popen=lambda cmd, **kw: calls.append(cmd))
    assert not sync.start_background(anna, "anna", popen=lambda cmd, **kw: calls.append(cmd))   # already running
    assert calls[0][-6:] == ["sync", "--background", "--seat", "anna", "--path", str(anna)]
    assert main(["sync", "--background", "--path", str(anna), "--seat", "anna"]) == 0
    assert not sync.lock_path(anna).exists()


def test_safety_rails_and_hooks(team):
    remote, anna, joris = team
    settings = json.loads((anna / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert {"Bash(git push --force*)", "Bash(git reset --hard*)", "Bash(git rebase*)"} <= set(settings["permissions"]["deny"])
    local = json.loads((joris / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    stop = [h["args"] for g in local["hooks"]["Stop"] for h in g["hooks"]]
    assert ["save", "--share", "--seat", "joris"] in stop
    start = [h["args"] for g in local["hooks"]["SessionStart"] for h in g["hooks"]]
    assert ["brief", "--seat", "joris", "--sync"] in start


def test_join_from_a_link_into_documents(tmp_path, monkeypatch, team, capsys):
    remote, anna, joris = team
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    assert main(["join", str(remote)]) == 0
    folder = tmp_path / "home" / "Documents" / "bimai" / "viaduct"
    assert (folder / ".bimai" / "project.yaml").exists() and str(folder) in capsys.readouterr().out
    assert main(["join", str(remote)]) == 0                                           # already there: fine
    assert main(["join", str(tmp_path / "missing.git")]) == 2
