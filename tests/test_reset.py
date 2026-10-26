"""Factory reset and uninstall (studio/reset.py), in a scratch ReelForge folder: what each moves and where, that videos
are kept and nothing is deleted, the name you type, a git copy refusing to uninstall, and the window asking for
either (the launcher does it). The Settings tab itself is tested in ui/test/settings.test.tsx."""

import io
import json
import os
import re
from contextlib import redirect_stdout
from unittest import mock

from studio import generate, profiles, reset
from studio import paths as P

from test_profiles import ANSWERS, Scratch


class ResetScratch(Scratch):
    def setUp(self):
        super().setUp()
        for name, value in (("ROOT", self.root), ("PENDING", self.root / ".reelforge-pending.json"),
                            ("BACKUPS", self.root / "backups")):
            patch = mock.patch.object(reset, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        os.environ["STUDIO_DRY_SYSTEM"] = "1"   # never the real PATH, scheduler, icon or Windows Terminal
        self.onboard_main()
        with redirect_stdout(io.StringIO()):
            self.second = profiles.create("Cool Epic Facts")
            generate.write_all({**ANSWERS, "channel_name": "Cool Epic Facts"}, self.second)
        self.write("dashboard/data/stats.db", "stats")
        self.write("dashboard/data/browser/Cookies", "log-in")
        self.write("episodes/ep01_duck/final/ep01_duck.mp4", "video")
        self.write("episodes/.gitkeep", "")
        self.write("completed videos/ep01_duck - Duck/ep01_duck.mp4", "video")
        self.write("profiles/cool-epic-facts/episodes/ep01_a/final/ep01_a.mp4", "video 2")
        self.write("research/README.md", "the kit's own")
        self.write("research/ideas.md", "your AI's")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def quiet(self, fn, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs)


class FactoryReset(ResetScratch):
    def test_settings_logins_and_stats_go_to_a_backup_and_the_videos_stay(self):
        done = self.quiet(reset.factory_reset)
        self.assertEqual(done.problems, [])
        backup = done.where
        self.assertEqual(backup.parent, self.root / "backups")
        for rel in ("my-studio/answers.json", "dashboard/config.toml", "dashboard/data/stats.db",
                    "dashboard/data/browser/Cookies", "profiles/cool-epic-facts/episodes/ep01_a/final/ep01_a.mp4",
                    "CLAUDE.md", "AGENTS.md", "research/ideas.md"):
            self.assertTrue((backup / rel).is_file(), rel)
        for rel in ("my-studio", "dashboard/data", "dashboard/config.toml", "profiles", "research/ideas.md"):
            self.assertFalse((self.root / rel).exists(), rel)
        self.assertTrue((self.root / "episodes/ep01_duck/final/ep01_duck.mp4").is_file())
        self.assertTrue((self.root / "completed videos/ep01_duck - Duck/ep01_duck.mp4").is_file())
        self.assertTrue((self.root / "research/README.md").is_file())
        self.assertTrue((backup / "README.txt").is_file())
        # until first-time setup runs again, your AI's notes say what happened (and first-time setup replaces them)
        note = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(generate.BOOTSTRAP_MARK, note)
        self.assertIn(f"backups/{backup.name}", note)
        self.assertFalse(profiles.main().onboarded)
        self.assertEqual(profiles.every(), [profiles.main()])

    def test_a_second_reset_leaves_the_bootstrap_notes_where_they_are(self):
        self.quiet(reset.factory_reset)
        items = [p.name for p, _ in reset.reset_items()]
        self.assertNotIn("CLAUDE.md", items)
        self.assertNotIn("AGENTS.md", items)

    def test_the_window_asks_and_the_launcher_does_it_then_first_time_setup(self):
        reset.request("reset")
        self.assertEqual(reset.pending()["do"], "reset")
        self.assertIsNone(self.quiet(reset.finish_pending))   # None: carry on opening ReelForge
        self.assertIsNone(reset.pending())
        self.assertFalse(profiles.main().onboarded)

    def test_a_reset_that_cant_move_something_stops_and_tries_again_next_time(self):
        reset.request("reset")
        with mock.patch.object(reset, "_move", return_value="in use"):
            self.assertEqual(self.quiet(reset.finish_pending), 1)
        self.assertIsNotNone(reset.pending())

    def test_the_confirmation_is_the_channels_name_in_any_case(self):
        self.assertTrue(reset.matches("night  PHYSICS "))
        self.assertFalse(reset.matches("Night"))
        self.assertFalse(reset.matches(""))


class Uninstall(ResetScratch):
    def test_it_says_what_goes_and_where_the_videos_go(self):
        info = reset.uninstall_info()
        self.assertEqual(info["keep_to"], str(reset.keep_folder()))
        self.assertEqual(reset.keep_folder().parent, self.root.parent)
        self.assertEqual([c["name"] for c in info["channels"]], ["Night Physics", "Cool Epic Facts"])
        self.assertIn("episodes", info["channels"][0]["folders"])
        self.assertEqual(info["word"], "Night Physics")
        self.assertFalse(info["git"])

    def test_videos_are_kept_before_the_folder_goes_to_the_bin(self):
        binned = []
        keep = reset.keep_folder()
        self.addCleanup(lambda: __import__("shutil").rmtree(keep, ignore_errors=True))
        with mock.patch.object(reset, "bin_folder", side_effect=lambda kept, say=print: binned.append(kept)):
            done = self.quiet(reset.uninstall, True)
        self.assertEqual(done.problems, [])
        self.assertEqual(binned, [keep])
        self.assertTrue((keep / "Night Physics/episodes/ep01_duck/final/ep01_duck.mp4").is_file())
        self.assertTrue((keep / "Night Physics/completed videos/ep01_duck - Duck/ep01_duck.mp4").is_file())
        self.assertTrue((keep / "Night Physics/my-studio/answers.json").is_file())
        self.assertTrue((keep / "Cool Epic Facts/episodes/ep01_a/final/ep01_a.mp4").is_file())
        self.assertFalse((self.root / "episodes/ep01_duck").exists())
        self.assertTrue((self.root / "dashboard/data/stats.db").is_file())   # goes to the bin with the folder

    def test_a_video_that_cant_be_moved_out_keeps_the_folder_out_of_the_bin(self):
        binned = []
        with mock.patch.object(reset, "_move", return_value="in use"), \
                mock.patch.object(reset, "bin_folder", side_effect=lambda kept, say=print: binned.append(kept)):
            done = self.quiet(reset.uninstall, True)
        self.assertTrue(done.problems)
        self.assertEqual(binned, [])

    def test_videos_outside_the_folder_are_left_where_they_are(self):
        outside = self.root.parent / f"{self.root.name}-elsewhere"
        outside.mkdir()
        self.addCleanup(outside.rmdir)
        cfg = profiles.main().config
        text = re.sub(r"(?m)^videos_dir\s*=.*$", "", cfg.read_text(encoding="utf-8"))
        cfg.write_text(f"videos_dir = {json.dumps(str(outside))}\n" + text, encoding="utf-8")
        plan = reset.keep_plan()
        self.assertIn(outside.resolve(), plan[0].outside)
        self.assertNotIn(outside.resolve(), plan[0].folders)

    def test_a_git_copy_isnt_uninstalled_from_inside(self):
        (self.root / ".git").mkdir()
        with mock.patch.object(reset, "uninstall") as un:
            self.assertEqual(self.quiet(reset.uninstall_main, ["--yes"]), 2)
        un.assert_not_called()

    def test_the_window_asks_and_the_launcher_does_it(self):
        reset.request("uninstall", keep=False)
        with mock.patch.object(reset, "uninstall", return_value=reset.Done()) as un:
            self.assertEqual(self.quiet(reset.finish_pending), 0)
        un.assert_called_once_with(False)
        self.assertIsNone(reset.pending())

    def test_a_test_copy_leaves_the_computer_alone(self):
        self.assertTrue(P.dry_system())
        with mock.patch("studio.stats_schedule.disable") as off, mock.patch("studio.command.disable") as cmd:
            self.assertEqual(self.quiet(reset.system_off), [])
        off.assert_not_called()
        cmd.assert_not_called()
