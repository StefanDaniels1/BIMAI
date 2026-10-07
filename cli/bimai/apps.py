"""Setting up vendor apps a connection needs (pyRevit): verified downloads, prerequisites in one prompt.

Trust chain as for the bimai bridges: every installer bimai runs is pinned in the catalogue (servers.yaml)
by version, URL and hash, and only runs when the download matches. Microsoft's runtimes are machine-wide,
so they are installed together in one elevated step; the app itself (pyRevit's per-user installer) runs
without administrator rights.
"""
from __future__ import annotations

import configparser
import hashlib
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

from bimai import bridges
from bimai import connections as conn
from bimai.bridges import BridgeError

MAX_DOWNLOAD = 200 * 1024 * 1024
OK_EXIT_CODES = (0, 1638, 3010)     # done, a newer version is already there, done but restart needed

WHY_RUNTIMES = (
    "Windows will now ask: \"Do you want to allow this app to make changes to your device?\"\n"
    "  Why: {app} needs {names} from Microsoft. Those are installed for the whole PC, so only an\n"
    "  administrator may install them, and Windows asks you once for all of them. bimai runs Microsoft's\n"
    "  official installers (checked against their published fingerprints) and changes nothing else.\n"
    "  Click Yes to continue. (No admin rights? Choose No, and ask IT to install them.)")


def _parts(version: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", version)[:3])


def _at_least(version: str, minimum: str) -> bool:
    return _parts(version) >= _parts(minimum)


# ------------------------------------------------------------------ what is installed

def installed_exe(server: conn.Server, environ=None, exists=None) -> str | None:
    environ = os.environ if environ is None else environ
    exists = exists or os.path.exists
    for variant in server.config.get("variants", []):
        command = conn.expand(variant["command"], environ)
        if exists(command):
            return command
    return None


def version_of(exe: str, run: Callable | None = None) -> str | None:
    """The app's version from `<exe> --version`; None when it doesn't start (e.g. its runtime is missing)."""
    run = run or subprocess.run
    try:
        out = run([exe, "--version"], capture_output=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\d+\.\d+\.\d+(?:\.\d+)?", (out.stdout or "") + (out.stderr or ""))
    return match.group(0) if out.returncode == 0 and match else None


def agent_enabled(server: conn.Server, environ=None) -> bool:
    """pyRevit's agent host switch: `[agent] enabled` in its user config (off by default)."""
    environ = os.environ if environ is None else environ
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read(conn.expand(server.app["config_file"], environ), encoding="utf-8-sig")
    except (OSError, configparser.Error):
        return False
    return parser.get("agent", "enabled", fallback="false").strip().strip('"').lower() in ("true", "1", "yes")


def problem(server: conn.Server, exe: str, run: Callable | None = None, environ=None) -> str | None:
    """Why the installed app can't serve the connection yet, or None."""
    app = server.app
    version = version_of(exe, run)
    if version is None:
        return f"{app['name']} is installed but doesn't start; a Microsoft .NET runtime it needs may be missing."
    if not _at_least(version, app["min_version"]):
        return (f"{app['name']} {version} is installed; your team needs {app['name']} {app['min_version']} or newer "
                "(it brings the agent runtime).")
    if not agent_enabled(server, environ):
        return f"{app['name']}'s agent runtime is switched off (it is off until you switch it on)."
    return None


def missing_prerequisites(server: conn.Server, environ=None, listdir: Callable | None = None) -> list[dict]:
    environ = os.environ if environ is None else environ
    listdir = listdir or os.listdir
    missing = []
    for pre in server.app.get("prerequisites", []):
        try:
            versions = listdir(conn.expand(pre["folder"], environ))
        except OSError:
            versions = []
        major = _parts(pre["min"])[0]
        if not any(_parts(v)[:1] == (major,) and _at_least(v, pre["min"]) for v in versions if _parts(v)):
            missing.append(pre)
    return missing


def install_log(app: dict, environ) -> str:
    """Where the app's installer writes its log (kept after bimai finishes, for the person or IT)."""
    temp = environ.get("TEMP") or tempfile.gettempdir()
    return os.path.join(temp, f"bimai-{app['name'].lower()}-install.log")


# ------------------------------------------------------------------ download, verify, run

def _fetch(url: str, dest: Path, algorithm: str, expected: str, opener: Callable) -> Path:
    bridges.download(url, dest, opener=opener, max_bytes=MAX_DOWNLOAD)
    h = hashlib.new(algorithm)
    with open(dest, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    if h.hexdigest().lower() != expected.lower():
        raise BridgeError(f"The download of {dest.name} could not be verified (its {algorithm.upper()} doesn't match "
                          "the one bimai expects), so nothing was installed. Try again later, or report this.")
    return dest


def _running(process: str, run: Callable) -> bool:
    try:
        out = run(["tasklist", "/FI", f"IMAGENAME eq {process}", "/NH"], capture_output=True,
                  encoding="utf-8", errors="replace", timeout=15)
        return process.lower() in (out.stdout or "").lower()
    except (OSError, subprocess.SubprocessError):
        return False


def _install_runtimes(missing: list[dict], app: str, work: Path, *, say, run, opener) -> None:
    files = []
    for pre in missing:
        say(f"Downloading {pre['name']} {pre['version']} from Microsoft…")
        files.append(_fetch(pre["url"], work / Path(pre["url"]).name, "sha512", pre["sha512"], opener))
    say("✓ Downloads verified.")
    say(WHY_RUNTIMES.format(app=app, names=" and ".join(p["name"] for p in missing)))
    error_file = work / "runtime-error.txt"
    lines = ["$ErrorActionPreference = 'Stop'"]
    for f in files:
        lines.append(f"$p = Start-Process -FilePath '{f}' -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru")
        lines.append(f"if ({' -and '.join(f'$p.ExitCode -ne {c}' for c in OK_EXIT_CODES)}) "
                     f"{{ Set-Content -LiteralPath '{error_file}' -Value \"{f.name} stopped with code $($p.ExitCode)\"; "
                     "exit $p.ExitCode }")
    script = work / "install-runtimes.ps1"
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    code, error = bridges.run_elevated(f'-NoProfile -ExecutionPolicy Bypass -File "{script}"', run)
    if code != 0:
        if bridges._declined(error):
            raise BridgeError(f"{app} was not installed: the Windows permission prompt was declined. Ask IT to install "
                              + " and ".join(p["name"] for p in missing) + ", then run this again.")
        detail = error_file.read_text(encoding="utf-8-sig", errors="replace").strip() if error_file.is_file() else error
        raise BridgeError(f"Installing the Microsoft runtimes stopped: {detail.strip()[-300:]}")
    say("✓ " + " and ".join(p["name"] for p in missing) + " installed.")


def setup(server: conn.Server, *, ask: Callable[[str], bool], say: Callable[[str], None],
          close_app: Callable[[str], bool] = lambda question: False, platform: str | None = None,
          run: Callable | None = None, opener: Callable | None = None, environ=None, exists=None,
          listdir: Callable | None = None) -> str:
    """Installs or updates the app (prerequisites first) and switches its agent host on, asking where it
    changes something (`close_app` asks to close Revit first). Returns the app's version. Raises BridgeError with what to do otherwise."""
    run = run or subprocess.run
    opener = opener or urllib.request.urlopen
    environ = os.environ if environ is None else environ
    app = server.app
    if (platform or conn.PLATFORM) != "windows":
        raise BridgeError(f"{app['name']} runs inside Revit, so it can only be set up on Windows.")

    exe = installed_exe(server, environ, exists)
    version = version_of(exe, run) if exe else None
    if not (version and _at_least(version, app["min_version"])):
        installer = app["installer"]
        while _running(app["process"], run):
            if not close_app("Revit is running. Close it (save your work first), then continue? (Y/n)"):
                raise BridgeError(f"Revit must be closed to install {app['name']}. Close it and try again.")
        with tempfile.TemporaryDirectory(prefix="bimai-app-") as tmp:
            work = Path(tmp)
            missing = missing_prerequisites(server, environ, listdir)
            if missing:
                _install_runtimes(missing, app["name"], work, say=say, run=run, opener=opener)
            say(f"Downloading {app['name']} {installer['version']}…")
            path = _fetch(installer["url"], work / Path(installer["url"]).name.replace("%2B", "+"), "sha256",
                          installer["sha256"], opener)
            say(f"✓ Download verified. Installing {app['name']} for your user (no administrator rights needed)…")
            log = install_log(app, environ)
            try:
                out = run([str(path), *installer.get("args", []), f"/LOG={log}"], capture_output=True,
                          encoding="utf-8", errors="replace", timeout=600)
            except (OSError, subprocess.SubprocessError) as exc:
                raise BridgeError(f"The {app['name']} installer didn't finish ({exc}). Its log: {log}") from exc
            if out.returncode != 0:
                raise BridgeError(f"The {app['name']} installer stopped with code {out.returncode}. Its log: {log}. "
                                  f"You can also install it by hand: {installer['url']}")
        exe = installed_exe(server, environ, exists)
        version = version_of(exe, run) if exe else None
        if not (version and _at_least(version, app["min_version"])):
            raise BridgeError(f"The installer finished, but {app['name']} {app['min_version']}+ isn't where it should be. "
                              f"See {server.docs}")
        say(f"✓ {app['name']} {version} installed.")

    if not agent_enabled(server, environ):
        question = (f"Switch on {app['name']}'s agent runtime? It lets Claude Code talk to Revit; it changes one "
                    f"setting in your {app['name']} configuration, and Revit needs a restart afterwards. (Y/n)")
        if not ask(question):
            raise BridgeError(f"{app['name']}'s agent runtime is off, so your team can't reach Revit yet. Switch it on "
                              f"later with: bimai connect {server.name} --install")
        try:
            out = run([exe, *app["enable"]], capture_output=True, encoding="utf-8", errors="replace", timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            raise BridgeError(f"Couldn't switch on the agent runtime: {exc}") from exc
        if out.returncode != 0 or not agent_enabled(server, environ):
            raise BridgeError(f"Couldn't switch on the agent runtime: {(out.stderr or out.stdout or '').strip()[-300:]}")
        say(f"✓ {app['name']}'s agent runtime is on. Restart Revit if it is open.")
    return version
