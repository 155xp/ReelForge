"""For the Settings tab's danger zone tests (ui/test/settings.test.tsx): a ReelForge folder of their own in a scratch
folder (REELFORGE_TEST_ROOT) with one channel set up, Night Physics, and a video, run inside the window's Python side
before it starts (REELFORGE_BRIDGE_PRELOAD). Factory reset and uninstall only get as far as asking for it (the request
in that folder) and closing the window: nothing here runs the launcher that would do them. Nothing is connected, so
nothing is read, and the update check stays offline."""

import io
import os
import shutil
from contextlib import redirect_stdout
from pathlib import Path

from dashboard import config
from studio import generate, profiles, reset, update
from studio import paths as P

root = Path(os.environ["REELFORGE_TEST_ROOT"]).resolve()
(root / "dashboard").mkdir(parents=True, exist_ok=True)
shutil.copy(P.DASHBOARD / "config.example.toml", root / "dashboard" / "config.example.toml")
P.ROOT, P.DASHBOARD = root, root / "dashboard"
profiles.ROOT, profiles.FOLDER = root, root / "profiles"
config.APP_DIR = root / "dashboard"
reset.ROOT, reset.PENDING, reset.BACKUPS = root, root / ".reelforge-pending.json", root / "backups"
if not profiles.main().onboarded:
    with redirect_stdout(io.StringIO()):
        generate.write_all({"creator": "Sam", "channel_name": "Night Physics", "about": "What-if videos with real science.",
                            "platforms": ["tiktok", "youtube"]})
video = root / "episodes" / "ep01_duck" / "final" / "ep01_duck.mp4"
video.parent.mkdir(parents=True, exist_ok=True)
video.write_bytes(b"a video")
update.check = lambda timeout=20: {"current": "1.0.0", "latest": "1.0.0", "newer": False, "notes": "", "url": "",
                                   "published": "", "assets": {}, "error": "", "checked": ""}
