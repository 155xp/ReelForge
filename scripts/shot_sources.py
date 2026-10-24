"""Which files the README's screenshots were drawn from, so a release can't go out with old pictures.

scripts/screenshots.py writes docs/screenshots/SOURCES.txt every time it retakes all of them: the SHA-256 of each of
ReelForge's own files that drew them (the window's and setup's code, styles and logo). scripts/package.py checks it
before building a release and stops when any of those files has changed since. Then retake the screenshots and
commit them, SOURCES.txt included.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / "docs" / "screenshots" / "SOURCES.txt"
FOLDERS = ("dashboard", "studio", "scripts")     # ReelForge's own code (not .venv's packages)
HEADER = """\
# What docs/screenshots/ and dashboard/docs/ were drawn from when scripts/screenshots.py last retook them all: each
# file's SHA-256 (with LF line endings). scripts/package.py won't build a release once any of them has changed.
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def record() -> Path:
    """Write SOURCES.txt from the files this process has loaded; call it once every screenshot is taken."""
    used = {Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)}
    used |= {p.resolve() for folder in FOLDERS[:2] for p in (ROOT / folder).rglob("*.tcss")}
    names = sorted(
        name for name in (p.relative_to(ROOT).as_posix() for p in used if p.is_relative_to(ROOT) and p.is_file())
        if name.startswith(tuple(f + "/" for f in FOLDERS)) and "/tests/" not in name and "__pycache__" not in name)
    RECORD.write_text(HEADER + "".join(f"{digest(ROOT / n)}  {n}\n" for n in names), encoding="utf-8", newline="\n")
    return RECORD


def stale() -> list[str]:
    """The recorded files that have changed or gone since the screenshots were taken (or a line saying there's no
    record)."""
    if not RECORD.is_file():
        return [f"{RECORD.relative_to(ROOT).as_posix()} is missing"]
    out = []
    for line in RECORD.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            want, name = line.split(None, 1)
            if not (ROOT / name).is_file() or digest(ROOT / name) != want:
                out.append(name)
    return out
