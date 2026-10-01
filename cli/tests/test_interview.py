"""Tests for the onboarding interview used with Claude Code's question tool."""
from __future__ import annotations

import json

import pytest

from bimai.cli import main
from bimai.interview import MAX_HEADER, MAX_OPTIONS, MAX_QUESTIONS, interview
from bimai.team import UnknownRole, load_catalogue, match_preset

CAT = load_catalogue()
ROLES = [p.label for p in CAT.presets.values()]


def questions(spec):
    return {q["id"]: q for step in spec["steps"] for q in step["questions"]}


# -- catalogue ---------------------------------------------------------------------

def test_every_preset_offers_four_goals_including_its_defaults_and_known_tools():
    for p in CAT.presets.values():
        assert p.description, p.id
        assert len(p.goal_options) == 4 and set(p.goals) <= set(p.goal_options), p.id
        assert set(p.goal_options) <= set(CAT.goals), p.id
        assert p.typical_tools and set(p.typical_tools) <= set(CAT.tools), p.id
    assert set(CAT.goal_labels) == set(CAT.goals)
    assert all(v["label"] and v["description"] for v in CAT.goal_labels.values())


# -- the tool's limits -------------------------------------------------------------

def check_limits(spec):
    for step in spec["steps"]:
        assert 1 <= len(step["questions"]) <= MAX_QUESTIONS
        for q in step["questions"]:
            assert len(q["header"]) <= MAX_HEADER, q["header"]
            assert 2 <= len(q["options"]) <= MAX_OPTIONS, q["id"]
            assert all(o["label"] and o["description"] for o in q["options"]), q["id"]
            assert len({o["label"] for o in q["options"]}) == len(q["options"]), q["id"]
            if q["kind"] == "choice":
                allowed = {a["value"] for a in q["allowed"]}
                assert all(o["value"] in allowed for o in q["options"]), q["id"]


@pytest.mark.parametrize("role", [None, *ROLES])
@pytest.mark.parametrize("files", [[], ["a.rvt", "b.ifc", "BEP-v3.pdf", "c.bcf", "d.dgn", "e.nwd"]])
def test_within_the_question_tool_limits(tmp_path, role, files):
    for f in files:
        (tmp_path / f).write_text("", encoding="utf-8")
    check_limits(interview(tmp_path, role=role, git_user="Anna de Vries"))


# -- step 1 ------------------------------------------------------------------------

def test_step_one(tmp_path):
    folder = tmp_path / "a2-tunnel"
    folder.mkdir()
    spec = interview(folder, git_user="Anna de Vries")
    q = questions(spec)
    assert list(q) == ["name", "person", "role", "language"]
    assert q["name"]["kind"] == "text" and q["name"]["recommended"] == "A2 tunnel"
    assert "a2-tunnel" in [o["value"] for o in q["name"]["options"]]
    assert q["person"]["recommended"] == "Anna de Vries"
    assert [o["label"] for o in q["role"]["options"]] == ROLES and q["role"]["recommended"] is None
    assert q["language"]["recommended"] == "en"
    assert "--interview --role" in spec["next"]


def test_text_question_with_one_suggestion_offers_typing(tmp_path, monkeypatch):
    monkeypatch.setattr("bimai.interview.getpass.getuser", lambda: "")
    q = questions(interview(tmp_path, git_user=None))["person"]
    assert [o["label"] for o in q["options"]][-1] == "Type it yourself"


# -- step 2 ------------------------------------------------------------------------

def test_found_tools_come_first_and_are_recommended(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "viaduct.rvt").write_text("", encoding="utf-8")
    q = questions(interview(tmp_path, role="BIM coordinator"))
    tools = q["tools"]
    assert tools["options"][0]["value"] == "revit"
    assert "models/viaduct.rvt" in tools["options"][0]["description"]
    assert tools["recommended"] == ["revit"] and tools["multi_select"]
    assert {"revit", "acc", "civil3d", "relatics"} <= {a["value"] for a in tools["allowed"]}


def test_goals_for_a_design_coordinator(tmp_path):
    goals = questions(interview(tmp_path, role="design coordinator"))["goals"]
    assert [o["value"] for o in goals["options"]] == ["requirements", "risks", "planning", "reporting"]
    assert goals["recommended"] == ["requirements", "risks", "planning", "reporting"]
    assert len(goals["allowed"]) == 8


def test_role_typed_in_dutch_or_with_hyphen(tmp_path):
    assert interview(tmp_path, role="BIM-coördinator")["steps"][0]["role"] == "BIM coordinator"
    assert interview(tmp_path, role="ontwerpleider")["steps"][0]["role"] == "Design coordinator"


def test_vs_code_question_maps_to_the_flag(tmp_path):
    q = questions(interview(tmp_path, role="BIM modeller"))["new_to_vscode"]
    assert [o["value"] for o in q["options"]] == [False, True]


# -- role matching -----------------------------------------------------------------

@pytest.mark.parametrize("typed, suggestion", [("BIM coordinater", "BIM coordinator"),
                                               ("informatie manager", "Information manager"),
                                               ("desing manager", "Design coordinator")])
def test_close_roles_are_suggested(typed, suggestion):
    with pytest.raises(UnknownRole, match=f"Did you mean: {suggestion}\\?"):
        match_preset(typed, CAT)


def test_unrelated_role_gets_no_suggestion():
    with pytest.raises(UnknownRole) as exc:
        match_preset("astronaut", CAT)
    assert "Did you mean" not in str(exc.value) and "Available roles" in str(exc.value)


# -- the command -------------------------------------------------------------------

def test_interview_command_writes_nothing(tmp_path, capsys):
    assert main(["init", str(tmp_path), "--interview"]) == 0
    spec = json.loads(capsys.readouterr().out)
    assert spec["steps"][0]["step"] == 1 and "AskUserQuestion" in spec["for"]
    assert list(tmp_path.iterdir()) == []


def test_interview_command_step_two_and_errors(tmp_path, capsys):
    assert main(["init", str(tmp_path), "--interview", "--role", "BIM modeller"]) == 0
    assert json.loads(capsys.readouterr().out)["steps"][0]["step"] == 2
    assert main(["init", str(tmp_path), "--interview", "--role", "BIM coordinater"]) == 2
    assert "Did you mean: BIM coordinator" in capsys.readouterr().err


def test_interview_refuses_an_existing_project(tmp_path):
    assert main(["init", str(tmp_path), "--person", "A", "--role", "bim modeller", "--yes"]) == 0
    assert main(["init", str(tmp_path), "--interview"]) == 2


def test_answers_from_the_interview_are_accepted_by_init(tmp_path, capsys):
    """Values offered by the interview are exactly what `bimai init` accepts."""
    (tmp_path / "x.rvt").write_text("", encoding="utf-8")
    q1 = questions(interview(tmp_path, git_user="Anna"))
    q2 = questions(interview(tmp_path, role=q1["role"]["options"][0]["value"]))
    args = ["init", str(tmp_path), "--name", q1["name"]["recommended"], "--person", q1["person"]["recommended"],
            "--role", q1["role"]["options"][0]["value"], "--language", q1["language"]["recommended"],
            "--goals", ",".join(o["value"] for o in q2["goals"]["options"]),
            "--tools", ",".join(o["value"] for o in q2["tools"]["options"] if o["value"]), "--yes"]
    assert main(args) == 0


def test_civil3d_option_on_a_mac_says_windows_only(tmp_path, monkeypatch):
    from bimai import connections as conn
    monkeypatch.setattr(conn, "PLATFORM", "macos")
    tools = interview(tmp_path, role="BIM modeller")["steps"][0]["questions"][1]["options"]
    civil3d = next(o for o in tools if o["value"] == "civil3d")
    assert civil3d["description"].startswith("Windows only")
    ifc = next(o for o in tools if o["value"] == "ifc")
    assert not ifc["description"].startswith("Windows only")
