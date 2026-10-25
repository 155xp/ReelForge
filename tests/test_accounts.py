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
        a, problems = questions.validate({"channel_name": "C", "about": "A", "handle_tiktok": "tiktok.com/@me"})
        self.assertEqual((problems, a["handle_tiktok"]), ([], "@me"))
        _, problems = questions.validate({"channel_name": "C", "about": "A", "handle_tiktok": "me and you"})
        self.assertTrue(any(p.startswith("handle_tiktok") for p in problems))

    def test_the_ai_interview_gets_the_sign_up_pages(self):
        items = {i["key"]: i for i in questions.describe()}
        self.assertEqual(items["handle_youtube"]["signup"]["page"], signup.GUIDES["youtube"].url)
        self.assertEqual(items["handle_tiktok"]["gmail"]["page"], signup.GMAIL.url)  # offered once, first
        self.assertNotIn("gmail", items["handle_youtube"])
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
        generate.write_all({"channel_name": "Night Physics", "about": "What-ifs.", "platforms": ["tiktok", "youtube"],
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
        generate.write_all({"channel_name": "Night Physics", "about": "What-ifs.", "platforms": ["tiktok"],
                            "handle_tiktok": "@np"})
        text = self.config.read_text(encoding="utf-8").replace('[instagram]\nhandle = ""', '[instagram]\nhandle = "@ig"')
        self.config.write_text(text, encoding="utf-8")
        generate.set_account("youtube", "@yt")
        self.assertEqual(self.handles(), {"tiktok": "@np", "youtube": "@yt", "instagram": "@ig", "x": ""})


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
