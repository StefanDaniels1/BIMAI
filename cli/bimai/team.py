"""Compose a lean team from a role preset and the onboarding answers (ARCHITECTURE.md §5.5).

Pure: every rule here is deterministic, so a proposal can be tested without touching disk.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

import yaml

MAX_MEMBERS = 5
ALWAYS = "coordinator"
MENTOR = "mentor"


class UnknownRole(Exception):
    pass


@dataclass(frozen=True)
class Role:
    id: str
    label: str
    description: str
    model: str
    handles: str
    examples: tuple[str, ...]
    requires: tuple[str, ...]
    serves: tuple[str, ...]
    charter: str
    uses: tuple[str, ...] = ()           # optional capabilities: used when connected, never required


@dataclass(frozen=True)
class Preset:
    id: str
    label: str
    matches: tuple[str, ...]
    team: tuple[str, ...]
    goals: tuple[str, ...]


@dataclass(frozen=True)
class Catalogue:
    roles: dict[str, Role]
    presets: dict[str, Preset]
    goals: tuple[str, ...]
    tools: dict[str, dict]          # id -> {label, provides}
    suggests: dict[str, str]        # scan suggestion key -> tool id
    capabilities: dict[str, str]    # capability -> words people understand

    def provided(self, tools) -> set[str]:
        return {cap for t in tools for cap in self.tools[t]["provides"]}


@dataclass
class Member:
    role: str
    why: str


@dataclass
class Team:
    preset: str
    members: list[Member]
    hints: list[str] = field(default_factory=list)   # roles that would join with more data

    def as_dict(self) -> dict:
        return {"preset": self.preset, "members": [{"role": m.role, "why": m.why} for m in self.members],
                "hints": self.hints}


def _front_matter(text: str) -> tuple[dict, str]:
    _, meta, body = text.split("---\n", 2)
    return yaml.safe_load(meta), body.strip() + "\n"


@cache
def load_catalogue() -> Catalogue:
    base = resources.files("bimai").joinpath("catalogue")
    roles = {}
    for f in sorted(base.joinpath("roles").iterdir(), key=lambda f: f.name):
        if not f.name.endswith(".md"):
            continue
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        roles[meta["name"]] = Role(meta["name"], meta["label"], meta["description"], meta["model"],
                                   meta["handles"], tuple(meta["examples"]),
                                   tuple(meta.get("requires") or ()), tuple(meta.get("serves") or ()), body,
                                   tuple(meta.get("uses") or ()))
    presets = {}
    for f in sorted(base.joinpath("presets").iterdir(), key=lambda f: f.name):
        if not f.name.endswith(".yaml"):
            continue
        p = yaml.safe_load(f.read_text(encoding="utf-8"))
        presets[p["id"]] = Preset(p["id"], p["label"], tuple(p["matches"]), tuple(p["team"]), tuple(p["goals"]))
    tools = yaml.safe_load(base.joinpath("tools.yaml").read_text(encoding="utf-8"))
    return Catalogue(roles, presets, tuple(tools["goals"]), tools["tools"], tools["suggests"], tools["capabilities"])


def normalize(text: str) -> str:
    """'BIM-coördinator ' -> 'bim coordinator'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").replace("_", " ").split())


def match_preset(role: str, cat: Catalogue) -> Preset:
    wanted = normalize(role)
    for preset in cat.presets.values():
        if wanted == normalize(preset.id) or wanted in {normalize(m) for m in preset.matches}:
            return preset
    options = ", ".join(p.label for p in cat.presets.values())
    raise UnknownRole(f"no role preset matches '{role}'. Available roles: {options}")


def _names(items, labels) -> str:
    return ", ".join(labels[i] for i in items)


def propose(role: str, goals, tools, new_to_vscode: bool, cat: Catalogue | None = None) -> Team:
    cat = cat or load_catalogue()
    preset = match_preset(role, cat)
    goals, tools = list(goals), list(tools)
    provided = cat.provided(tools)
    tool_labels = {t: v["label"] for t, v in cat.tools.items()}
    members: list[Member] = []
    hints: list[str] = []

    for rid in preset.team:
        r = cat.roles[rid]
        if rid == ALWAYS:
            members.append(Member(rid, "Always"))
            continue
        served = [g for g in goals if g in r.serves]
        if not served:
            continue
        missing = [c for c in r.requires if c not in provided]
        if missing:
            wanted = [t for t, v in cat.tools.items() if any(c in v["provides"] for c in missing)]
            hints.append(f"{r.label} would join with: {' or '.join(tool_labels[t] for t in wanted)}")
            continue
        why = f"Goal{'s' if len(served) > 1 else ''}: {', '.join(served)}"
        data = [t for t in tools if any(c in cat.tools[t]["provides"] for c in r.requires)]
        if data:
            why += f" · Data: {_names(data, tool_labels)}"
        members.append(Member(rid, why))

    if new_to_vscode:
        members.append(Member(MENTOR, "New to VS Code"))
    if len(members) > MAX_MEMBERS:
        dropped = members[MAX_MEMBERS - 1:-1] if new_to_vscode else members[MAX_MEMBERS:]
        members = [m for m in members if m not in dropped]
        hints.append(f"Team limit of {MAX_MEMBERS} reached; left out: "
                     + ", ".join(cat.roles[m.role].label for m in dropped))
    return Team(preset.id, members, hints)
