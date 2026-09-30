"""Tests for `bimai validate`. Run: python -m pytest cli/tests"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from bimai import __version__
from bimai.cli import main
from bimai.validate import NoWorkspace, _validator, validate

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "packs" / "project-site" / "examples" / "knooppunt-oost"


@pytest.fixture
def ws(tmp_path):
    """A copy of the example project, safe to break."""
    shutil.copytree(EXAMPLE / ".bimai", tmp_path / ".bimai", ignore=shutil.ignore_patterns("*.pdf"))
    return tmp_path


def edit(path: Path, change) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_workflow(ws: Path, steps: dict) -> Path:
    path = ws / ".bimai" / "workflows" / "test.yaml"
    path.write_text(yaml.safe_dump({"id": "test", "steps": steps}), encoding="utf-8")
    return path


def messages(problems) -> list[str]:
    return [str(p) for p in problems]


# -- the command -----------------------------------------------------------------

def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_runs_as_a_module():
    out = subprocess.run([sys.executable, "-m", "bimai", "--version"], capture_output=True, encoding="utf-8", check=True)
    assert __version__ in out.stdout


def test_no_workspace_exits_2(tmp_path, capsys):
    assert main(["validate", str(tmp_path)]) == 2
    assert str(tmp_path.resolve()) in capsys.readouterr().err
    with pytest.raises(NoWorkspace):
        validate(tmp_path)


# -- schema validation -----------------------------------------------------------

def test_example_project_is_valid(capsys):
    assert validate(EXAMPLE) == []
    assert main(["validate", str(EXAMPLE)]) == 0
    assert "valid" in capsys.readouterr().out


@pytest.mark.parametrize("workflow", sorted(ROOT.glob("packs/*/workflows/*.yaml")), ids=lambda p: p.parent.parent.name)
def test_pack_workflows_fit_the_schema(workflow):
    data = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    assert [e.message for e in _validator("workflow").iter_errors(data)] == []


def test_missing_project_id(ws):
    edit(ws / ".bimai" / "project.yaml", lambda d: d.pop("id"))
    problems = validate(ws)
    assert any(p.file == ".bimai/project.yaml" and "'id'" in p.message for p in problems)


def test_needs_must_be_a_list(ws):
    write_workflow(ws, {"a": {"tool": "x"}, "b": {"needs": "a", "tool": "y"}})
    problems = validate(ws)
    assert [(p.file, p.location) for p in problems] == [(".bimai/workflows/test.yaml", "steps.b.needs")]


def test_broken_yaml_is_reported_and_other_files_still_checked(ws):
    (ws / ".bimai" / "people.yaml").write_text("people:\n  - { id: eva, name: [unclosed\n", encoding="utf-8")
    edit(ws / ".bimai" / "project.yaml", lambda d: d.pop("id"))
    problems = validate(ws)
    broken = [p for p in problems if p.file == ".bimai/people.yaml"]
    assert len(broken) == 1 and broken[0].location.startswith("line ")
    assert any(p.file == ".bimai/project.yaml" for p in problems)


def test_dates_are_checked(ws):
    edit(ws / ".bimai" / "ownership.yaml", lambda d: d["cover"][0].update({"until": "next week"}))
    assert any(p.location == "cover.0.until" for p in validate(ws))


# -- cross-file references -------------------------------------------------------

def test_unknown_person_in_held_by(ws):
    edit(ws / ".bimai" / "ownership.yaml", lambda d: d["positions"]["bim-coordinator"]["held_by"].append("jan"))
    assert messages(validate(ws)) == [
        ".bimai/ownership.yaml: positions.bim-coordinator.held_by: 'jan' is not in people.yaml"]


def test_unknown_position_in_seat(ws):
    edit(ws / ".bimai" / "seats" / "eva" / "seat.yaml", lambda d: d["positions"].append("modeller-mep"))
    assert messages(validate(ws)) == [
        ".bimai/seats/eva/seat.yaml: positions.1: 'modeller-mep' is not a position in ownership.yaml"]


def test_unknown_seat_person_cover_and_automation_owner(ws):
    b = ws / ".bimai"
    edit(b / "seats" / "eva" / "seat.yaml", lambda d: d.update({"person": "eve"}))
    edit(b / "ownership.yaml", lambda d: d["cover"][0].update({"by": "piet", "position": "modeller-mep"}))
    edit(b / "automations" / "daily-triage.yaml", lambda d: d.update({"owner": "nobody"}))
    assert {(p.file, p.location) for p in validate(ws)} == {
        (".bimai/seats/eva/seat.yaml", "person"),
        (".bimai/ownership.yaml", "cover.0.by"),
        (".bimai/ownership.yaml", "cover.0.position"),
        (".bimai/automations/daily-triage.yaml", "owner"),
    }


def test_references_are_not_checked_against_a_broken_people_file(ws):
    (ws / ".bimai" / "people.yaml").write_text(": : :\n", encoding="utf-8")
    assert [p.file for p in validate(ws)] == [".bimai/people.yaml"]


# -- workflow graph --------------------------------------------------------------

def test_unknown_step(ws):
    write_workflow(ws, {"b": {"needs": ["fetch"], "tool": "y"}})
    assert messages(validate(ws)) == [".bimai/workflows/test.yaml: steps.b.needs: step 'fetch' does not exist"]


def test_cycle(ws):
    write_workflow(ws, {"a": {"needs": ["b"], "tool": "x"}, "b": {"needs": ["a"], "tool": "y"}})
    assert messages(validate(ws)) == [".bimai/workflows/test.yaml: steps: cycle: a -> b -> a"]


def test_step_needs_exactly_one_type(ws):
    write_workflow(ws, {"a": {"script": "p/s.py", "agent": "scribe"}, "b": {"needs": ["a"]}})
    problems = validate(ws)
    assert {p.location for p in problems} == {"steps.a", "steps.b"}
    assert "found: script, agent" in next(p.message for p in problems if p.location == "steps.a")


def test_unknown_step_key_is_a_typo(ws):
    write_workflow(ws, {"a": {"tool": "x", "neds": ["b"]}})
    assert any("neds" in p.message for p in validate(ws))


# -- output ----------------------------------------------------------------------

def test_problem_lines_and_summary(ws, capsys):
    edit(ws / ".bimai" / "project.yaml", lambda d: d.pop("id"))
    write_workflow(ws, {"b": {"needs": ["fetch"], "tool": "y"}})
    assert main(["validate", str(ws)]) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith(".bimai/project.yaml: ")
    assert lines[1].startswith(".bimai/workflows/test.yaml: ")
    assert lines[2] == "2 problems found"


def test_json_output(capsys):
    assert main(["validate", str(EXAMPLE), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"valid": True, "problems": []}


def test_json_output_with_problems(ws, capsys):
    edit(ws / ".bimai" / "project.yaml", lambda d: d.pop("id"))
    assert main(["validate", str(ws), "--json"]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is False
    assert set(out["problems"][0]) == {"file", "location", "message"}
