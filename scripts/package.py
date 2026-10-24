"""Build the per-OS downloads for a release (GitHub Actions runs this on every version tag).

  python scripts/package.py                  dist/ReelForge-<v>-Windows.zip, -macOS.zip, -Linux.tar.gz
  python scripts/package.py --stage-only     dist/stage/ReelForge/ only (what the Windows installer packs)
  python scripts/package.py --print-version

Every package holds the files git tracks, inside a ReelForge-<v>/ folder, plus that system's double-click
launchers and a START-HERE.txt. Executable bits are set for the shell scripts so macOS and Linux can run them.

It won't build while the README's screenshots are older than ReelForge's look (scripts/shot_sources.py): retake them
all with scripts/screenshots.py and commit them first. --allow-old-screenshots builds anyway, for a local test.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import shot_sources

ROOT = Path(__file__).resolve().parent.parent
EXECUTABLE = (".sh", ".command", "bin/reelforge")
SKIP = (".github/",)                    # CI files aren't useful in a download

START = {
    "windows": """ReelForge {v} for Windows

1. Double-click setup.bat. It lists what ReelForge still needs (Python packages, Blender, ffmpeg, the sound
   effects, the reelforge command), sets it all up in this folder once you say yes, then starts a short interview
   about your channel. If Windows says "Windows protected your PC", click More info, then Run anyway.
2. Open this folder in Claude Code (the Claude desktop app's Code tab, then Open folder...) or run codex here,
   and say: "make my first video".
3. Open ReelForge (double-click ReelForge.bat, or type reelforge in a terminal) and go to Publish (tab 4) to post
   it.

Keep this folder somewhere with a short path, e.g. C:\\Users\\<you>\\ReelForge. Full guide: README.md
""",
    "macos": """ReelForge {v} for macOS (experimental: ReelForge is built and tested on Windows)

1. Double-click "Set up ReelForge.command". The first time, macOS may refuse because the file isn't from the
   App Store: right-click it, choose Open, then Open again. Setup installs Python packages, Blender and the sound
   effects into this folder and starts a short interview about your channel. It needs Python 3.11+ and ffmpeg
   (brew install python@3.13 ffmpeg).
2. Open this folder in Claude Code (the Claude desktop app's Code tab) or run codex in it, and say:
   "make my first video".
3. Double-click "Open ReelForge.command" (or type reelforge in a terminal) and go to Publish (tab 4) to post it.

Full guide: README.md
""",
    "linux": """ReelForge {v} for Linux (experimental: ReelForge is built and tested on Windows)

1. In a terminal in this folder: ./setup.sh   It installs Python packages, Blender and the sound effects into this
   folder and starts a short interview about your channel. It needs Python 3.11+ (with venv) and ffmpeg from your
   package manager.
2. Run claude or codex in this folder and say: "make my first video".
3. Type reelforge (or ./reelforge.sh) and go to Publish (tab 4) to post it.

Full guide: README.md
""",
}

MAC_LAUNCHERS = {
    "Set up ReelForge.command": "setup.sh",
    "Change my channel answers.command": "onboard.sh",
    "Open ReelForge.command": "reelforge.sh",
}


def version() -> str:
    text = (ROOT / "studio" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'KIT_VERSION = "([^"]+)"', text).group(1)


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    files = [f for f in out.decode("utf-8").split("\0") if f]
    return sorted(f for f in files if not f.startswith(SKIP) and (ROOT / f).is_file())


def mac_launcher(target: str) -> str:
    return f"""#!/bin/bash
# Double-click to run {target} in Terminal. The first time, macOS may ask: right-click, Open.
cd "$(dirname "$0")" || exit 1
chmod +x ./*.sh
./{target}
echo
read -n 1 -s -r -p "Press any key to close this window."
"""


def extras(os_name: str, v: str) -> dict[str, tuple[bytes, bool]]:
    """Files only that system's package gets: name -> (content, executable)."""
    out = {"START-HERE.txt": (START[os_name].format(v=v).encode("utf-8"), False)}
    if os_name == "macos":
        for name, target in MAC_LAUNCHERS.items():
            out[name] = (mac_launcher(target).encode("utf-8"), True)
    return out


def build_zip(dest: Path, top: str, files: list[str], extra: dict[str, tuple[bytes, bool]]) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            info = zipfile.ZipInfo.from_file(ROOT / f, f"{top}/{f}")
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if f.endswith(EXECUTABLE) else 0o644
            info.external_attr = (0o100000 | mode) << 16
            z.writestr(info, (ROOT / f).read_bytes())
        for name, (data, exe) in extra.items():
            info = zipfile.ZipInfo(f"{top}/{name}")
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100000 | (0o755 if exe else 0o644)) << 16
            z.writestr(info, data)


def build_tar(dest: Path, top: str, files: list[str], extra: dict[str, tuple[bytes, bool]]) -> None:
    with tarfile.open(dest, "w:gz", compresslevel=9) as t:
        for f in files:
            ti = t.gettarinfo(str(ROOT / f), f"{top}/{f}")
            ti.mode = 0o755 if f.endswith(EXECUTABLE) else 0o644
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            with open(ROOT / f, "rb") as fh:
                t.addfile(ti, fh)
        for name, (data, exe) in extra.items():
            ti = tarfile.TarInfo(f"{top}/{name}")
            ti.size, ti.mode = len(data), 0o755 if exe else 0o644
            t.addfile(ti, io.BytesIO(data))


def stage(dest: Path, files: list[str], extra: dict[str, tuple[bytes, bool]]) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    for f in files:
        target = dest / f
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, target)
    for name, (data, _exe) in extra.items():
        (dest / name).write_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--version", default="")
    ap.add_argument("--stage-only", action="store_true")
    ap.add_argument("--print-version", action="store_true")
    ap.add_argument("--sums-only", action="store_true", help="just (re)write dist/SHA256SUMS.txt")
    ap.add_argument("--allow-old-screenshots", action="store_true", help="build even if the screenshots are out of date")
    args = ap.parse_args()
    v = (args.version or version()).lstrip("v")
    if args.print_version:
        print(v)
        return 0
    if args.sums_only:
        write_sums(args.out)
        return 0
    if v != version():
        # Its files would say another version, so every copy's Updates tab would offer this release forever.
        print(f"error: packaging {v} but studio/__init__.py says KIT_VERSION = {version()!r}: change that first",
              file=sys.stderr)
        return 1
    changed = shot_sources.stale()
    if changed and not args.allow_old_screenshots:
        # Every release's README shows the ReelForge it ships.
        print("error: the README's screenshots are older than ReelForge's look (changed since: "
              + ", ".join(changed[:6]) + (", ..." if len(changed) > 6 else "") + "). Retake them all with "
              "scripts/screenshots.py and commit docs/screenshots/ and dashboard/docs/ first.", file=sys.stderr)
        return 1
    files = tracked()
    args.out.mkdir(parents=True, exist_ok=True)
    stage(args.out / "stage" / "ReelForge", files, extras("windows", v))
    print(f"staged {len(files)} files in {args.out / 'stage' / 'ReelForge'}")
    if args.stage_only:
        return 0
    top = f"ReelForge-{v}"
    built = []
    for os_name, name, fn in (("windows", f"{top}-Windows.zip", build_zip), ("macos", f"{top}-macOS.zip", build_zip),
                              ("linux", f"{top}-Linux.tar.gz", build_tar)):
        dest = args.out / name
        fn(dest, top, files, extras(os_name, v))
        built.append(dest)
        print(f"built {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    write_sums(args.out)
    return 0


def write_sums(out: Path) -> None:
    """SHA256SUMS.txt for every download in dist/ (the Updates tab checks a download against it)."""
    lines = []
    for f in sorted(out.iterdir()):
        if f.is_file() and f.name.startswith("ReelForge-") and f.suffix in (".zip", ".gz", ".exe"):
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.name}")
    (out / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote SHA256SUMS.txt ({len(lines)} files)")


if __name__ == "__main__":
    sys.exit(main())
