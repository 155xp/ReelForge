"""Finished video discovery and saved paths after moving a channel between systems."""

import tempfile
import unittest
from pathlib import Path

from dashboard import db, demo, videos
from dashboard.tests.window import Window, plain


class PublishFiles(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(self.root / "stats.db")
        self.cfg = {"refresh_minutes": 0, "videos_dir": str(self.root / "videos"),
                    "episodes_dir": str(self.root / "episodes"), "completed_dir": str(self.root / "completed")}

    def window(self):
        w = Window(self.cfg, demo.platforms(), tab="publish")
        self.addCleanup(w.close)
        return w

    def test_only_files_are_discovered_in_every_video_folder(self):
        expected = set()
        for folder in (self.root / "videos", self.root / "episodes" / "ep01" / "final",
                       self.root / "completed" / "ep02"):
            folder.mkdir(parents=True)
            real = folder / f"{folder.parent.name}.MP4"
            real.write_bytes(b"video")
            expected.add(real.resolve())
            for ext in ("mp4", "mov", "m4v"):
                (folder / f"directory.{ext}").mkdir()
        self.assertEqual(set(videos.find(self.cfg)), expected)

    def test_windows_paths_keep_posted_marks_and_upload_matches(self):
        eid = db.create_episode("A video", r"C:\Users\me\episodes\ep01\final\ep01.mp4")
        db.add_post("youtube", "post-1", eid, "A video", "https://example.invalid/post")
        db.log_upload("youtube", "ep01.mp4", "manual")
        w = self.window()
        self.assertEqual(w.svc.posted_platforms(), {"ep01.mp4": {"youtube"}})
        w.svc.update_uploads()
        rendered = str(w.view("uploads"))
        self.assertIn("live", rendered)
        self.assertNotIn("not spotted yet", rendered)

    def test_windows_hidden_paths_stay_hidden_after_a_move(self):
        folder = self.root / "videos"
        folder.mkdir()
        (folder / "ep01.mp4").write_bytes(b"video")
        db.set_meta("hidden_videos", [r"C:\Users\me\videos\ep01.mp4"])
        w = self.window()
        self.assertEqual(w.view("files")["items"], [])
        w.call("show_file", "ep01.mp4")
        self.assertTrue(any("hidden" in t for t in w.toasts()))
        self.assertIn("Show 1 hidden", plain(w.view("files")["heading"]))
