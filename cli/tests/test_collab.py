"""Working together: three personas in one project (collab.py and its commands)."""
from __future__ import annotations

import datetime as dt
import io
import json
from pathlib import Path

import pytest
import yaml

from bimai import collab, nap
from bimai.cli import main
from bimai.validate import validate


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Anna (BIM coordinator) starts the project; Joris (constructeur) and Fatima (BIM modeller) join."""
    monkeypatch.setattr("bimai.connections.claude_cli", lambda: None)
    root = tmp_path / "viaduct"
    root.mkdir()
    (root / "Viaduct.esa").write_bytes(b"esa")
    (root / "Deck.rvt").write_bytes(b"rvt")
    assert main(["init", str(root), "--person", "Anna", "--role", "BIM coordinator", "--goals", "issues,meetings",
                 "--tools", "acc,revit", "--yes"]) == 0
    return root


def files(root: Path, *names) -> dict:
    return {n: (root / n).read_text(encoding="utf-8") for n in names if (root / n).exists()}


def join(root, person, role, *extra):
    return main(["join", str(root), "--person", person, "--role", role, "--yes", *extra])


def test_three_personas_join_without_breaking_each_other(project):
    anna_agents = sorted(p.name for p in (project / ".claude" / "agents").glob("*.md"))
    assert join(project, "Joris", "constructeur", "--goals", "calculations", "--tools", "scia") == 0
    assert join(project, "Fatima", "BIM modeller", "--goals", "model-checks", "--tools", "revit") == 0
    assert validate(project) == []
    agents = sorted(p.name for p in (project / ".claude" / "agents").glob("*.md"))
    assert set(anna_agents) <= set(agents) and "structural-analyst.md" in agents and "model-checker.md" in agents
    claude_md = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Anna" not in claude_md and "Joris" not in claude_md and "seat brief" in claude_md
    ownership = yaml.safe_load((project / ".bimai" / "ownership.yaml").read_text(encoding="utf-8"))["positions"]
    assert ownership["constructeur"]["held_by"] == ["joris"] and ownership["bim-modeller"]["held_by"] == ["fatima"]

    shared = [".claude/agents/" + a for a in agents] + ["CLAUDE.md", ".mcp.json"]
    before = files(project, *shared)
    for seat in ("anna", "joris", "fatima"):                 # any seat regenerating writes the same shared files
        assert main(["team", str(project), "--seat", seat]) == 0
        assert files(project, *shared) == before, seat


def test_join_refuses_twice_and_init_points_to_join(project, capsys):
    assert join(project, "Joris", "constructeur") == 0
    assert join(project, "Joris", "constructeur") == 2
    assert "already has a seat" in capsys.readouterr().err
    assert main(["init", str(project), "--person", "Bob", "--yes"]) == 2
    assert "bimai join" in capsys.readouterr().err
    assert main(["join", str(project), "--person", "Bob", "--role", "astronaut", "--yes"]) == 2
    assert "Available roles" in capsys.readouterr().err


def test_second_modeller_gets_their_own_or_a_shared_position(project):
    assert join(project, "Fatima", "BIM modeller") == 0
    assert join(project, "Bob", "BIM modeller") == 0                                   # default: his own
    assert join(project, "Ines", "BIM modeller", "--position", "bim-modeller") == 0    # shares Fatima's
    positions = yaml.safe_load((project / ".bimai" / "ownership.yaml").read_text(encoding="utf-8"))["positions"]
    assert positions["bim-modeller-bob"]["held_by"] == ["bob"]
    assert positions["bim-modeller"]["held_by"] == ["fatima", "ines"] and positions["bim-modeller"]["lead"] == "fatima"
    assert validate(project) == []


def test_join_dry_run_writes_nothing(project, capsys):
    before = files(project, ".bimai/people.yaml", ".bimai/ownership.yaml")
    assert join(project, "Joris", "constructeur", "--tools", "scia", "--dry-run", "--json") == 0
    out = json.loads(capsys.readouterr().out)
    assert out["position"] == "constructeur" and "structural-analyst" in [m["role"] for m in out["team"]["members"]]
    assert files(project, ".bimai/people.yaml", ".bimai/ownership.yaml") == before
    assert not (project / ".bimai" / "seats" / "joris").exists()


def test_join_interview(project, capsys):
    assert main(["join", str(project), "--interview"]) == 0
    spec = json.loads(capsys.readouterr().out)
    q = {q["id"]: q for q in spec["steps"][0]["questions"]}
    assert list(q) == ["person", "role"] and spec["project"] == "viaduct"
    assert q["role"]["options"][0]["label"] == "Constructeur"                        # the folder has a .esa file
    assert join(project, "Fatima", "BIM modeller") == 0
    capsys.readouterr()
    assert main(["join", str(project), "--interview", "--role", "BIM modeller"]) == 0
    step = json.loads(capsys.readouterr().out)["steps"][0]
    position = next(q for q in step["questions"] if q["id"] == "position")
    assert [o["value"] for o in position["options"]] == [None, "bim-modeller"] and len(step["questions"]) <= 4


# -- handoffs, decisions, brief --------------------------------------------------------

def test_handoff_from_coordinator_to_modeller(project, capsys):
    join(project, "Fatima", "BIM modeller")
    capsys.readouterr()
    assert main(["handoff", "--path", str(project), "--seat", "anna", "--to", "bim-modeller",
                 "--title", "Clash between slab and duct at grid C4", "--evidence", "outputs/Clashes C4.bcfzip"]) == 0
    assert "Handed over to bim-modeller" in capsys.readouterr().out
    items = collab.inbox(project, "fatima")
    assert len(items) == 1 and items[0]["from"] == "anna" and items[0]["evidence"] == ["outputs/Clashes C4.bcfzip"]
    assert collab.inbox(project, "anna") == []
    assert main(["handoff", "--path", str(project), "--seat", "anna", "--done", items[0]["id"]]) == 2   # not hers
    assert main(["handoff", "--path", str(project), "--seat", "fatima", "--done", items[0]["id"], "--note", "moved the duct"]) == 0
    assert collab.inbox(project, "fatima") == [] and collab.inbox(project, "fatima", include_done=True)[0]["note"] == "moved the duct"
    assert main(["handoff", "--path", str(project), "--seat", "anna", "--to", "structure", "--title", "x"]) == 2
    assert "Positions: bim-coordinator (Anna); bim-modeller (Fatima)" in capsys.readouterr().err


def test_decisions_and_supersede(project, capsys):
    assert main(["decide", "--path", str(project), "--title", "Deck slab thickness", "--decision", "300 mm",
                 "--source", "coordination meeting 2026-10-21"]) == 0
    first = collab.decisions(project)[0]["id"]
    assert main(["decide", "--path", str(project), "--title", "Deck slab thickness", "--decision", "350 mm",
                 "--supersedes", first]) == 0
    items = collab.decisions(project)
    assert len(items) == 2 and items[0]["decision"] == "350 mm" and items[1]["status"] == "superseded"
    assert items[0]["id"] != items[1]["id"]                                         # same title, same day: no clash
    assert f".bimai/decisions/{first}.md" in nap.reversed_decisions(project)        # the nap treats it as reversed
    assert main(["decide", "--path", str(project), "--title", "x", "--decision", "y", "--supersedes", "nope"]) == 2
    capsys.readouterr()
    assert main(["decisions", "--path", str(project)]) == 0
    assert "(superseded)" in capsys.readouterr().out


def test_brief_says_who_and_whats_new(project):
    join(project, "Joris", "constructeur", "--goals", "calculations", "--tools", "scia")
    t0 = dt.datetime.now().replace(microsecond=0) - dt.timedelta(minutes=5)
    first = collab.brief(project, "joris", now=t0)
    assert "You work for **Joris** (Constructeur)" in first and "Positions: constructeur" in first
    assert "Structural Analyst" in first and "Anna (bim-coordinator)" in first
    collab.decide(project, "anna", "Load model", "Eurocode, CC2")
    collab.handoff(project, "anna", "constructeur", "Check the deck for the new duct opening")
    second = collab.brief(project, "joris", now=dt.datetime.now().replace(microsecond=0) + dt.timedelta(seconds=1))
    assert "Handoff to you (constructeur) from Anna (bim-coordinator): Check the deck" in second and "Decision" in second and "Load model" in second
    third = collab.brief(project, "joris", now=dt.datetime.now().replace(microsecond=0) + dt.timedelta(seconds=2))
    assert "Load model" not in third                                                # no longer new
    assert "from Anna (bim-coordinator)" in third                                             # still open
    assert len(first) <= collab.BRIEF_CHARS + 80


def test_brief_command_from_the_hook(project, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "SessionStart", "source": "compact"})))
    assert main(["brief", "--path", str(project), "--seat", "anna"]) == 0
    assert "You work for **Anna**" in capsys.readouterr().out
    assert not (project / ".bimai" / "state" / "brief-anna.json").exists()          # compaction isn't a new session


def test_my_seat_comes_from_personal_settings(project):
    join(project, "Joris", "constructeur")
    assert collab.my_seat(project) == "joris"                                       # the last setup on this computer
    assert main(["team", str(project), "--seat", "anna"]) == 0
    assert collab.resolve_seat(project, None) == "anna"


def test_team_log(project, capsys):
    join(project, "Joris", "constructeur")
    for seat, text in (("anna", "issue triage"), ("joris", "moment in B3")):
        folder = project / ".bimai" / "log" / seat
        folder.mkdir(parents=True)
        (folder / f"{dt.date.today().isoformat()}.md").write_text(f"# today · {seat}\n\n## 09:00\n- Asked: {text}\n", encoding="utf-8")
    assert main(["log", "--path", str(project), "--team", "--since", "today"]) == 0
    out = capsys.readouterr().out
    assert "issue triage" in out and "moment in B3" in out
