"""Finding (and, if you agree, downloading) the tools the pipeline needs: Blender 4.5 LTS, ffmpeg and fonts.

Downloads come only from the official sources (download.blender.org, gyan.dev for Windows ffmpeg) and are
checked against the checksums those sites publish. Everything lands in the kit's tools/ folder, so nothing is
installed system-wide and deleting the folder removes it.
"""

from __future__ import annotations

import glob
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

from . import BLENDER_VERSION, net
from .paths import FONTS, MAC, ROOT, TOOLS, WINDOWS

BLENDER_SERIES = ".".join(BLENDER_VERSION.split(".")[:2])          # "4.5"
BLENDER_BASE = f"https://download.blender.org/release/Blender{BLENDER_SERIES}/"
FFMPEG_WIN_ZIP = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def _exists(p) -> bool:
    try:
        return bool(p) and Path(p).is_file()
    except OSError:
        return False


def _prefer_45(paths: list[str]) -> list[str]:
    """Blender installs, the 4.5 ones first (the pipeline is built on 4.5 LTS), newest patch first. The version is
    read from the folder name ("blender-4.5.5-windows-x64", "Blender 4.5"); unversioned paths come last."""
    series = tuple(int(x) for x in BLENDER_SERIES.split("."))

    def key(p):
        stamp = Path(p).parent / "kit-version.txt"            # the copy setup put in tools/blender
        if stamp.exists():
            m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", stamp.read_text(encoding="utf-8"))
        else:
            m = re.search(r"blender[- _](\d+)\.(\d+)(?:\.(\d+))?", p, re.IGNORECASE)
        ver = tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)
        return (ver[:2] == series, ver)
    return sorted(paths, key=key, reverse=True)


def path_too_long() -> bool:
    """Windows can't load some of Blender's files when their full path passes 260 characters. Blender's deepest
    program files sit about 95 characters below tools/blender, so the kit's own folder path must stay under ~160."""
    return WINDOWS and len(str(ROOT)) > 160


def _kit_only() -> bool:
    """STUDIO_ONLY_KIT_TOOLS=1: ignore Blender/ffmpeg installed elsewhere and use only tools/ (for testing setup)."""
    return os.environ.get("STUDIO_ONLY_KIT_TOOLS", "").strip() in ("1", "true", "yes")


def blender_candidates() -> list[str]:
    exe = "blender.exe" if WINDOWS else "blender"
    found: list[str] = []
    found += glob.glob(str(TOOLS / "blender" / exe)) + glob.glob(str(TOOLS / "blender-*" / exe))
    if MAC:
        found += glob.glob(str(TOOLS / "Blender*.app" / "Contents" / "MacOS" / "Blender"))
    if _kit_only():
        return [p for p in dict.fromkeys(_prefer_45([p for p in found if _exists(p)]))]
    if MAC:
        found += ["/Applications/Blender.app/Contents/MacOS/Blender",
                  str(Path.home() / "Applications" / "Blender.app" / "Contents" / "MacOS" / "Blender")]
    if WINDOWS:
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("LOCALAPPDATA", "")):
            if base:
                found += glob.glob(os.path.join(base, "Blender Foundation", "Blender *", exe))
        found += glob.glob(str(Path.home() / "Tools" / "blender-*" / exe))         # portable copies
        found += glob.glob(str(Path.home() / "Desktop" / "blender-*" / exe))
        found += glob.glob(str(Path.home() / "Downloads" / "blender-*" / exe))
    on_path = shutil.which("blender")
    if on_path:
        found.append(on_path)
    return [p for p in dict.fromkeys(_prefer_45([p for p in found if _exists(p)]))]


def find_blender() -> str | None:
    env = os.environ.get("STUDIO_BLENDER")
    if env:
        return env if _exists(env) else None
    c = blender_candidates()
    return c[0] if c else None


def blender_version(path: str) -> str:
    """'4.5.5' (or '' if it won't start). Takes a second or two."""
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60,
                             encoding="utf-8", errors="replace").stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"Blender (\d+\.\d+(?:\.\d+)?)", out)
    return m.group(1) if m else ""


def find_ffmpeg() -> str | None:
    env = os.environ.get("STUDIO_FFMPEG")
    if env:
        return env if _exists(env) else None
    exe = "ffmpeg.exe" if WINDOWS else "ffmpeg"
    local = sorted(glob.glob(str(TOOLS / "ffmpeg*" / "bin" / exe)) + glob.glob(str(TOOLS / "ffmpeg*" / exe)))
    if local:
        return local[-1]
    if _kit_only():
        return None
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    if WINDOWS:
        winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        hits = sorted(winget.glob("Gyan.FFmpeg*/*/bin/ffmpeg.exe"))
        if hits:
            return str(hits[-1])
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if _exists(p):
            return p
    return None


def ffprobe_for(ffmpeg: str) -> str:
    p = Path(ffmpeg)
    return str(p.with_name("ffprobe" + p.suffix))


# ---------------------------------------------------------------- fonts

def find_fonts() -> tuple[Path, Path, Path, Path, Path]:
    """(serif, serif italic, serif bold, mono, mono bold). Georgia + Consolas on Windows (the look the pipeline was
    tuned with); Georgia + the bundled JetBrains Mono on macOS; DejaVu/Liberation on Linux. STUDIO_FONTS_DIR may hold
    serif.ttf, serif-italic.ttf, serif-bold.ttf, mono.ttf and mono-bold.ttf to override all five."""
    override = os.environ.get("STUDIO_FONTS_DIR")
    if override:
        d = Path(override)
        return tuple(d / n for n in ("serif.ttf", "serif-italic.ttf", "serif-bold.ttf", "mono.ttf", "mono-bold.ttf"))
    win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    mac = Path("/System/Library/Fonts/Supplemental")
    lin = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu"),
           Path("/usr/share/fonts/TTF"), Path("/usr/share/fonts/truetype/liberation")]
    bundled_mono, bundled_mono_bold = FONTS / "JetBrainsMono-Regular.ttf", FONTS / "JetBrainsMono-Bold.ttf"
    roles = [
        [win / "georgia.ttf", mac / "Georgia.ttf", *(d / "DejaVuSerif.ttf" for d in lin),
         *(d / "LiberationSerif-Regular.ttf" for d in lin)],
        [win / "georgiai.ttf", mac / "Georgia Italic.ttf", *(d / "DejaVuSerif-Italic.ttf" for d in lin),
         *(d / "LiberationSerif-Italic.ttf" for d in lin)],
        [win / "georgiab.ttf", mac / "Georgia Bold.ttf", *(d / "DejaVuSerif-Bold.ttf" for d in lin),
         *(d / "LiberationSerif-Bold.ttf" for d in lin)],
        [win / "consola.ttf", bundled_mono, *(d / "DejaVuSansMono.ttf" for d in lin)],
        [win / "consolab.ttf", bundled_mono_bold, *(d / "DejaVuSansMono-Bold.ttf" for d in lin)],
    ]
    out = []
    for cands in roles:
        hit = next((c for c in cands if c.is_file()), None)
        out.append(hit or cands[0])
    return tuple(out)


# ---------------------------------------------------------------- downloads

# A progress callback takes (what's happening, done, total); total 0 means "no idea how long". Without one, progress
# is printed on a single updating line.
Progress = Callable[[str, float, float], None]


def _say(progress: "Progress | None", text: str) -> None:
    if progress:
        progress(text, 0, 0)
    else:
        print(f"  {text}...", flush=True)


def _progress(done: int, total: int, label: str):
    if not sys.stdout.isatty() and done < total:
        return
    pct = f"{100 * done / total:5.1f}%" if total else ""
    mb = f"{done / 1e6:7.1f} MB" + (f" of {total / 1e6:.0f} MB" if total else "")
    print(f"\r  {label}: {mb} {pct}   ", end="", flush=True)


def download(url: str, dest: Path, label: str = "", sha256: str | None = None,
             progress: Progress | None = None) -> Path:
    """Download url to dest (resuming is not needed: a failed download is simply restarted)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    with net.open_url(url) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(f"Downloading {label or dest.name}", done, total)
            else:
                _progress(done, total, label or dest.name)
    if not progress:
        print()
    if sha256 and h.hexdigest().lower() != sha256.lower():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"{dest.name}: checksum mismatch (download corrupted or changed); try again")
    tmp.replace(dest)
    return dest


def _fetch_text(url: str) -> str:
    return net.fetch_text(url)


def blender_asset() -> str:
    machine = platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if WINDOWS:
        return f"blender-{BLENDER_VERSION}-windows-{'arm64' if arm else 'x64'}.zip"
    if MAC:
        return f"blender-{BLENDER_VERSION}-macos-{'arm64' if arm else 'x64'}.dmg"
    return f"blender-{BLENDER_VERSION}-linux-x64.tar.xz"


def install_blender(progress: Progress | None = None) -> str:
    """Download the official portable Blender into tools/ and return the path to its executable."""
    asset = blender_asset()
    sums = _fetch_text(BLENDER_BASE + f"blender-{BLENDER_VERSION}.sha256")
    want = next((ln.split()[0] for ln in sums.splitlines() if ln.strip().endswith(asset)), None)
    if not want:
        raise RuntimeError(f"no checksum published for {asset}")
    archive = download(BLENDER_BASE + asset, TOOLS / "downloads" / asset, f"Blender {BLENDER_VERSION}", want,
                       progress)
    _say(progress, "Unpacking Blender (a minute or two)")
    if asset.endswith((".zip", ".tar.xz")):
        # unpack, then rename the folder to the short tools/blender (Windows struggles with very long paths)
        if asset.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                top = z.namelist()[0].split("/")[0]
                z.extractall(TOOLS)
        else:
            with tarfile.open(archive) as t:
                top = t.getnames()[0].split("/")[0]
                t.extractall(TOOLS, filter="data")
        dst = TOOLS / "blender"
        if dst.exists():
            shutil.rmtree(dst)
        (TOOLS / top).rename(dst)
        (dst / "kit-version.txt").write_text(f"{BLENDER_VERSION}\n", encoding="utf-8")
    else:  # macOS .dmg: mount it and copy Blender.app out
        mnt = TOOLS / "downloads" / "blender-dmg"
        mnt.mkdir(parents=True, exist_ok=True)
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-quiet", "-mountpoint", str(mnt), str(archive)], check=True)
        try:
            dst = TOOLS / f"Blender-{BLENDER_VERSION}.app"
            if dst.exists():
                shutil.rmtree(dst)
            subprocess.run(["cp", "-R", str(mnt / "Blender.app"), str(dst)], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", "-quiet", str(mnt)], check=False)
    archive.unlink(missing_ok=True)
    path = find_blender()
    if not path:
        raise RuntimeError("Blender was unpacked but its executable wasn't found in tools/")
    return path


def install_ffmpeg(progress: Progress | None = None) -> str:
    """Windows: the gyan.dev 'release essentials' build into tools/ffmpeg. Elsewhere: explain the one command."""
    if not WINDOWS:
        hint = "brew install ffmpeg" if MAC else "sudo apt install ffmpeg   (or your distro's package manager)"
        raise RuntimeError(f"install ffmpeg with:  {hint}   then run setup again")
    want = _fetch_text(FFMPEG_WIN_ZIP + ".sha256").split()[0]
    archive = download(FFMPEG_WIN_ZIP, TOOLS / "downloads" / "ffmpeg-release-essentials.zip", "ffmpeg", want,
                       progress)
    _say(progress, "Unpacking ffmpeg")
    with zipfile.ZipFile(archive) as z:
        top = z.namelist()[0].split("/")[0]
        z.extractall(TOOLS)
    dst = TOOLS / "ffmpeg"
    if dst.exists():
        shutil.rmtree(dst)
    (TOOLS / top).rename(dst)
    archive.unlink(missing_ok=True)
    path = find_ffmpeg()
    if not path:
        raise RuntimeError("ffmpeg was unpacked but ffmpeg.exe wasn't found in tools/ffmpeg")
    return path


def tool_size_note() -> str:
    return "Blender is about 400 MB to download (1.2 GB unpacked); ffmpeg about 115 MB."


if __name__ == "__main__":  # pragma: no cover
    print("blender:", find_blender())
    print("ffmpeg:", find_ffmpeg())
    print("fonts:", *find_fonts(), sep="\n  ")
    print("root:", ROOT)
