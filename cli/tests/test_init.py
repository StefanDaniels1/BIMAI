"""Tests for `bimai init`: catalogue, repo scan, team proposal, file plan and the command."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from bimai import connections as conn
from bimai.cli import main
from bimai.init import BLOCK_END, BLOCK_START, Answers, apply, plan_files
from bimai.scan import scan
from bimai.team import UnknownRole, load_catalogue, propose
from bimai.validate import validate

P6 = ('<?xml version="1.0"?>\n<APIBusinessObjects xmlns="http://xmlns.oracle.com/Primavera/P6/V8.3/API/'
      'BusinessObjects"><Project/></APIBusinessObjects>')
MSPDI = '<?xml version="1.0"?>\n<Project xmlns="http://schemas.microsoft.com/project"><Name>x</Name></Project>'


def touch(root: Path, rel: str, content: str = "") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def snapshot(root: Path) -> dict[str, float]:
    return {str(p.relative_to(root)): p.stat().st_mtime for p in root.rglob("*")}


def init(root: Path, *flags: str) -> int:
    return main(["init", str(root), "--person", "Anna de Vries", *flags])


# -- catalogue -------------------------------------------------------------------

def test_roles_have_the_architecture_model_tiers():
    tiers = {r.id: r.model for r in load_catalogue().roles.values()}
    assert tiers == {
        "coordinator": "sonnet", "requirements-risk-manager": "sonnet", "information-manager": "sonnet",
        "scribe": "sonnet", "planning-analyst": "haiku", "model-checker": "haiku", "issue-manager": "haiku",
        "mentor": "haiku",
    }


def test_catalogue_is_consistent():
    cat = load_catalogue()
    provided = {c for t in cat.tools.values() for c in t["provides"]}
    for preset in cat.presets.values():
        assert preset.team[0] == "coordinator"
        assert set(preset.team) <= set(cat.roles), preset.id
        assert set(preset.goals) <= set(cat.goals), preset.id
    for role in cat.roles.values():
        assert set(role.requires) <= provided, role.id
        assert set(role.serves) <= set(cat.goals), role.id
    assert set(cat.suggests.values()) <= set(cat.tools)


# -- repo scan -------------------------------------------------------------------

def test_scan_existing_project_folder(tmp_path):
    touch(tmp_path, "models/bridge.ifc")
    touch(tmp_path, "BEP-v3.pdf")
    touch(tmp_path, "planning/DO-planning.xml", P6)
    before = snapshot(tmp_path)
    s = scan(tmp_path)
    counts = {k: v.count for k, v in s.categories.items() if v.count}
    assert counts == {"models": 1, "bep": 1, "planning": 1}
    assert s.categories["models"].examples == ["models/bridge.ifc"]
    assert s.suggestions == {".ifc": "models/bridge.ifc", "bep": "BEP-v3.pdf", "p6-xml": "planning/DO-planning.xml"}
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("rel, content, category", [
    ("a.rvt", "", "models"), ("a.nwc", "", "models"), ("issues/x.bcfzip", "", "issues"),
    ("checks/wall.ids", "", "requirements_checks"), ("plan.xer", "", "planning"),
    ("plan.xml", MSPDI, "planning"), ("exports/Relatics_2026-09.json", "{}", "relatics"),
    ("meet.vtt", "", "transcripts"), ("meet.srt", "", "transcripts"),
    ("docs/BIM Uitvoeringsplan v2.docx", "", "bep"), ("EIR_client.pdf", "", "bep"),
])
def test_scan_categories(tmp_path, rel, content, category):
    touch(tmp_path, rel, content)
    assert scan(tmp_path).categories[category].count == 1


def test_unrelated_files_are_not_counted(tmp_path):
    touch(tmp_path, "config.xml", "<config/>")
    touch(tmp_path, "broken.xml", "<not xml")
    touch(tmp_path, "report.pdf")
    touch(tmp_path, "data.json", "{}")
    assert all(f.count == 0 for f in scan(tmp_path).categories.values())


def test_scan_skips_hidden_and_tooling_folders(tmp_path):
    for folder in (".git", "node_modules", ".bimai", ".cache"):
        touch(tmp_path, f"{folder}/model.ifc")
    assert scan(tmp_path).categories["models"].count == 0


def test_scan_empty_folder_and_missing_folder(tmp_path):
    s = scan(tmp_path)
    assert all(f.count == 0 for f in s.categories.values())
    assert not (s.is_git or s.has_claude_md or s.has_claude_dir)
    assert scan(tmp_path / "does-not-exist").categories["models"].count == 0


def test_scan_examples_are_limited_to_five(tmp_path):
    for i in range(8):
        touch(tmp_path, f"m{i}.ifc")
    found = scan(tmp_path).categories["models"]
    assert found.count == 8 and len(found.examples) == 5


def test_scan_notices_git_and_claude(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".claude").mkdir()
    touch(tmp_path, "CLAUDE.md", "# notes")
    s = scan(tmp_path)
    assert s.is_git and s.has_claude_md and s.has_claude_dir


# -- team proposal ---------------------------------------------------------------

def roles(team) -> list[str]:
    return [m.role for m in team.members]


def test_modeller_never_gets_a_requirements_manager():
    team = propose("BIM modeller", ["model-checks", "requirements"], ["revit"], False)
    assert roles(team) == ["coordinator", "model-checker"]


def test_missing_data_drops_a_role_with_a_hint():
    team = propose("design coordinator", ["requirements", "planning"], ["relatics"], False)
    assert "planning-analyst" not in roles(team)
    assert team.hints == ["Planning Analyst would join with: Primavera P6 planning or MS Project planning"]


def test_reasons():
    team = propose("bim coordinator", ["issues", "meetings"], ["acc"], False)
    why = {m.role: m.why for m in team.members}
    assert why == {"coordinator": "Always", "issue-manager": "Goal: issues · Data: ACC / Forma",
                   "scribe": "Goal: meetings"}


def test_roles_join_only_for_chosen_goals():
    team = propose("bim coordinator", ["issues"], ["acc", "revit"], False)
    assert roles(team) == ["coordinator", "issue-manager"]


def test_mentor_only_for_new_users_and_team_limit():
    cat = load_catalogue()
    assert "mentor" not in roles(propose("information manager", ["delivery", "meetings"], ["bep", "ifc"], False))
    team = propose("information manager", ["delivery", "meetings"], ["bep", "ifc"], True, cat)
    assert roles(team) == ["coordinator", "information-manager", "model-checker", "scribe", "mentor"]
    assert len(team.members) <= 5


@pytest.mark.parametrize("typed, preset", [
    ("BIM-coördinator", "bim-coordinator"), ("  bim coordinator ", "bim-coordinator"),
    ("Ontwerpmanager", "design-coordinator"), ("BIM modeler", "bim-modeller"),
    ("informatiemanager", "information-manager"), ("bim-modeller", "bim-modeller"),
])
def test_role_matching_english_and_dutch(typed, preset):
    assert propose(typed, [], [], False).preset == preset


def test_unknown_role():
    with pytest.raises(UnknownRole, match="Available roles: .*BIM coordinator"):
        propose("astronaut", [], [], False)


# -- file plan -------------------------------------------------------------------

def answers(**kw) -> Answers:
    base = dict(name="Knooppunt Oost", person="Anna de Vries", role="BIM coordinator",
                goals=["issues", "model-checks", "meetings"], tools=["acc", "revit"])
    return Answers(**{**base, **kw})


def write(root: Path, a: Answers | None = None):
    a = a or answers()
    team = propose(a.role, a.goals, a.tools, a.new_to_vscode)
    plan = plan_files(root, a, team)
    apply(root, plan)
    return plan


def test_written_workspace_is_valid(tmp_path):
    write(tmp_path)
    assert validate(tmp_path) == []
    b = tmp_path / ".bimai"
    assert yaml.safe_load((b / "project.yaml").read_text(encoding="utf-8"))["id"] == "knooppunt-oost"
    seat = yaml.safe_load((b / "seats" / "anna" / "seat.yaml").read_text(encoding="utf-8"))
    assert seat["preset"] == "bim-coordinator" and seat["positions"] == ["bim-coordinator"]
    assert [m["role"] for m in seat["team"]] == ["coordinator", "issue-manager", "model-checker", "scribe"]
    assert "| Issue Manager | Goal: issues · Data: ACC / Forma |" in (b / "seats" / "anna" / "team.md").read_text(encoding="utf-8")


def test_subagents_and_models(tmp_path):
    write(tmp_path)
    agents = tmp_path / ".claude" / "agents"
    assert sorted(p.name for p in agents.iterdir()) == ["issue-manager.md", "model-checker.md", "scribe.md"]
    meta = yaml.safe_load((agents / "model-checker.md").read_text(encoding="utf-8").split("---\n")[1])
    assert meta["model"] == "haiku" and meta["name"] == "model-checker" and meta["description"]
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")) == {"model": "sonnet"}


def test_existing_claude_md_is_kept_and_block_is_replaced_not_duplicated(tmp_path):
    touch(tmp_path, "CLAUDE.md", "# Our rules\n\nUse metric units.\n")
    write(tmp_path)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# Our rules\n\nUse metric units.\n\n" + BLOCK_START)
    assert "| Issue Manager (`issue-manager`) |" in text
    # A later regeneration replaces only the block and keeps text after it.
    (tmp_path / "CLAUDE.md").write_text(text + "\n## After\n", encoding="utf-8")
    for p in (tmp_path / ".bimai").rglob("*"):
        if p.is_file():
            p.unlink()
    write(tmp_path, answers(goals=["issues"]))
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.count(BLOCK_START) == 1 and text.count(BLOCK_END) == 1
    assert "Use metric units." in text and "## After" in text and "Scribe (`scribe`)" not in text


def test_existing_settings_are_kept(tmp_path):
    settings = {"model": "opus", "permissions": {"allow": ["Bash(npm test)"]}}
    touch(tmp_path, ".claude/settings.json", json.dumps(settings))
    plan = write(tmp_path)
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")) == settings
    assert next(f for f in plan if f.path == ".claude/settings.json").action == "unchanged"


def test_settings_without_model_get_sonnet_and_keep_the_rest(tmp_path):
    touch(tmp_path, ".claude/settings.json", json.dumps({"permissions": {"allow": ["Read"]}}))
    write(tmp_path)
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")) == {
        "permissions": {"allow": ["Read"]}, "model": "sonnet"}


def test_invalid_settings_are_left_alone(tmp_path):
    touch(tmp_path, ".claude/settings.json", "{ not json")
    plan = write(tmp_path)
    assert (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8") == "{ not json"
    assert next(f for f in plan if f.path == ".claude/settings.json").action == "conflict"


def test_gitignore_lines_are_added_once(tmp_path):
    touch(tmp_path, ".gitignore", "node_modules/\n.bimai/state/\n")
    write(tmp_path)
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert text.startswith("node_modules/\n.bimai/state/\n")
    assert text.count(".bimai/state/") == 1 and ".bimai/site/" in text and ".bimai/data/" in text


def test_changed_subagent_and_stray_files_are_never_overwritten(tmp_path):
    touch(tmp_path, ".claude/agents/scribe.md", "my own scribe\n")
    touch(tmp_path, ".bimai/people.yaml", "people: []\n")
    plan = write(tmp_path)
    assert (tmp_path / ".claude" / "agents" / "scribe.md").read_text(encoding="utf-8") == "my own scribe\n"
    assert (tmp_path / ".bimai" / "people.yaml").read_text(encoding="utf-8") == "people: []\n"
    conflicts = {f.path for f in plan if f.action == "conflict"}
    assert conflicts == {".claude/agents/scribe.md", ".bimai/people.yaml"}


# -- the command -----------------------------------------------------------------

def test_non_interactive_init(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("no question may be asked"))
    assert init(tmp_path, "--role", "bim coordinator", "--goals", "issues,meetings", "--tools", "bcf", "--yes") == 0
    out = capsys.readouterr().out
    assert ".bimai/project.yaml" in out and "workspace is valid" in out
    assert validate(tmp_path) == []
    assert (tmp_path / ".claude" / "agents" / "issue-manager.md").exists()


def test_scan_prefills_tools(tmp_path, capsys):
    touch(tmp_path, "models/bridge.rvt")
    assert init(tmp_path, "--role", "bim modeller", "--dry-run", "--json", "--yes") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["answers"]["tools"] == ["revit"]
    assert out["team"]["members"][1] == {"role": "model-checker", "why": "Goal: model-checks · Data: Revit"}
    assert set(out) == {"scan", "answers", "team", "connections", "files"}


def test_interactive_shows_found_tools_and_uses_defaults(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(conn, "PLATFORM", "linux")          # no connection setup offered at the end
    touch(tmp_path, "models/bridge.rvt")
    replies = iter(["", "", "BIM modeller", "", "", "", "", ""])   # name, person, role, goals, tools, vscode, lang, write
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    assert main(["init", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Revit" in out and "models/bridge.rvt" in out
    assert (tmp_path / ".claude" / "agents" / "model-checker.md").exists()


def test_interactive_reasks_unknown_role(tmp_path, monkeypatch, capsys):
    replies = iter(["", "", "astronaut", "bim modeller", "", "", "", "", ""])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    assert init(tmp_path, "--dry-run") == 0
    assert "no role preset matches 'astronaut'" in capsys.readouterr().out


def test_dry_run_writes_nothing(tmp_path):
    touch(tmp_path, "CLAUDE.md", "keep")
    before = snapshot(tmp_path)
    assert init(tmp_path, "--role", "bim modeller", "--dry-run", "--yes") == 0
    assert snapshot(tmp_path) == before


def test_declined_proposal_writes_nothing(tmp_path, monkeypatch):
    replies = iter(["", "", "bim modeller", "", "", "", "", "n"])
    monkeypatch.setattr("builtins.input", lambda *_: next(replies))
    assert init(tmp_path) == 1
    assert list(tmp_path.iterdir()) == []


def test_already_initialised(tmp_path, capsys):
    assert init(tmp_path, "--role", "bim modeller", "--yes") == 0
    before = snapshot(tmp_path)
    assert init(tmp_path, "--role", "bim modeller", "--yes") == 2
    assert "already a bimai project" in capsys.readouterr().err
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("flags, message", [
    (["--role", "astronaut"], "Available roles"),
    ([], "--role is required"),
    (["--role", "bim modeller", "--goals", "coffee"], "unknown goals: coffee"),
    (["--role", "bim modeller", "--tools", "sketchup"], "unknown tools: sketchup"),
])
def test_bad_flags_exit_2(tmp_path, capsys, flags, message):
    assert init(tmp_path, *flags, "--yes") == 2
    assert message in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_fresh_folder_is_created(tmp_path):
    target = tmp_path / "new-project"
    assert init(target, "--role", "bim modeller", "--yes") == 0
    assert validate(target) == []


def test_json_needs_dry_run(tmp_path):
    assert init(tmp_path, "--role", "bim modeller", "--yes", "--json") == 2


def test_person_defaults_to_git_user(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("bimai.cli._git_user", lambda root: "Jan Jansen")
    assert main(["init", str(tmp_path), "--role", "bim modeller", "--yes", "--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["answers"]["person_id"] == "jan"


def test_default_person_never_fails(tmp_path, monkeypatch):
    from bimai import cli
    monkeypatch.setattr(cli, "_git_user", lambda root: "")
    monkeypatch.setattr(cli.getpass, "getuser", lambda: (_ for _ in ()).throw(ModuleNotFoundError("pwd")))
    assert cli._default_person(tmp_path) == "me"


def test_person_flag_skips_the_login_lookup(tmp_path, monkeypatch):
    from bimai import cli
    monkeypatch.setattr(cli.getpass, "getuser", lambda: (_ for _ in ()).throw(AssertionError("should not be called")))
    monkeypatch.setattr(cli, "_git_user", lambda root: (_ for _ in ()).throw(AssertionError("should not be called")))
    assert main(["init", str(tmp_path), "--person", "Anna", "--role", "bim modeller", "--yes"]) == 0
