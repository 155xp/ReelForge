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


if __name__ == "__main__":
    unittest.main()
