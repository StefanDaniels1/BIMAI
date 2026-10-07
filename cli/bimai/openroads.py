"""Installing the bimai OpenRoads bridge: built on the user's PC, against the OpenRoads Designer installed there.

Bentley's API assemblies can't be redistributed, so the release holds the bridge's source (C# 5, pinned by
SHA-256 like every bimai download). bimai compiles it with the C# compiler that ships with Windows' .NET
Framework 4.8, once per installed OpenRoads Designer, into C:\\ProgramData\\bimai\\openroads\\<version>, and
registers it with one small configuration file in OpenRoads' own configuration folder (Bentley's documented
way to load an add-in automatically). That one file needs Windows' permission; the bridge itself doesn't.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from bimai import bridges
from bimai import connections as conn
from bimai.bridges import BridgeError

DLL = "BimaiOpenRoads.dll"
CFG = "bimai-openroads.cfg"
PROCESS = "OpenRoadsDesigner.exe"
PLATFORM_ASSEMBLY = "Bentley.MstnPlatformNET.dll"

WHY_PERMISSION = (
    "Windows will now ask: \"Do you want to allow this app to make changes to your device?\"\n"
    "  Why: OpenRoads Designer only loads add-ins named in its configuration folder, inside C:\\Program Files.\n"
    "  Only administrators may write there, so Windows asks you once. bimai writes one small text file there\n"
    f"  ({CFG}) that points to the bridge in C:\\ProgramData\\bimai\\openroads, and changes nothing else.\n"
    "  Click Yes to continue. (No admin rights? Choose No, and ask IT to run this command.)")


@dataclass(frozen=True)
class Installation:
    name: str           # e.g. "OpenRoads Designer 2024"
    root: str           # the folder with OpenRoadsDesigner.exe

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")

    @property
    def cfg(self) -> str:
        return os.path.join(self.root, "config", "appl", CFG)


def installations(environ=None) -> list[Installation]:
    """OpenRoads Designer versions installed under Program Files\\Bentley (CONNECT Edition and 2023+)."""
    environ = os.environ if environ is None else environ
    program_files = environ.get("ProgramFiles", r"C:\Program Files")
    found = []
    for exe in sorted(glob.glob(os.path.join(program_files, "Bentley", "*", "OpenRoadsDesigner", PROCESS))):
        root = os.path.dirname(exe)
        found.append(Installation(os.path.basename(os.path.dirname(root)), root))
    return found


def target_dir(inst: Installation, environ=None) -> str:
    environ = os.environ if environ is None else environ
    return os.path.join(environ.get("ProgramData", r"C:\ProgramData"), "bimai", "openroads", inst.slug)


def cfg_text(dll_dir: str) -> str:
    folder = dll_dir.rstrip("\\/") + "\\"
    return (f"# bimai OpenRoads bridge, read-only. https://docs.bimai.nl/docs/guides/openroads-bridge\n"
            f"# Written by `bimai bridge install openroads`. To stop loading it: bimai bridge uninstall openroads\n"
            f"_BIMAI_OPENROADS_={folder}\n"
            f"%if exists ($(_BIMAI_OPENROADS_){DLL})\n"
            f"MS_ADDINPATH < $(_BIMAI_OPENROADS_)\n"
            f"MS_DGNAPPS < {DLL}\n"
            f"%endif\n")


def compiler(environ=None) -> str:
    environ = os.environ if environ is None else environ
    windir = environ.get("WINDIR") or environ.get("SystemRoot") or r"C:\Windows"
    return os.path.join(windir, "Microsoft.NET", "Framework64", "v4.0.30319", "csc.exe")


def platform_assembly(inst: Installation) -> str | None:
    """Bentley.MstnPlatformNET.dll: next to the executable, or in a subfolder (Assemblies)."""
    for pattern in (PLATFORM_ASSEMBLY, os.path.join("*", PLATFORM_ASSEMBLY), os.path.join("*", "*", PLATFORM_ASSEMBLY)):
        hits = sorted(glob.glob(os.path.join(inst.root, pattern)))
        if hits:
            return hits[0]
    return None


def installed(environ=None, exists=None) -> list[Installation]:
    """The OpenRoads Designer versions that have the bridge registered and present."""
    exists = exists or os.path.exists
    return [i for i in installations(environ)
            if exists(i.cfg) and exists(os.path.join(target_dir(i, environ), DLL))]


def installed_version(inst: Installation, environ=None) -> str | None:
    try:
        return Path(target_dir(inst, environ), "version.txt").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


# ------------------------------------------------------------------ build

def unpack_sources(zip_path: Path, workdir: Path) -> list[Path]:
    """The bridge's C# sources from a release zip (src/*.cs only; unsafe paths refused)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            sources = []
            for name in z.namelist():
                p = PurePosixPath(name)
                if p.is_absolute() or ".." in p.parts or ":" in name:
                    raise BridgeError("The zip contains unsafe paths; nothing was installed.")
                if len(p.parts) == 2 and p.parts[0] == "src" and p.suffix == ".cs":
                    target = workdir / p.name
                    target.write_bytes(z.read(name))
                    sources.append(target)
    except zipfile.BadZipFile as exc:
        raise BridgeError("That file is not a valid OpenRoads bridge zip.") from exc
    if not any(s.name == "AddIn.cs" for s in sources):
        raise BridgeError("That zip doesn't contain the OpenRoads bridge sources (src/AddIn.cs).")
    return sorted(sources)


def build(inst: Installation, sources: list[Path], out_dll: Path, *, run: Callable, environ=None) -> None:
    """Compiles the bridge against this OpenRoads Designer's assemblies. Raises BridgeError naming the version."""
    csc = compiler(environ)
    platform = platform_assembly(inst)
    if platform is None:
        raise BridgeError(f"{inst.name}: {PLATFORM_ASSEMBLY} wasn't found in {inst.root}, so the bridge can't be built "
                          "for it. Is this a complete OpenRoads Designer installation?")
    references = [platform]
    lib_dirs = sorted({os.path.dirname(platform), inst.root})
    for _ in range(8):     # add assemblies the compiler asks for (CS0012), from OpenRoads' own folders
        cmd = [csc, "/nologo", "/target:library", "/langversion:5", "/optimize+", f"/out:{out_dll}",
               *(f"/lib:{d}" for d in lib_dirs), "/r:System.dll", "/r:System.Core.dll", "/r:System.Windows.Forms.dll",
               *(f"/r:{r}" for r in references), *(str(s) for s in sources)]
        try:
            out = run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=300)
        except FileNotFoundError as exc:
            raise BridgeError(f"The .NET Framework C# compiler wasn't found ({csc}). It comes with Windows 10 and 11; "
                              "ask IT to repair the .NET Framework 4.8.") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise BridgeError(f"{inst.name}: the C# compiler didn't run ({exc}).") from exc
        text = (out.stdout or "") + (out.stderr or "")
        if out.returncode == 0:
            return
        missing = [m for m in re.findall(r"assembly '([^',]+),", text) if m]
        new = [path for m in missing for path in [_find_assembly(inst, m)] if path and path not in references]
        if not new:
            errors = [line.strip() for line in text.splitlines() if "error" in line.lower()][:5]
            raise BridgeError(f"{inst.name}: the bridge didn't compile against this OpenRoads Designer:\n    "
                              + "\n    ".join(errors or [text.strip()[-500:]])
                              + "\n  Please report this with your OpenRoads version (https://github.com/StefanDaniels1/BIMAI/issues).")
        references += new
    raise BridgeError(f"{inst.name}: the bridge didn't compile (too many missing references).")


def _find_assembly(inst: Installation, name: str) -> str | None:
    for pattern in (f"{name}.dll", os.path.join("*", f"{name}.dll"), os.path.join("*", "*", f"{name}.dll")):
        hits = sorted(glob.glob(os.path.join(inst.root, pattern)))
        if hits:
            return hits[0]
    return None


def _running(run: Callable) -> bool:
    try:
        out = run(["tasklist", "/FI", f"IMAGENAME eq {PROCESS}", "/NH"], capture_output=True,
                  encoding="utf-8", errors="replace", timeout=15)
        return PROCESS.lower() in (out.stdout or "").lower()
    except (OSError, subprocess.SubprocessError):
        return False


# ------------------------------------------------------------------ install, uninstall, status

def install(server: conn.Server, *, zip_path: Path | None = None, ask: Callable[[str], bool], say: Callable[[str], None],
            platform: str | None = None, run: Callable | None = None, opener: Callable | None = None,
            environ=None) -> list[str]:
    """Builds and registers the bridge for every installed OpenRoads Designer; returns their names."""
    run = run or subprocess.run
    opener = opener or urllib.request.urlopen
    environ = os.environ if environ is None else environ
    if (platform or conn.PLATFORM) != "windows":
        raise BridgeError("OpenRoads Designer runs on Windows, so its bridge can only be installed on Windows.")
    found = installations(environ)
    if not found:
        raise BridgeError("No OpenRoads Designer was found on this computer (looked in "
                          f"{os.path.join(environ.get('ProgramFiles', 'C:/Program Files'), 'Bentley')}).")
    rel = bridges.release_of(server)
    if zip_path is None and not (rel and rel.sha256):
        raise BridgeError(f"No verified release of {server.label} is published yet. Install a zip you have with: "
                          f"bimai bridge install {server.name} --from <zip>")
    while _running(run):
        if not ask("OpenRoads Designer is running. Close it (save your work first), then continue? (Y/n)"):
            raise BridgeError("OpenRoads Designer must be closed to install the bridge. Close it and try again.")

    with tempfile.TemporaryDirectory(prefix="bimai-openroads-") as tmp:
        work = Path(tmp)
        if zip_path is None:
            say(f"Downloading {server.label} {rel.version}…")
            zip_path = bridges.download(rel.url, work / rel.asset, opener=opener)
            bridges.verify(zip_path, rel.sha256)
            say("✓ Download verified.")
        elif not zip_path.is_file():
            raise BridgeError(f"No file at {zip_path}.")
        else:
            say(f"Installing from {zip_path} (SHA-256 {bridges.sha256_file(zip_path)}).")
        (work / "src").mkdir()
        sources = unpack_sources(zip_path, work / "src")
        version = rel.version if rel and zip_path.parent == work else "local"

        built: list[Installation] = []
        failures: list[str] = []
        for inst in found:
            say(f"Building the bridge for {inst.name}…")
            out = work / inst.slug / DLL
            out.parent.mkdir()
            try:
                build(inst, sources, out, run=run, environ=environ)
            except BridgeError as exc:
                failures.append(str(exc))
                say(f"  ✗ {exc}")
                continue
            dest = Path(target_dir(inst, environ))
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(out, dest / DLL)
            (dest / "version.txt").write_text(version + "\n", encoding="utf-8")
            built.append(inst)
            say(f"  ✓ built for {inst.name}")
        if not built:
            raise BridgeError("The bridge couldn't be built for any OpenRoads Designer on this computer.\n  "
                              + "\n  ".join(failures))

        pending = [i for i in built if _read(i.cfg) != cfg_text(target_dir(i, environ))]
        if pending:
            lines = ["$ErrorActionPreference = 'Stop'"]
            for i in pending:
                staged = work / f"{i.slug}.cfg"
                staged.write_text(cfg_text(target_dir(i, environ)), encoding="utf-8")
                lines.append(f"New-Item -ItemType Directory -Force -Path {bridges._ps_quote(os.path.dirname(i.cfg))} | Out-Null")
                lines.append(f"Copy-Item -LiteralPath {bridges._ps_quote(str(staged))} -Destination {bridges._ps_quote(i.cfg)} -Force")
            script = work / "register.ps1"
            script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
            say(WHY_PERMISSION)
            code, error = bridges.run_elevated(f'-NoProfile -ExecutionPolicy Bypass -File "{script}"', run)
            if code != 0:
                if bridges._declined(error):
                    raise BridgeError("The bridge was built but not registered: the Windows permission prompt was declined. "
                                      f"Ask IT to run: bimai bridge install {server.name}")
                raise BridgeError(f"Registering the bridge stopped with an error: {error.strip()[-400:]}")
    names = [i.name for i in built]
    say(f"✓ {server.label} installed for {', '.join(names)}. It starts together with OpenRoads Designer.")
    return names


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def uninstall(server: conn.Server, *, say: Callable[[str], None], platform: str | None = None,
              run: Callable | None = None, environ=None) -> None:
    run = run or subprocess.run
    environ = os.environ if environ is None else environ
    if (platform or conn.PLATFORM) != "windows":
        raise BridgeError(f"{server.label} only exists on Windows.")
    registered = [i for i in installations(environ) if os.path.exists(i.cfg)]
    if registered:
        if _running(run):
            raise BridgeError("Close OpenRoads Designer first, then try again.")
        with tempfile.TemporaryDirectory(prefix="bimai-openroads-") as tmp:
            script = Path(tmp) / "unregister.ps1"
            script.write_text("\r\n".join(f"Remove-Item -LiteralPath {bridges._ps_quote(i.cfg)} -Force" for i in registered)
                              + "\r\n", encoding="utf-8")
            code, error = bridges.run_elevated(f'-NoProfile -ExecutionPolicy Bypass -File "{script}"', run)
        if code != 0 or any(os.path.exists(i.cfg) for i in registered):
            reason = "the Windows permission prompt was declined" if bridges._declined(error) else error.strip()[-300:]
            raise BridgeError(f"The bridge was not removed ({reason}).")
    for inst in installations(environ):
        shutil.rmtree(target_dir(inst, environ), ignore_errors=True)
    say(f"✓ {server.label} removed." if registered else f"{server.label} is not installed.")


def status(server: conn.Server, *, environ=None, opener: Callable | None = None) -> dict:
    environ = os.environ if environ is None else environ
    found = installations(environ)
    have = installed(environ)
    rel = bridges.release_of(server)
    info = bridges.probe(server.port, **({"opener": opener} if opener else {}))
    versions = {i.name: installed_version(i, environ) for i in have}
    return {
        "openroads": [i.name for i in found],
        "installed": bool(have),
        "versions": versions,
        "latest": rel.version if rel else None,
        "update_available": bool(rel and any(v and v != "local" and bridges._newer(rel.version, v) for v in versions.values())),
        "running": info is not None,
    }
