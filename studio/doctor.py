"""Checks that everything the pipeline needs is in place, and says how to fix whatever isn't.

  python -m studio doctor                  quick checks (a few seconds)
  python -m studio doctor --render-test    also builds the example scene in Blender and renders one frame
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import BLENDER_VERSION, KIT_NAME, KIT_VERSION
from . import paths as P
from . import settings as S
from . import sounds, tools

OK, WARN, FAIL = "ok", "warn", "FAIL"
MARK = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}


class Report:
    def __init__(self, quiet: bool = False):
        self.rows: list[tuple[str, str, str]] = []
        self.quiet = quiet

    def add(self, status: str, what: str, detail: str = ""):
        self.rows.append((status, what, detail))
        if not self.quiet:
            print(f"[{MARK[status]}] {what}" + (f": {detail}" if detail else ""), flush=True)

    @property
    def failed(self) -> bool:
        return any(s == FAIL for s, _, _ in self.rows)


def run(render_test: bool = False) -> int:
    print(f"{KIT_NAME} {KIT_VERSION}: checking {P.ROOT}\n")
    r = checks(render_test)
    print()
    if r.failed:
        print("Some checks FAILED. Fix those first (the line says how), then run this again.")
        return 1
    print("All set." if not any(s == WARN for s, _, _ in r.rows) else "Ready, with the warnings above.")
    return 0


def window_check(r: Report, fix: str) -> None:
    """ReelForge's window: Bun runs it, and its packages (OpenTUI) are installed (studio/ui.py)."""
    from . import ui

    bun = ui.bun_path()
    version = ""
    if bun:
        try:
            version = subprocess.run([str(bun), "--version"], capture_output=True, text=True, timeout=30,
                                     stdin=subprocess.DEVNULL).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            version = ""
    if not version:
        r.add(FAIL, "Window", f"Bun isn't installed: {fix} (it downloads Bun {ui.BUN_VERSION})")
        return
    if not ui.packages_ready():
        r.add(FAIL, "Window", f"Bun {version}, but the window's packages aren't installed: {fix}")
        return
    try:
        core = json.loads((ui.UI / "node_modules" / "@opentui" / "core" / "package.json").read_text("utf-8"))
        r.add(OK, "Window", f"Bun {version}, OpenTUI {core['version']}")
    except (OSError, ValueError, KeyError):
        r.add(FAIL, "Window", f"Bun {version}, but OpenTUI isn't installed: {fix}")


def checks(render_test: bool = False, quiet: bool = False) -> Report:
    """Every check, as a Report (printed line by line unless quiet)."""
    r = Report(quiet)
    fix = "run setup again (reelforge setup, or setup.bat)" if P.WINDOWS else "run ./setup.sh again"

    v = sys.version_info
    r.add(OK if v >= (3, 11) else FAIL, "Python", f"{v.major}.{v.minor}.{v.micro}" +
          ("" if v >= (3, 11) else " (needs 3.11 or newer)"))
    missing = []
    for mod in ("numpy", "PIL", "jinja2", "httpx", "playwright"):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    r.add(FAIL if missing else OK, "Python packages", f"missing {', '.join(missing)}: {fix}" if missing else
          "numpy, Pillow, Jinja2, httpx, Playwright")
    window_check(r, fix)

    blender = tools.find_blender()
    if not blender:
        r.add(FAIL, "Blender", f"not found: {fix} (it can download Blender {BLENDER_VERSION}), or set STUDIO_BLENDER")
    else:
        ver = tools.blender_version(blender)
        series = ".".join(BLENDER_VERSION.split(".")[:2])
        if not ver:
            r.add(FAIL, "Blender", f"{blender} won't start")
        elif ver.startswith(series + ".") or ver == series:
            r.add(OK, "Blender", f"{ver} ({P.rel(Path(blender))})")
        else:
            r.add(WARN, "Blender", f"{ver} found; the pipeline is built on {series} LTS and may not work on other "
                                   f"versions. Setup can put {BLENDER_VERSION} in this folder.")

    ffmpeg = tools.find_ffmpeg()
    if not ffmpeg:
        r.add(FAIL, "ffmpeg", f"not found: {fix}, or set STUDIO_FFMPEG")
    else:
        probe = tools.ffprobe_for(ffmpeg)
        try:
            out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=30).stdout
            ver = out.split("\n", 1)[0].replace("ffmpeg version ", "").split(" ")[0]
            has_probe = Path(probe).exists() or shutil.which("ffprobe")
            r.add(OK if has_probe else FAIL, "ffmpeg", f"{ver} ({P.rel(Path(ffmpeg))})" +
                  ("" if has_probe else "; ffprobe is missing next to it"))
        except (OSError, subprocess.SubprocessError) as e:
            r.add(FAIL, "ffmpeg", f"won't run: {e}")

    fonts = tools.find_fonts()
    absent = [str(f) for f in fonts if not Path(f).is_file()]
    hint = "" if P.WINDOWS or P.MAC else f" ({tools.font_package()})"
    r.add(FAIL if absent else OK, "Fonts", ("missing: " + ", ".join(absent) + hint) if absent else
          ", ".join(sorted({Path(f).stem for f in fonts})))

    from . import browsers

    b = browsers.find()
    r.add(OK if b else WARN, "Stats browser", b.describe() if b else
          f"no Chrome, Edge or Chromium for the TikTok, Instagram and X stats: {fix} (it downloads Chromium)")

    try:
        gone = sounds.missing()
        mix = [n for n, m in gone if m["source"] == "mixkit"]
        other = [n for n, m in gone if m["source"] != "mixkit"]
        total = len(sounds.manifest()["sounds"])
        if other:
            r.add(FAIL, "Sounds", f"{len(other)} kit sounds are missing ({', '.join(other[:3])}...): re-download the kit")
        elif mix:
            r.add(FAIL, "Sounds", f"{len(mix)} Mixkit sounds not downloaded yet: {fix} (or python -m studio sounds)")
        else:
            r.add(OK, "Sounds", f"all {total} in place")
    except (OSError, ValueError) as e:
        r.add(FAIL, "Sounds", f"can't read assets/sfx/manifest.json: {e}")

    if tools.path_too_long():
        r.add(WARN, "Folder path", f"{len(str(P.ROOT))} characters long; Windows can't load some of Blender's files "
                                   "from paths that deep. Move this folder somewhere shorter, e.g. C:\\Studio")
    free = P.free_gb()
    r.add(OK if free >= 10 else WARN, "Disk space", f"{free:.0f} GB free" + ("" if free >= 10 else
          " (keep 10 GB free: a render needs about 1 GB per video until it is shipped)"))

    if S.onboarded():
        s = S.load()
        r.add(OK, "First-time setup", f"done for {s['channel']['name']} (my-studio/studio.toml)")
        for name in ("CLAUDE.md", "AGENTS.md"):
            f = P.ROOT / name
            gen = f.exists() and "generated by" in f.read_text(encoding="utf-8", errors="replace")[:400]
            r.add(OK if gen else WARN, name, "written by first-time setup" if gen else
                  "not generated yet: run reelforge channel")
    else:
        r.add(WARN, "First-time setup", "not done yet: run reelforge channel (or channel" +
              (".bat)" if P.WINDOWS else ".sh)"))

    dash_cfg = P.DASHBOARD / "config.toml"
    if P.DASHBOARD.exists():
        r.add(OK if dash_cfg.exists() else WARN, "Dashboard", "configured" if dash_cfg.exists() else
              "not configured yet (first-time setup writes dashboard/config.toml)")
    from . import profiles

    more = profiles.extra()
    if more:  # the other channels, each set up in its own folder (studio/profiles.py)
        unset = [p.name for p in more if not p.onboarded]
        r.add(WARN if unset else OK, "Profiles", f"{len(more) + 1} channels: " +
              ", ".join(p.name for p in profiles.every()) +
              (f" ({', '.join(unset)} not set up yet: its Settings in the profile menu)" if unset else ""))

    if render_test and not r.failed:
        render_check(r)
    return r


def render_check(r: Report) -> None:
    """Build the example scene and render one frame, in a temporary episode folder that is deleted afterwards."""
    example = next((P.EXAMPLES / n / "episode.json" for n in ("demo_doubling_duck", "demo_disaster_pov")
                    if (P.EXAMPLES / n / "episode.json").exists()), None)
    if example is None:
        r.add(WARN, "Render test", "no example scene found in examples/")
        return
    tmp = Path(tempfile.mkdtemp(prefix="render_test_", dir=P.ROOT / "episodes"))
    try:
        spec = json.loads(example.read_text(encoding="utf-8"))
        spec["id"] = tmp.name
        (tmp / "episode.json").write_text(json.dumps(spec), encoding="utf-8")
        t0 = time.time()
        print("        building the example scene in Blender (about a minute)...", flush=True)
        cmd = [sys.executable, str(P.ROOT / "pipeline" / "make_episode.py"), str(tmp), "--steps", "build,stills",
               "--stills", "21"]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        still = next(iter(sorted((tmp / "build" / "stills").glob("s_*.jpg"))), None) if res.returncode == 0 else None
        if still and still.stat().st_size > 10_000:
            keep = P.ROOT / "my-studio" / "render-test.jpg"
            keep.parent.mkdir(exist_ok=True)
            shutil.copy2(still, keep)
            r.add(OK, "Render test", f"built and rendered a frame in {time.time() - t0:.0f} s "
                                     f"(my-studio/render-test.jpg)")
        else:
            log = tmp / "build" / "build.log"
            tail = log.read_text(encoding="utf-8", errors="replace")[-600:] if log.exists() else res.stdout[-600:]
            r.add(FAIL, "Render test", "Blender couldn't build or render the example:\n" + tail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
