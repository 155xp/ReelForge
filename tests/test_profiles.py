"""Profiles, one for each channel (studio/profiles.py), in a scratch ReelForge folder: making and finding them, the
files each one's settings and data go to, onboarding a new one (and what it tells your AI), the hourly job reading
every one, the video pipeline following an episode's folder, and the -p option. The profile button and switching in
the window are tested in ui/test/dashboard.test.tsx."""

import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest import mock

from dashboard import config
from studio import dashboard_config, generate, profiles
from studio import paths as P
from studio import settings as S
from studio.bridge import Loop
from studio.setup_service import Setup

KIT = Path(__file__).resolve().parent.parent
ANSWERS = {"creator": "Sam", "channel_name": "Night Physics", "about": "What-if videos with real science.",
           "platforms": ["tiktok", "youtube"], "handle_tiktok": "@nightphysics"}


class Scratch(unittest.TestCase):
    """A ReelForge folder of its own: studio.profiles, studio.paths and the dashboard's settings pointed at a scratch
    folder (with the kit's dashboard settings example), and no profile chosen."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / "dashboard").mkdir()
        shutil.copy(KIT / "dashboard" / "config.example.toml", self.root / "dashboard" / "config.example.toml")
        for target, name, value in ((profiles, "ROOT", self.root), (profiles, "FOLDER", self.root / "profiles"),
                                    (P, "ROOT", self.root), (P, "DASHBOARD", self.root / "dashboard"),
                                    (config, "APP_DIR", self.root / "dashboard")):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(profiles.ENV, None)

    def onboard_main(self, **more) -> None:
        with redirect_stdout(io.StringIO()):
            generate.write_all({**ANSWERS, **more})


class Finding(Scratch):
    def test_the_first_profile_is_the_reelforge_folder_itself(self):
        main = profiles.main()
        self.assertEqual(profiles.every(), [main])
        self.assertEqual((main.key, main.main, main.name), (".", True, "My channel"))
        self.assertFalse(profiles.several())
        self.assertEqual(profiles.current(), main)
        self.onboard_main()
        self.assertEqual(main.name, "Night Physics")
        self.assertEqual(main.slug, "night-physics")

    def test_new_profiles_get_their_own_folders_and_come_after_the_first(self):
        a = profiles.create("Cool Epic Facts!")
        b = profiles.create("Cool Epic Facts!")
        self.assertEqual(a.folder, self.root / "profiles" / "cool-epic-facts")
        self.assertEqual(b.folder.name, "cool-epic-facts-2")
        self.assertEqual((a.key, a.name, a.main), ("profiles/cool-epic-facts", "Cool Epic Facts!", False))
        self.assertEqual(profiles.every(), [profiles.main(), a, b])
        self.assertEqual(profiles.get("profiles/cool-epic-facts"), a)
        self.assertEqual(profiles.get(str(a.folder)), a)
        self.assertEqual(profiles.get("."), profiles.main())
        self.assertIsNone(profiles.get("profiles/nothing-here"))

    def test_a_profile_by_number_name_short_name_or_start(self):
        self.onboard_main()
        a = profiles.create("Cool Epic Facts")
        b = profiles.create("Tiny Worlds")
        self.assertEqual(profiles.find("1"), profiles.main())
        self.assertEqual(profiles.find("3"), b)
        self.assertIsNone(profiles.find("4"))
        self.assertEqual(profiles.find("cool epic facts"), a)
        self.assertEqual(profiles.find("tiny-worlds"), b)
        self.assertEqual(profiles.find("Night"), profiles.main())
        self.assertEqual(profiles.find("cool"), a)
        self.assertIsNone(profiles.find("nope"))
        profiles.create("Cool Cats")
        self.assertIsNone(profiles.find("cool"))  # two start that way
        self.assertEqual(profiles.taken("TINY WORLDS"), b)
        self.assertIsNone(profiles.taken("Tiny Worlds", but=b))

    def test_the_profile_a_file_is_in(self):
        a = profiles.create("Cool Epic Facts")
        self.assertEqual(profiles.of(a.episodes / "ep01_volcano"), a)
        self.assertEqual(profiles.of(self.root / "episodes" / "ep01_duck"), profiles.main())
        self.assertEqual(profiles.of(self.root / "profiles" / "not-one" / "episodes"), profiles.main())

    def test_the_window_opens_on_the_one_it_showed_last(self):
        profiles.remember(profiles.main())  # only the first: nothing to remember, nothing written
        self.assertFalse((self.root / "profiles").exists())
        a = profiles.create("Cool Epic Facts")
        profiles.remember(a)
        self.assertEqual(profiles.last(), a)
        shutil.rmtree(a.folder)
        self.assertEqual(profiles.last(), profiles.main())


class Paths(Scratch):
    def test_each_profile_has_its_own_settings_and_data(self):
        main = profiles.main()
        self.assertEqual(P.SETTINGS, self.root / "my-studio" / "studio.toml")
        self.assertEqual(config.CONFIG_PATH, self.root / "dashboard" / "config.toml")
        self.assertEqual(config.DB_PATH, self.root / "dashboard" / "data" / "stats.db")
        self.assertEqual(dashboard_config.config_toml(), self.root / "dashboard" / "config.toml")
        a = profiles.create("Cool Epic Facts")
        profiles.use(a)
        self.assertEqual(os.environ[profiles.ENV], "profiles/cool-epic-facts")
        self.assertEqual(P.PROFILE, a)
        self.assertEqual(P.SETTINGS, a.folder / "my-studio" / "studio.toml")
        self.assertEqual(P.EPISODES, a.folder / "episodes")
        self.assertEqual(P.COMPLETED, a.folder / "completed videos")
        self.assertEqual(config.CONFIG_PATH, a.folder / "dashboard" / "config.toml")
        self.assertEqual(config.DATA_DIR, a.folder / "dashboard" / "data")
        self.assertEqual(config.TOKENS_PATH, a.folder / "dashboard" / "data" / "tokens.json")
        self.assertEqual(config.resolve("videos"), a.folder / "dashboard" / "videos")
        self.assertEqual(config.episodes_dir({}), a.folder / "episodes")
        self.assertEqual(dashboard_config.config_toml(), a.config)
        self.assertEqual(dashboard_config.config_toml(main), self.root / "dashboard" / "config.toml")
        from dashboard.platforms import browser
        self.assertEqual(browser.profile_dir(), a.folder / "dashboard" / "data" / "browser")
        cfg = config.load_config()  # a new profile's settings start from the example
        self.assertTrue(a.config.exists())
        self.assertEqual(cfg["tiktok"], {"handle": ""})
        config.set_token("browser:x", {"since": 1})
        self.assertTrue((a.data / "tokens.json").exists())
        self.assertFalse((self.root / "dashboard" / "data" / "tokens.json").exists())


class Onboarding(Scratch):
    def test_a_new_profile_is_written_into_its_folder_and_listed_in_the_first_ones_notes(self):
        self.onboard_main()
        claude = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertNotIn("Other channels", claude)
        a = profiles.create("Cool Epic Facts")
        with redirect_stdout(io.StringIO()):
            written = generate.write_all({**ANSWERS, "channel_name": "Cool Epic Facts", "handle_tiktok": "@cool",
                                          "handle_youtube": "@coolyt"}, a)
        self.assertIn(a.folder / "CLAUDE.md", written)
        self.assertTrue(a.answers.exists() and a.settings.exists() and a.bible.exists())
        self.assertTrue((a.completed / "production-log.md").exists())
        self.assertEqual(S.load(a.settings)["channel"]["name"], "Cool Epic Facts")
        self.assertEqual(dashboard_config.handles(a), {"tiktok": "@cool", "youtube": "@coolyt", "instagram": "",
                                                       "x": ""})
        self.assertEqual(dashboard_config.handles(profiles.main())["tiktok"], "@nightphysics")  # untouched
        notes = (a.folder / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("one of several channels in this ReelForge folder", notes)
        self.assertIn(f"profiles{os.sep}cool-epic-facts{os.sep}episodes{os.sep}<id>", notes)
        self.assertIn("-m studio -p cool-epic-facts new-episode <slug>", notes)
        self.assertIn("`profiles/cool-epic-facts/completed videos/production-log.md`", notes)
        self.assertNotIn(".claude", [p.name for p in a.folder.iterdir()])
        claude = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("## Other channels in this folder", claude)
        self.assertIn("**Cool Epic Facts**: `profiles/cool-epic-facts/`", claude)
        self.assertEqual(S.load()["channel"]["name"], "Night Physics")  # the first profile's own settings stay

    def test_the_first_profiles_notes_are_as_they_were_without_others(self):
        self.onboard_main()
        before = (self.root / "CLAUDE.md").read_text(encoding="utf-8")
        a = profiles.create("Cool Epic Facts")
        generate.write_guides(profiles.main())
        self.assertIn("Other channels", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        shutil.rmtree(a.folder)
        generate.write_guides(profiles.main())
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), before)

    def test_the_interview_makes_a_new_profile_from_your_answers_about_you(self):
        self.onboard_main(quality="high")
        svc = Setup(Loop(out=io.StringIO()))
        init = svc.start({"start": "onboard", "new": True, "embedded": True})
        self.assertTrue(init["new"])
        start = svc.onboard_start()
        self.assertEqual((start["side"], start["create"]), ("Set up a new channel", "Create the profile"))
        self.assertEqual((svc.answers["creator"], svc.answers["quality"]), ("Sam", "high"))  # about you: carried
        self.assertNotIn("channel_name", svc.answers)                                       # the channel: not
        svc.onboard_step(1)
        bad = svc.onboard_next({"channel_name": "night physics", "about": "Facts."})
        self.assertFalse(bad["ok"])
        self.assertIn("already have a profile called Night Physics", bad["errors"]["channel_name"])
        self.assertFalse((self.root / "profiles").exists())
        svc.answers.update(channel_name="Cool Epic Facts", about="Mind-blowing facts.", platforms=["tiktok"])
        with mock.patch.object(svc.loop, "run_worker"):
            self.assertEqual(svc.onboard_create(), {"ok": True})
            made = profiles.find("Cool Epic Facts")
            self.assertEqual(made.folder, self.root / "profiles" / "cool-epic-facts")
            self.assertTrue((made.folder / "CLAUDE.md").exists())
            done = svc.done_info()
        self.assertEqual(done["profile"], "profiles/cool-epic-facts")
        self.assertEqual(done["open"], "Open Cool Epic Facts")
        self.assertEqual(done["back"], "Back to Night Physics")
        self.assertIn('make my first Cool Epic Facts video', json.dumps(done["steps"]))


class Job(Scratch):
    def test_the_hourly_job_reads_every_profile_in_a_process_of_its_own(self):
        from dashboard import __main__ as dash

        self.onboard_main()
        a = profiles.create("Cool Epic Facts")
        b = profiles.create("Quiet One")
        with redirect_stdout(io.StringIO()):
            generate.write_all({**ANSWERS, "channel_name": "Quiet One", "background_stats": False}, b)
        calls = []

        def call(cmd, cwd=None, env=None, timeout=None):
            calls.append((env[profiles.ENV], cmd[-2:], int(env["REELFORGE_REFRESH_WAIT"])))
            return 0

        with mock.patch.object(subprocess, "call", call), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(dash.refresh_profiles(), 0)
        self.assertEqual([c[0] for c in calls], [".", a.key])  # Quiet One reads only while its window is open
        self.assertEqual(calls[0][1], ["dashboard", "refresh"])
        self.assertTrue(all(0 < c[2] <= 600 for c in calls))
        self.assertIn("Cool Epic Facts:", out.getvalue())

    def test_one_profile_or_one_asked_for_is_read_here(self):
        from dashboard import __main__ as dash

        for setup in (lambda: None, lambda: profiles.use(profiles.create("Cool Epic Facts"))):
            setup()
            with mock.patch.object(dash, "load_platforms", return_value=({}, {})) as load, \
                    mock.patch.object(dash, "refresh", return_value=0) as read, \
                    mock.patch.object(subprocess, "call") as spawn, mock.patch.object(dash.db, "stored_platforms",
                                                                                      return_value=set()):
                self.assertEqual(dash.refresh_profiles(), 0)
            load.assert_called_once()
            read.assert_called_once()
            spawn.assert_not_called()


class Pipeline(Scratch):
    def test_an_episode_follows_the_rules_of_the_channel_whose_folder_it_is_in(self):
        self.onboard_main()
        a = profiles.create("Cool Epic Facts")
        with redirect_stdout(io.StringIO()):
            generate.write_all({**ANSWERS, "channel_name": "Cool Epic Facts", "length": "30-45"}, a)
        for folder, want in ((self.root / "episodes" / "ep01_duck", ("Night Physics", 61.0, ".")),
                             (a.episodes / "ep01_volcano", ("Cool Epic Facts", 30.0, a.key))):
            folder.mkdir(parents=True)
            (folder / "episode.json").write_text("{}", encoding="utf-8")
            script = (f"import sys; sys.path[:0] = [{str(KIT)!r}, {str(KIT / 'pipeline')!r}]\n"
                      "from pathlib import Path\n"
                      "from studio import profiles\n"
                      f"profiles.ROOT = Path({str(self.root)!r}); profiles.FOLDER = profiles.ROOT / 'profiles'\n"
                      f"sys.argv = ['qa.py', {str(folder)!r}]\n"
                      "import config\n"
                      "print(config.SETTINGS['channel']['name'], config.MIN_SECONDS, config.PROFILE.key, "
                      "config.COMPLETED, sep='|')\n")
            env = {k: v for k, v in os.environ.items() if k != profiles.ENV}
            out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env,
                                 encoding="utf-8")
            self.assertEqual(out.returncode, 0, out.stderr)
            name, seconds, key, completed = out.stdout.strip().split("|")
            self.assertEqual((name, float(seconds), key), want)
            self.assertEqual(Path(completed), profiles.get(key).completed)


class Command(Scratch):
    def test_the_profile_option_comes_out_of_any_command(self):
        from studio.__main__ import take_profile

        self.assertEqual(take_profile(["-p", "Cool", "4"]), (["4"], "Cool"))
        self.assertEqual(take_profile(["new-episode", "duck", "--profile", "2"]), (["new-episode", "duck"], "2"))
        self.assertEqual(take_profile(["--profile=tiny", "refresh"]), (["refresh"], "tiny"))
        self.assertEqual(take_profile(["doctor"]), (["doctor"], None))

    def test_an_unknown_profile_says_which_there_are(self):
        from studio.__main__ import main

        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["-p", "nope", "doctor"]), 2)
        self.assertIn("There's no profile called 'nope'", out.getvalue())
        self.assertIn("1. My channel", out.getvalue())

    def test_profiles_lists_them(self):
        from studio.__main__ import main

        profiles.create("Cool Epic Facts")
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(["profiles"]), 0)
        self.assertIn("2. Cool Epic Facts", out.getvalue())
        self.assertIn(f"profiles{os.sep}cool-epic-facts", out.getvalue())


class Switcher(Scratch):
    def test_another_profiles_platforms_and_unread_notifications(self):
        from dashboard import switcher

        a = profiles.create("Cool Epic Facts")
        a.dashboard.mkdir(parents=True)
        a.config.write_text('[tiktok]\nhandle = "@cool"\n[instagram]\nhandle = "@coolig"\n', encoding="utf-8")
        self.assertEqual(switcher.summary(a), {"platforms": ["tiktok"], "unread": 0})  # Instagram: no log-in yet
        a.data.mkdir(parents=True)
        with closing(sqlite3.connect(a.db)) as c, c:
            c.execute("CREATE TABLE account_stats (platform TEXT, ts TEXT)")
            c.execute("CREATE TABLE notifications (kind TEXT, key TEXT, title TEXT, read INTEGER, deleted INTEGER)")
            c.executemany("INSERT INTO notifications VALUES (?,?,?,?,?)", [
                ("hot", "hot:tiktok|1", "Taking off on TikTok", 0, 0),
                ("login", "login:instagram", "Log in to Instagram again", 0, 0),  # not connected: hidden there too
                ("update", "update:9.9.9", "ReelForge 9.9.9 is out", 0, 0),
                ("hot", "hot:tiktok|2", "Taking off on TikTok", 1, 0),           # read
                ("video", "video:a.mp4", "A new video is ready to post", 0, 1),  # deleted
            ])
        self.assertEqual(switcher.summary(a), {"platforms": ["tiktok"], "unread": 2})
        self.assertEqual(switcher.unread_elsewhere(profiles.main(), profiles.every()), 2)
        self.assertEqual(switcher.unread_elsewhere(a, profiles.every()), 0)



class Menu(Scratch):
    def test_the_menu_lists_every_profile_and_removing_one_sends_it_to_the_bin(self):
        from dashboard import db, desktop, service
        from dashboard.platforms import build
        from dashboard.tests.window import Window

        self.onboard_main()
        a = profiles.create("Cool Epic Facts")
        db.init(config.DB_PATH)
        cfg = config.load_config()
        with mock.patch.object(service, "kit_update", None):  # no update check
            w = Window(cfg, build(cfg), demo=False)
        self.addCleanup(w.close)
        self.assertEqual(w.init["profile"], {"key": ".", "name": "Night Physics", "main": True, "several": True,
                                             "elsewhere": 0})
        menu = w.call("profiles_menu")
        self.assertEqual([(r["number"], r["name"], r["current"], r["where"]) for r in menu["rows"]],
                         [(1, "Night Physics", True, ""), (2, "Cool Epic Facts", False, f"profiles{os.sep}cool-epic-facts")])
        self.assertEqual([t["short"] for t in menu["rows"][0]["platforms"]], ["TT"])
        self.assertIsNone(w.call("remove_profile_info", "."))  # never the first one
        info = w.call("remove_profile_info", a.key)
        self.assertIn("Recycle Bin" if sys.platform == "win32" else "Trash", json.dumps(info["note"]))
        bin_ = self.root / "bin"
        bin_.mkdir()
        with mock.patch.object(desktop, "recycle", lambda path: shutil.move(str(path), str(bin_ / path.name)) and True):
            self.assertTrue(w.call("remove_profile", a.key))
        self.assertTrue((bin_ / "cool-epic-facts" / "profile.toml").exists())
        self.assertEqual(profiles.every(), [profiles.main()])
        self.assertNotIn("Other channels", (self.root / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertTrue(any("is in the" in t for t in w.toasts()))
        self.assertFalse(w.call("remove_profile", "."))


if __name__ == "__main__":
    unittest.main()
