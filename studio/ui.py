"""ReelForge's window and first-run screens are an OpenTUI app (ui/, TypeScript), run by Bun. This finds Bun, keeps
the app's packages installed, and runs it.

Setup puts Bun in tools/bun (from Bun's own releases on GitHub, checked against their published checksums) and the
app's packages in ui/node_modules (bun install, exactly the versions in ui/bun.lock). Both are checked each time the
window opens, so an update that changes the packages, or a ReelForge that predates the OpenTUI window, gets them
then; it prints what it's doing on plain lines first.

  run("dashboard", {"tab": "publish"})    the ReelForge window
  run("setup", {"start": "tools"})        the first-run screens: tools, onboarding, ready

The app starts studio/bridge.py with this same Python for everything it shows (REELFORGE_PYTHON). Its exit code is
the window's: 75 asks the launcher to start ReelForge again (it updated itself).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from .paths import MAC, ROOT, TOOLS, WINDOWS

BUN_VERSION = "1.4.3"   # the Bun the app is tested with (OpenTUI needs 1.3.14 or newer, 1.4 on Windows ARM)
BUN_RELEASES = f"https://github.com/oven-sh/bun/releases/download/bun-v{BUN_VERSION}/"
BUN_DIR = TOOLS / "bun"
UI = ROOT / "ui"
LOCK = UI / "bun.lock"
STAMP = UI / "node_modules" / ".reelforge-installed"   # a copy of bun.lock as last installed
ENTRY = UI / "src" / "main.tsx"
LOG = ROOT / "dashboard" / "data" / "window-log.txt"   # what the Python side wrote to stderr last time


def bun_asset() -> str:
    """Bun's download for this computer. The x64 builds are the "baseline" ones, which run on every x64 processor
    (the others need AVX2, which some older PCs lack)."""
    arm = platform.machine().lower() in ("arm64", "aarch64")
    system = "windows" if WINDOWS else "darwin" if MAC else "linux"
    return f"bun-{system}-{'aarch64' if arm else 'x64-baseline'}.zip"


def bun_path() -> Path | None:
    """The Bun to run the app with: REELFORGE_BUN, the one setup put in tools/bun, or a Bun of your own on the PATH
    (a git copy for working on ReelForge)."""
    forced = os.environ.get("REELFORGE_BUN", "").strip()
    if forced:
        return Path(forced) if Path(forced).is_file() else None
    own = BUN_DIR / ("bun.exe" if WINDOWS else "bun")
    if own.is_file():
        return own
    found = shutil.which("bun")
    return Path(found) if found else None


def packages_ready() -> bool:
    return STAMP.is_file() and LOCK.is_file() and STAMP.read_bytes() == LOCK.read_bytes()


def missing() -> list[str]:
    """What the window still needs: [] when it can open."""
    out = []
    if bun_path() is None:
        out.append(f"Bun {BUN_VERSION}")
    if not packages_ready():
        out.append("the window's packages")
    return out


def install_bun(progress=None) -> Path:
    """Download Bun into tools/bun and return its path."""
    from . import tools

    asset = bun_asset()
    sums = tools._fetch_text(BUN_RELEASES + "SHASUMS256.txt")
    want = next((ln.split()[0] for ln in sums.splitlines() if ln.strip().endswith(asset)), None)
    if not want:
        raise RuntimeError(f"no checksum published for {asset}")
    archive = tools.download(BUN_RELEASES + asset, TOOLS / "downloads" / asset, f"Bun {BUN_VERSION}", want,
                             progress)
    if progress:
        progress("Unpacking Bun", 0, 0)
    exe = "bun.exe" if WINDOWS else "bun"
    with zipfile.ZipFile(archive) as z:
        inner = next(n for n in z.namelist() if n.endswith("/" + exe) or n == exe)
        BUN_DIR.mkdir(parents=True, exist_ok=True)
        dest = BUN_DIR / exe
        with z.open(inner) as src, dest.open("wb") as out:
            shutil.copyfileobj(src, out)
    if not WINDOWS:
        dest.chmod(0o755)
    archive.unlink(missing_ok=True)
    return dest


def install_packages(bun: Path, log=None) -> None:
    """bun install: exactly the packages ui/bun.lock lists (and only this computer's build of OpenTUI's core)."""
    cmd = [str(bun), "install", "--frozen-lockfile", "--production", "--no-progress"]
    res = subprocess.run(cmd, cwd=UI, capture_output=True, text=True, encoding="utf-8", errors="replace",
                         stdin=subprocess.DEVNULL)
    if log:
        log(res.stdout + res.stderr)
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-3:]
        raise RuntimeError("bun install didn't finish: " + " / ".join(tail))
    shutil.copyfile(LOCK, STAMP)


def ensure(say=print) -> bool:
    """Get whatever the window still needs (Bun, its packages), saying so on plain lines. True once it can open."""
    need = missing()
    if not need:
        return True
    say(f"Getting ReelForge's window ready ({' and '.join(need)})…")
    try:
        bun = bun_path() or install_bun()
        if not packages_ready():
            install_packages(bun)
    except Exception as e:
        say(f"Couldn't get it ready: {e}\nCheck your internet connection and try again, or run: reelforge setup")
        return False
    return True


def run(screen: str, options: dict | None = None) -> tuple[int, dict | None]:
    """Open the window (screen "dashboard" or "setup") and wait for it to close. Returns its exit code, and what it
    asked for as it closed (the first-run screens' last button: {"open": "dashboard", "tab": "accounts"}), if
    anything."""
    if not ensure():
        return 1, None
    with tempfile.TemporaryDirectory(prefix="reelforge-") as tmp:
        result = Path(tmp) / "result.json"
        env = dict(os.environ, REELFORGE_PYTHON=sys.executable, REELFORGE_ROOT=str(ROOT), PYTHONUTF8="1",
                   REELFORGE_LOG=str(LOG), REELFORGE_RESULT=str(result))
        try:
            from . import logo

            env["REELFORGE_QUADRANTS"] = "1" if logo.quadrants() else "0"
        except Exception:
            pass
        args = [str(bun_path()), str(ENTRY), screen, json.dumps(options or {})]
        try:
            code = subprocess.call(args, cwd=UI, env=env)
        except KeyboardInterrupt:
            code = 130
        try:
            value = json.loads(result.read_text(encoding="utf-8")) if result.is_file() else None
        except ValueError:
            value = None
    return code, value


def main(argv: list[str] | None = None) -> int:
    """python -m studio.ui [install]: get Bun and the window's packages (setup's first box runs this)."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "install":
        def show(what: str, done: float, total: float) -> None:
            pct = f" {100 * done / total:.0f}%" if total else ""
            print(f"{what}{pct}", flush=True)

        try:
            bun = bun_path()
            if bun is None:
                print(f"Downloading Bun {BUN_VERSION}", flush=True)
                bun = install_bun(show)
            print(f"Bun ready ({bun})", flush=True)
            if not packages_ready():
                print("Installing the window's packages", flush=True)
                install_packages(bun, log=lambda text: print(text, flush=True))
            print("The window's packages: ready", flush=True)
        except Exception as e:
            print(f"ERROR: {e}", flush=True)
            return 1
        return 0
    print("python -m studio.ui install    get Bun and the window's packages")
    return 2


if __name__ == "__main__":
    sys.exit(main())
