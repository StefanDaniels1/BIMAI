"""Memory hygiene (nap.py) and the session log (sessionlog.py). Claude Code is simulated."""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bimai import nap, sessionlog
from bimai.cli import main
from bimai.team import load_catalogue

LEARNINGS = "# Model Checker · bim-modeller\n\nWhat it learned.\n\n## Learnings\n\n<!-- one line per learning -->\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr("bimai.connections.claude_cli", lambda: None)
    root = tmp_path / "p"
    assert main(["init", str(root), "--person", "Anna", "--role", "bim modeller", "--yes"]) == 0
    return root


def history(root: Path, lines: list[str], role="model-checker") -> Path:
    path = root / ".bimai" / "positions" / "bim-modeller" / "agents" / role / "history.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(LEARNINGS + "".join(f"{line}\n" for line in lines), encoding="utf-8")
    return path


def line(i: int, day="2026-03-01", source="meeting 1", text=None) -> str:
    return f"- {day}: {text or f'learning number {i} about the project conventions'} (source: {source})"


def archived(path: Path) -> str:
    archive = path.with_name("history-archive.md")
    return archive.read_text(encoding="utf-8") if archive.exists() else ""


# -- session log -------------------------------------------------------------------

def hook(root, name, session="s1", **data):
    sessionlog.handle({"hook_event_name": name, "session_id": session, "cwd": str(root), **data}, "anna",
                      now=dt.datetime(2026, 10, 8, 14, 32))


def test_a_turn_becomes_one_entry(project):
    hook(project, "UserPromptSubmit", prompt="check the structure model\nfor missing fire ratings")
    hook(project, "PostToolUse", tool_name="Agent", tool_input={"subagent_type": "model-checker"})
    hook(project, "PostToolUse", tool_name="Write", tool_input={"file_path": str(project / "outputs" / "fire.md")})
    hook(project, "PostToolUse", tool_name="Write", tool_input={"file_path": str(project / "outputs" / "fire.md")})
    hook(project, "PostToolUse", tool_name="Edit", tool_input={"file_path": str(project / ".bimai" / "state" / "x")})
    hook(project, "Stop", last_assistant_message="**12 walls** have no fire rating.\n\n| a | b |\n|---|---|\n")
    text = (project / ".bimai" / "log" / "anna" / "2026-10-08.md").read_text(encoding="utf-8")
    assert text == ("# 2026-10-08 · anna\n\n## 14:32\n- Asked: check the structure model for missing fire ratings\n"
                    "- Team: Model Checker\n- Files: outputs/fire.md\n- Answer: 12 walls have no fire rating.\n\n")
    assert not list((project / ".bimai" / "state" / "log").glob("*.json"))


def test_interrupted_turn_and_parallel_sessions(project):
    hook(project, "UserPromptSubmit", session="a", prompt="first question")
    hook(project, "UserPromptSubmit", session="b", prompt="other window")
    hook(project, "UserPromptSubmit", session="a", prompt="second question")
    hook(project, "Stop", session="b", last_assistant_message="Answer for b.")
    hook(project, "Stop", session="a", last_assistant_message="Answer for a.")
    text = (project / ".bimai" / "log" / "anna" / "2026-10-08.md").read_text(encoding="utf-8")
    assert "- Asked: first question\n- Answer: (interrupted)" in text
    assert "- Asked: other window\n- Answer: Answer for b." in text
    assert "- Asked: second question\n- Answer: Answer for a." in text


def test_hook_outside_a_project_does_nothing(tmp_path):
    sessionlog.handle({"hook_event_name": "Stop", "cwd": str(tmp_path), "last_assistant_message": "x"}, "anna")
    assert not any(tmp_path.rglob("*.md"))


def test_cli_hook_never_fails(project, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert main(["log", "hook", "--seat", "anna"]) == 0
    assert capsys.readouterr().out == ""


def test_periods():
    today = dt.date(2026, 10, 8)
    assert sessionlog.parse_period("yesterday", None, today) == (dt.date(2026, 10, 7), today)
    assert sessionlog.parse_period("7d", None, today) == (dt.date(2026, 10, 1), today)
    assert sessionlog.parse_period("2w", "yesterday", today) == (dt.date(2026, 9, 24), dt.date(2026, 10, 7))
    assert sessionlog.parse_period("2026-10-01", "2026-10-03", today)[1] == dt.date(2026, 10, 3)
    with pytest.raises(ValueError, match="not a date"):
        sessionlog.parse_period("last tuesday", None, today)


def test_bimai_log_shows_days_and_digests(project, capsys):
    folder = project / ".bimai" / "log" / "anna"
    folder.mkdir(parents=True)
    (folder / "2026-10-07.md").write_text("# 2026-10-07 · anna\n\n## 09:10\n- Asked: yesterday's question\n", encoding="utf-8")
    (folder / "weeks").mkdir()
    (folder / "weeks" / "2026-W36.md").write_text("# Week 2026-W36 · anna\n\n- Monday: model checks\n", encoding="utf-8")
    assert main(["log", "--path", str(project), "--since", "2026-10-07", "--until", "2026-10-07"]) == 0
    assert "yesterday's question" in capsys.readouterr().out
    assert main(["log", "--path", str(project), "--since", "2026-09-01", "--until", "2026-09-07"]) == 0
    assert "Week 2026-W36" in capsys.readouterr().out
    assert main(["log", "--path", str(project), "--since", "2020-01-01", "--until", "2020-01-02"]) == 0
    assert "No log entries" in capsys.readouterr().out


def test_init_writes_personal_hooks_and_routing(project):
    settings = json.loads((project / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
    events = {e: [h["args"] for g in groups for h in g["hooks"]] for e, groups in settings["hooks"].items()}
    assert events["SessionStart"] == [["nap", "--if-due"]]
    assert events["UserPromptSubmit"] == events["Stop"] == [["log", "hook", "--seat", "anna"]]
    assert settings["hooks"]["PostToolUse"][0]["matcher"] == sessionlog.HOOK_MATCHER
    assert not any(h.get("async") for g in settings["hooks"]["Stop"] for h in g["hooks"])   # in order, never cancelled
    gitignore = (project / ".gitignore").read_text(encoding="utf-8")
    assert ".bimai/log/" in gitignore and ".claude/settings.local.json" in gitignore
    assert "bimai log --since yesterday" in (project / "CLAUDE.md").read_text(encoding="utf-8")


def test_team_keeps_other_personal_hooks(project):
    path = project / ".claude" / "settings.local.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["hooks"]["Stop"].append({"hooks": [{"type": "command", "command": "bimai", "args": ["voice", "hook"], "async": True}]})
    data["permissions"] = {"allow": ["Bash(ls)"]}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert main(["team", str(project)]) == 0
    after = json.loads(path.read_text(encoding="utf-8"))
    stop = [h["args"] for g in after["hooks"]["Stop"] for h in g["hooks"]]
    assert stop.count(["log", "hook", "--seat", "anna"]) == 1 and ["voice", "hook"] in stop
    assert after["permissions"] == {"allow": ["Bash(ls)"]}


# -- nap: script part --------------------------------------------------------------

def test_dry_run_shows_tokens_and_changes_nothing(project, capsys):
    path = history(project, [line(i, source=f"m{i}") for i in range(200)])
    before = path.read_text(encoding="utf-8")
    assert main(["nap", "--path", str(project), "--dry-run", "--no-model"]) == 0
    out = capsys.readouterr().out
    assert "model-checker/history.md" in out and "over budget" in out and "Dry run" in out
    assert path.read_text(encoding="utf-8") == before


def test_nap_archives_duplicates_reversed_and_oldest_and_loses_nothing(project):
    decisions = project / ".bimai" / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    (decisions / "0003-deck.md").write_text("---\nstatus: reversed\n---\nDeck slab in steel.\n", encoding="utf-8")
    original = ([line(i, day=f"2026-0{1 + i % 9}-1{i % 9}", source=f"m{i}") for i in range(150)]
                + [line(1, day="2026-02-11", source="m1"),                         # the same as line 1
                   line(999, text="deck slab is steel", source=".bimai/decisions/0003-deck.md")])
    path = history(project, original)
    report = nap.nap(project, use_model=False)
    kept = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    archive = archived(path)
    assert nap.read_history(path).tokens <= nap.DEFAULT_BUDGET
    assert "⟵ duplicate" in archive and "⟵ decision reversed (.bimai/decisions/0003-deck.md)" in archive
    for original_line in set(original):                                         # nothing lost
        assert original_line in kept or original_line in archive
    oldest_kept = min(nap._date(l) for l in kept)
    assert all(nap._date(l.split("  ⟵")[0]) <= oldest_kept for l in archive.splitlines() if "over budget" in l)
    assert path.read_text(encoding="utf-8").startswith(LEARNINGS.rstrip("\n"))
    assert any("only the script part" in n for n in report.notes) is False      # use_model=False: no such note


def test_nap_under_budget_changes_nothing(project):
    path = history(project, [line(i, source=f"m{i}") for i in range(5)])
    before = path.read_text(encoding="utf-8")
    nap.nap(project, use_model=False)
    assert path.read_text(encoding="utf-8") == before and not archived(path)


# -- nap: Haiku part ---------------------------------------------------------------

def test_haiku_proposal_is_checked(project):
    lines = [line(1, source="m1", text="walls use the NLRS classification"),
             line(2, day="2026-04-01", source="m2", text="walls are classified with NLRS"),
             line(3, source="m3", text="slabs use the NLRS classification"),
             line(4, source="m4", text="Piet is off sick this week"),
             line(5, source="m5", text="models live in 03_Models"),
             line(6, source="m6", text="old phase note")]
    path = history(project, lines)
    calls = []

    def fake_ask(prompt, schema):
        calls.append(prompt)
        assert schema == nap.PROPOSAL_SCHEMA and "6. - 2026-03-01: old phase note" in prompt
        return {"merges": [
            {"replace": [1, 2], "line": "- 2026-04-01: walls use NLRS (source: m1; m2)", "reason": "same rule"},
            {"replace": [3, 5], "line": "- 2026-03-01: slabs NLRS, models in 03_Models (source: m3)", "reason": "bad"},
        ], "drops": [{"id": 4, "reason": "personal", "explain": "health"},
                     {"id": 99, "reason": "stale", "explain": "no such line"}]}, "claude-haiku-x"

    report = nap.nap(project, force_model=True, ask=fake_ask)
    kept = [l for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
    assert kept[0] == "- 2026-04-01: walls use NLRS (source: m1; m2)"
    assert lines[2] in kept and lines[4] in kept                    # merge without all sources: refused
    assert lines[3] not in kept                                      # personal: always removed
    assert "⟵ personal" in archived(path) and "merged into the line below" in archived(path)
    assert any("doesn't keep all sources" in n for n in report.notes)
    assert any("drop 99" in n for n in report.notes) and "model: claude-haiku-x" in report.notes
    assert len(calls) == 1


def test_haiku_failure_falls_back_to_the_script(project):
    path = history(project, [line(i, source=f"m{i}") for i in range(150)])

    def broken(prompt, schema):
        raise RuntimeError("rate limited")

    report = nap.nap(project, force_model=True, ask=broken)
    assert nap.read_history(path).tokens <= nap.DEFAULT_BUDGET
    assert any("Haiku step skipped (rate limited)" in n for n in report.notes)


def test_ask_claude_uses_haiku_high_and_falls_back_without_effort():
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        if "--effort" in cmd:
            return SimpleNamespace(returncode=1, stdout="", stderr="Effort level 'high' is not available for this model")
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps(
            {"result": "", "structured_output": {"merges": [], "drops": []}, "modelUsage": {"claude-haiku-5-5": {}}}))

    result, used = nap.ask_claude("p", nap.PROPOSAL_SCHEMA, "haiku", "high", run=run, cli="claude")
    assert result == {"merges": [], "drops": []} and used == "claude-haiku-5-5"
    first = seen[0]
    assert first[first.index("--model") + 1] == "haiku" and first[first.index("--effort") + 1] == "high"
    assert "--json-schema" in first and "--no-session-persistence" in first and "--max-budget-usd" in first
    assert first[first.index("--tools") + 1] == ""                    # no tools: it only reads the prompt
    assert "--effort" not in seen[1]


def test_model_settings_from_project(project):
    project_yaml = project / ".bimai" / "project.yaml"
    project_yaml.write_text(project_yaml.read_text(encoding="utf-8")
                            + "memory:\n  model: claude-haiku-5-5\n  effort: max\n  history_tokens: 1500\n", encoding="utf-8")
    assert nap.model_settings(project) == ("claude-haiku-5-5", "max") and nap.budget(project) == 1500
    assert main(["validate", str(project)]) == 0


# -- digests -----------------------------------------------------------------------

def test_weekly_digest_and_old_days(project):
    folder = project / ".bimai" / "log" / "anna"
    folder.mkdir(parents=True)
    for day in ("2026-08-03", "2026-08-04", "2026-10-07"):
        (folder / f"{day}.md").write_text(f"# {day}\n\n## 09:00\n- Asked: question on {day}\n", encoding="utf-8")
    notes = nap.digest_weeks(project, dt.date(2026, 10, 8), None)
    digest = folder / "weeks" / "2026-W32.md"
    assert digest.exists() and "question on 2026-08-03" in digest.read_text(encoding="utf-8")
    assert not (folder / "2026-08-03.md").exists()                    # older than 30 days and digested
    assert (folder / "2026-10-07.md").exists()                        # this week: untouched, no digest yet
    assert not (folder / "weeks" / "2026-W41.md").exists()
    assert any("digest written" in n for n in notes)


def test_digest_with_haiku(project):
    folder = project / ".bimai" / "log" / "anna"
    folder.mkdir(parents=True)
    (folder / "2026-09-28.md").write_text("# 2026-09-28\n\n## 09:00\n- Asked: clash check\n", encoding="utf-8")
    nap.digest_weeks(project, dt.date(2026, 10, 8), lambda prompt, schema: ("- Monday: clash check done", "haiku"))
    assert "- Monday: clash check done" in (folder / "weeks" / "2026-W40.md").read_text(encoding="utf-8")
    assert (folder / "2026-09-28.md").exists()                        # only 10 days old: kept


# -- daily trigger -----------------------------------------------------------------

def test_if_due(project, capsys, monkeypatch):
    started = []
    monkeypatch.setattr(nap, "start_background", lambda root, popen=None: started.append(root))
    assert main(["nap", "--if-due", "--path", str(project)]) == 0
    assert started == [project] and capsys.readouterr().out == ""
    nap.save_state(project, {"last_run": dt.datetime.now().isoformat(timespec="seconds")})
    assert main(["nap", "--if-due", "--path", str(project)]) == 0
    assert len(started) == 1                                          # ran less than 24 hours ago


def test_lock_blocks_a_second_nap(project):
    nap.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    nap.lock_path(project).write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    assert not nap.is_due(project)
    nap.lock_path(project).write_text((dt.datetime.now() - dt.timedelta(hours=3)).isoformat(timespec="seconds"), encoding="utf-8")
    assert nap.is_due(project)                                        # a stale lock doesn't block forever


def test_background_start_is_detached(project):
    seen = {}
    nap.start_background(project, popen=lambda cmd, **kw: seen.update(cmd=cmd, **kw))
    assert seen["cmd"][-4:] == ["nap", "--background", "--path", str(project)]
    assert seen.get("start_new_session") or seen.get("creationflags")
    assert nap.lock_path(project).exists()


def test_background_nap_releases_the_lock(project, monkeypatch):
    monkeypatch.setattr(nap, "claude_cli", lambda: None)
    nap.lock_path(project).parent.mkdir(parents=True, exist_ok=True)
    nap.lock_path(project).write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    assert main(["nap", "--background", "--path", str(project)]) == 0
    assert not nap.lock_path(project).exists()
    assert "Done" in (project / ".bimai" / "state" / "nap.log").read_text(encoding="utf-8")
    assert "last_run" in nap.load_state(project)


def test_if_due_outside_a_project_is_silent(tmp_path, capsys):
    assert main(["nap", "--if-due", "--path", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


# -- lean charters -----------------------------------------------------------------

def test_charters_stay_small():
    for role in load_catalogue().roles.values():
        assert nap.tokens(role.charter) <= 400, f"{role.id} charter is {nap.tokens(role.charter)} tokens"
