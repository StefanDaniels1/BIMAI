"""The onboarding interview as data, for Claude Code's question tool (AskUserQuestion).

The script owns the interview: which questions, which options (from the folder scan and the role), which
values are valid. Claude owns the conversation: it shows the options, maps an "Other" answer to an allowed
value, and passes everything back as `bimai init` flags, which the script validates.

Limits of the question tool: at most 4 questions per call, 2 to 4 options per question, headers of at most
12 characters, and an automatic "Other" with free text.
"""
from __future__ import annotations

import getpass
import re
from pathlib import Path

from bimai.init import suggested_tools
from bimai.scan import scan
from bimai.team import Catalogue, load_catalogue, match_preset

MAX_QUESTIONS = 4
MAX_OPTIONS = 4
MAX_HEADER = 12
TYPE_IT = {"label": "Type it yourself", "description": "Choose 'Other' below and type the answer.", "value": None}


def _option(label: str, description: str, value) -> dict:
    return {"label": label, "description": description, "value": value}


def _text_question(qid: str, header: str, question: str, suggestions: list[tuple[str, str]]) -> dict:
    seen, options = set(), []
    for value, description in suggestions:
        if value and value not in seen:
            seen.add(value)
            options.append(_option(value, description, value))
    options = options[:MAX_OPTIONS]
    if len(options) < 2:
        options.append(dict(TYPE_IT))
    return {"id": qid, "header": header, "question": question, "kind": "text", "multi_select": False,
            "options": options, "recommended": options[0]["value"]}


def _pretty(name: str) -> str:
    """'a2_tunnel-oost' -> 'A2 tunnel oost' (only when it differs from the folder name)."""
    spaced = re.sub(r"[-_]+", " ", name).strip()
    return spaced[:1].upper() + spaced[1:] if spaced else name


def step_one(root: Path, git_user: str | None, cat: Catalogue) -> dict:
    folder = root.name
    try:
        login = getpass.getuser()
    except Exception:
        login = ""
    roles = [_option(p.label, p.description, p.label) for p in cat.presets.values()]
    return {
        "step": 1,
        "questions": [
            _text_question("name", "Project", "What is the project called?",
                           [(_pretty(folder), "Based on the folder name"), (folder, "Exactly the folder name")]),
            _text_question("person", "Your name", "What is your name? It appears in the team files.",
                           [(git_user or "", "Your name in git"), (login, "Your login name on this computer")]),
            {"id": "role", "header": "Your role", "question": "What is your role on this project?",
             "kind": "choice", "multi_select": False, "options": roles[:MAX_OPTIONS], "recommended": None,
             "allowed": [{"value": p.label, "label": p.label, "also": list(p.matches)} for p in cat.presets.values()]},
            {"id": "language", "header": "Language", "question": "In which language should your team write documents?",
             "kind": "choice", "multi_select": False,
             "options": [_option("English", "Documents, minutes and reports in English", "en"),
                         _option("Nederlands", "Documenten, notulen en rapporten in het Nederlands", "nl")],
             "recommended": "en", "allowed": [{"value": "en", "label": "English"}, {"value": "nl", "label": "Nederlands"}]},
        ],
    }


def step_two(root: Path, role: str, cat: Catalogue) -> dict:
    preset = match_preset(role, cat)                     # UnknownRole when it can't be matched
    labels = cat.goal_labels
    goal_ids = list(preset.goal_options or preset.goals)[:MAX_OPTIONS]
    goals = [_option(labels[g]["label"], labels[g]["description"], g) for g in goal_ids]

    found = suggested_tools(scan(root), cat)              # tool id -> file that suggested it
    tool_ids = list(found)
    for t in preset.typical_tools:
        if t not in tool_ids:
            tool_ids.append(t)
    tools = []
    for t in tool_ids[:MAX_OPTIONS]:
        provides = ", ".join(cat.capabilities.get(c, c) for c in cat.tools[t]["provides"])
        description = f"Found in this folder: {found[t]}" if t in found else f"Lets your team {provides}"
        tools.append(_option(cat.tools[t]["label"], description, t))
    if len(tools) < 2:
        tools.append(dict(TYPE_IT))

    return {
        "step": 2,
        "role": preset.label,
        "questions": [
            {"id": "goals", "header": "Help with", "question": "What do you want your team to help you with?",
             "kind": "choice", "multi_select": True, "options": goals, "recommended": list(preset.goals),
             "allowed": [{"value": g, "label": labels[g]["label"]} for g in cat.goals]},
            {"id": "tools", "header": "Tools", "question": "Which tools and data does the project use?",
             "kind": "choice", "multi_select": True, "options": tools, "recommended": list(found),
             "allowed": [{"value": t, "label": v["label"]} for t, v in cat.tools.items()]},
            {"id": "new_to_vscode", "header": "VS Code", "question": "How familiar are you with VS Code?",
             "kind": "choice", "multi_select": False,
             "options": [_option("I know VS Code", "No extra help needed", False),
                         _option("I'm new to VS Code", "A Mentor joins your team to explain things", True)],
             "recommended": False, "allowed": [{"value": False, "label": "I know VS Code"},
                                               {"value": True, "label": "I'm new to VS Code"}]},
        ],
    }


def interview(root: str | Path, role: str | None = None, git_user: str | None = None,
              cat: Catalogue | None = None) -> dict:
    root = Path(root).resolve()
    cat = cat or load_catalogue()
    result = {
        "for": "Claude Code's AskUserQuestion tool: one call per step; options in the given order (recommended first); "
               "multi_select as given. Map an 'Other' answer to the closest allowed value and confirm it when unsure.",
        "init_command": "bimai init --name <name> --person <person> --role <role> --goals <goal,goal> "
                        "--tools <tool,tool> --language <en|nl> [--new-to-vscode] --yes",
    }
    if role is None:
        result["steps"] = [step_one(root, git_user, cat)]
        result["next"] = "After step 1, run: bimai init --interview --role \"<role>\"  (for step 2)"
    else:
        result["steps"] = [step_two(root, role, cat)]
        result["next"] = "After step 2, show the team first: the init command with --dry-run --json, then ask for a final yes."
    return result
