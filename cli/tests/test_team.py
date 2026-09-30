"""Tests for routing, per-position history, `bimai team` and the seat team checks."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from bimai.claude import SeatContext, history_path, plan_claude_files, routing_section, subagent
from bimai.cli import main
from bimai.files import GENERATED
from bimai.team import Member, load_catalogue
from bimai.validate import validate

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "packs" / "project-site" / "examples" / "knooppunt-oost"


def ctx(*roles: str, positions=("bim-coordinator",)) -> SeatContext:
    return SeatContext(project_name="A2 tunnel", language="en", person_name="Anna", seat="anna",
                       title="BIM coordinator", positions=list(positions), goals=["issues"],
                       team=[Member(r, "why") for r in roles])


@pytest.fixture
def project(tmp_path):
    """A project made by `bimai init`: Coordinator, Issue Manager, Model Checker, Scribe."""
    assert main(["init", str(tmp_path), "--person", "Anna de Vries", "--role", "bim coordinator",
                 "--tools", "acc,revit", "--yes"]) == 0
    return tmp_path


def seat_file(root: Path) -> Path:
    return root / ".bimai" / "seats" / "anna" / "seat.yaml"


def edit_team(root: Path, change) -> None:
    data = yaml.safe_load(seat_file(root).read_text(encoding="utf-8"))
    change(data["team"])
    seat_file(root).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def team(root: Path, *flags: str) -> int:
    return main(["team", str(root), *flags])


# -- catalogue -------------------------------------------------------------------

def test_every_role_has_routing_fields():
    for role in load_catalogue().roles.values():
        assert role.handles.strip(), role.id
        assert len(role.examples) == 2, role.id


# -- routing ---------------------------------------------------------------------

def test_routing_table_matches_the_team():
    text = routing_section(ctx("coordinator", "model-checker", "scribe"), load_catalogue())
    rows = [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| Work")]
    assert len(rows) == 3
    assert rows[0].startswith("| Quick facts") and "Coordinator (you)" in rows[0]
    assert "Model Checker (`model-checker`)" in rows[1] and '"which walls have no fire rating?"' in rows[1]
    assert "Scribe (`scribe`)" in rows[2]


def test_scribe_rule_only_with_a_scribe():
    cat = load_catalogue()
    assert "recorded by the Scribe" in routing_section(ctx("coordinator", "scribe"), cat)
    assert "Scribe" not in routing_section(ctx("coordinator", "model-checker"), cat)


def test_routing_is_deterministic():
    cat = load_catalogue()
    c = ctx("coordinator", "issue-manager", "scribe")
    assert routing_section(c, cat) == routing_section(c, cat)


# -- history and memory ----------------------------------------------------------

def test_histories_are_created_on_init(project):
    positions = project / ".bimai" / "positions" / "bim-coordinator" / "agents"
    assert sorted(p.name for p in positions.iterdir()) == ["coordinator", "issue-manager", "model-checker", "scribe"]
    text = (positions / "model-checker" / "history.md").read_text(encoding="utf-8")
    assert "Model Checker" in text and "bim-coordinator" in text and "## Learnings" in text


def test_existing_history_is_kept(project):
    history = project / history_path("bim-coordinator", "model-checker")
    history.write_text(history.read_text(encoding="utf-8") + "- 2026-09-30: Zone A models use RD New (source: BEP §4)\n")
    before = history.read_text(encoding="utf-8")
    assert team(project) == 0
    assert history.read_text(encoding="utf-8") == before


def test_subagent_names_its_history_and_the_rules():
    text = subagent(ctx("coordinator", "model-checker"), "model-checker", load_catalogue())
    assert "`.bimai/positions/bim-coordinator/agents/model-checker/history.md`" in text
    for rule in ("Only confirmed outcomes", "YYYY-MM-DD", "personal remarks", "correct that line",
                 "`.bimai/decisions/`"):
        assert rule in text
    front = yaml.safe_load(text.split("---\n")[1])
    assert set(front) == {"name", "description", "model"}
    assert text.split("---\n", 2)[2].startswith(GENERATED)


def test_several_positions_list_every_history():
    text = subagent(ctx("model-checker", positions=("modeller-a", "modeller-b")), "model-checker", load_catalogue())
    assert "modeller-a/agents/model-checker" in text and "modeller-b/agents/model-checker" in text
    assert "of the position the work belongs to" in text


def test_coordinator_memory_is_in_the_block(project):
    text = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "## Your memory" in text and "agents/coordinator/history.md" in text


# -- bimai team ------------------------------------------------------------------

def test_up_to_date_team_changes_nothing(project, capsys):
    assert team(project) == 0
    assert "Everything is up to date" in capsys.readouterr().out


def test_member_added_by_hand(project):
    edit_team(project, lambda t: t.append({"role": "planning-analyst"}))
    assert team(project) == 0
    assert (project / ".claude" / "agents" / "planning-analyst.md").exists()
    assert "Planning Analyst (`planning-analyst`)" in (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "| Planning Analyst | Added by hand |" in (project / ".bimai" / "seats" / "anna" / "team.md").read_text(encoding="utf-8")
    assert (project / history_path("bim-coordinator", "planning-analyst")).exists()


def test_member_removed(project):
    edit_team(project, lambda t: t.remove(next(m for m in t if m["role"] == "scribe")))
    assert team(project) == 0
    assert not (project / ".claude" / "agents" / "scribe.md").exists()
    assert (project / history_path("bim-coordinator", "scribe")).exists()
    block = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Scribe (`scribe`)" not in block and "recorded by the Scribe" not in block


def test_users_own_agent_file_is_left_alone(project, capsys):
    own = project / ".claude" / "agents" / "scribe.md"
    own.write_text("---\nname: scribe\ndescription: my scribe\n---\nMine.\n", encoding="utf-8")
    assert team(project) == 0
    assert own.read_text(encoding="utf-8") == "---\nname: scribe\ndescription: my scribe\n---\nMine.\n"
    assert "conflict  .claude/agents/scribe.md" in capsys.readouterr().out
    # ... and not deleted when the member is removed.
    edit_team(project, lambda t: t.remove(next(m for m in t if m["role"] == "scribe")))
    assert team(project) == 0
    assert own.exists()


def test_generated_agent_is_updated(project):
    agent = project / ".claude" / "agents" / "model-checker.md"
    agent.write_text(agent.read_text(encoding="utf-8").replace("You are the **Model Checker**", "Old text"))
    assert team(project) == 0
    assert "You are the **Model Checker**" in agent.read_text(encoding="utf-8")


def test_user_text_in_claude_md_is_kept(project):
    claude_md = project / "CLAUDE.md"
    claude_md.write_text("# Our rules\n\n" + claude_md.read_text(encoding="utf-8") + "\n## After\n")
    edit_team(project, lambda t: t.append({"role": "planning-analyst"}))
    assert team(project) == 0
    text = claude_md.read_text(encoding="utf-8")
    assert text.startswith("# Our rules\n\n") and text.rstrip().endswith("## After")
    assert text.count("<!-- bimai:start -->") == 1


def test_missing_coordinator_is_added_first(project):
    edit_team(project, lambda t: t.remove(next(m for m in t if m["role"] == "coordinator")))
    assert team(project) == 0
    rows = (project / ".bimai" / "seats" / "anna" / "team.md").read_text(encoding="utf-8").splitlines()
    assert rows[5] == "| Coordinator | Always |"


def test_dry_run_writes_nothing(project):
    edit_team(project, lambda t: t.append({"role": "planning-analyst"}))
    before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert team(project, "--dry-run") == 0
    assert {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_invalid_seat_writes_nothing(project, capsys):
    edit_team(project, lambda t: t.append({"role": "clash-wizard"}))
    before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    assert team(project) == 1
    assert "clash-wizard" in capsys.readouterr().out
    assert {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


def test_two_seats_need_a_choice(project, capsys):
    shutil.copytree(project / ".bimai" / "seats" / "anna", project / ".bimai" / "seats" / "jan")
    assert team(project) == 2
    assert "anna, jan" in capsys.readouterr().err
    assert team(project, "--seat", "anna") == 0
    assert team(project, "--seat", "piet") == 2


def test_no_workspace(tmp_path):
    assert team(tmp_path) == 2


def test_team_md_footer(project):
    text = (project / ".bimai" / "seats" / "anna" / "team.md").read_text(encoding="utf-8")
    assert text.rstrip().endswith("Edit the `team` list in seat.yaml, then run `bimai team`.")


def test_plan_is_pure(project):
    edit_team(project, lambda t: t.append({"role": "planning-analyst"}))
    from bimai.claude import load_seat_context
    before = {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()}
    plan_claude_files(project, load_seat_context(project, "anna"))
    assert {str(p): p.read_bytes() for p in project.rglob("*") if p.is_file()} == before


# -- validate --------------------------------------------------------------------

def test_unknown_role_in_team(project):
    edit_team(project, lambda t: t.append({"role": "clash-wizard"}))
    [problem] = validate(project)
    assert problem.location == "team.4.role" and "clash-wizard" in problem.message and "model-checker" in problem.message


def test_duplicate_role_in_team(project):
    edit_team(project, lambda t: t.append({"role": "scribe"}))
    [problem] = validate(project)
    assert problem.location == "team.4.role" and "twice" in problem.message


def test_too_many_members(project):
    edit_team(project, lambda t: t.extend([{"role": "planning-analyst"}, {"role": "mentor"}]))
    [problem] = validate(project)
    assert problem.location == "team" and "6 members" in problem.message


def test_example_project_teams_are_valid():
    assert validate(EXAMPLE) == []
