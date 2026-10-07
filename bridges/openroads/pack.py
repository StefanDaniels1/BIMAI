"""Packs the OpenRoads bridge release: dist/bimai-openroads-bridge.zip with src/*.cs and README.txt.

The zip is reproducible (sorted names, fixed timestamps), so its SHA-256 only changes when the sources do.
Usage: python bridges/openroads/pack.py [output.zip]
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXED = (2026, 1, 1, 0, 0, 0)


def pack(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    files = [(f"src/{p.name}", p) for p in sorted((HERE / "src").glob("*.cs"))] + [("README.txt", HERE / "README.txt")]
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, path in files:
            info = zipfile.ZipInfo(name, FIXED)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, path.read_bytes())
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "dist" / "bimai-openroads-bridge.zip"
    print(pack(target))
