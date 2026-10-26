"""For the window's profile tests (ui/test/dashboard.test.tsx): a ReelForge folder of their own in a scratch folder
(REELFORGE_TEST_ROOT), with two profiles besides the first, Alpha and Beta, run inside the window's Python side before
it starts (REELFORGE_BRIDGE_PRELOAD). Nothing is connected, so nothing is read, the update check stays offline, and a
sign-up page opens nothing (its private window is Chrome's, on every computer)."""

import os
import shutil
from pathlib import Path

from studio import profiles, signup, update

signup.open_page = lambda url: None
signup.launch = lambda command: None
signup.private_browser = lambda: signup.Private("Chrome", ("chrome", "--incognito"))

root = Path(os.environ["REELFORGE_TEST_ROOT"])
profiles.ROOT = root
profiles.FOLDER = root / "profiles"
example = Path(__file__).resolve().parent.parent.parent / "dashboard" / "config.example.toml"
for day, name in ((1, "Alpha"), (2, "Beta")):
    folder = profiles.FOLDER / profiles.slug_for(name)
    if not (folder / profiles.MARK).exists():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / profiles.MARK).write_text(f'name = "{name}"\ncreated = "2026-01-0{day}T00:00:00"\n',
                                            encoding="utf-8")
        (folder / "dashboard").mkdir(exist_ok=True)
        shutil.copy(example, folder / "dashboard" / "config.toml")
update.check = lambda timeout=20: {"current": "1.0.0", "latest": "1.0.0", "newer": False, "notes": "", "url": "",
                                   "published": "", "assets": {}, "error": "", "checked": ""}
