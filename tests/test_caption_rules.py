"""A channel can turn hashtags off without blocking new episodes or publishing."""

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from pipeline import make_episode, qa
from studio import generate, paths, profiles, publish_check, questions, settings
from studio.__main__ import new_episode


class CaptionRules(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.final = self.root / "episodes" / "ep01_test" / "final"
        self.final.mkdir(parents=True)
        self.spec = {"id": "ep01_test", "title": "What if the Moon stopped moving?", "hashtags": []}
        self.settings = copy.deepcopy(settings.DEFAULTS)

    def configure(self, maximum):
        self.settings["captions"]["max_hashtags"] = maximum
        patch = mock.patch.multiple(make_episode.config, SETTINGS=self.settings, MAX_HASHTAGS=maximum,
                                    PLATFORMS=self.settings["platforms"]["enabled"], TIKTOK_FIRST_TAG="fyp")
        patch.start()
        self.addCleanup(patch.stop)

    def write_captions(self):
        with redirect_stdout(io.StringIO()):
            make_episode.write_captions(self.spec, self.final)

    def caption_report(self):
        report = qa.Report()
        qa.check_captions(self.spec, self.final, report)
        return report

    def publish_check(self):
        episode = self.final.parent
        (episode / "episode.json").write_text(json.dumps(self.spec), encoding="utf-8")
        video = self.final / "ep01_test.mp4"
        video.write_bytes(b"video already checked by QA")
        qa_dir = episode / "build" / "qa"
        qa_dir.mkdir(parents=True)
        st = video.stat()
        (qa_dir / "qa.json").write_text(json.dumps({"pass": True,
                                                   "fingerprint": f"{st.st_size}:{int(st.st_mtime)}"}),
                                        encoding="utf-8")
        (qa_dir / "review.md").write_text("APPROVED", encoding="utf-8")
        with mock.patch.object(profiles, "of", return_value=profiles.Profile(self.root)), \
                mock.patch.object(profiles, "use"), mock.patch.object(settings, "load", return_value=self.settings), \
                mock.patch.object(publish_check, "_dashboard_listing", return_value=None):
            return publish_check.check(episode)

    def test_new_episode_drops_example_hashtags_when_the_maximum_is_zero(self):
        self.settings["captions"]["max_hashtags"] = 0
        with mock.patch.object(paths, "EPISODES", self.root / "new-episodes"), \
                mock.patch.object(settings, "load", return_value=self.settings), redirect_stdout(io.StringIO()):
            self.assertEqual(new_episode(["test"]), 0)
        spec = json.loads(next((self.root / "new-episodes").glob("*/episode.json")).read_text(encoding="utf-8"))
        self.assertEqual(spec["hashtags"], [])

    def test_new_episode_preserves_copied_tags_when_enabled_and_defaults_are_empty(self):
        self.settings["captions"]["default_tags"] = []
        prior = self.root / "new-episodes" / "ep01_previous"
        prior.mkdir(parents=True)
        spec = json.loads((paths.EXAMPLES / "demo_doubling_duck" / "episode.json").read_text(encoding="utf-8"))
        spec["hashtags"] = ["fyp", "custom"]
        (prior / "episode.json").write_text(json.dumps(spec), encoding="utf-8")
        with mock.patch.object(paths, "EPISODES", self.root / "new-episodes"), \
                mock.patch.object(settings, "load", return_value=self.settings), redirect_stdout(io.StringIO()):
            self.assertEqual(new_episode(["test", "--from", "ep01_previous"]), 0)
        spec = json.loads((prior.parent / "ep02_test" / "episode.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["hashtags"], ["fyp", "custom"])

    def test_zero_hashtag_guides_and_settings_do_not_require_a_first_tag(self):
        from dashboard.settings_tab import _channel_rows

        answers, problems = questions.validate({"channel_name": "Test Channel", "about": "Science videos", "assistant": "codex",
                                                "max_hashtags": 0})
        self.assertEqual(problems, [])
        s = generate.settings_from(answers)
        for template in ("context.md.j2", "channel-bible.md.j2"):
            text = generate.render(template, generate.context(answers, s, "codex"))
            self.assertNotIn("#fyp", text)
            self.assertNotIn("caption + hashtags", text)
        self.assertEqual(dict(_channel_rows(s))["Captions"], "no hashtags")

    def test_zero_hashtag_captions_contain_only_the_hook(self):
        self.configure(0)
        self.write_captions()
        for name in ("caption.txt", *(f"caption_{p}.txt" for p in settings.PLATFORMS)):
            self.assertEqual((self.final / name).read_text(encoding="utf-8"), self.spec["title"] + "\n")

    def test_default_captions_keep_tiktoks_first_tag_and_no_tags_on_x(self):
        self.configure(5)
        self.spec["hashtags"] = ["physics", "whatif"]
        self.write_captions()
        self.assertEqual((self.final / "caption_tiktok.txt").read_text(encoding="utf-8"),
                         self.spec["title"] + " #fyp #physics #whatif\n")
        self.assertEqual((self.final / "caption_x.txt").read_text(encoding="utf-8"), self.spec["title"] + "\n")

    def test_caption_generation_still_rejects_tags_over_the_maximum(self):
        for maximum in (0, 1):
            with self.subTest(maximum=maximum):
                self.configure(maximum)
                self.spec["hashtags"] = ["fyp", "physics"]
                with self.assertRaisesRegex(SystemExit, "maximum"):
                    self.write_captions()

    def test_caption_generation_still_requires_room_for_tiktoks_first_tag(self):
        self.configure(1)
        self.spec["hashtags"] = ["physics"]
        with self.assertRaisesRegex(SystemExit, "TikTok needs #fyp"):
            self.write_captions()

    def test_publish_check_accepts_no_tags_when_the_maximum_is_zero(self):
        self.configure(0)
        (self.final / "caption.txt").write_text(self.spec["title"] + "\n", encoding="utf-8")
        ok, report = self.publish_check()
        self.assertTrue(ok, report)

    def test_publish_check_still_requires_tags_when_enabled(self):
        self.configure(5)
        (self.final / "caption.txt").write_text(self.spec["title"] + "\n", encoding="utf-8")
        ok, report = self.publish_check()
        self.assertFalse(ok)
        self.assertIn("FAIL  hashtags", report)

    def test_qa_accepts_hook_only_captions_when_the_maximum_is_zero(self):
        self.configure(0)
        for name in ("caption.txt", *(f"caption_{p}.txt" for p in settings.PLATFORMS)):
            (self.final / name).write_text(self.spec["title"] + "\n", encoding="utf-8")
        report = self.caption_report()
        self.assertTrue(report.passed, report.checks)

    def test_qa_keeps_the_default_caption_rules(self):
        self.configure(5)
        self.spec["hashtags"] = ["fyp", "physics"]
        self.write_captions()
        self.assertTrue(self.caption_report().passed)
        (self.final / "caption_tiktok.txt").write_text(self.spec["title"] + " #physics\n", encoding="utf-8")
        self.assertFalse(self.caption_report().passed)

    def test_qa_rejects_tags_when_the_maximum_is_zero(self):
        self.configure(0)
        for name in ("caption.txt", *(f"caption_{p}.txt" for p in settings.PLATFORMS)):
            (self.final / name).write_text(self.spec["title"] + "\n", encoding="utf-8")
        (self.final / "caption_tiktok.txt").write_text(self.spec["title"] + " #fyp\n", encoding="utf-8")
        self.assertFalse(self.caption_report().passed)

    def test_qa_rejects_more_tags_than_the_positive_maximum(self):
        self.configure(1)
        self.spec["hashtags"] = ["fyp"]
        self.write_captions()
        (self.final / "caption_tiktok.txt").write_text(self.spec["title"] + " #fyp #physics\n", encoding="utf-8")
        self.assertFalse(self.caption_report().passed)
