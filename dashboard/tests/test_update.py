"""The updater (studio.update): versions, how a copy was installed, and copying a new version over a folder."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from studio import update


class VersionTest(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(update.version_tuple("v1.2"), (1, 2, 0))
        self.assertEqual(update.version_tuple("1.10.0-beta"), (1, 10, 0))
        self.assertTrue(update.is_newer("v1.0.1", "1.0.0"))
        self.assertTrue(update.is_newer("1.10.0", "1.9.9"))
        self.assertFalse(update.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(update.is_newer("0.9", "1.0.0"))

    def test_asset_names(self):
        self.assertEqual(update.asset_name("1.2.0", "installer"), "ReelForge-1.2.0-Windows-Setup.exe")
        self.assertEqual(update.asset_name("1.2.0", "zip", "win32"), "ReelForge-1.2.0-Windows.zip")
        self.assertEqual(update.asset_name("1.2.0", "zip", "darwin"), "ReelForge-1.2.0-macOS.zip")
        self.assertEqual(update.asset_name("1.2.0", "zip", "linux"), "ReelForge-1.2.0-Linux.tar.gz")

    def test_offline_check_is_calm(self):
        with mock.patch.object(update, "latest", side_effect=update.UpdateError("Couldn't reach GitHub (offline?)")):
            info = update.check()
        self.assertFalse(info["newer"])
        self.assertIn("offline", info["error"])

    def test_check_round_trips_to_a_release(self):
        rel = update.Release("9.0.0", "v9.0.0", "notes", assets={"ReelForge-9.0.0-Windows.zip": ("https://x/z", 10)})
        with mock.patch.object(update, "latest", return_value=rel):
            info = update.check()
        self.assertTrue(info["newer"])
        again = update.release_from(json.loads(json.dumps(info)))  # as the dashboard stores it
        self.assertEqual((again.version, again.assets), ("9.0.0", {"ReelForge-9.0.0-Windows.zip": ("https://x/z", 10)}))


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.root = self.dir / "ReelForge"
        self.root.mkdir()

    def test_install_kind(self):
        self.assertEqual(update.install_kind(self.root), "zip")
        (self.root / ".git").mkdir()
        self.assertEqual(update.install_kind(self.root), "git")
        (self.root / "unins000.exe").write_bytes(b"")
        self.assertEqual(update.install_kind(self.root), "installer")

    def test_kept_paths(self):
        for rel in ("my-studio/studio.toml", "episodes/ep01/episode.json", "completed videos/x/x.mp4", "CLAUDE.md",
                    "dashboard/data/stats.db", "dashboard/config.toml", ".venv/Scripts/python.exe", "tools/blender/b"):
            self.assertTrue(update.kept(rel), rel)
        for rel in ("dashboard/app.py", "dashboard/config.example.toml", "studio/__init__.py", "README.md"):
            self.assertFalse(update.kept(rel), rel)

    def test_zip_update_copies_kit_files_and_leaves_yours(self):
        mine = {"my-studio/studio.toml": "my settings", "CLAUDE.md": "my instructions",
                "dashboard/config.toml": "my handles", "episodes/ep01/episode.json": "{}"}
        for rel, text in {**mine, "studio/__init__.py": 'KIT_VERSION = "1.0.0"\n', "README.md": "old",
                          "bin/reelforge.cmd": "same launcher"}.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        launcher = self.root / "bin" / "reelforge.cmd"
        before = launcher.stat().st_mtime_ns
        archive = self.dir / "ReelForge-1.1.0-Windows.zip"
        with zipfile.ZipFile(archive, "w") as z:
            for rel, text in {"studio/__init__.py": 'KIT_VERSION = "1.1.0"\n', "README.md": "new",
                              "studio/new_module.py": "x = 1\n", "bin/reelforge.cmd": "same launcher",
                              "my-studio/studio.toml": "kit default", "CLAUDE.md": "bootstrap"}.items():
                z.writestr(f"ReelForge-1.1.0/{rel}", text)
        work = self.dir / "work"
        work.mkdir()
        update._copy_release(archive, self.root, work, lambda *a: None)
        self.assertEqual(update.read_version(self.root), "1.1.0")
        self.assertEqual((self.root / "README.md").read_text(encoding="utf-8"), "new")
        self.assertTrue((self.root / "studio" / "new_module.py").exists())
        for rel, text in mine.items():
            self.assertEqual((self.root / rel).read_text(encoding="utf-8"), text, rel)
        self.assertEqual(launcher.stat().st_mtime_ns, before)  # unchanged files aren't rewritten

    def test_something_else_is_refused(self):
        archive = self.dir / "other.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Other/readme.txt", "hi")
        work = self.dir / "work"
        work.mkdir()
        with self.assertRaises(update.UpdateError):
            update._copy_release(archive, self.root, work, lambda *a: None)

    def test_marker_is_read_once(self):
        update._write_marker(self.root, "1.0.0", "1.1.0")
        self.assertEqual(update.take_marker(self.root)["to"], "1.1.0")
        self.assertIsNone(update.take_marker(self.root))


if __name__ == "__main__":
    unittest.main()
