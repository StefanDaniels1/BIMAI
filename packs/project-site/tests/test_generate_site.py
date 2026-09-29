"""Tests for the project-site generator. Run: python -m pytest packs/project-site/tests"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import sys
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
DEMO = HERE.parent / "examples" / "knooppunt-oost"
sys.path.insert(0, str(HERE.parent / "scripts"))

from generate_site import generate, mdx_cell, mdx_markdown, mdx_text, mm, short  # noqa: E402

TODAY = dt.date(2026, 9, 26)


@pytest.fixture
def project(tmp_path):
    """A writable copy of the demo project."""
    root = tmp_path / "project"
    shutil.copytree(DEMO, root)
    return root


def build(project, tmp_path, **kw):
    out = tmp_path / "site"
    generate(project, out, public_dir=tmp_path / "public", base_url="/docs/p", today=TODAY, **kw)
    return out


def all_text(out: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file())


# ---------------------------------------------------------------- escaping
def test_mdx_text_escapes_jsx_and_expressions():
    assert mdx_text("a {b} <c>") == "a \\{b\\} &lt;c&gt;"


def test_mdx_cell_escapes_pipes_and_newlines():
    assert mdx_cell("a | b\nc") == "a \\| b c"
    assert mdx_cell(None) == "—"


def test_mdx_markdown_keeps_code_intact():
    md = "Use `<zone>` and {x}\n```\n<keep> {as is}\n```\nAfter <b>"
    out = mdx_markdown(md)
    assert "`<zone>`" in out and "\\{x\\}" in out
    assert "<keep> {as is}" in out
    assert out.endswith("After &lt;b&gt;")


def test_mermaid_labels_and_short():
    assert mm('say "hi" <b>{x}</b>') == "say #quot;hi#quot; bx/b"
    assert short("Add the verification property to the drainage elements", 30) == "Add the verification property…"
    assert short("short") == "short"


# ---------------------------------------------------------------- the demo site
def test_demo_generates_every_page(project, tmp_path):
    out = build(project, tmp_path)
    expected = {"index.mdx", "people.mdx", "ai-teams.mdx", "how-we-work.mdx", "agreements.mdx",
                "decisions.mdx", "this-week.mdx", "meta.json", "meetings/index.mdx",
                "meetings/meta.json", "meetings/2026-09-22-coordination.mdx"}
    assert expected <= {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()}


def test_overview_counts_and_links(project, tmp_path):
    index = (build(project, tmp_path) / "index.mdx").read_text(encoding="utf-8")
    assert '<Card title="6" description="people on the project" />' in index      # externals not counted
    assert '<Card title="19" description="AI agents across all teams" />' in index
    assert 'description="Models, issues and documents"' in index
    assert "/project-files/knooppunt-oost/BEP-Knooppunt-Oost-v3.pdf" in index


def test_bep_is_copied_for_download(project, tmp_path):
    build(project, tmp_path)
    assert (tmp_path / "public" / "BEP-Knooppunt-Oost-v3.pdf").exists()


def test_agreements_show_their_source(project, tmp_path):
    text = (build(project, tmp_path) / "agreements.mdx").read_text(encoding="utf-8")
    assert "BIM execution plan v3 · p. 21 · §6.1 Naming" in text
    assert "`KNO-<originator>-<zone>-<level>-<type>-<role>-<number>`" in text  # inline code, not escaped
    assert "Open questions" in text


def test_active_cover_is_shown(project, tmp_path):
    people = (build(project, tmp_path) / "people.mdx").read_text(encoding="utf-8")
    assert "Ruben Smit → 2026-10-09" in people
    assert "covers modeller-roads-zone-a until 2026-10-09" in people


def test_expired_cover_is_not_shown(project, tmp_path):
    own = project / ".bimai" / "ownership.yaml"
    data = yaml.safe_load(own.read_text(encoding="utf-8"))
    data["cover"][0].update({"from": "2026-08-01", "until": "2026-08-15"})
    own.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert "covers" not in (build(project, tmp_path) / "people.mdx").read_text(encoding="utf-8")


def test_teams_and_handoffs(project, tmp_path):
    text = (build(project, tmp_path) / "ai-teams.mdx").read_text(encoding="utf-8")
    assert 'subgraph S_sanne["Sanne Visser · bim-coordinator"]' in text
    assert 'S_sanne -->|"Handoff: Fix the wall types in the structural model"| S_eva' in text  # to the lead


def test_long_workflows_are_drawn_top_to_bottom(project, tmp_path):
    text = (build(project, tmp_path) / "how-we-work.mdx").read_text(encoding="utf-8")
    assert "flowchart TB" in text        # meeting-intake has 8 steps
    assert "Weekdays 07:45" in text and "Fridays 08:00" in text


# ---------------------------------------------------------------- nothing private leaks
def test_private_journal_sessions_stay_private(project, tmp_path):
    (project / ".bimai/seats/ruben/journal/2026-09-25.md").write_text(
        "---\ndate: 2026-09-25\nprivate: true\n---\n- SECRET-NOTE about a sensitive topic\n", encoding="utf-8")
    text = all_text(build(project, tmp_path))
    assert "SECRET-NOTE" not in text
    assert "A private session (not shared)." in (tmp_path / "site" / "this-week.mdx").read_text(encoding="utf-8")


def test_raw_transcripts_and_desk_are_never_read(project, tmp_path):
    meeting = project / ".bimai/meetings/2026-09-22-coordination"
    (meeting / "transcript.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v X>RAW-TRANSCRIPT-LINE</v>\n", encoding="utf-8")
    desk = project / "desk"
    desk.mkdir()
    (desk / "tasks.yaml").write_text("- { title: DESK-ONLY-TASK }\n", encoding="utf-8")
    text = all_text(build(project, tmp_path))
    assert "RAW-TRANSCRIPT-LINE" not in text and "DESK-ONLY-TASK" not in text


def test_pending_meetings_are_not_published(project, tmp_path):
    pending = project / ".bimai/meetings/2026-09-25-design"
    pending.mkdir()
    (pending / "meeting.yaml").write_text("title: Design review\ndate: 2026-09-25\nstatus: pending\nuploader: daan\n", encoding="utf-8")
    (pending / "minutes.md").write_text("# Design review\n- UNCONFIRMED-ITEM\n", encoding="utf-8")
    out = build(project, tmp_path)
    assert "UNCONFIRMED-ITEM" not in all_text(out)
    assert not (out / "meetings" / "2026-09-25-design.mdx").exists()


def test_user_text_cannot_inject_jsx(project, tmp_path):
    (project / ".bimai/decisions/2026-09-24-evil.md").write_text(
        "---\nid: evil\ndate: 2026-09-24\ntitle: \"Use <script>alert(1)</script> {process.exit()}\"\nby: sanne\n---\n"
        "Body with <Callout> and {danger}.\n", encoding="utf-8")
    text = (build(project, tmp_path) / "decisions.mdx").read_text(encoding="utf-8")
    assert "<script>" not in text and "<Callout> and" not in text
    assert not re.search(r"(?<!\\)\{(process|danger)", text)   # every brace is escaped
    assert "&lt;script&gt;" in text and "\\{danger\\}" in text


# ---------------------------------------------------------------- language and errors
def test_dutch_project_site(project, tmp_path):
    cfg = project / ".bimai/project.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("language: en", "language: nl"), encoding="utf-8")
    out = build(project, tmp_path)
    assert "## In één oogopslag" in (out / "index.mdx").read_text(encoding="utf-8")
    assert "Werkdagen 07:45" in (out / "how-we-work.mdx").read_text(encoding="utf-8")
    assert '"title": "Overleggen"' in (out / "meetings" / "meta.json").read_text(encoding="utf-8")


def test_missing_project_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        generate(tmp_path, tmp_path / "out", today=TODAY)
