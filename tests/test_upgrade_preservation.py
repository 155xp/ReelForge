"""The released updater's regeneration command must preserve existing user settings."""
import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from studio import __main__ as cli
from studio import dashboard_config, generate, paths, profiles, settings


class UpgradePreservation(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "dashboard").mkdir()
        shutil.copyfile(paths.DASHBOARD / "config.example.toml", self.root / "dashboard/config.example.toml")
        for target, values in ((profiles, {"ROOT": self.root, "FOLDER": self.root / "profiles"}),
                               (paths, {"ROOT": self.root, "DASHBOARD": self.root / "dashboard"})):
            patch = mock.patch.multiple(target, **values)
            patch.start()
            self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ, {"REELFORGE_PROFILE": ".", "STUDIO_DRY_SYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)
        self.channels = [profiles.main(), profiles.create("Second channel")]
        for p in self.channels:
            generate.write_all({"channel_name": p.name, "about": "Fixture channel", "assistant": ["codex"],
                                "handle_youtube": "@original", "background_stats": False}, p)

    def test_actual_released_updater_command_preserves_hand_edits_and_accounts(self):
        before = {}
        for p in self.channels:
            saved = settings.load(p.settings)
            saved["sound"]["target_lufs"] = -24.0
            saved["video"]["backend"] = "blender"
            p.settings.write_text(settings.dump_toml(saved))
            dashboard_config.set_handle("youtube", "@hand_edited", target=p.config)
            (p.my_studio / "brief.md").write_text("Handwritten notes, keep exactly.\n")
            for file in (p.settings, p.answers, p.config, p.my_studio / "brief.md", p.bible):
                before[file] = file.read_bytes()
        with redirect_stdout(io.StringIO()), \
                mock.patch("studio.move.finish_leftover"), mock.patch("studio.reset.finish_pending", return_value=None):
            # Exactly the command embedded in the latest published Mac package.
            self.assertEqual(cli.main(["onboard", "--regenerate"]), 0)
        for file, data in before.items():
            self.assertEqual(file.read_bytes(), data, str(file))
        for p in self.channels:
            guide = (p.folder / "AGENTS.md").read_text()
            self.assertIn("-24", guide)
            self.assertIn("@hand_edited", guide)
            self.assertIn("default is **AI Blender scenes**", guide)

    def test_explicit_channel_regeneration_still_applies_edited_answers(self):
        p = self.channels[0]
        answers = json.loads(p.answers.read_text())
        answers["channel_name"] = "Explicitly changed"
        p.answers.write_text(json.dumps(answers))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.onboard(["--regenerate"]), 0)
        self.assertEqual(settings.load(p.settings)["channel"]["name"], "Explicitly changed")

    def test_future_updater_flag_preserves_settings(self):
        p = self.channels[0]
        p.settings.write_text(p.settings.read_text().replace("target_lufs = -25.5", "target_lufs = -23.0"))
        before = p.settings.read_bytes()
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.onboard(["--regenerate", "--preserve-settings"]), 0)
        self.assertEqual(p.settings.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
