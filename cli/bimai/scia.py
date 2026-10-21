"""The SCIA Engineer bridge: a read-only MCP server (stdio) that reads calculation results through SCIA's OpenAPI.

SCIA's OpenAPI (shipped with SCIA Engineer, .NET Framework 4.8) starts a SCIA Engineer of its own and opens a
project file. The bridge loads it with pythonnet at run time, as SCIA's own Python example does
(github.com/scia-garage/open-api-adm-jupyter), so nothing of SCIA is redistributed. It always opens a copy of
the project and closes it without saving: the engineer's file is never touched.

Every OpenAPI call used here appears in SCIA's examples (scia-garage/open-api-adm-dotnet,
SciaOpenAPI_example_CSharp_simple_structure): Environment, RunSCIAEngineer, OpenProject, Model.FindGuid,
Model.InitializeResultsAPI, ResultKey, LoadResult, Result.GetMagnitudesCount / GetMagnitudeName /
GetSectionCount / GetSectionPosX / GetMeshElementCount / GetValue / GetTextOutput, RunCalculation, CloseProject.
"""
from __future__ import annotations

import atexit
import glob
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from bimai import __version__
from bimai.mcpstdio import Server, Tool, ToolError, schema

DOWNLOAD = "https://www.scia.net/en/scia-engineer/downloads"
UNITS = ("Values as SCIA's result API returns them (SI: N, N·m, m, Pa unless SCIA reports otherwise); "
         "check against SCIA's own output.")
MAX_SECTIONS = 101

# Result kinds -> (entity type, dimension, result type), with the enum names from SCIA's examples.
MEMBER_RESULTS = {"internal_forces": "eFemBeamInnerForces", "deformations": "eFemBeamDeformation",
                  "relative_deformations": "eFemBeamRelativeDeformation"}
SURFACE_RESULTS = {"internal_forces": "eFemInnerForces", "deformations": "eFemDeformations", "stresses": "eFemStress",
                   "strains": "eFemStrains", "contact_stresses": "eFemContactStress"}


# ------------------------------------------------------------------ finding SCIA Engineer

@dataclass(frozen=True)
class Installation:
    version: str
    path: str

    @property
    def openapi(self) -> str:
        return os.path.join(self.path, "OpenAPI_dll", "SCIA.OpenAPI.dll")


def _version_key(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3]) or (0,)


def installations(environ=None, registry: Callable | None = None, exists: Callable = os.path.exists) -> list[Installation]:
    """SCIA Engineer versions with the OpenAPI, newest first: SCIA's registry entries, then Program Files."""
    environ = os.environ if environ is None else environ
    found: dict[str, Installation] = {}
    for version, path in (registry or _registry)():
        inst = Installation(version, path)
        if exists(inst.openapi):
            found.setdefault(os.path.normcase(path), inst)
    for root in {environ.get("ProgramFiles", r"C:\Program Files"), environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")}:
        for path in glob.glob(os.path.join(root, "SCIA", "Engineer*")):
            inst = Installation(os.path.basename(path).replace("Engineer", "") or "?", path)
            if exists(inst.openapi):
                found.setdefault(os.path.normcase(path), inst)
    return sorted(found.values(), key=lambda i: _version_key(i.version), reverse=True)


def _registry() -> list[tuple[str, str]]:
    """(version, install folder) from HKCU\\Software\\SCIA\\ESA\\<version>\\Admin\\Dir (value SYSTEM)."""
    if sys.platform != "win32":
        return []
    import winreg
    out = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SCIA\ESA") as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                version = winreg.EnumKey(root, i)
                try:
                    with winreg.OpenKey(root, version + r"\Admin\Dir") as key:
                        out.append((version, str(winreg.QueryValueEx(key, "SYSTEM")[0])))
                except OSError:
                    continue
    except OSError:
        pass
    return out


# ------------------------------------------------------------------ the OpenAPI, through pythonnet

@dataclass
class ResultView:
    """A loaded result: magnitude names and values per section (members) or mesh element (surfaces)."""
    names: list[str]
    values: list[list[float]]                       # [magnitude][index]
    positions: list[float] | None = None            # members: section positions along the member
    text: str = ""                                  # SCIA's own text output (GetTextOutput)


class OpenApiBackend:
    """The real SCIA OpenAPI. Only constructed on Windows with SCIA Engineer installed."""

    def __init__(self, inst: Installation, temp: str, show: bool = False):
        self.inst, self.temp, self.show = inst, temp, show
        self.env = self.project = self.model = self.rapi = None

    def _load(self) -> None:
        import pythonnet
        try:
            pythonnet.load("netfx")                 # SCIA's OpenAPI is .NET Framework 4.8
        except RuntimeError:
            pass                                    # already loaded
        import clr
        import System
        folders = [os.path.join(self.inst.path, "OpenAPI_dll"), self.inst.path]
        sys.path.extend(f for f in folders if f not in sys.path)

        def resolve(sender, args):                  # SCIA's own examples resolve dependencies the same way
            name = args.Name.split(",")[0] + ".dll"
            for folder in folders:
                candidate = os.path.join(folder, name)
                if os.path.exists(candidate):
                    return System.Reflection.Assembly.LoadFrom(candidate)
            return None

        System.AppDomain.CurrentDomain.AssemblyResolve += System.ResolveEventHandler(resolve)
        clr.AddReference(os.path.join(folders[0], "SCIA.OpenAPI.dll"))
        import SCIA.OpenAPI as api
        import SCIA.OpenAPI.Results as results
        import Results64Enums as enums
        self.api, self.results, self.enums, self.System = api, results, enums, System

    def start(self) -> None:
        self._load()
        os.makedirs(self.temp, exist_ok=True)
        self.env = self.api.Environment(self.inst.path, self.temp, "1.0.0.0")
        modes = list(self.System.Enum.GetNames(self.api.Environment.GuiMode))
        wanted = ["ShowWindowShow"] if self.show else ["ShowWindowHide", "ShowWindowMinimize", "ShowWindowShow"]
        mode = next((m for m in wanted if m in modes), modes[0])
        if not self.env.RunSCIAEngineer(getattr(self.api.Environment.GuiMode, mode)):
            raise ToolError("SCIA Engineer didn't start. Is it licensed on this computer (including the OpenAPI)? "
                            f"Its log is in {self.temp}.")

    def open(self, path: str) -> None:
        self.close()
        self.project = self.env.OpenProject(path)
        if self.project is None:
            raise ToolError("SCIA Engineer couldn't open the project (the copy). Is it from a newer SCIA version?")
        self.model = self.project.Model
        self.rapi = self.model.InitializeResultsAPI()

    def calculate(self) -> None:
        self.project.RunCalculation()
        self.rapi = self.model.InitializeResultsAPI()

    def has_results(self) -> bool:
        return self.rapi is not None

    def load(self, entity: str, kind: str, case: str, combination: bool, name: str) -> ResultView | None:
        e = self.enums
        key = self.results.ResultKey()
        key.CaseType = e.eDsElementType.eDsElementType_Combination if combination else e.eDsElementType.eDsElementType_LoadCase
        key.CaseId = self.model.FindGuid(case)
        key.EntityName = name
        key.CoordSystem = e.eCoordSystem.eCoordSys_Local
        if entity == "member":
            key.EntityType, key.Dimension = e.eDsElementType.eDsElementType_Beam, e.eDimension.eDim_1D
            key.ResultType = getattr(e.eResultType, MEMBER_RESULTS[kind])
        elif entity == "surface":
            key.EntityType, key.Dimension = e.eDsElementType.eDsElementType_Slab, e.eDimension.eDim_2D
            key.ResultType = getattr(e.eResultType, SURFACE_RESULTS[kind])
        else:
            key.EntityType, key.Dimension = e.eDsElementType.eDsElementType_PointSupportPoint, e.eDimension.eDim_reactionsPoint
            key.ResultType = e.eResultType.eResultTypeReactionsSupport0D
        result = self.rapi.LoadResult(key)
        if result is None:
            return None
        names = [str(result.GetMagnitudeName(i)) for i in range(result.GetMagnitudesCount())]
        text = ""
        try:
            text = str(result.GetTextOutput())
        except Exception:
            pass
        if entity == "member":
            count = result.GetSectionCount()
            positions = [float(result.GetSectionPosX(i)) for i in range(count)]
        else:
            count = result.GetMeshElementCount() if entity == "surface" else max(1, _safe(result.GetSectionCount, 1))
            positions = None
        values = [[float(result.GetValue(m, i)) for i in range(count)] for m in range(len(names))]
        return ResultView(names, values, positions, text)

    def close(self) -> None:
        if self.project is not None:
            try:
                self.project.CloseProject(self.api.SaveMode.SaveChangesNo)
            except Exception:
                pass
        self.project = self.model = self.rapi = None

    def shutdown(self) -> None:
        self.close()
        if self.env is not None:
            try:
                self.env.Dispose()
            except Exception:
                pass
            self.env = None


def _safe(call: Callable, default):
    try:
        return call()
    except Exception:
        return default


# ------------------------------------------------------------------ the session: copies, results, summaries

@dataclass
class Session:
    root: Path
    backend_factory: Callable[[], object]
    workdir: Path = field(default_factory=lambda: Path(tempfile.gettempdir()) / "bimai-scia")
    backend: object = None
    original: Path | None = None
    copy: Path | None = None
    started: bool = False

    def _backend(self):
        if self.backend is None:
            self.backend = self.backend_factory()
        if not self.started:
            self.backend.start()
            self.started = True
        return self.backend

    def project_files(self) -> list[Path]:
        files = []
        for path in sorted(self.root.rglob("*.esa")):
            if ".bimai" not in path.parts and not path.name.startswith("~"):
                files.append(path)
            if len(files) >= 50:
                break
        return files

    def open_project(self, path: str | None) -> dict:
        if path:
            target = (self.root / path).resolve() if not os.path.isabs(path) else Path(path)
        else:
            files = self.project_files()
            if len(files) != 1:
                listing = ", ".join(str(f.relative_to(self.root)) for f in files[:20]) or "none found"
                raise ToolError(f"Which SCIA project? Give 'path'. .esa files in this project: {listing}")
            target = files[0]
        if target.suffix.lower() != ".esa" or not target.is_file():
            raise ToolError(f"No SCIA project file (.esa) at {target}")
        self.workdir.mkdir(parents=True, exist_ok=True)
        copy = self.workdir / f"{int(time.time() * 1000)}-{target.name}"
        shutil.copy2(target, copy)                          # the original is never opened by SCIA
        backend = self._backend()
        backend.open(str(copy))
        if self.copy and self.copy != copy:
            _remove(self.copy)
        self.original, self.copy = target, copy
        return {"project": str(self.relative(target)), "opened": "a copy (your file is never changed)",
                "results": "available" if backend.has_results() else "not calculated yet: use run_calculation",
                "scia": getattr(getattr(backend, "inst", None), "version", None)}

    def relative(self, path: Path) -> Path:
        try:
            return path.relative_to(self.root)
        except ValueError:
            return path

    def _ready(self):
        if self.copy is None:
            self.open_project(None)
        backend = self._backend()
        if not backend.has_results():
            raise ToolError("This project has no calculation results yet. Ask the person whether to run a linear "
                            "calculation on the copy (run_calculation); their file stays unchanged.")
        return backend

    def _load(self, entity: str, kind: str, case: str, case_type: str, name: str) -> tuple[ResultView, str]:
        backend = self._ready()
        order = {"load_case": [False], "combination": [True], "auto": [False, True]}.get(case_type)
        if order is None:
            raise ToolError("case_type must be load_case, combination or auto")
        errors = []
        for combination in order:
            try:
                view = backend.load(entity, kind, case, combination, name)
            except ToolError:
                raise
            except Exception as exc:
                errors.append(str(exc))
                continue
            if view is not None and view.names:
                return view, "combination" if combination else "load case"
        detail = f" (SCIA: {errors[-1][:200]})" if errors else ""
        raise ToolError(f"No {kind.replace('_', ' ')} for '{name}' in '{case}'. Check the names exactly as SCIA shows "
                        f"them, and that the case is calculated{detail}.")

    def member_results(self, member: str, case: str, kind: str = "internal_forces", case_type: str = "auto") -> dict:
        if kind not in MEMBER_RESULTS:
            raise ToolError(f"result must be one of: {', '.join(MEMBER_RESULTS)}")
        view, found = self._load("member", kind, case, case_type, member)
        count = len(view.positions or [])
        step = max(1, -(-count // MAX_SECTIONS))
        sections = [{"position": round(view.positions[i], 6),
                     **{n: _num(view.values[m][i]) for m, n in enumerate(view.names)}} for i in range(0, count, step)]
        if count and (count - 1) % step:
            i = count - 1
            sections.append({"position": round(view.positions[i], 6), **{n: _num(view.values[m][i]) for m, n in enumerate(view.names)}})
        return {"member": member, "case": case, "case_type": found, "result": kind, "sections_total": count,
                "sections": sections, "extremes": _extremes(view, view.positions, "position"), "units": UNITS}

    def surface_results(self, surface: str, case: str, kind: str = "internal_forces", case_type: str = "auto") -> dict:
        if kind not in SURFACE_RESULTS:
            raise ToolError(f"result must be one of: {', '.join(SURFACE_RESULTS)}")
        view, found = self._load("surface", kind, case, case_type, surface)
        return {"surface": surface, "case": case, "case_type": found, "result": kind,
                "mesh_elements": len(view.values[0]) if view.values else 0,
                "extremes": _extremes(view, None, "mesh_element"), "units": UNITS}

    def support_reactions(self, support: str, case: str, case_type: str = "auto") -> dict:
        view, found = self._load("support", "reactions", case, case_type, support)
        values = {n: (_num(v[0]) if len(v) == 1 else [_num(x) for x in v]) for n, v in zip(view.names, view.values)}
        out = {"support": support, "case": case, "case_type": found, "reactions": values, "units": UNITS}
        if not view.values or not any(view.values):
            out["text"] = view.text[:4000]
        return out

    def run_calculation(self) -> dict:
        if self.copy is None:
            self.open_project(None)
        backend = self._backend()
        backend.calculate()
        return {"project": str(self.relative(self.original)), "calculated": "linear calculation of the copy",
                "results": "available" if backend.has_results() else "still not available: check the model in SCIA",
                "your_file": "unchanged"}

    def shutdown(self) -> None:
        if self.backend is not None and self.started:
            try:
                self.backend.shutdown()
            except Exception:
                pass
        if self.copy:
            _remove(self.copy)


def _num(value: float) -> float | None:
    return None if value != value or value in (float("inf"), float("-inf")) else round(value, 6)


def _extremes(view: ResultView, positions: list[float] | None, where: str) -> dict:
    out = {}
    for m, name in enumerate(view.names):
        values = view.values[m]
        if not values:
            continue
        lo = min(range(len(values)), key=values.__getitem__)
        hi = max(range(len(values)), key=values.__getitem__)
        at = (lambda i: round(positions[i], 6)) if positions else (lambda i: i)
        out[name] = {"min": _num(values[lo]), f"min_{where}": at(lo), "max": _num(values[hi]), f"max_{where}": at(hi)}
    return out


def _remove(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ the MCP server

INSTRUCTIONS = ("Read-only access to SCIA Engineer calculation results on this computer. The bridge opens a copy of "
                "the project (.esa); the engineer's file is never changed. Use member, surface, support, load case "
                "and combination names exactly as SCIA shows them. Start with open_project.")


def tools(session: Session) -> list[Tool]:
    case = ("string", "Load case or combination name as in SCIA, e.g. LC1 or CO1")
    case_type = ("string", "load_case, combination, or auto (try both; default)")
    return [
        Tool("open_project", "Open a SCIA project",
             "Opens a copy of a SCIA Engineer project (.esa) from this project folder and says whether it has results. "
             "Without 'path', opens the only .esa file in the folder.",
             schema({"path": ("string", "Path to the .esa file, relative to the project folder")}),
             lambda a: session.open_project(a.get("path"))),
        Tool("get_member_results", "Member results",
             "Internal forces or deformations along a member (beam, column) for a load case or combination: values per "
             "section and the extremes.",
             schema({"member": ("string", "Member name as in SCIA, e.g. B3"), "case": case,
                     "result": ("string", "internal_forces (default), deformations or relative_deformations"),
                     "case_type": case_type}, ("member", "case"),
                    {"result": list(MEMBER_RESULTS), "case_type": ["auto", "load_case", "combination"]}),
             lambda a: session.member_results(a["member"], a["case"], a.get("result", "internal_forces"), a.get("case_type", "auto"))),
        Tool("get_surface_results", "Surface results",
             "Internal forces, deformations, stresses, strains or contact stresses of a surface (slab, wall) for a load "
             "case or combination: minimum and maximum per magnitude and the mesh element where they occur.",
             schema({"surface": ("string", "Surface name as in SCIA, e.g. S1"), "case": case,
                     "result": ("string", "internal_forces (default), deformations, stresses, strains or contact_stresses"),
                     "case_type": case_type}, ("surface", "case"),
                    {"result": list(SURFACE_RESULTS), "case_type": ["auto", "load_case", "combination"]}),
             lambda a: session.surface_results(a["surface"], a["case"], a.get("result", "internal_forces"), a.get("case_type", "auto"))),
        Tool("get_support_reactions", "Support reactions",
             "Reactions of a point support for a load case or combination.",
             schema({"support": ("string", "Support name as in SCIA, e.g. Sn1"), "case": case, "case_type": case_type},
                    ("support", "case"), {"case_type": ["auto", "load_case", "combination"]}),
             lambda a: session.support_reactions(a["support"], a["case"], a.get("case_type", "auto"))),
        Tool("run_calculation", "Run a linear calculation (on the copy)",
             "Runs SCIA's linear calculation on the opened copy when it has no results yet. The person's file is not "
             "changed. Can take minutes for large models: ask the person first.",
             schema({}), lambda a: session.run_calculation()),
    ]


def serve(root: Path, *, backend_factory: Callable | None = None, stdin=None, stdout=None, show: bool = False) -> int:
    log_path = Path(tempfile.gettempdir()) / "bimai-scia.log"

    def log(message: str) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + message + "\n")
        except OSError:
            pass

    def default_factory():
        if sys.platform != "win32":
            raise ToolError("SCIA Engineer runs on Windows, so its bridge only works on Windows.")
        found = installations()
        if not found:
            raise ToolError(f"SCIA Engineer (version 21 or newer, with the OpenAPI) wasn't found on this computer. {DOWNLOAD}")
        return OpenApiBackend(found[0], os.path.join(tempfile.gettempdir(), "bimai-scia", "scia-temp"), show)

    session = Session(root, backend_factory or default_factory)
    atexit.register(session.shutdown)
    server = Server("bimai-scia", "bimai SCIA Engineer bridge", __version__, INSTRUCTIONS, tools(session), log)
    try:
        server.serve(stdin, stdout)
    finally:
        session.shutdown()
    return 0
