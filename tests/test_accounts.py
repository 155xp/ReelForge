"""Onboarding's platforms and "Your accounts" step, the sign-up guides, and connecting a platform afterwards
(studio.questions, studio.signup, studio.onboard_app, studio.generate.set_account), in a scratch folder. No browser
opens: the sign-up pages go to a stand-in."""

import asyncio
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from textual.widgets import Input

from studio import generate, questions, settings, signup
from studio import paths as P
from studio.onboard_app import GmailOffer, Onboard, OnboardScreen, SignupGuide

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


class AccountsStep(Scratch):
    """The interview's "Your accounts" step, in the full-screen box."""

    def run_onboarding(self, scenario, answers=None) -> None:
        app = Onboard({"channel_name": "Night Physics", "about": "What-ifs.", **(answers or {})}, preview=True)

        async def main():
            async with app.run_test(size=(140, 46)) as pilot:
                await pilot.pause(0.5)
                screen = app.screen
                self.assertIsInstance(screen, OnboardScreen)
                await screen.show_step([k for k, _ in screen.steps].index("accounts"))
                await pilot.pause(0.3)
                await scenario(app, screen, pilot)

        asyncio.run(main())

    def test_a_gmail_first_then_a_handle_each(self):
        opened = []

        async def scenario(app, screen, pilot):
            self.assertTrue(screen.query(GmailOffer))
            shown = [f.q.key for f in screen.fields() if not f.has_class("hidden")]
            self.assertEqual(shown, ["handle_tiktok", "handle_youtube", "handle_instagram"])  # X wasn't picked
            await pilot.click("#gmail")
            await pilot.pause(0.3)
            self.assertIsInstance(app.screen, SignupGuide)
            await pilot.click("#guide-open")
            await pilot.pause(0.2)
            self.assertEqual(opened, [signup.GMAIL.url])
            await pilot.click("#guide-done")
            await pilot.pause(0.2)
            self.assertIs(app.screen, screen)

        with mock.patch.object(signup, "open_page", opened.append):
            self.run_onboarding(scenario)

    def test_sign_up_fills_in_the_handle(self):
        opened = []

        async def scenario(app, screen, pilot):
            await pilot.click("#signup-youtube")
            await pilot.pause(0.3)
            guide = app.screen
            self.assertIsInstance(guide, SignupGuide)
            await pilot.click("#guide-open")
            await pilot.pause(0.2)
            self.assertEqual(opened, ["https://www.youtube.com/create_channel"])
            guide.query_one("#guide-handle", Input).value = "not a handle!"
            await pilot.click("#guide-done")
            await pilot.pause(0.2)
            self.assertIs(app.screen, guide)  # it says what's wrong instead
            guide.query_one("#guide-handle", Input).value = "youtube.com/@NightPhysics"
            await pilot.click("#guide-done")
            await pilot.pause(0.3)
            self.assertIs(app.screen, screen)
            self.assertEqual(screen.query_one("#w-handle_youtube", Input).value, "@NightPhysics")
            self.assertTrue(screen.validate_step())
            self.assertEqual(screen.answers["handle_youtube"], "@NightPhysics")

        with mock.patch.object(signup, "open_page", opened.append):
            self.run_onboarding(scenario)

    def test_a_bad_handle_stops_next(self):
        async def scenario(app, screen, pilot):
            screen.query_one("#w-handle_tiktok", Input).value = "two words"
            await pilot.pause(0.2)
            self.assertFalse(screen.validate_step())
            self.assertIn("isn't a handle", str(screen.query_one("#e-handle_tiktok").render()))

        with mock.patch.object(signup, "open_page", lambda url: self.fail("no page should open")):
            self.run_onboarding(scenario)


if __name__ == "__main__":
    unittest.main()
