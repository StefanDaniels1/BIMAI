"""Installing bimai's own desktop bridges (the Civil 3D bridge): verified downloads, one-click installs.

Trust chain: the release's SHA-256 is pinned in the catalogue (servers.yaml). A download is only installed
when it matches, so neither a compromised release nor the network can swap the add-in. Installation runs
the verified zip's own install.ps1 through the normal Windows administrator prompt.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from bimai import connections as conn

MAX_DOWNLOAD = 50 * 1024 * 1024

# Shown right before the Windows administrator prompt, so nobody is surprised by it.
WHY_PERMISSION = (
    "Windows will now ask: \"Do you want to allow this app to make changes to your device?\"\n"
    "  Why: the bridge goes into C:\\Program Files\\Autodesk\\ApplicationPlugins. That is the one folder Civil 3D\n"
    "  always trusts, so the bridge loads without security warnings, also on company PCs with strict settings.\n"
    "  Only administrators may write there, so Windows asks you once. bimai copies the verified bridge there and\n"
    "  changes nothing else. Click Yes to continue. (No admin rights? Choose No, and ask IT to install it.)")


class BridgeError(Exception):
    """Installation didn't happen, with the reason and what to do in plain language (exit 1)."""


@dataclass(frozen=True)
class Release:
    repo: str
    tag: str
    asset: str
    version: str
    sha256: str | None

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}/releases/download/{self.tag}/{self.asset}"


def release_of(server: conn.Server) -> Release | None:
    r = server.release
    if not r:
        return None
    return Release(r["repo"], r["tag"], r["asset"], str(r["version"]), (r.get("sha256") or None))


def it_help(server: conn.Server) -> str:
    rel = release_of(server)
    where = rel.url if rel else server.docs
    return (f"If you can't approve administrator prompts, ask IT to install it: they can run install.ps1 from {where} "
            f"as administrator (see {server.docs}).")


# ------------------------------------------------------------------ download and verify

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path, opener: Callable = urllib.request.urlopen, max_bytes: int = MAX_DOWNLOAD) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": "bimai"})
    try:
        with opener(request, timeout=60) as response, open(dest, "wb") as out:
            total = 0
            while chunk := response.read(1 << 16):
                total += len(chunk)
                if total > max_bytes:
                    raise BridgeError("The download is larger than expected; it was not installed.")
                out.write(chunk)
    except BridgeError:
        raise
    except OSError as exc:      # URLError, HTTPError, timeouts and TLS problems are all OSErrors
        raise BridgeError(f"Couldn't download the bridge ({exc}). Check your internet connection or proxy, "
                          f"or download it yourself and use --from: {url}") from exc
    return dest


def verify(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise BridgeError("The download could not be verified (its SHA-256 doesn't match the one bimai expects), "
                          "so it was not installed. Try again later, or report this.")


def unpack(zip_path: Path, workdir: Path, bundle_name: str) -> tuple[Path, Path]:
    """Extracts the zip safely and returns (bundle folder, install.ps1)."""
    try:
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                p = PurePosixPath(name)
                if p.is_absolute() or ".." in p.parts or ":" in name:
                    raise BridgeError("The zip contains unsafe paths; it was not installed.")
            z.extractall(workdir)
    except zipfile.BadZipFile as exc:
        raise BridgeError("That file is not a valid bridge zip.") from exc
    bundle = workdir / bundle_name
    script = workdir / "install.ps1"
    if not (bundle / "PackageContents.xml").is_file() or not script.is_file():
        raise BridgeError(f"That zip doesn't contain {bundle_name} with PackageContents.xml and install.ps1.")
    return bundle, script


# ------------------------------------------------------------------ the installed bridge

def installed_bundle(server: conn.Server, environ=None, exists=None) -> str | None:
    environ = os.environ if environ is None else environ
    exists = exists or os.path.exists
    for folder in conn.plugin_folders(environ):
        path = f"{folder}\\{server.bundle}"
        if exists(path):
            return path
    return None


def installed_version(bundle_path: str) -> str | None:
    try:
        root = ET.parse(os.path.join(bundle_path, "PackageContents.xml")).getroot()
        return root.get("AppVersion")
    except (OSError, ET.ParseError):
        return None


def probe(port: int, timeout: float = 2.0, opener: Callable = urllib.request.urlopen) -> dict | None:
    """Asks a local bridge who it is (MCP server/discover). None when nothing answers."""
    version = "2026-07-28"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {
        "io.modelcontextprotocol/protocolVersion": version,
        "io.modelcontextprotocol/clientInfo": {"name": "bimai", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {}}}}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": version, "Mcp-Method": "server/discover"})
    try:
        with opener(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8")).get("result", {})
            return result.get("_meta", {}).get("io.modelcontextprotocol/serverInfo") or {}
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------ Windows processes

def civil3d_running(run: Callable = subprocess.run) -> bool:
    try:
        out = run(["tasklist", "/FI", "IMAGENAME eq acad.exe", "/NH"], capture_output=True,
                  encoding="utf-8", errors="replace", timeout=15)
        return "acad.exe" in (out.stdout or "").lower()
    except (OSError, subprocess.SubprocessError):
        return False


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def run_elevated(arguments: str, run: Callable = subprocess.run) -> tuple[int, str]:
    """Runs `powershell <arguments>` with the Windows administrator prompt and waits.
    Returns (exit code, error text). Arguments are one string: Start-Process doesn't quote list items."""
    command = (f"$p = Start-Process -FilePath powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden "
               f"-ArgumentList {_ps_quote(arguments)}; exit $p.ExitCode")
    try:
        out = run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                  capture_output=True, encoding="utf-8", errors="replace", timeout=600)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return out.returncode, (out.stderr or "") + (out.stdout or "")


def _declined(error: str) -> bool:
    text = error.lower()
    return "canceled by the user" in text or "cancelled by the user" in text or "1223" in text


# ------------------------------------------------------------------ install and uninstall

def install(server: conn.Server, *, zip_path: Path | None = None, ask: Callable[[str], bool], say: Callable[[str], None],
            platform: str | None = None, run: Callable = subprocess.run, opener: Callable = urllib.request.urlopen,
            environ=None, exists=None) -> str:
    """Installs the bridge; returns the installed version. Raises BridgeError with what to do otherwise."""
    platform = platform or conn.PLATFORM
    if platform != "windows":
        raise BridgeError(f"{server.label} runs inside a Windows program, so it can only be installed on Windows.")
    rel = release_of(server)
    if zip_path is None and rel is None:
        raise BridgeError(f"{server.label} has no published release to install.")
    if zip_path is None and rel and not rel.sha256:
        raise BridgeError(f"No verified release of {server.label} is published yet. Install a zip you have with: "
                          f"bimai bridge install {server.name} --from <zip>")

    while civil3d_running(run):
        if not ask("Civil 3D is running. Close it (save your work first), then continue? (Y/n)"):
            raise BridgeError("Civil 3D must be closed to install the bridge. Close it and try again.")

    with tempfile.TemporaryDirectory(prefix="bimai-bridge-") as tmp:
        work = Path(tmp)
        if zip_path is None:
            say(f"Downloading {server.label} {rel.version}…")
            zip_path = download(rel.url, work / rel.asset, opener=opener)
            verify(zip_path, rel.sha256)
            say("✓ Download verified.")
        else:
            if not zip_path.is_file():
                raise BridgeError(f"No file at {zip_path}.")
            say(f"Installing from {zip_path} (SHA-256 {sha256_file(zip_path)}).")
        bundle, script = unpack(zip_path, work / "unpacked", server.bundle)
        say(WHY_PERMISSION)
        error_file = work / "install-error.txt"
        code, error = run_elevated(f'-NoProfile -ExecutionPolicy Bypass -File "{script}" -Bundle "{bundle}" '
                                   f'-ErrorFile "{error_file}"', run)
        if code != 0:
            if _declined(error):
                raise BridgeError("The bridge was not installed: the Windows permission prompt was declined. " + it_help(server))
            detail = error_file.read_text(encoding="utf-8-sig", errors="replace").strip() if error_file.is_file() else error.strip()
            raise BridgeError(f"The installer stopped with an error: {detail[-400:]} " + it_help(server))

    installed = installed_bundle(server, environ, exists)
    if not installed:
        raise BridgeError("The installer finished, but the bridge isn't where it should be. " + it_help(server))
    version = installed_version(installed) or "?"
    say(f"✓ {server.label} {version} installed. It starts together with Civil 3D.")
    return version


def uninstall(server: conn.Server, *, say: Callable[[str], None], platform: str | None = None,
              run: Callable = subprocess.run, environ=None, exists=None) -> None:
    platform = platform or conn.PLATFORM
    if platform != "windows":
        raise BridgeError(f"{server.label} only exists on Windows.")
    path = installed_bundle(server, environ, exists)
    if not path:
        say(f"{server.label} is not installed.")
        return
    if civil3d_running(run):
        raise BridgeError("Close Civil 3D first, then try again.")
    code, error = run_elevated(f"-NoProfile -Command \"Remove-Item -LiteralPath '{path}' -Recurse -Force\"", run)
    if code != 0 or installed_bundle(server, environ, exists):
        reason = "the Windows permission prompt was declined" if _declined(error) else error.strip()[-300:]
        raise BridgeError(f"The bridge was not removed ({reason}).")
    say(f"✓ {server.label} removed.")


def status(server: conn.Server, *, environ=None, exists=None, opener: Callable = urllib.request.urlopen,
           port: int | None = None) -> dict:
    path = installed_bundle(server, environ, exists)
    version = installed_version(path) if path else None
    rel = release_of(server)
    info = probe(port or server.port, opener=opener) if server.port else None
    return {
        "installed": bool(path),
        "path": path,
        "version": version,
        "latest": rel.version if rel else None,
        "update_available": bool(version and rel and _newer(rel.version, version)),
        "running": info is not None,
        "running_version": (info or {}).get("version"),
    }


def _newer(a: str, b: str) -> bool:
    def parts(v: str) -> tuple:
        return tuple(int(x) if x.isdigit() else 0 for x in v.split("-")[0].split("."))
    return parts(a) > parts(b)
