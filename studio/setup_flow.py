"""Setup's second half, once setup.bat / setup.sh has Python and the packages in: find what's still missing
(Blender, ffmpeg, the sound effects, the reelforge command, a desktop shortcut), ask once, set it all up, check
everything, then onboarding. Everything downloaded goes into this folder.

In a terminal this is the boxed first-run screen (studio/firstrun.py). With --yes, or when nobody is at the
keyboard (an AI running setup for someone), the same steps print as plain lines.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from . import BLENDER_VERSION, KIT_NAME, command, doctor, sounds, tools
from . import paths as P
from . import settings as S

SERIES = ".".join(BLENDER_VERSION.split(".")[:2])


@dataclass
class Item:
    key: str              # blender, ffmpeg, sounds, command, shortcut
    name: str             # "Blender 4.5.5"
    why: str              # what it's for, in a few words
    ready: bool
    detail: str = ""      # where it was found, or what setting it up does
    size_mb: int = 0      # download size when it isn't ready
    can_install: bool = True
    default: bool = True  # ticked to begin with


def _shortcut_path():
    import os
    from pathlib import Path

    desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
    return desktop / f"{KIT_NAME}.lnk"


def _where(path: str) -> str:
    """'ready' for the copy setup put in tools/, 'already installed' for one found elsewhere."""
    from pathlib import Path

    try:
        Path(path).resolve().relative_to(P.TOOLS.resolve())
        return "ready"
    except ValueError:
        return "already installed"


def installed_by_installer() -> bool:
    return (P.ROOT / "unins000.exe").exists()


def plan() -> list[Item]:
    """Everything setup looks after, each marked ready or not. Takes a few seconds (it starts Blender once)."""
    items: list[Item] = []
    blender = tools.find_blender()
    ver = tools.blender_version(blender) if blender else ""
    if blender and (ver.startswith(SERIES + ".") or ver == SERIES):
        items.append(Item("blender", f"Blender {ver}", "builds and renders your 3D scenes", True, _where(blender)))
    else:
        note = "about 400 MB from blender.org"
        if blender:
            note += f" (your Blender {ver or '?'} stays as it is)"
        items.append(Item("blender", f"Blender {BLENDER_VERSION}", "builds and renders your 3D scenes", False, note,
                          400))

    ffmpeg = tools.find_ffmpeg()
    if ffmpeg:
        items.append(Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", True, _where(ffmpeg)))
    elif P.WINDOWS:
        items.append(Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", False,
                          "about 115 MB from gyan.dev", 115))
    else:
        hint = "brew install ffmpeg" if P.MAC else "sudo apt install ffmpeg"
        items.append(Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", False,
                          f"install it yourself with:  {hint}", can_install=False, default=False))

    gone = [n for n, m in sounds.missing() if m["source"] == "mixkit"]
    total = sounds.mixkit_count()
    if not gone:
        items.append(Item("sounds", "Sound effects", "booms, whooshes and hits for your videos", True,
                          f"all {len(sounds.manifest()['sounds'])} ready"))
    else:
        mb = max(1, round(55 * len(gone) / max(total, 1)))       # all of Mixkit's files come to about 55 MB
        items.append(Item("sounds", "Sound effects", "booms, whooshes and hits for your videos", False,
                          f"{len(gone)} from Mixkit, about {mb} MB", mb))

    on = command.status() == "on"
    items.append(Item("command", "The reelforge command", "type reelforge in any terminal to open it", on,
                      "ready" if on else "no admin rights needed"))

    if P.WINDOWS:
        link = _shortcut_path()
        items.append(Item("shortcut", "Desktop shortcut", "a ReelForge icon on your desktop", link.exists(),
                          "ready" if link.exists() else "double-click to open ReelForge",
                          default=not installed_by_installer()))
    return items


def todo(items: list[Item]) -> list[Item]:
    return [i for i in items if not i.ready and i.can_install]


def make_shortcut() -> str:
    """A desktop shortcut that opens ReelForge (Windows)."""
    link = _shortcut_path()
    target = P.ROOT / "ReelForge.bat"
    icon = P.ROOT / "assets" / "icon" / "reelforge.ico"

    def q(s) -> str:
        return "'" + str(s).replace("'", "''") + "'"

    ps = (f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({q(link)}); $s.TargetPath = {q(target)}; "
          f"$s.WorkingDirectory = {q(P.ROOT)}; $s.Description = 'ReelForge'; "
          + (f"$s.IconLocation = {q(icon)}; " if icon.exists() else "") + "$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["PowerShell couldn't make the shortcut"])[-1])
    return str(link)


def apply(item: Item, progress=None) -> str:
    """Set up one item. Returns a short sentence; raises with a readable message if it fails."""
    if item.key == "blender":
        return f"Blender ready ({P.rel(tools.install_blender(progress))})"
    if item.key == "ffmpeg":
        return f"ffmpeg ready ({P.rel(tools.install_ffmpeg(progress))})"
    if item.key == "sounds":
        failed = sounds.fetch_mixkit(progress=progress)
        if failed:
            raise RuntimeError(f"{len(failed)} sounds didn't download ({', '.join(failed[:3])}). Run setup again "
                               "later to fetch them.")
        return "sounds ready"
    if item.key == "command":
        return command.enable()
    if item.key == "shortcut":
        if P.test_copy():
            return "Left alone in a test copy: it never adds a desktop shortcut."
        if P.dry_system():
            return "(dry run) would add the desktop shortcut"
        return f"shortcut added ({make_shortcut()})"
    raise ValueError(item.key)


def prepare_sounds(progress=None) -> None:
    """Convert every sound to 48 kHz WAV for fast mixing (needs ffmpeg and every sound in place)."""
    if not sounds.missing() and tools.find_ffmpeg():
        if progress:
            progress("Preparing the sound library", 0, 0)
        sounds.build_cache(quiet=progress is not None)


# ---------------------------------------------------------------- plain mode (--yes, or no keyboard)

def _ask(question: str, default: bool, yes: bool) -> bool:
    if yes:
        print(f"{question} yes (--yes)")
        return True
    if not sys.stdin.isatty():
        return False
    hint = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            a = input(f"{question} {hint} ").strip().lower()
        except EOFError:                # no one at the keyboard after all
            print()
            return False
        if not a:
            return default
        if a in ("y", "yes"):
            return True
        if a in ("n", "no"):
            return False


def run(yes: bool = False, onboard: bool = True) -> int:
    print(f"\n{KIT_NAME} setup: tools, sounds and a health check\n")
    ok = True
    if tools.path_too_long():
        print(f"Warning: this folder's path is {len(str(P.ROOT))} characters long. Windows can't load some of "
              "Blender's files from paths that deep.\n  Move the folder somewhere shorter (e.g. C:\\ReelForge) and run "
              "setup again.\n")
    print("Checking what's here...")
    items = plan()
    for i in items:
        mark = "ok  " if i.ready else ("todo" if i.can_install else "you ")
        print(f"  [{mark}] {i.name}: {i.why} ({i.detail})")
    work = [i for i in todo(items) if i.default or yes]
    manual = [i for i in items if not i.ready and not i.can_install]
    if work:
        size = sum(i.size_mb for i in work)
        names = ", ".join(i.name for i in work)
        print()
        if _ask(f"Set up {names} now" + (f" (about {size} MB of downloads)" if size else "") + "?", True, yes):
            for i in work:
                print(f"\n{i.name}:")
                try:
                    print(f"  {apply(i)}")
                except Exception as e:
                    ok = False
                    print(f"  Couldn't set it up: {e}")
        else:
            ok = False
            print("Skipped. Run setup again whenever you're ready.")
    if manual:
        ok = False
        for i in manual:
            print(f"\n{i.name} is needed: {i.detail}, then run setup again.")
    try:
        if not sounds.missing() and tools.find_ffmpeg():
            print("\nPreparing the sound library...")
            prepare_sounds()
    except Exception as e:
        ok = False
        print(f"  Couldn't prepare the sounds: {e}")

    print()
    if doctor.run() != 0:
        ok = False

    if onboard and not S.onboarded():
        print()
        if yes or not sys.stdin.isatty():
            print("Next: run onboarding (reelforge onboard, or " + ("onboard.bat" if P.WINDOWS else "./onboard.sh") +
                  "), a short interview about your channel.")
        elif _ask("Start onboarding now (a short interview about your channel)?", True, False):
            from .__main__ import onboard as run_onboard
            run_onboard(["--plain"])
    elif S.onboarded():
        print(f"\nOnboarding is done ({S.load()['channel']['name']}). Run reelforge onboard to change your answers.")
    print("\nSetup finished." if ok else "\nSetup finished with problems (see above).")
    return 0 if ok else 1
