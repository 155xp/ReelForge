"""Setup's second half, once setup.bat / setup.sh has Python and the packages in: find what's still missing
(Blender, ffmpeg, the sound effects, the reelforge command, ReelForge's icon and, on a Mac or Linux PC without Chrome
or Edge, a browser for the stats), ask once, set it all up, check everything, then onboarding. Everything downloaded
goes into this folder (Playwright keeps its Chromium in its own cache folder).

In a terminal this is the boxed first-run screen (studio/firstrun.py). With --yes, or when nobody is at the
keyboard (an AI running setup for someone), the same steps print as plain lines.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from . import BLENDER_VERSION, KIT_NAME, browsers, command, doctor, shortcut, sounds, tools
from . import paths as P
from . import settings as S

SERIES = ".".join(BLENDER_VERSION.split(".")[:2])


@dataclass
class Item:
    key: str              # blender, ffmpeg, sounds, browser, fonts, command, shortcut
    name: str             # "Blender 4.5.5"
    why: str              # what it's for, in a few words
    ready: bool
    detail: str = ""      # where it was found, or what setting it up does
    size_mb: int = 0      # download size when it isn't ready
    can_install: bool = True
    default: bool = True  # ticked to begin with


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
    elif not tools.blender_downloadable():
        items.append(Item("blender", f"Blender {SERIES}", "builds and renders your 3D scenes", False,
                          "blender.org has no ARM Linux build: install Blender 4.5 with your package manager",
                          can_install=False, default=False))
    else:
        note = "about 400 MB from blender.org"
        if blender:
            note += f" (your Blender {ver or '?'} stays as it is)"
        items.append(Item("blender", f"Blender {BLENDER_VERSION}", "builds and renders your 3D scenes", False, note,
                          400))

    ffmpeg = tools.find_ffmpeg()
    if ffmpeg:
        items.append(Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", True, _where(ffmpeg)))
    else:
        source, mb = tools.ffmpeg_source()
        items.append(Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", False,
                          f"about {mb} MB from {source}", mb))

    gone = [n for n, m in sounds.missing() if m["source"] == "mixkit"]
    total = sounds.mixkit_count()
    if not gone:
        items.append(Item("sounds", "Sound effects", "booms, whooshes and hits for your videos", True,
                          f"all {len(sounds.manifest()['sounds'])} ready"))
    else:
        mb = max(1, round(55 * len(gone) / max(total, 1)))       # all of Mixkit's files come to about 55 MB
        items.append(Item("sounds", "Sound effects", "booms, whooshes and hits for your videos", False,
                          f"{len(gone)} from Mixkit, about {mb} MB", mb))

    if not browsers.installed():        # Windows always has Edge; a Mac or Linux PC may have no Chrome or Edge
        items.append(Item("browser", "Chromium", "reads your TikTok, Instagram and X stats", False,
                          "about 170 MB from Playwright (there's no Chrome or Edge here)", 170))

    if not P.WINDOWS and not P.MAC and not tools.find_fonts()[0].is_file():
        items.append(Item("fonts", "DejaVu fonts", "the serif font for your videos' text", False,
                          f"install them with:  {tools.font_package()}", can_install=False, default=False))

    on = command.status() == "on"
    items.append(Item("command", "The reelforge command", "type reelforge in any terminal to open it", on,
                      "ready" if on else "no admin rights needed"))

    name, why, does = shortcut.label()
    made = shortcut.ready()
    items.append(Item("shortcut", name, why, made, "ready" if made else does, default=not installed_by_installer()))
    return items


def todo(items: list[Item]) -> list[Item]:
    return [i for i in items if not i.ready and i.can_install]


def make_shortcut() -> str:
    """ReelForge's icon: a desktop shortcut (Windows), ReelForge in Applications (macOS), an app-menu entry (Linux)."""
    return shortcut.make()


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
    if item.key == "browser":
        return browsers.install_chromium(progress)
    if item.key == "command":
        return command.enable()
    if item.key == "shortcut":
        if P.test_copy():
            return f"Left alone in a test copy: it never adds {KIT_NAME}'s icon."
        if P.dry_system():
            return f"(dry run) would add {KIT_NAME}'s icon ({item.name})"
        return f"{item.name}: added ({make_shortcut()})"
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
