"""Onboarding's platforms and "Your accounts" step, the sign-up guides, and connecting a platform afterwards
(studio.questions, studio.signup, studio.setup_service, studio.generate.set_account), in a scratch folder. No browser
opens: the sign-up pages go to a stand-in. The step's screen is tested in ui/test/setup.test.tsx."""

import copy
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from studio import generate, questions, settings, signup
from studio import paths as P
from studio import settings as S
from studio.bridge import Loop
from studio.setup_service import Setup

KIT = Path(__file__).resolve().parent.parent


class Handles(unittest.TestCase):
    def test_what_you_type_becomes_a_handle(self):
        for typed, handle in (("", ""), ("  ", ""), ("nightphysics", "@nightphysics"), ("@Night.Physics_1", "@Night.Physics_1"),
                              ("https://www.tiktok.com/@nightphysics", "@nightphysics"),
                              ("youtube.com/@NightPhysics/shorts", "@NightPhysics"),
                              ("https://www.instagram.com/nightphysics/", "@nightphysics"),
                              ("https://x.com/night_physics?s=21", "@night_physics"),
                              ("twitter.com/night_physics", "@night_physics")):
            self.assertEqual(signup.handle_from(typed), handle, typed)

    def test_what_isnt_a_handle(self):
        for typed in ("my channel", "@", "no!", "https://www.youtube.com/channel/UCabc", "instagram.com/p/xyz",
                      "a" * 31):
            with self.assertRaises(ValueError, msg=typed):
                signup.handle_from(typed)

    def test_every_platform_has_an_official_sign_up_page(self):
        self.assertEqual(set(signup.GUIDES), set(settings.PLATFORMS))
        hosts = {"tiktok": "www.tiktok.com", "youtube": "www.youtube.com", "instagram": "www.instagram.com",
                 "x": "x.com"}
        for key, guide in signup.GUIDES.items():
            self.assertTrue(guide.url.startswith(f"https://{hosts[key]}/"), guide.url)
            self.assertEqual(guide.logs_in, key in ("instagram", "x"))
        self.assertTrue(signup.GMAIL.url.startswith("https://accounts.google.com/"))


class Suggestions(unittest.TestCase):
    def test_names_made_from_the_channels(self):
        self.assertEqual(signup.suggest("Cool Epic Facts"),
                         {"gmail": "coolepicfacts@gmail.com", "handle": "@coolepicfacts"})
        self.assertEqual(signup.suggest("Zap!"), {"gmail": "zapvideos@gmail.com", "handle": "@zap"})  # Google wants 6+
        self.assertEqual(signup.suggest("Ünïcode Wörld"), {"gmail": "unicodeworld@gmail.com", "handle": "@unicodeworld"})
        self.assertEqual(signup.suggest("Cool Epic Facts Every Day", 15)["handle"], "@coolepicfacts")  # words that fit X
        self.assertEqual(signup.suggest("Supercalifragilisticexpialidocious", 15)["handle"], "@supercalifragil")
        self.assertEqual((signup.suggest(""), signup.suggest("!!!")), ({}, {}))

    def test_the_steps_use_them(self):
        self.assertIn("like @coolepicfacts:", signup.GUIDES["x"].steps_for("Cool Epic Facts")[-1])
        self.assertIn("like Cool Epic Facts and @coolepicfacts.", signup.GUIDES["youtube"].steps_for("Cool Epic Facts")[-1])
        self.assertIn("like coolepicfacts@gmail.com.", signup.GMAIL.steps_for("Cool Epic Facts")[0])
        self.assertIn("like nightphysics@gmail.com.", signup.GMAIL.steps_for()[0])  # no name yet: the usual example
        self.assertEqual(signup.GUIDES["tiktok"].steps_for()[-1], "Pick a username that matches your channel: that's "
                                                                  "your @handle. You can change it later in Edit profile.")
        for guide in (signup.GMAIL, *signup.GUIDES.values()):
            for channel in ("", "Cool Epic Facts"):
                self.assertFalse(any("{" in step or "}" in step for step in guide.steps_for(channel)))


CHROME = signup.Private("Chrome", ("chrome.exe", "--incognito"))


class PrivateWindows(unittest.TestCase):
    """A second channel signs up in a private window of your usual browser. Nothing opens here: the browser found and
    started are stand-ins (the ways of finding one are tested with what each system keeps)."""

    def test_windows_finds_the_browser_from_its_open_command(self):
        for command, name, switch in (
                (r'"C:\Program Files\Google\Chrome\Application\chrome.exe" --single-argument %1', "Chrome", "--incognito"),
                (r'"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --single-argument %1', "Edge",
                 "--inprivate"),
                (r'"C:\Program Files\Mozilla Firefox\firefox.exe" -osint -url "%1"', "Firefox", "-private-window"),
                (r'"C:\Users\Sam\AppData\Local\BraveSoftware\Brave-Browser\Application\brave.exe" --single-argument %1',
                 "Brave", "--incognito"),
                (r"C:\Vivaldi\Application\vivaldi.exe %1", "Vivaldi", "--incognito")):
            found = signup.from_command(command)
            self.assertEqual((found.name, found.command[1:]), (name, (switch,)), command)
            self.assertTrue(found.command[0].lower().endswith(".exe"))
        # One it doesn't know, even in a folder named like one it does (Windows then uses Edge).
        self.assertIsNone(signup.from_command(r'"C:\Users\Chrome Fan\AppData\Local\Programs\Opera\launcher.exe" "%1"'))
        self.assertIsNone(signup.from_command(""))

    def test_a_mac_opens_the_chrome_based_ones(self):
        handlers = [{"LSHandlerURLScheme": "mailto", "LSHandlerRoleAll": "com.apple.mail"},
                    {"LSHandlerURLScheme": "https", "LSHandlerRoleAll": "com.google.Chrome"}]
        self.assertEqual(signup.mac_default(handlers), "com.google.chrome")
        self.assertEqual(signup.mac_default([]), "com.apple.safari")  # never picked one
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Google Chrome.app").mkdir()
            found = signup.from_bundle("com.google.chrome", [Path(tmp)])
            self.assertEqual((found.name, found.command),
                             ("Chrome", ("open", "-na", str(Path(tmp) / "Google Chrome.app"), "--args", "--incognito")))
            self.assertIsNone(signup.from_bundle("com.microsoft.edgemac", [Path(tmp)]))  # not installed
        self.assertIsNone(signup.from_bundle("com.apple.safari", []))  # Safari can't be told

    def test_linux_reads_the_browsers_desktop_file(self):
        chrome = signup.from_desktop("google-chrome.desktop",
                                     "[Desktop Entry]\nName=Google Chrome\nExec=/usr/bin/google-chrome-stable %U\n\n"
                                     "[Desktop Action new-window]\nExec=/usr/bin/google-chrome-stable --new-window\n")
        self.assertEqual((chrome.name, chrome.command), ("Chrome", ("/usr/bin/google-chrome-stable", "--incognito")))
        snap = signup.from_desktop("firefox_firefox.desktop", "[Desktop Entry]\nExec=env BAMF_DESKTOP_FILE_HINT=/var/lib/"
                                   "snapd/desktop/applications/firefox_firefox.desktop /snap/bin/firefox %u\n")
        self.assertEqual(snap.command[-2:], ("/snap/bin/firefox", "-private-window"))
        flatpak = signup.from_desktop("org.mozilla.firefox.desktop", "[Desktop Entry]\nExec=/usr/bin/flatpak run "
                                      "--command=firefox --file-forwarding org.mozilla.firefox @@u %u @@\n")
        self.assertEqual(flatpak.command[-2:], ("org.mozilla.firefox", "-private-window"))
        self.assertIsNone(signup.from_desktop("org.gnome.Epiphany.desktop", "[Desktop Entry]\nExec=epiphany %U\n"))

    def test_opening_one(self):
        launched = []
        with mock.patch.object(signup, "private_browser", lambda: CHROME), \
                mock.patch.object(signup, "launch", launched.append):
            self.assertEqual(signup.open_private("https://x.com/i/flow/signup"), "Chrome")
        self.assertEqual(launched, [["chrome.exe", "--incognito", "https://x.com/i/flow/signup"]])

        def gone(command):
            raise FileNotFoundError(command[0])

        with mock.patch.object(signup, "private_browser", lambda: CHROME), mock.patch.object(signup, "launch", gone):
            self.assertIsNone(signup.open_private("https://x.com/"))
        with mock.patch.object(signup, "private_browser", lambda: None):
            self.assertIsNone(signup.open_private("https://x.com/"))

    def test_a_second_channels_guides(self):
        opened, launched = [], []
        with mock.patch.object(signup, "private_browser", lambda: CHROME), \
                mock.patch.object(signup, "launch", launched.append), mock.patch.object(signup, "open_page", opened.append):
            tiktok = signup.guide_view("tiktok", "Cool Epic Facts", ["Rendered Wrong"])
            self.assertEqual(tiktok["steps"][0], "Press Open TikTok sign-up: it opens in a private Chrome window, so "
                                                 "you sign up fresh while Rendered Wrong stays logged in.")
            self.assertIn("like @coolepicfacts", tiktok["steps"][-1])
            gmail = signup.guide_view("gmail", "Cool Epic Facts", ["Rendered Wrong", "Tiny Worlds"])
            self.assertIn("while Rendered Wrong and Tiny Worlds stay logged in", gmail["steps"][0])
            self.assertIn("Keep the private window open", gmail["steps"][-1])
            self.assertIn("your other channel stays", signup.guide_view("x", "", [""])["steps"][0])  # one with no name
            self.assertEqual(signup.open_guide("tiktok", ["Rendered Wrong"]),
                             "Opened in a private Chrome window. Come back here when you're done.")
            self.assertEqual((opened, launched), ([], [["chrome.exe", "--incognito", "https://www.tiktok.com/signup"]]))
            # One channel: your usual window, as before.
            self.assertEqual(signup.guide_view("tiktok")["steps"][0],
                             "Press Open TikTok sign-up: the page opens in your browser.")
            self.assertEqual(len(signup.guide_view("gmail")["steps"]), 4)
            self.assertEqual(signup.open_guide("tiktok"), "Opened in your browser. Come back here when you're done.")
            self.assertEqual(opened, ["https://www.tiktok.com/signup"])
        with mock.patch.object(signup, "private_browser", lambda: None), \
                mock.patch.object(signup, "open_page", opened.append):
            # A browser ReelForge can't open a private window of: the usual one, and what to do about the log-in.
            first = signup.guide_view("x", "Cool Epic Facts", ["Rendered Wrong"])["steps"][0]
            self.assertIn("Logged in to Rendered Wrong there? Log out first, or open the page in a private window.",
                          first)
            self.assertIn("can't open a private window", signup.open_guide("x", ["Rendered Wrong"]))
            self.assertEqual(opened[-1], "https://x.com/i/flow/signup")
            self.assertEqual(signup.where(["Rendered Wrong"]), "")


class PlatformQuestions(unittest.TestCase):
    def test_three_recommended_and_ticked(self):
        q = questions.BY_KEY["platforms"]
        self.assertEqual(q.default, ["tiktok", "youtube", "instagram"])
        labels = dict(q.options)
        self.assertTrue(all("recommended" in labels[p] for p in ("tiktok", "youtube", "instagram")))
        self.assertNotIn("recommended", labels["x"])

    def test_handles_have_their_own_step(self):
        self.assertIn(("accounts", "Your accounts"), questions.STEPS)
        for p in settings.PLATFORMS:
            q = questions.BY_KEY[f"handle_{p}"]
            self.assertEqual((q.step, q.kind), ("accounts", "handle"))
        a, problems = questions.validate({"channel_name": "C", "about": "A", "assistant": "codex",
                                             "handle_tiktok": "tiktok.com/@me"})
        self.assertEqual((problems, a["handle_tiktok"]), ([], "@me"))
        _, problems = questions.validate({"channel_name": "C", "about": "A", "assistant": "codex",
                                             "handle_tiktok": "me and you"})
        self.assertTrue(any(p.startswith("handle_tiktok") for p in problems))

    def test_the_ai_interview_gets_the_sign_up_pages(self):
        items = {i["key"]: i for i in questions.describe()}
        self.assertEqual(items["handle_youtube"]["signup"]["page"], signup.GUIDES["youtube"].url)
        self.assertEqual(items["handle_tiktok"]["gmail"]["page"], signup.GMAIL.url)  # offered once, first
        self.assertIn("private window", items["handle_tiktok"]["gmail"]["another_channel"])
        self.assertNotIn("gmail", items["handle_youtube"])
        steps = [s for i in items.values() for s in i.get("signup", {}).get("steps", []) + i.get("gmail", {}).get(
            "steps", [])]
        self.assertTrue(steps)
        self.assertFalse(any("{" in s for s in steps))  # the steps' examples filled in
        json.dumps(list(items.values()))


class Scratch(unittest.TestCase):
    """studio.paths pointed at a scratch folder with the kit's dashboard settings example."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        mine = root / "my-studio"
        (root / "dashboard").mkdir()
        shutil.copy(KIT / "dashboard" / "config.example.toml", root / "dashboard" / "config.example.toml")
        for name, value in {"ROOT": root, "MY_STUDIO": mine, "ANSWERS": mine / "answers.json",
                            "SETTINGS": mine / "studio.toml", "BIBLE": mine / "channel-bible.md",
                            "BACKUPS": mine / "backups", "COMPLETED": root / "completed videos",
                            "DASHBOARD": root / "dashboard"}.items():
            patch = mock.patch.object(P, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.config = root / "dashboard" / "config.toml"

    def handles(self) -> dict:
        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        return {p: data[p]["handle"] for p in settings.PLATFORMS}


class SetAccount(Scratch):
    def test_before_onboarding_only_the_dashboard_changes(self):
        generate.set_account("youtube", "@mine")
        self.assertEqual(self.handles()["youtube"], "@mine")
        self.assertFalse(P.ANSWERS.exists())

    def test_after_onboarding_everything_follows(self):
        generate.write_all({"channel_name": "Night Physics", "about": "What-ifs.", "assistant": "claude",
                            "platforms": ["tiktok", "youtube"],
                            "handle_tiktok": "@np"})
        generate.set_account("x", "@np_x")      # connect one onboarding left out
        generate.set_account("tiktok", "")      # and disconnect one
        a = json.loads(P.ANSWERS.read_text(encoding="utf-8"))
        self.assertEqual(a["platforms"], ["tiktok", "youtube", "x"])  # still posting to TikTok: captions keep it
        self.assertEqual((a.get("handle_tiktok"), a["handle_x"]), (None, "@np_x"))
        self.assertEqual(self.handles(), {"tiktok": "", "youtube": "", "instagram": "", "x": "@np_x"})
        s = settings.load(P.SETTINGS)
        self.assertEqual(s["platforms"]["handles"]["x"], "@np_x")
        self.assertIn("X", (P.ROOT / "CLAUDE.md").read_text(encoding="utf-8"))
        # a later onboarding run keeps it
        generate.write_all(json.loads(P.ANSWERS.read_text(encoding="utf-8")))
        self.assertEqual(self.handles()["x"], "@np_x")

    def test_a_handle_typed_into_the_dashboard_settings_counts(self):
        generate.write_all({"channel_name": "Night Physics", "about": "What-ifs.", "assistant": "claude",
                            "platforms": ["tiktok"],
                            "handle_tiktok": "@np"})
        text = self.config.read_text(encoding="utf-8").replace('[instagram]\nhandle = ""', '[instagram]\nhandle = "@ig"')
        self.config.write_text(text, encoding="utf-8")
        generate.set_account("youtube", "@yt")
        self.assertEqual(self.handles(), {"tiktok": "@np", "youtube": "@yt", "instagram": "@ig", "x": ""})

    def test_the_notes_an_older_version_wrote_into_the_settings_say_first_time_setup(self):
        example = (P.DASHBOARD / "config.example.toml").read_text(encoding="utf-8")
        old = example.replace("first-time\n# setup fills that one in", "onboarding\n# fills that one in").replace(
            "# (first-time setup fills this in;", "# (onboarding fills this in;")
        self.assertEqual(old.count("onboarding"), 2)  # how 1.0.5 and older copied them in
        self.config.write_bytes(old.replace("\n", "\r\n").encode("utf-8"))
        generate.set_account("youtube", "@yt")
        self.assertEqual(self.config.read_text(encoding="utf-8").replace('handle = "@yt"', 'handle = ""', 1), example)


class Quiet(Loop):
    def send(self, msg: dict) -> None:
        pass


class AccountsStep(unittest.TestCase):
    """The interview's "Your accounts" step, as the onboarding screen gets it."""

    def setUp(self) -> None:
        self.svc = Setup(Quiet(out=None))
        self.svc.start({"preview": True, "start": "onboard"})
        with mock.patch("studio.setup_service.saved_answers",
                        lambda: {"channel_name": "Night Physics", "about": "What-ifs."}):
            self.svc.onboard_start()
        self.step = self.svc.onboard_step([k for k, _ in self.svc.steps].index("accounts"))
        self.opened: list[str] = []
        patch = mock.patch.object(signup, "open_page", self.opened.append)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_gmail_first_then_a_handle_each(self):
        self.assertIn("Make a Gmail", self.step["gmail"]["button"])
        shown = [f["key"] for f in self.step["fields"] if f["visible"]]
        self.assertEqual(shown, ["handle_tiktok", "handle_youtube", "handle_instagram"])  # X wasn't picked
        self.assertEqual({f["platform"] for f in self.step["fields"]}, set(settings.PLATFORMS))
        guide = self.svc.signup_guide("gmail")
        self.assertFalse(guide["account"])
        self.assertTrue(guide["steps"][0].startswith(f"Press {signup.GMAIL.button}"))
        self.svc.open_signup("gmail")
        self.assertEqual(self.opened, [signup.GMAIL.url])

    def test_sign_up_fills_in_the_handle(self):
        guide = self.svc.signup_guide("youtube")
        self.assertTrue(guide["account"])
        self.assertEqual(guide["steps"][-1], "Type your @handle below.")
        self.assertIn("one log-in", self.svc.signup_guide("instagram")["steps"][-1])
        self.svc.open_signup("youtube")
        self.assertEqual(self.opened, ["https://www.youtube.com/create_channel"])
        self.assertIn("isn't a handle", self.svc.signup_handle("not a handle!")["error"])  # it says what's wrong
        handle = self.svc.signup_handle("youtube.com/@NightPhysics")["handle"]
        self.assertEqual(handle, "@NightPhysics")
        self.svc.onboard_change("handle_youtube", handle)  # the screen puts it in its box: your answer
        res = self.svc.onboard_next({"handle_youtube": handle})
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.svc.answers["handle_youtube"], "@NightPhysics")

    def test_a_bad_handle_stops_next(self):
        res = self.svc.onboard_next({"handle_tiktok": "two words"})
        self.assertFalse(res["ok"])
        self.assertIn("isn't a handle", res["errors"]["handle_tiktok"])
        self.assertEqual(self.opened, [])  # no page opens by itself

    def test_a_skipped_handle_can_wait(self):
        self.assertTrue(self.svc.onboard_next({})["ok"])
        self.assertIn("connect it any time on ReelForge's Accounts tab", self.svc.summary())
        self.assertIn("**Where will you post?** TikTok, YouTube Shorts, Instagram Reels\n", self.svc.summary())

    def test_the_last_screen_says_to_connect_them_later(self):
        sample = copy.deepcopy(S.DEFAULTS)
        sample["platforms"]["enabled"] = ["tiktok", "youtube", "instagram"]
        sample["platforms"]["handles"] = {"tiktok": "@np"}
        with mock.patch.object(S, "load", lambda path=None: sample), \
                mock.patch.object(self.svc.loop, "run_worker", lambda *a, **k: None):  # nothing turned on here
            info = self.svc.done_info()
        self.assertIn("When you've made your YouTube Shorts and Instagram Reels accounts, connect them on "
                      "ReelForge's Accounts tab", info["login"])
        self.assertEqual(info["tab"], "accounts")


if __name__ == "__main__":
    unittest.main()
