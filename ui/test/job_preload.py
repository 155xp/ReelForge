"""For the Settings tab's Background refresh switch test (ui/test/settings.test.tsx): settings_preload.py's channel in a
scratch folder (REELFORGE_TEST_ROOT), on a computer ReelForge may change, with the hourly job made up: whether it's on
is kept in job.txt in that folder, so the test can see it, and turning it on or off takes a moment, as Windows' task
scheduler does. Nothing here touches this computer: the reelforge command and the icon are made up too, and changing
either of them fails."""

import os
import runpy
import time
from pathlib import Path

from studio import command, shortcut, stats_schedule
from studio import paths as P

runpy.run_path(str(Path(__file__).with_name("settings_preload.py")), run_name="preload")
job = Path(os.environ["REELFORGE_TEST_ROOT"]).resolve() / "job.txt"
job.write_text("on", encoding="utf-8")


def turn(on: bool) -> str:
    time.sleep(0.8)
    job.write_text("on" if on else "off", encoding="utf-8")
    return "Your stats will update every 60 minutes while this computer is on." if on else "Background stats are off."


def never(*args, **kwargs):
    raise RuntimeError("the tests never change this computer")


P.test_copy = P.dry_system = lambda: False
stats_schedule.status = lambda: job.read_text(encoding="utf-8")
stats_schedule.enable = lambda minutes=60: turn(True)
stats_schedule.disable = lambda: turn(False)
command.status = lambda: "on"
command.enable = command.disable = shortcut.make = never
shortcut.label = lambda: ("Desktop shortcut", "a ReelForge icon on your desktop", "double-click to open ReelForge")
shortcut.ours = lambda: True
