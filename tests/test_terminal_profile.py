"""ReelForge's Windows Terminal profile (studio/terminal_profile.py): the anvil on its tab.

  .venv\\Scripts\\python -m unittest tests.test_terminal_profile
"""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path, PureWindowsPath
from unittest import mock

from studio import paths as P
from studio import terminal_profile as T

NO_MARKER = Path(__file__).with_name("no-such-marker.txt")         # a normal copy, even when run in a test copy


class Profile(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.local = Path(tmp.name)
        for patch in (mock.patch.dict(os.environ, {"LOCALAPPDATA": tmp.name, "STUDIO_DRY_SYSTEM": ""}),
                      mock.patch.object(P, "TEST_COPY", NO_MARKER), mock.patch.object(P, "WINDOWS", True)):
            patch.start()
            self.addCleanup(patch.stop)
        self.where = self.local / "Microsoft" / "Windows Terminal" / "Fragments" / "ReelForge"

    def test_the_command_line_is_the_one_windows_starts_for_the_bat(self):
        # Opened from Explorer (a shortcut, the Start menu, a double-click), a .bat runs as exactly this, and
        # Terminal gives the window the profile whose command line it starts with.
        with mock.patch.dict(os.environ, {"ComSpec": r"C:\WINDOWS\system32\cmd.exe"}), \
                mock.patch.object(P, "ROOT", PureWindowsPath(r"C:\Users\Sam O'Neil\ReelForge")):
            self.assertEqual(T.command_line(),
                             r'''C:\WINDOWS\system32\cmd.exe /c ""C:\Users\Sam O'Neil\ReelForge\ReelForge.bat" "''')

    def test_the_guid_is_the_one_terminal_would_make(self):
        def v5(namespace: uuid.UUID, name: str) -> uuid.UUID:       # Terminal hashes names as UTF-16LE
            return uuid.uuid5(namespace, name.encode("utf-16-le").decode("latin-1"))

        fragments = uuid.UUID("{f65ddb7e-706b-4499-8a50-40313caf510a}")
        self.assertEqual(str(v5(v5(fragments, "Git"), "Git Bash")), "2ece5bfe-50ed-5f3a-ab87-5cd4baafed2b")  # docs
        self.assertEqual(f"{{{v5(v5(fragments, 'ReelForge'), 'ReelForge')}}}", T.GUID)

    def test_written_once_and_kept_up_to_date(self):
        self.assertIn("is in Windows Terminal", T.ensure())
        profile = json.loads((self.where / "ReelForge.json").read_text(encoding="utf-8"))["profiles"][0]
        self.assertEqual(profile["name"], "ReelForge")
        self.assertEqual(profile["guid"], T.GUID)
        self.assertEqual(profile["commandline"], T.command_line())
        self.assertEqual(profile["startingDirectory"], str(P.ROOT))
        self.assertEqual(Path(profile["icon"]), self.where / "reelforge-terminal.png")
        self.assertEqual(Path(profile["icon"]).read_bytes(), T.ICON.read_bytes())
        self.assertEqual(sorted(p.name for p in self.where.iterdir()), ["ReelForge.json", "reelforge-terminal.png"])

        stamps = {p: p.stat().st_mtime_ns for p in self.where.iterdir()}
        self.assertIn("up to date", T.ensure())
        self.assertEqual({p: p.stat().st_mtime_ns for p in self.where.iterdir()}, stamps)

        moved = P.ROOT.parent / "ReelForge (moved)"                  # a moved folder: the profile follows it
        with mock.patch.object(P, "ROOT", moved):
            self.assertIn("is in Windows Terminal", T.ensure())
            profile = json.loads((self.where / "ReelForge.json").read_text(encoding="utf-8"))["profiles"][0]
            self.assertEqual(profile["startingDirectory"], str(moved))
            self.assertIn(str(moved / "ReelForge.bat"), profile["commandline"])

    def test_a_test_copy_or_a_dry_run_leaves_terminal_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "TEST-COPY.txt"
            marker.write_text("a test copy", encoding="utf-8")
            with mock.patch.object(P, "TEST_COPY", marker):
                self.assertIn("test copy", T.ensure())
        with mock.patch.dict(os.environ, {"STUDIO_DRY_SYSTEM": "1"}):
            self.assertIn("dry run", T.ensure())
        self.assertFalse((self.local / "Microsoft").exists())


if __name__ == "__main__":
    unittest.main()
