"""The channel brief. First-time setup only asks a few questions, so your AI asks for the rest before the first video
(a description, or a file about the channel), and keeps it as the channel's brief (my-studio/brief.md, in the
channel's own folder) and plans from it. These check what the AI is told, for the first channel and another one;
that the first channel's notes give every channel's videos a day, so "make today's videos" covers them all; that
changing the answers never touches a brief; and the last screen, whose prompt for your AI (with its Copy button)
names the ReelForge folder, so nothing has to be dragged into the chat. In a scratch ReelForge folder."""

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from dashboard import config
from studio import __main__ as cli
from studio import generate, profiles, questions
from studio import settings as S
from studio import paths as P
from studio.bridge import Loop
from studio.setup_service import Setup

KIT = Path(__file__).resolve().parent.parent
ANSWERS = {"creator": "Sam", "assistant": "claude", "channel_name": "Night Physics",
           "about": "What-if videos with real science.", "platforms": ["tiktok", "youtube"],
           "handle_tiktok": "@nightphysics"}


class Brief(unittest.TestCase):
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
        with redirect_stdout(io.StringIO()):
            generate.write_all(ANSWERS)

    def another(self, name: str = "Cool Epic Facts", **more) -> profiles.Profile:
        p = profiles.create(name)
        with redirect_stdout(io.StringIO()):
            generate.write_all({**ANSWERS, "channel_name": name, **more}, p)
        return p

    def notes(self, folder: Path, name: str = "CLAUDE.md") -> str:
        return (folder / name).read_text(encoding="utf-8")

    def test_the_notes_say_where_the_brief_goes_and_what_to_do_with_it(self):
        for name in ("CLAUDE.md", "AGENTS.md"):
            notes = self.notes(self.root, name)
            self.assertIn("## The channel brief", notes)
            self.assertIn("- `my-studio/brief.md`: Sam's own description of the channel", notes)  # read first
            self.assertIn("1. Save it as `my-studio/brief.md`, in their words.", notes)
            self.assertIn("-m studio channel --regenerate", notes)
            self.assertIn("**No brief yet?** Before the first video, ask Sam for one", notes)
        self.assertIn("- **Brief:** `my-studio/brief.md`, Sam's own description", P.BIBLE.read_text(encoding="utf-8"))

    def test_another_channels_brief_is_in_its_own_folder(self):
        p = self.another()
        notes = self.notes(p.folder)
        self.assertIn("1. Save it as `profiles/cool-epic-facts/my-studio/brief.md`, in their words.", notes)
        self.assertIn("copy it into\n     `profiles/cool-epic-facts/my-studio/backups/` first", notes)
        self.assertIn("- its settings, brief and channel bible: `profiles/cool-epic-facts/my-studio/`", notes)
        self.assertIn("**Brief:** `profiles/cool-epic-facts/my-studio/brief.md`", p.bible.read_text(encoding="utf-8"))
        # the first channel's notes send a file about another channel to that channel's notes
        self.assertIn("A file or a description of\none of them is that channel's brief", self.notes(self.root))

    def test_the_first_channels_notes_give_every_channels_videos_a_day(self):
        self.another(cadence="1/day")
        profiles.create("Half Made")  # its setup never finished
        generate.write_guides(profiles.main())
        notes = self.notes(self.root)
        self.assertIn("(its notes: `profiles/cool-epic-facts/CLAUDE.md`; 1 video a day)", notes)
        self.assertIn("(its notes: `profiles/half-made/CLAUDE.md`; not set up yet)", notes)
        run = notes[notes.index('## A production run ("make today\'s videos")'):notes.index("## Commands")]
        self.assertIn('"Make today\'s videos" is for every channel in this folder', run)
        self.assertIn("- **Night Physics**: 2 videos, as below\n", run)
        self.assertIn("- **Cool Epic Facts**: 1 video, by `profiles/cool-epic-facts/CLAUDE.md`\n", run)
        self.assertIn("- **Half Made**: not set up yet, so none (say so)\n", run)
        self.assertIn("For Night Physics:\n\n2 videos a day: each run makes 2.", run)
        own = self.notes(profiles.find("Cool Epic Facts").folder)
        self.assertNotIn("for every channel in this folder", own)
        self.assertIn("1 video a day: each run makes 1.", own)

    def test_a_channel_that_posts_only_when_asked_is_left_out_of_todays_videos(self):
        # "Only when I ask" (a test channel, say): no regular videos, so "make today's videos" makes none for it
        a, problems = questions.validate({**ANSWERS, "cadence": "ask"})
        self.assertEqual(problems, [])
        self.assertEqual(generate.settings_from(a)["schedule"]["per_day"], 0)
        test = self.another("Test Channel", cadence="ask")
        self.another("Weekly Wonders", cadence="3/week")
        notes = self.notes(self.root)
        self.assertIn("(its notes: `profiles/test-channel/CLAUDE.md`; only when asked)", notes)
        run = notes[notes.index('## A production run ("make today\'s videos")'):notes.index("## Commands")]
        self.assertIn("- **Test Channel**: none (only when Sam asks for one)\n", run)
        self.assertIn("- **Weekly Wonders**: 1 video unless this week's are already made (3 a week), by "
                      "`profiles/weekly-wonders/CLAUDE.md`\n", run)
        own = self.notes(test.folder)
        run = own[own.index('## A production run ("make today\'s videos")'):own.index("## Commands")]
        self.assertIn('None: Sam picked "Only when I ask" for Test Channel, so a production run makes no videos', run)
        self.assertNotIn(".run.lock", run)
        self.assertIn("| Cadence | only when asked", own)

    def test_one_channels_run_is_as_it_was(self):
        notes = self.notes(self.root)
        self.assertIn('## A production run ("make today\'s videos")\n\n2 videos a day: each run makes 2.\n', notes)
        self.assertNotIn("Other channels", notes)

    def test_changing_the_answers_never_touches_a_brief(self):
        p = self.another()
        for brief in (P.MY_STUDIO / "brief.md", p.my_studio / "brief.md"):
            brief.write_text("# My channel\n\nSlow-motion sports breakdowns.\n", encoding="utf-8")
        answers = json.loads(P.ANSWERS.read_text(encoding="utf-8"))
        answers.update(format="custom", custom_format="Slow-motion breakdowns of one sports move.")
        P.ANSWERS.write_text(json.dumps(answers), encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(cli.regenerate(), 0)
        self.assertIn("Slow-motion breakdowns of one sports move.", self.notes(self.root))
        for brief in (P.MY_STUDIO / "brief.md", p.my_studio / "brief.md"):
            self.assertEqual(brief.read_text(encoding="utf-8"), "# My channel\n\nSlow-motion sports breakdowns.\n")

    def done(self, svc: Setup) -> dict:
        with mock.patch.object(svc.loop, "run_worker"):
            return svc.done_info()

    @staticmethod
    def lines(lines: list) -> str:
        return "\n".join("".join(seg[0] for seg in line) for line in lines)

    def test_the_last_screen_has_the_prompt_for_your_ai_with_the_folder_in_it(self):
        # Nothing to drag into the chat or open first: the prompt names the ReelForge folder, any AI can take it, and
        # the notes it points at ask for the brief before the first video.
        out = io.StringIO()
        svc = Setup(Loop(out=out))
        with mock.patch.object(S, "onboarded", return_value=False):  # first-time setup: nothing written yet
            svc.start({"start": "onboard"})
        done = self.done(svc)
        self.assertEqual(done["prompt"], "I make videos for my channel, Night Physics, with ReelForge. My ReelForge "
                                         f"folder is:\n{self.root}\n\nWork in that folder from now on. First read the "
                                         "notes it has for you, and follow them: CLAUDE.md if you're Claude, AGENTS.md "
                                         "if you're another AI. Then make my first video.")
        self.assertEqual(self.lines(done["steps"]), "  1. Copy the prompt for your AI with the button below. It has "
                                                    "your ReelForge folder's path in it, so there's nothing to drag in.")
        then = self.lines(done["then"])
        self.assertIn("  2. Paste it into Claude Code (the Code tab in the Claude desktop app, or claude in a "
                      "terminal), or any other AI that can work with files on this computer. It gets to know your "
                      "channel, then makes your first video.\n  3. When it's done, it's waiting in ReelForge → "
                      "Publish", then)
        self.assertIn("Copy prompt for your AI, on ReelForge's Settings tab, copies it again any time.", then)
        self.assertNotIn("drag", then)
        # Copy puts it on the clipboard, or (when the system's can't be reached) hands it to the window for OSC 52
        with mock.patch("dashboard.desktop.copy", return_value=True) as copy:
            svc.copy_prompt()
        copy.assert_called_once_with(done["prompt"])
        self.assertNotIn('"clipboard"', out.getvalue())
        with mock.patch("dashboard.desktop.copy", return_value=False):
            svc.copy_prompt()
        sent = [json.loads(line) for line in out.getvalue().splitlines()]
        self.assertIn({"ev": "clipboard", "d": {"text": done["prompt"]}}, sent)

    def test_another_channels_prompt_points_at_its_notes_too(self):
        svc = Setup(Loop(out=io.StringIO()))
        svc.start({"start": "onboard", "new": True, "embedded": True})
        svc.made = self.another(assistant="codex")
        done = self.done(svc)
        self.assertIn(f"My ReelForge folder is:\n{self.root}\n", done["prompt"])  # the same folder for every channel
        self.assertTrue(done["prompt"].endswith(
            f"Cool Epic Facts has its own notes too, the same two files in profiles{os.sep}cool-epic-facts. Then make "
            "my first Cool Epic Facts video."))
        self.assertIn("the ReelForge folder's path (the same for every channel)", self.lines(done["steps"]))
        self.assertIn("  2. Paste it into Codex (run codex in a terminal), or any other AI that can work with files "
                      "on this computer. It gets to know Cool Epic Facts, then makes its first video.",
                      self.lines(done["then"]))

    def test_a_channel_made_with_both_ais_names_both(self):
        p = self.another(assistant=["claude", "codex"])
        self.assertEqual(S.load(p.settings)["ai"], {"assistant": ["claude", "codex"]})
        svc = Setup(Loop(out=io.StringIO()))
        svc.start({"start": "onboard", "new": True, "embedded": True})
        svc.made = p
        self.assertIn("Paste it into Claude Code (the Code tab in the Claude desktop app, or claude in a terminal) or "
                      "Codex (run codex in a terminal), or any other AI that can work with files on this computer.",
                      self.lines(self.done(svc)["then"]))
        self.assertIn("Paste this prompt into Claude Code or Codex, or any other AI", cli.next_steps(p))
        # Claude's notes say what setup asked Claude Code for, as for Claude Code alone
        self.assertIn("first-time" + chr(10) + "  setup asked Claude Code for high effort", self.notes(p.folder))

    def test_a_channel_with_videos_asks_for_its_next_one(self):
        video = self.root / "episodes" / "ep01_duck" / "final" / "ep01_duck.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"a video")
        svc = Setup(Loop(out=io.StringIO()))
        with mock.patch.object(S, "onboarded", return_value=False):
            svc.start({"start": "done"})
        done = self.done(svc)
        self.assertTrue(done["prompt"].endswith("Then make my next video."))
        self.assertIn("It gets to know your channel, then makes your next video.", self.lines(done["then"]))
        self.assertTrue(cli.next_steps().endswith("copies this prompt again any time."))
        self.assertIn("     Work in that folder from now on.", cli.next_steps())
        self.assertIn("Then make my next video.", cli.next_steps())

    def test_setup_run_again_gives_the_update_prompt_with_the_folder_in_it(self):
        # The channel was set up already (setUp wrote it), so its notes are new: the AI reads them again and says what
        # changed, rather than starting on the channel as if it were new.
        svc = Setup(Loop(out=io.StringIO()))
        svc.start({"start": "onboard"})
        done = self.done(svc)
        self.assertEqual(done["prompt"], "I make videos for my channel, Night Physics, with ReelForge, and I've just "
                                         "changed its answers in ReelForge's setup. My ReelForge folder is:\n"
                                         f"{self.root}\n\nWork in that folder. The notes it has for you are updated, "
                                         "so read them again now and follow them from now on, in place of what you "
                                         "read before: CLAUDE.md if you're Claude, AGENTS.md if you're another AI. "
                                         "Then tell me in a few lines what changed, and use it from my next video on.")
        self.assertIn("Night Physics's answers are updated.", self.lines(done["head"]))
        self.assertIn("1. Copy the prompt for your AI with the button below. It has your ReelForge folder's path in it",
                      self.lines(done["steps"]))
        then = self.lines(done["then"])
        self.assertIn("It reads the updated notes and tells you what changed, then goes by your new answers from the "
                      "next video on.", then)
        self.assertNotIn("3. ", then)
        with mock.patch("dashboard.desktop.copy", return_value=True) as copy:
            svc.copy_prompt()
        copy.assert_called_once_with(done["prompt"])
        # a new channel is never a run again, though the one it's made from was set up
        new = Setup(Loop(out=io.StringIO()))
        new.start({"start": "onboard", "new": True, "embedded": True})
        new.made = self.another()
        self.assertTrue(self.done(new)["prompt"].endswith("Then make my first Cool Epic Facts video."))
        # the terminal's next steps, after reelforge channel on a channel set up already
        steps = cli.next_steps(again=True)
        self.assertIn("Night Physics's answers are updated. Next:", steps)
        self.assertIn(f"     I make videos for my channel, Night Physics, with ReelForge, and I've just changed its "
                      f"answers in ReelForge's setup. My ReelForge folder is:\n     {self.root}\n", steps)
        self.assertIn("2. It reads the updated notes and tells you what changed", steps)

    def test_the_terminal_says_the_same_after_first_time_setup(self):
        steps = cli.next_steps()
        self.assertIn("\n  1. Paste this prompt into Claude Code, or any other AI that can work with files on this "
                      "computer. It has the ReelForge folder's path in it, so there's nothing to drag in or open first:"
                      "\n\n     I make videos for my channel, Night Physics, with ReelForge. My ReelForge folder is:\n"
                      f"     {self.root}\n\n     Work in that folder from now on.", steps)
        self.assertIn("Then make my first video.\n\n  2. It gets to know your channel, then makes your first video.\n"
                      "  3. When it's done, open ReelForge", steps)
        self.assertNotIn("drag a file", steps)
        steps = cli.next_steps(self.another())
        self.assertIn("Cool Epic Facts is ready. Next:", steps)
        self.assertIn("Then make my first Cool Epic Facts video.", steps)
        self.assertIn("  2. It gets to know Cool Epic Facts, then makes its first video.", steps)


if __name__ == "__main__":
    unittest.main()
