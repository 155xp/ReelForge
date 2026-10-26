"""The channel brief. First-time setup only asks a few questions, so its last screen asks you to drop a file about your
channel (or a description) into your AI's chat, and your AI keeps it as the channel's brief (my-studio/brief.md, in
the channel's own folder) and plans from it. These check what the AI is told, for the first channel and another one;
that the first channel's notes give every channel's videos a day, so "make today's videos" covers them all; that
changing the answers never touches a brief; and the last screen. In a scratch ReelForge folder."""

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
from studio import generate, profiles
from studio import paths as P
from studio.bridge import Loop
from studio.setup_service import Setup

KIT = Path(__file__).resolve().parent.parent
ANSWERS = {"creator": "Sam", "channel_name": "Night Physics", "about": "What-if videos with real science.",
           "platforms": ["tiktok", "youtube"], "handle_tiktok": "@nightphysics"}


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

    def steps(self, svc: Setup) -> str:
        with mock.patch.object(svc.loop, "run_worker"):
            done = svc.done_info()
        return "\n".join("".join(seg[0] for seg in line) for line in done["steps"])

    def test_the_last_screen_asks_for_the_channel_file_before_the_first_video(self):
        svc = Setup(Loop(out=io.StringIO()))
        svc.start({"start": "onboard"})
        steps = self.steps(svc)
        self.assertIn('\n  2. Say "here\'s my channel" and drag a file about it into the chat, or paste a description.'
                      "\n     Your notes, a doc, examples you like: it keeps it as your channel's brief and plans every "
                      'video from it.\n  3. Say: "', steps)
        self.assertIn('make my first video"\n  4. When it\'s done', steps)
        svc = Setup(Loop(out=io.StringIO()))
        svc.start({"start": "onboard", "new": True, "embedded": True})
        svc.made = self.another()
        steps = self.steps(svc)
        self.assertIn('  2. Say "here\'s Cool Epic Facts" and drag a file about it into the chat', steps)
        self.assertIn("it keeps it as the brief for Cool Epic Facts and plans", steps)
        self.assertIn('make my first Cool Epic Facts video"', steps)

    def test_the_terminal_says_the_same_after_first_time_setup(self):
        steps = cli.next_steps()
        self.assertIn('\n  2. Say "here\'s my channel" and drag a file about it into the chat, or paste a description '
                      "(your notes, a doc, examples you like). It keeps it as your channel's brief and plans every video "
                      'from it.\n  3. Say: "make my first video"\n  4. When it\'s done', steps)
        steps = cli.next_steps(self.another())
        self.assertIn('2. Say "here\'s Cool Epic Facts"', steps)
        self.assertIn("It keeps it as the brief for Cool Epic Facts", steps)
        self.assertIn('3. Say: "make my first Cool Epic Facts video"', steps)


if __name__ == "__main__":
    unittest.main()
