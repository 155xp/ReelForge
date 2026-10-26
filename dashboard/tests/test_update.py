"""The updater (studio.update): versions, how a copy was installed, and copying a new version over a folder."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
                    "dashboard/data/stats.db", "dashboard/config.toml", ".venv/Scripts/python.exe", "tools/blender/b",
                    "ui/node_modules/@opentui/core/package.json"):
            self.assertTrue(update.kept(rel), rel)
        for rel in ("dashboard/service.py", "ui/src/main.tsx", "ui/bun.lock", "studio/__init__.py", "README.md"):
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

    @unittest.skipIf(os.name == "nt", "file permissions are a macOS and Linux thing")
    def test_mac_zip_update_keeps_scripts_runnable(self):
        """ZipFile unpacks without permissions; the update gives the zip's executable files theirs back."""
        (self.root / "studio").mkdir()
        (self.root / "studio" / "__init__.py").write_text('KIT_VERSION = "1.0.0"\n', encoding="utf-8")
        (self.root / "setup.sh").write_text("old\n", encoding="utf-8")
        (self.root / "setup.sh").chmod(0o755)
        archive = self.dir / "ReelForge-1.1.0-macOS.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("ReelForge-1.1.0/studio/__init__.py", 'KIT_VERSION = "1.1.0"\n')
            z.writestr("ReelForge-1.1.0/README.md", "plain\n")
            for rel in ("setup.sh", "bin/reelforge"):
                info = zipfile.ZipInfo(f"ReelForge-1.1.0/{rel}")
                info.external_attr = 0o100755 << 16
                z.writestr(info, "#!/bin/sh\necho new\n")
        work = self.dir / "work"
        work.mkdir()
        update._copy_release(archive, self.root, work, lambda *a: None)
        for rel in ("setup.sh", "bin/reelforge"):
            self.assertTrue(os.access(self.root / rel, os.X_OK), rel)
        self.assertFalse(os.access(self.root / "README.md", os.X_OK))

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


@unittest.skipUnless(shutil.which("git"), "needs git")
class GitPullTest(unittest.TestCase):
    """A git clone that onboarding has written its CLAUDE.md and AGENTS.md into still updates."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.kit = self.dir / "kit"
        self.kit.mkdir()
        self.git(self.kit, "init", "-q")
        self.commit({"CLAUDE.md": "placeholder\n", "AGENTS.md": "placeholder\n", "README.md": "1.0\n"})
        self.git(self.dir, "clone", "-q", str(self.kit), "copy")
        self.copy = self.dir / "copy"

    def git(self, where: Path, *args: str) -> None:
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True, env=env)

    def commit(self, files: dict[str, str]) -> None:
        for rel, text in files.items():
            (self.kit / rel).write_text(text, encoding="utf-8")
        self.git(self.kit, "add", "-A")
        self.git(self.kit, "commit", "-q", "-m", "kit")

    def test_onboarded_files_are_kept(self):
        (self.copy / "CLAUDE.md").write_text("my channel\n", encoding="utf-8")
        (self.copy / "AGENTS.md").write_text("my channel\n", encoding="utf-8")
        self.commit({"README.md": "1.1\n", "CLAUDE.md": "new placeholder\n"})
        update._git_pull(self.copy, lambda *a: None)
        self.assertEqual((self.copy / "README.md").read_text(encoding="utf-8"), "1.1\n")
        self.assertEqual((self.copy / "CLAUDE.md").read_text(encoding="utf-8"), "my channel\n")
        self.assertEqual((self.copy / "AGENTS.md").read_text(encoding="utf-8"), "my channel\n")

    def test_other_changes_stop_it(self):
        (self.copy / "README.md").write_text("edited\n", encoding="utf-8")
        self.commit({"README.md": "1.1\n"})
        with self.assertRaises(update.UpdateError):
            update._git_pull(self.copy, lambda *a: None)
        self.assertEqual((self.copy / "README.md").read_text(encoding="utf-8"), "edited\n")


class WhatsNewTest(unittest.TestCase):
    NOTES = Path(__file__).resolve().parents[2] / ".github" / "release-notes.md"

    def test_the_updates_tab_shows_only_whats_new(self):
        from dashboard.service import whats_new

        shown = whats_new(self.NOTES.read_text(encoding="utf-8"))
        self.assertTrue(shown.startswith("## What's new in "))
        for gone in ("## Download", "| Your computer", "Already have ReelForge?", "---"):
            self.assertNotIn(gone, shown)
        self.assertEqual(whats_new("- one\r\n\r\nAlready have ReelForge? Update.\r\n---\r\nguide"), "- one")
        self.assertEqual(whats_new(""), "")

    def test_whats_new_is_short_and_says_first_time_setup(self):
        shown = self.NOTES.read_text(encoding="utf-8").split("\n---")[0]
        for word in ("onboarding", "ultracode"):
            self.assertNotIn(word, shown.lower())
        for line in shown.splitlines():
            self.assertLessEqual(len(line), 120, line)


if __name__ == "__main__":
    unittest.main()
