"""Regression coverage for approval reuse across captions, post-production and content substitutions."""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import make_episode
from studio import review, settings


class ContentBoundApproval(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.ep = self.root / "episodes" / "ep01_review"
        self.final = self.ep / "final"
        self.final.mkdir(parents=True)
        self.build = self.ep / "build"
        self.qa = self.build / "qa"
        self.qa.mkdir(parents=True)
        self.spec = {"id": "ep01_review", "title": "The reviewed hook", "hashtags": ["fyp", "space"]}
        self.s = copy.deepcopy(settings.DEFAULTS)
        (self.ep / "episode.json").write_text(json.dumps(self.spec), encoding="utf-8")
        (self.final / "ep01_review.mp4").write_bytes(b"reviewed encoded video with audio")
        (self.final / "cover.jpg").write_bytes(b"reviewed cover")
        patch = mock.patch.multiple(make_episode.config, SETTINGS=self.s, COMPLETED=self.root / "completed",
                                    MAX_HASHTAGS=5, PLATFORMS=self.s["platforms"]["enabled"], TIKTOK_FIRST_TAG="fyp")
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(settings, "load", return_value=self.s)
        patch.start()
        self.addCleanup(patch.stop)
        make_episode.write_captions(self.spec, self.final)
        self.write_qa()
        self.approve()

    def write_qa(self):
        # Synthetic media unit fixture: acceptance tests separately exercise real QA and renders.
        receipt = review.snapshot(self.ep)
        report = {"pass": True, "review_snapshot": receipt, "review_fingerprint": review.fingerprint(receipt)}
        (self.qa / "qa.json").write_text(json.dumps(report), encoding="utf-8")
        return report

    def approve(self):
        report = json.loads((self.qa / "qa.json").read_text(encoding="utf-8"))
        (self.qa / "review.md").write_text(
            f"Fixture review: picture, sound, cover, captions and inputs checked.\n"
            f"Review-SHA256: {report['review_fingerprint']}\nAPPROVED\n", encoding="utf-8")

    def deliver(self):
        make_episode.deliver(self.spec, self.final, self.build)

    def test_unchanged_review_delivers_the_exact_files_without_optional_editor(self):
        with mock.patch("studio.agentcut.executable", side_effect=AssertionError("optional editor invoked")):
            self.deliver()
        dst = make_episode.completed_dir(self.spec)
        for file in self.final.iterdir():
            self.assertEqual(file.read_bytes(), (dst / file.name).read_bytes())

    def test_title_then_caption_deliver_requires_qa_and_fresh_review(self):
        self.spec["title"] = "A changed hook"
        (self.ep / "episode.json").write_text(json.dumps(self.spec), encoding="utf-8")
        make_episode.write_captions(self.spec, self.final)
        with self.assertRaisesRegex(SystemExit, "fresh review"):
            self.deliver()
        self.write_qa()
        with self.assertRaisesRegex(SystemExit, "Review-SHA256"):
            self.deliver()
        self.approve()
        self.deliver()

    def test_postproduction_replacements_invalidate_even_with_same_size_and_timestamp(self):
        for name in ("ep01_review.mp4", "cover.jpg", "caption.txt", "caption_youtube.txt"):
            with self.subTest(name=name):
                path = self.final / name
                original = path.read_bytes()
                stat = path.stat()
                path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
                with self.assertRaisesRegex(SystemExit, "out of date"):
                    self.deliver()
                self.write_qa()
                with self.assertRaisesRegex(SystemExit, "Review-SHA256"):
                    self.deliver()
                path.write_bytes(original)
                self.write_qa()

    def test_adding_or_removing_delivery_artifacts_invalidates_review(self):
        extra = self.final / "caption_new.txt"
        extra.write_text("a newly added caption", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "out of date"):
            self.deliver()
        extra.unlink()
        (self.final / "cover.jpg").unlink()
        with self.assertRaisesRegex(SystemExit, "out of date"):
            self.deliver()

    def test_input_changes_require_review_even_before_outputs_are_regenerated(self):
        self.spec["audio"] = {"gain": 0.2}
        (self.ep / "episode.json").write_text(json.dumps(self.spec), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "out of date"):
            self.deliver()

    def test_caption_rule_changes_require_review(self):
        self.s["captions"]["hashtags_on_x"] = True
        with self.assertRaisesRegex(SystemExit, "out of date"):
            self.deliver()

    def test_old_unbound_approval_cannot_authorize_new_delivery(self):
        (self.qa / "review.md").write_text("APPROVED", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "Review-SHA256"):
            self.deliver()

    def test_change_during_delivery_preserves_completed_video(self):
        self.deliver()
        before = {p.name: p.read_bytes() for p in make_episode.completed_dir(self.spec).iterdir()}
        copy_file = make_episode.shutil.copy2

        def replace_while_copying(src, dst):
            if src.suffix == ".mp4":
                src.write_bytes(b"unreviewed video")
            return copy_file(src, dst)

        with mock.patch.object(make_episode.shutil, "copy2", side_effect=replace_while_copying):
            with self.assertRaisesRegex(SystemExit, "changed during delivery"):
                self.deliver()
        after = {p.name: p.read_bytes() for p in make_episode.completed_dir(self.spec).iterdir()}
        self.assertEqual(before, after)

    def test_cleaning_frames_does_not_invalidate_review(self):
        frames = self.build / "frames"
        frames.mkdir()
        (frames / "f_0001.jpg").write_bytes(b"retained frame")
        self.deliver()
        make_episode.clean(self.spec, self.build)
        self.deliver()


if __name__ == "__main__":
    unittest.main()
