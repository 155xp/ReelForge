"""Onboarding's files (studio.generate.write_all), written into a scratch folder instead of this kit."""

import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from studio import generate
from studio import paths as P


class WriteAll(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        mine = root / "my-studio"
        for name, value in {"ROOT": root, "MY_STUDIO": mine, "ANSWERS": mine / "answers.json",
                            "SETTINGS": mine / "studio.toml", "BIBLE": mine / "channel-bible.md",
                            "BACKUPS": mine / "backups", "COMPLETED": root / "completed videos",
                            "DASHBOARD": root / "dashboard"}.items():
            patch = mock.patch.object(P, name, value)
            patch.start()
            self.addCleanup(patch.stop)

    def created(self) -> str:
        return tomllib.loads(P.SETTINGS.read_text(encoding="utf-8"))["studio"]["created"]

    def test_created_date_when_the_answers_file_is_the_input(self):
        # Onboarding in the chat writes my-studio/answers.json, then reads that same file back in: no date yet.
        answers = {"channel_name": "Test Channel", "about": "What-if videos with real science.", "creator": "Sam"}
        P.MY_STUDIO.mkdir()
        P.ANSWERS.write_text(json.dumps(answers), encoding="utf-8")
        generate.write_all(answers)
        self.assertRegex(self.created(), r"^\d{4}-\d\d-\d\d$")
        self.assertEqual(json.loads(P.ANSWERS.read_text(encoding="utf-8"))["_created"], self.created())
        # a later run keeps the first date
        P.ANSWERS.write_text(json.dumps({**answers, "_created": "2026-01-02"}), encoding="utf-8")
        generate.write_all(answers)
        self.assertEqual(self.created(), "2026-01-02")

    def test_an_older_versions_answers_lose_ultracode_and_quality(self):
        # What 1.0.5 saved: its Quality step's answer (Max was its default) and "Use ultracode for video runs?"; 1.0.6
        # kept the first. Your AI app decides how hard it works now (the Settings tab's FAQ), so neither is kept.
        answers = {"channel_name": "Test Channel", "about": "What-if videos with real science.", "creator": "Sam",
                   "quality": "max", "ultracode": True}
        generate.write_all(answers)
        saved = json.loads(P.ANSWERS.read_text(encoding="utf-8"))
        self.assertNotIn("ultracode", saved)
        self.assertNotIn("quality", saved)
        settings = P.SETTINGS.read_text(encoding="utf-8")
        self.assertEqual(tomllib.loads(settings)["ai"], {"assistant": "claude"})
        for text in (settings, (P.ROOT / "CLAUDE.md").read_text(encoding="utf-8")):
            self.assertNotIn("ultracode", text.lower())
            self.assertNotIn("reasons:", text)


class ClaudeSettings(unittest.TestCase):
    """First-time setup's start for Claude Code in the folder (.claude/settings.local.json): Opus at high effort, only
    where the file doesn't name a model or an effort, and nothing at all for Codex."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        patch = mock.patch.object(P, "ROOT", Path(tmp.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.path = Path(tmp.name) / ".claude" / "settings.local.json"

    def write(self, assistant="claude"):
        return generate.write_claude_settings({"ai": {"assistant": assistant}})

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_a_new_folder_gets_opus_at_high_effort(self):
        self.assertEqual(self.write(), self.path)
        self.assertEqual(self.read(), {"model": "opus", "effortLevel": "high"})

    def test_only_what_the_file_doesnt_name_already_is_added(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "model": "sonnet"}), encoding="utf-8")
        self.write()
        self.assertEqual(self.read(), {"permissions": {"allow": ["Bash(ls)"]}, "model": "sonnet",
                                       "effortLevel": "high"})
        self.path.write_text(json.dumps({"env": {"CLAUDE_CODE_EFFORT_LEVEL": "max"}}), encoding="utf-8")
        self.write()
        self.assertEqual(self.read(), {"env": {"CLAUDE_CODE_EFFORT_LEVEL": "max"}, "model": "opus"})
        before = json.dumps({"model": "opus", "effortLevel": "xhigh"})
        self.path.write_text(before, encoding="utf-8")
        self.assertIsNone(self.write())
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_a_file_it_cant_read_is_kept_beside_the_new_one(self):
        self.path.parent.mkdir()
        self.path.write_text("{not json", encoding="utf-8")
        self.write()
        self.assertEqual(self.read(), {"model": "opus", "effortLevel": "high"})
        self.assertEqual(self.path.with_suffix(".json.bak").read_text(encoding="utf-8"), "{not json")

    def test_codex_gets_none(self):
        self.assertIsNone(self.write("codex"))
        self.assertFalse(self.path.exists())
        self.write("both")
        self.assertTrue(self.path.exists())

if __name__ == "__main__":
    unittest.main()
