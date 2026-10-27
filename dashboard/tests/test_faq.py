"""The Settings tab's FAQ (dashboard/faq.py): the honest answer about your AI's model and how hard it thinks (your AI
app decides, and ReelForge offers no setting for it), answers that fit the channel and its AI, folders named the way
you'd find them, and the demo naming nothing on this computer. Opening the answers is tested in
ui/test/settings.test.tsx."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from dashboard import config, db, demo, faq
from dashboard.tests.window import Window

ROOT = Path(tempfile.gettempdir()) / "ReelForge"


def items(**over) -> list[dict]:
    args = dict(assistant="claude", root=ROOT, episodes=ROOT / "episodes", completed=ROOT / "completed videos",
                channel="Night Physics", main=True, several=False, refresh_minutes=30)
    return faq.items(**{**args, **over})


def answer(question: str, **over) -> str:
    return next(i["a"] for i in items(**over) if i["q"].startswith(question))


class FaqTest(unittest.TestCase):
    def test_the_first_answer_says_your_ai_app_decides_and_where_reelforge_cant_control_it(self):
        first = items()[0]
        self.assertEqual(first["q"], "Which model does my AI use, and how hard does it think?")
        a = first["a"]
        self.assertTrue(a.startswith("Your AI app decides that, not ReelForge."))
        for said in ("**Opus at high effort**", "`.claude/settings.local.json`", "never changes it after that",
                     "can't control it everywhere", "Claude desktop app", "already open", "usage limits",
                     "`/model`", "`/effort`", "uses more of your plan"):
            self.assertIn(said, a)
        self.assertNotIn("Codex", a)

    def test_codex_gets_codexs_answers(self):
        a = answer("Which model", assistant="codex")
        self.assertTrue(a.startswith("Your AI app decides that, not ReelForge. ReelForge's `.codex/config.toml`"))
        self.assertNotIn("Claude", a)
        made = answer("How do I make a video?", assistant="codex")
        self.assertIn("Run `codex` in a terminal in", made)
        self.assertNotIn("Claude desktop app", made)
        self.assertIn("`AGENTS.md`", answer("My AI doesn't know", assistant="codex"))
        both = answer("Which model", assistant="both")
        self.assertIn("With Codex: ReelForge's `.codex/config.toml`", both)
        self.assertIn("`CLAUDE.md` (or `AGENTS.md` for Codex)", answer("My AI doesn't know", assistant="both"))

    def test_no_answer_offers_a_setting_for_it(self):
        for assistant in ("claude", "codex", "both", ""):
            text = "\n".join(f"{i['q']}\n{i['a']}" for i in items(assistant=assistant))
            for gone in ("Advanced settings", "**Max**", "**High**", "**Fast**", "Max, High", "the standard",
                         "ultracode", "onboarding", "Settings tab (7) picks"):
                self.assertNotIn(gone, text)
            self.assertIsNone(re.search(r"\b(Max|Fast)\b", text))

    def test_every_question_is_one_line_with_an_answer(self):
        qs = [i["q"] for i in items()]
        self.assertEqual(len(qs), len(set(qs)))
        for i in items():
            self.assertLessEqual(len(i["q"]), 60)
            self.assertNotIn("\n", i["q"])
            self.assertTrue(i["a"].strip())

    def test_folders_are_named_from_the_reelforge_folder_or_in_full(self):
        a = answer("Where are my videos?")
        self.assertIn("in `episodes`", a)
        self.assertIn("goes to `completed videos`", a)
        elsewhere = ROOT.parent / "my videos" / "episodes"
        self.assertIn(f"in `{elsewhere}`", answer("Where are my videos?", episodes=elsewhere))
        self.assertIn(f"pick `{ROOT}`", answer("How do I make a video?"))

    def test_another_channel_asks_for_its_own_first_video_and_brief(self):
        name = "Cool *Epic* Facts"
        made = answer("How do I make a video?", channel=name, main=False, several=True)
        self.assertIn(r"**make my first Cool \*Epic\* Facts video**", made)
        self.assertIn("for every channel that posts regularly", made)
        self.assertIn(r"**here's Cool \*Epic\* Facts**", answer("My AI doesn't know", channel=name, main=False))
        self.assertIn("**make my first video**", answer("How do I make a video?"))

    def test_how_often_an_open_reelforge_reads_the_stats(self):
        self.assertIn("every 30 minutes", answer("Do my stats update"))
        self.assertIn("every 5 minutes", answer("Do my stats update", refresh_minutes=5))
        self.assertNotIn("every 0 minutes", answer("Do my stats update", refresh_minutes=0))

    def test_the_demo_names_nothing_on_this_computer(self):
        text = "\n".join(i["a"] for i in items(demo=True))
        self.assertNotIn(str(ROOT), text)
        self.assertRegex(text, r"`(C:\\Users\\you\\ReelForge|~/ReelForge)`")


class SettingsViewTest(unittest.TestCase):
    def test_the_settings_tab_gets_the_faq_and_no_setting_for_your_ais_reasoning(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "demo.db")
        demo.seed()
        w = Window(config.load_config(), demo.platforms(), tab="settings")
        self.addCleanup(w.close)
        self.assertTrue(w.until(lambda: w.view("settings") is not None))
        view = w.view("settings")
        self.assertEqual([i["q"] for i in view["faq"]], [i["q"] for i in items()])
        self.assertNotIn("ai", view)
        self.assertFalse(hasattr(w.svc, "set_reasoning") or hasattr(w.svc, "advanced_info"))


if __name__ == "__main__":
    unittest.main()
