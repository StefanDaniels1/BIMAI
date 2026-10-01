"""Shipped scripts must run everywhere they are used."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def tracked(pattern: str) -> list[Path]:
    out = subprocess.run(["git", "ls-files", pattern], cwd=ROOT, capture_output=True, encoding="utf-8", check=True)
    return [ROOT / line for line in out.stdout.splitlines() if line]


@pytest.mark.parametrize("script", tracked("*.ps1"), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_powershell_scripts_are_ascii(script):
    # Windows PowerShell 5.1 reads .ps1 files without a BOM as ANSI: a UTF-8 "✓" turns into characters
    # that end a string early, and the script no longer parses. Keep every PowerShell script ASCII.
    for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
        assert all(ord(c) < 128 for c in line), f"{script.name}:{number} has non-ASCII characters: {line.strip()}"


def test_install_sh_is_posix_sh():
    # Runs as `curl … | sh`, so it must work in plain POSIX sh (dash on Debian/Ubuntu), not only bash.
    text = (ROOT / "docs" / "public" / "install.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    for bashism in ("[[", "function ", "local ", "$'", "<<<"):
        assert bashism not in text, bashism
