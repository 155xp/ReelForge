"""Sample data for the README's screenshots (scripts/screenshots.py) and the window's tests (ui/test/), run inside the
window's Python side before it starts (REELFORGE_BRIDGE_PRELOAD, see studio/bridge.py). Nothing on this computer
changes: it only swaps what ReelForge would find here for the same things on a fresh computer.

  - The Publish tab lists the kit's three demo videos, rendered a day ago (their files are made in a scratch folder,
    their sizes those of the real renders).
  - The first-run screens show a neutral folder (C:\\Users\\you\\ReelForge) and what a computer with nothing installed
    sees, and the last screen a new channel's (Night Physics) with nothing turned on here.
  - The channel's questions start from a sample channel's answers, so its later steps can be shown.
  - A sign-up guide's button, Open profile and every other link open nothing: no browser ever opens from a picture
    or a test (a test that sets REELFORGE_OPENED to a file finds the pages listed there), and a second channel's
    private window is always Chrome's.
"""

from __future__ import annotations

import atexit
import copy
import json
import os
import pathlib
import shutil
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="reelforge-shots-"))
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)
RENDERS = {  # file -> (size in MB as the Publish tab shows it, hours since it was rendered)
    "demo_everyone_jumps.mp4": (131.4, 24.2),
    "demo_doubling_duck.mp4": (81.5, 25.1),
    "demo_disaster_pov.mp4": (50.9, 25.3),
}


def _episodes() -> pathlib.Path:
    """The demos as rendered pipeline episodes: episodes/<id>/episode.json and final/<id>.mp4."""
    episodes = SCRATCH / "episodes"
    for name, (_, hours) in RENDERS.items():
        folder = episodes / pathlib.Path(name).stem
        (folder / "final").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "examples" / folder.name / "episode.json", folder / "episode.json")
        video = folder / "final" / name
        video.write_bytes(b"\0")
        when = time.time() - hours * 3600
        os.utime(video, (when, when))
    return episodes


def _dashboard() -> None:
    from dashboard import config

    episodes = _episodes()
    config.episodes_dir = lambda cfg: episodes
    config.videos_dir = lambda cfg: SCRATCH / "videos"
    config.completed_dir = lambda cfg: SCRATCH / "none"
    real_stat = pathlib.Path.stat

    def stat(self, *args, **kwargs):
        st = real_stat(self, *args, **kwargs)
        if self.name in RENDERS:  # only the demos' scratch renders are called that here
            fields = list(st[:10])
            fields[6] = int(RENDERS[self.name][0] * 1024 * 1024)  # st_size
            st = os.stat_result(fields)
        return st

    pathlib.Path.stat = stat


# Your accounts as a new channel sees it: the three recommended platforms, one handle typed in and two to sign up for.
ACCOUNTS_ANSWERS = {"creator": "Sam", "channel_name": "Night Physics", "handle_tiktok": "@nightphysics",
                    "about": "Mind-bending what-if videos: everyday things pushed to impossible extremes, with real "
                             "science."}


def _first_run() -> None:
    from studio import command, setup_flow, setup_service, sounds, stats_schedule, tools
    from studio import paths as P
    from studio import settings as S

    P.ROOT = pathlib.Path(r"C:\Users\you\ReelForge")  # a neutral folder in the picture
    tools.path_too_long = lambda: False
    Item = setup_flow.Item
    setup_flow.plan = lambda: [  # what a computer with nothing installed sees
        Item("blender", "Blender 4.5.5", "builds and renders your 3D scenes", False, "about 400 MB from blender.org",
             400),
        Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", False, "about 115 MB from gyan.dev", 115),
        Item("sounds", "Sound effects", "booms, whooshes and hits for your videos", False,
             f"{sounds.mixkit_count()} from Mixkit, about 55 MB", 55),
        Item("command", "The reelforge command", "type reelforge in any terminal to open it", False,
             "no admin rights needed"),
        Item("shortcut", "Desktop shortcut", "a ReelForge icon on your desktop", True, "ready"),
    ]
    sample = copy.deepcopy(S.DEFAULTS)  # a new channel's last screen, with nothing turned on here
    sample["channel"]["name"] = "Night Physics"
    sample["ai"].update(assistant="both")
    sample["platforms"]["handles"] = {p: "yourchannel" for p in S.PLATFORMS}
    S.load = lambda path=None: sample
    stats_schedule.enable = lambda minutes=60: (f"Your stats will update every {minutes} minutes while this computer "
                                                "is on, even with ReelForge closed.")
    command.status = lambda: "on"
    answers = json.loads((ROOT / "scripts" / "shots_answers.json").read_text(encoding="utf-8"))
    if os.environ.get("REELFORGE_SHOT") == "setup-accounts":
        answers = ACCOUNTS_ANSWERS
    setup_service.saved_answers = lambda profile=None: dict(answers)


def _list_modules() -> None:
    """For docs/screenshots/SOURCES.txt: the modules this process drew with, listed as it exits."""
    import sys

    path = os.environ.get("REELFORGE_SHOT_MODULES")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.writelines(f"{m.__file__}\n" for m in list(sys.modules.values()) if getattr(m, "__file__", None))


def _no_browser() -> None:
    """Sign-up pages open nothing, and a second channel's private window is Chrome's on every computer (so the pictures
    and tests say the same everywhere). Nor does any other page: each goes in REELFORGE_OPENED's file, if it's set."""
    from dashboard import desktop
    from studio import signup

    signup.open_page = lambda url: None
    signup.launch = lambda command: None
    signup.private_browser = lambda: signup.Private("Chrome", ("chrome", "--incognito"))

    def opened(url: str) -> None:
        if os.environ.get("REELFORGE_OPENED"):
            with open(os.environ["REELFORGE_OPENED"], "a", encoding="utf-8", newline="\n") as f:
                f.write(url + "\n")

    desktop.open_url = opened


atexit.register(_list_modules)
_dashboard()
_first_run()
_no_browser()
