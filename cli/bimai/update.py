"""`bimai update`: update bimai itself, with the tool it was installed with.

(`bimai upgrade` is a different thing: it updates the bimai files inside a project.)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from importlib import metadata
from typing import Callable

from bimai import __version__

PYPI_URL = "https://pypi.org/pypi/bimai/json"


class UpdateError(Exception):
    pass


def install_method(prefix: str | None = None, dist_files=None) -> str:
    """'uv', 'pipx', 'editable' or 'pip', from where this bimai runs."""
    p = (prefix or sys.prefix).replace("\\", "/").lower()
    if "/uv/tools/bimai" in p:
        return "uv"
    if "/pipx/venvs/bimai" in p:
        return "pipx"
    try:
        direct = (dist_files if dist_files is not None else metadata.distribution("bimai")).read_text("direct_url.json")
        if direct and json.loads(direct).get("dir_info", {}).get("editable"):
            return "editable"
    except (metadata.PackageNotFoundError, ValueError):
        pass
    return "pip"


def update_command(method: str, which: Callable | None = None) -> list[str]:
    which = which or shutil.which
    if method == "uv":
        return [which("uv") or "uv", "tool", "upgrade", "bimai"]
    if method == "pipx":
        return [which("pipx") or "pipx", "upgrade", "bimai"]
    if method == "pip":
        return [sys.executable, "-m", "pip", "install", "--upgrade", "bimai"]
    raise UpdateError("This bimai runs from source (an editable install). Update it with git pull in your clone instead.")


def latest_version(opener: Callable = urllib.request.urlopen, timeout: float = 5.0) -> str:
    request = urllib.request.Request(PYPI_URL, headers={"User-Agent": f"bimai/{__version__}", "Accept": "application/json"})
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))["info"]["version"]
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("bimai isn't published on PyPI yet, so there is nothing to update to.") from exc
        raise UpdateError(f"PyPI answered with an error ({exc.code}). Try again later.") from exc
    except (OSError, ValueError, KeyError) as exc:
        raise UpdateError(f"Couldn't reach PyPI to check for updates ({exc}). Check your internet connection or proxy.") from exc


def newer(a: str, b: str) -> bool:
    """True when version a is newer than b (plain numeric versions, as bimai uses)."""
    def parts(v: str) -> tuple:
        return tuple(int(x) if x.isdigit() else 0 for x in v.split("+")[0].split("."))
    return parts(a) > parts(b)


def run_update(method: str, run: Callable | None = None, which: Callable | None = None) -> int:
    command = update_command(method, which or shutil.which)
    try:
        return (run or subprocess.run)(command).returncode
    except OSError as exc:
        raise UpdateError(f"Couldn't run {command[0]} ({exc}). Reinstall bimai with the one-line installer: "
                          "https://docs.bimai.nl/docs/start/install") from exc
