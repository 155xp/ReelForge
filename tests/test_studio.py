"""Quick checks for onboarding, settings and captions (no Blender needed).

  .venv\\Scripts\\python -m unittest discover tests
"""

import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from studio import formats, generate, jsonfmt, logo, questions, settings


DEFAULTS_ONLY = Path(__file__).with_name("no-such-studio.toml")    # the defaults, whatever my-studio/ holds


def answers(**over):
    a = {"channel_name": "Test Channel", "about": "What-if videos with real science.", "creator": "Sam"}
    a.update(over)
    return a


class Questions(unittest.TestCase):
    def test_defaults_fill_in(self):
        a, problems = questions.validate(answers())
        self.assertEqual(problems, [])
        self.assertEqual(a["format"], "doubling")
        self.assertEqual(a["series"], "Doubling")
        self.assertEqual(a["platforms"], list(settings.PLATFORMS))

    def test_required_and_conditional(self):
        _, problems = questions.validate({})
        self.assertTrue(any(p.startswith("channel_name") for p in problems))
        _, problems = questions.validate(answers(format="custom"))
        self.assertTrue(any(p.startswith("custom_format") for p in problems))
        _, problems = questions.validate(answers(length="custom", length_custom="banana"))
        self.assertTrue(any(p.startswith("length_custom") for p in problems))

    def test_coerce(self):
        q = questions.BY_KEY
        self.assertEqual(questions.coerce(q["platforms"], "1, 3"), ["tiktok", "instagram"])
        self.assertEqual(questions.coerce(q["format"], "2"), "disappear")
        self.assertIs(questions.coerce(q["hashtags_on_x"], "y"), True)
        with self.assertRaises(ValueError):
            questions.coerce(q["max_hashtags"], "lots")

    def test_describe_is_json(self):
        json.dumps(questions.describe())


class Captions(unittest.TestCase):
    def test_platform_rules(self):
        s = settings.load(DEFAULTS_ONLY)
        posts = settings.post_texts("What if your coffee doubled every 2 seconds?", ["whatif", "fyp", "physics"], s)
        self.assertTrue(posts["tiktok"].split()[-3] == "#fyp")
        self.assertNotIn("#", posts["x"])
        self.assertTrue(posts["youtube"].startswith("What if your coffee doubled every 2 seconds?\n\n#"))

    def test_max_hashtags(self):
        s = settings.load(DEFAULTS_ONLY)
        s["captions"]["max_hashtags"] = 2
        tags = settings.platform_tags("tiktok", "a b c d", s)
        self.assertEqual(tags, ["fyp", "a"])


class Generate(unittest.TestCase):
    def check(self, **over):
        a, problems = questions.validate(answers(**over))
        self.assertEqual(problems, [])
        s = generate.settings_from(a)
        tomllib.loads(settings.dump_toml(s, generate.SETTINGS_COMMENTS))
        for who in ("claude", "codex"):
            text = generate.render("context.md.j2", generate.context(a, s, who))
            self.assertIn("Test Channel", text)
            self.assertIn("Publish (tab 4)", text)
            self.assertLess(len(text.encode("utf-8")), 30_000)
        generate.render("channel-bible.md.j2", generate.context(a, s, "claude"))
        return s

    def test_every_format(self):
        for key in formats.FORMATS:
            extra = {"custom_format": "Five weird animals, ranked.", "series": "Top 5"} if key == "custom" else {}
            self.check(format=key, **extra)

    def test_variants(self):
        s = self.check(assistant="codex", platforms=["youtube"], length="30-45", loudness="loud", quality="fast",
                       cadence="1/week", hud=False)
        self.assertEqual(s["video"]["min_seconds"], 30.0)
        self.assertEqual(s["sound"]["target_lufs"], -15.0)
        self.assertFalse(s["ai"]["ultracode"])


class JsonFormat(unittest.TestCase):
    def test_round_trip(self):
        spec = {"lines": [[1.0, 2.0, "A line."]], "hud": {"chapters": [{"from": 0, "to": 2, "label": "X"}]},
                "nested": {"a": [1, 2, 3], "b": {"c": "d"}}}
        self.assertEqual(json.loads(jsonfmt.dumps(spec)), spec)


class Logo(unittest.TestCase):
    def test_sizes_and_colours(self):
        big, anvil = logo.big(), logo.anvil()
        self.assertEqual(len(big), 16)
        self.assertEqual({len(r) for r in big}, {logo.width(big)})
        self.assertLessEqual(logo.width(big), 110)              # fits a 120-column terminal inside the box
        self.assertEqual(logo.rows(anvil), 3)
        self.assertEqual(set("".join(big)) - {"."}, {"W", "R"})   # white "reel", red "forge", nothing else

    def test_terminal_cells(self):
        lines = logo.ansi(logo.big())
        self.assertEqual(len(lines), 8)
        self.assertTrue(all(line.endswith("\x1b[0m") for line in lines))
        top, bottom = logo.cells(["W.", ".R"])[0]
        self.assertEqual(top, ("▀", logo.WHITE, None))
        self.assertEqual(bottom, ("▄", logo.RED, None))


class SystemChanges(unittest.TestCase):
    """The reelforge command and the background stats job never touch the system in tests (STUDIO_DRY_SYSTEM)."""

    def setUp(self):
        self._old = os.environ.get("STUDIO_DRY_SYSTEM")
        os.environ["STUDIO_DRY_SYSTEM"] = "1"

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STUDIO_DRY_SYSTEM", None)
        else:
            os.environ["STUDIO_DRY_SYSTEM"] = self._old

    def test_dry_runs(self):
        from studio import command, stats_schedule
        self.assertIn("dry run", command.enable())
        self.assertIn("dry run", command.disable())
        self.assertIn("dry run", stats_schedule.enable())
        self.assertIn("dry run", stats_schedule.disable())

    def test_background_stats_setting(self):
        a, _ = questions.validate(answers())
        self.assertIs(generate.settings_from(a)["platforms"]["background_stats"], True)
        a, _ = questions.validate(answers(background_stats=False))
        self.assertIs(generate.settings_from(a)["platforms"]["background_stats"], False)


class SetupPlan(unittest.TestCase):
    def test_missing_tools_are_listed(self):
        from studio import setup_flow
        with mock.patch.object(setup_flow.tools, "find_blender", return_value=None), \
                mock.patch.object(setup_flow.tools, "find_ffmpeg", return_value=None), \
                mock.patch.object(setup_flow.command, "status", return_value="off"):
            items = {i.key: i for i in setup_flow.plan()}
        self.assertFalse(items["blender"].ready)
        self.assertEqual(items["blender"].size_mb, 400)
        self.assertFalse(items["ffmpeg"].ready)
        self.assertFalse(items["command"].ready)
        self.assertIn(items["blender"], setup_flow.todo(list(items.values())))


if __name__ == "__main__":
    unittest.main()
