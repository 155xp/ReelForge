"""Backend preferences survive onboarding and reach each coding agent's instructions."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from studio import generate, paths as P, questions, settings


class BackendChoice(unittest.TestCase):
    def answers(self, **over):
        a, problems = questions.validate({"channel_name": "Test Channel", "about": "Science videos.", **over})
        self.assertEqual(problems, [])
        return a

    def test_existing_answers_and_unconfigured_settings_use_blender(self):
        self.assertEqual(self.answers()["backend"], "blender")
        self.assertEqual(generate.settings_from(self.answers())["video"]["backend"], "blender")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(settings.load(Path(tmp) / "missing.toml")["video"]["backend"], "blender")

    def test_unknown_backend_is_rejected(self):
        _, problems = questions.validate({"channel_name": "Test Channel", "about": "Science videos.",
                                          "backend": "other"})
        self.assertTrue(any(p.startswith("backend") for p in problems))

    def test_agentcut_choice_reaches_both_agents(self):
        a = self.answers(backend="agentcut")
        s = generate.settings_from(a)
        self.assertEqual(s["video"]["backend"], "agentcut")
        for assistant in ("claude", "codex"):
            text = generate.render("context.md.j2", generate.context(a, s, assistant))
            self.assertIn("default is **AI AgentCut edits**", text)
            self.assertIn('"open AgentCut and make a video about ..."', text)
            self.assertIn("-m studio agentcut schema", text)
            self.assertIn("-m studio agentcut validate", text)
            self.assertIn("docs/AGENTCUT.md", text)
            self.assertIn("https://github.com/heygen-com/hyperframes", text)
            self.assertIn("edit/index.html", text)
            self.assertIn("edit/media/", text)
            self.assertIn("--preview <seconds-within-duration>", text)
            self.assertNotIn("--stills", text)
            self.assertNotIn("agentcut.json", text)
            self.assertIn("**Build the edit:**", text)
            self.assertNotIn("**Rendering runs Blender**", text)
            self.assertLess(len(text.encode("utf-8")), 30_000)

    def test_default_blender_agents_can_discover_optional_agentcut(self):
        a = self.answers()
        s = generate.settings_from(a)
        text = generate.render("context.md.j2", generate.context(a, s, "codex"))
        self.assertIn("default is **AI Blender scenes**", text)
        self.assertIn("--backend agentcut", text)
        self.assertIn('"open AgentCut and make a video about ..."', text)
        self.assertIn("**Build the scene:**", text)

    def test_saved_choice_survives_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mine = root / "my-studio"
            patched = {"ROOT": root, "MY_STUDIO": mine, "ANSWERS": mine / "answers.json",
                       "SETTINGS": mine / "studio.toml", "BIBLE": mine / "channel-bible.md",
                       "BACKUPS": mine / "backups", "COMPLETED": root / "completed videos",
                       "DASHBOARD": root / "dashboard"}
            with mock.patch.multiple(P, **patched):
                generate.write_all(self.answers(assistant="both", backend="agentcut"))
                saved = json.loads(P.ANSWERS.read_text(encoding="utf-8"))
                self.assertEqual(saved["backend"], "agentcut")
                generate.write_all(saved)
                self.assertEqual(settings.load(P.SETTINGS)["video"]["backend"], "agentcut")
                for name in ("AGENTS.md", "CLAUDE.md"):
                    self.assertIn("default is **AI AgentCut edits**", (root / name).read_text(encoding="utf-8"))
