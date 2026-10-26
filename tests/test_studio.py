"""Quick checks for onboarding, settings and captions (no Blender needed).

  .venv\\Scripts\\python -m unittest discover tests
"""

import json
import os
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from studio import formats, generate, jsonfmt, logo, logo_art, questions, settings


DEFAULTS_ONLY = Path(__file__).with_name("no-such-studio.toml")    # the defaults, whatever my-studio/ holds
NO_MARKER = Path(__file__).with_name("no-such-marker.txt")         # a normal copy, even when run in a test copy


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
        self.assertEqual(a["platforms"], list(settings.RECOMMENDED))

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

    def test_custom_length_accepts_the_ways_people_write_it(self):
        for text in ("20-30", "20 to 30", "45s-60s", "20-30 seconds", "20–30", "61 - 75s"):
            _, problems = questions.validate(answers(length="custom", length_custom=text))
            self.assertEqual(problems, [], text)
        self.assertEqual(questions.parse_length("75-61 seconds"), (61.0, 75.0))
        self.assertEqual(questions.parse_length("30"), (30.0, 30.0))
        with self.assertRaises(ValueError):
            questions.parse_length("1m-2m")

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
        self.assertEqual(s["ai"], {"assistant": "codex", "quality": "fast"})  # picked in Advanced settings
        a, _ = questions.validate(answers(quality="ultra"))
        self.assertEqual(generate.settings_from(a)["ai"]["quality"], "high")  # anything else: the standard


class JsonFormat(unittest.TestCase):
    def test_round_trip(self):
        spec = {"lines": [[1.0, 2.0, "A line."]], "hud": {"chapters": [{"from": 0, "to": 2, "label": "X"}]},
                "nested": {"a": [1, 2, 3], "b": {"c": "d"}}}
        self.assertEqual(json.loads(jsonfmt.dumps(spec)), spec)


class Logo(unittest.TestCase):
    def test_sizes_and_colours(self):
        for mode in ("1", "0"):                                  # quadrants (Windows Terminal) and half blocks
            with mock.patch.dict(os.environ, {"REELFORGE_QUADRANTS": mode}):
                big, anvil = logo.big(), logo.anvil()
                self.assertEqual(logo.rows(big), 8)
                self.assertEqual({len(r) for r in big.grid}, {logo.width(big) * big.sub_w})
                self.assertLessEqual(logo.width(big), 110)       # fits a 120-column terminal inside the box
                self.assertEqual(logo.rows(anvil), 3)
                self.assertEqual(set("".join(big.grid)) - {"."}, {"W", "R"})   # white "reel", red "forge"

    def test_big_logo_in_ten_clean_pieces(self):
        """The anvil and the nine letters each stay in one piece, apart from the others (corners count as touching),
        so nothing sticks out on its own and no two letters run together."""
        def pieces(grid):
            seen, count = set(), 0
            for y, line in enumerate(grid):
                for x, ch in enumerate(line):
                    if ch == "." or (y, x) in seen:
                        continue
                    count += 1
                    stack = [(y, x)]
                    seen.add((y, x))
                    while stack:
                        cy, cx = stack.pop()
                        for ny in (cy - 1, cy, cy + 1):
                            for nx in (cx - 1, cx, cx + 1):
                                if (0 <= ny < len(grid) and 0 <= nx < len(line) and grid[ny][nx] != "."
                                        and (ny, nx) not in seen):
                                    seen.add((ny, nx))
                                    stack.append((ny, nx))
            return count

        for grid in (logo_art.BIG_QUAD, logo_art.BIG_HALF):
            self.assertEqual(pieces(grid), 10)
            self.assertNotEqual(set(grid[0]), {"."})                 # the art fills its box: the l and f reach the top
            self.assertNotEqual(set(grid[-1]), {"."})                # and the g's tail the bottom
            self.assertNotEqual({line[-1] for line in grid}, {"."})  # no empty columns on the right
        q = logo_art.BIG_QUAD                                        # a quadrant cell has one colour, so none mixes
        self.assertFalse([(x, y) for y in range(0, len(q), 2) for x in range(0, len(q[0]), 2)
                          if len({q[y + dy][x + dx] for dy in (0, 1) for dx in (0, 1)} - {"."}) > 1])

    def test_hand_drawn_anvil(self):
        for art in (logo.Art(logo.ANVIL_QUAD, 2, 2), logo.Art(logo.ANVIL_HALF, 1, 2)):
            self.assertEqual(len(art.grid), 3 * art.sub_h)                       # the header's 3 rows
            self.assertEqual({len(r) for r in art.grid}, {logo.width(art) * art.sub_w})
            self.assertEqual(set("".join(art.grid)), {"W", "."})                 # a white anvil
            self.assertLessEqual(logo.width(art), 11)                             # no wider than before

    def test_windows_terminal(self):
        def found(env, window=""):
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(logo, "_console_window_class", return_value=window):
                return logo.windows_terminal()

        self.assertTrue(found({"WT_SESSION": "1"}))                                # started by Windows Terminal
        self.assertTrue(found({}, "PseudoConsoleWindow"))                         # handed to it: desktop shortcut
        self.assertFalse(found({}, "ConsoleWindowClass"))                         # the old Windows console
        self.assertFalse(found({"TERM_PROGRAM": "vscode"}, "PseudoConsoleWindow"))   # another modern terminal
        with mock.patch.dict(os.environ, {"REELFORGE_QUADRANTS": "0", "WT_SESSION": "1"}):
            self.assertFalse(logo.quadrants())                                    # the override still wins

    def test_terminal_cells(self):
        with mock.patch.dict(os.environ, {"REELFORGE_QUADRANTS": "1"}):
            lines = logo.ansi(logo.big())
        self.assertEqual(len(lines), 8)
        self.assertTrue(all(line.endswith("\x1b[0m") for line in lines))
        top, bottom = logo.cells(logo.Art(["W.", ".R"], 1, 2))[0]
        self.assertEqual(top, ("▀", logo.WHITE, None))
        self.assertEqual(bottom, ("▄", logo.RED, None))
        # quadrants: top-left and bottom-right, then everything but the top-right
        (a, b), = logo.cells(logo.Art(["W.W.", ".WWW"], 2, 2))
        self.assertEqual(a, ("▚", logo.WHITE, None))
        self.assertEqual(b, ("▙", logo.WHITE, None))


class SystemChanges(unittest.TestCase):
    """The reelforge command and the background stats job never touch the system in tests (STUDIO_DRY_SYSTEM)."""

    def setUp(self):
        from studio import paths as P

        self._old = os.environ.get("STUDIO_DRY_SYSTEM")
        os.environ["STUDIO_DRY_SYSTEM"] = "1"
        patch = mock.patch.object(P, "TEST_COPY", NO_MARKER)
        patch.start()
        self.addCleanup(patch.stop)

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


class StatsJobOwner(unittest.TestCase):
    """The hourly job belongs to the folder whose refresh.pyw it runs: a second copy (a test install) never takes
    it over or turns it off while that folder is there, and takes it over once that folder is gone."""

    def setUp(self):
        import tempfile

        from studio import paths as P
        from studio import stats_schedule

        self.s = stats_schedule
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.ours, self.theirs = root / "Test copy" / "dashboard", root / "ReelForge" / "dashboard"
        for d in (self.ours, self.theirs):
            d.mkdir(parents=True)
            (d / "refresh.pyw").write_text("", encoding="utf-8")
        (root / "pythonw.exe").write_text("", encoding="utf-8")
        self.calls: list[str] = []
        for patch in (mock.patch.dict(os.environ, {"STUDIO_DRY_SYSTEM": ""}),
                      mock.patch.object(P, "TEST_COPY", NO_MARKER),
                      mock.patch.object(P, "WINDOWS", True), mock.patch.object(P, "MAC", False),
                      mock.patch.object(P, "ROOT", self.ours.parent), mock.patch.object(P, "DASHBOARD", self.ours),
                      mock.patch.object(stats_schedule, "_python", return_value=root / "pythonw.exe"),
                      mock.patch.object(stats_schedule, "_ps", side_effect=self._ps)):
            patch.start()
            self.addCleanup(patch.stop)
        self.job: Path | None = None

    def _ps(self, script: str):
        self.calls.append(script)
        if "Get-ScheduledTask" in script:
            out = f'job:"{self.job}"' if self.job is not None else ""
        else:
            out = "ok"
        return mock.Mock(returncode=0, stdout=out + "\n", stderr="")

    def changed(self) -> bool:
        return any("Register-ScheduledTask" in c or "Unregister-ScheduledTask" in c for c in self.calls)

    def test_no_job(self):
        self.assertEqual(self.s.status(), "off")
        self.assertIn("every 60 minutes", self.s.enable())
        self.assertTrue(self.changed())

    def test_our_job(self):
        self.job = self.ours / "refresh.pyw"
        self.assertEqual(self.s.status(), "on")
        self.assertEqual(self.s.disable(), "Background stats are off.")
        self.assertTrue(self.changed())

    def test_another_copys_job_is_left_alone(self):
        self.job = self.theirs / "refresh.pyw"
        self.assertEqual(self.s.status(), "other")
        self.assertTrue(self.s.enable().startswith(self.s.ELSEWHERE))
        self.assertIn(str(self.theirs.parent), self.s.disable())
        self.assertFalse(self.changed())

    def test_a_gone_copys_job_moves_here(self):
        self.job = self.theirs.parent.parent / "Deleted" / "dashboard" / "refresh.pyw"
        self.assertEqual(self.s.status(), "other")
        self.assertIn("every 60 minutes", self.s.enable())
        self.assertTrue(self.changed())


class TestCopy(unittest.TestCase):
    """A folder with TEST-COPY.txt in it is a test copy: it leaves the reelforge command, the hourly stats job and
    the desktop shortcut alone, even without STUDIO_DRY_SYSTEM."""

    def setUp(self):
        import tempfile

        from studio import command, setup_flow, stats_schedule
        from studio import paths as P

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.marker = Path(tmp.name) / "TEST-COPY.txt"
        self.marker.write_text("a test copy", encoding="utf-8")
        touched = AssertionError("a test copy changed the computer")
        for patch in (mock.patch.dict(os.environ, {"STUDIO_DRY_SYSTEM": ""}),
                      mock.patch.object(P, "TEST_COPY", self.marker),
                      mock.patch.object(command, "_win_set_user_path", side_effect=touched),
                      mock.patch.object(stats_schedule, "_ps", side_effect=touched),
                      mock.patch.object(setup_flow, "make_shortcut", side_effect=touched),
                      mock.patch("subprocess.run", side_effect=touched)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_the_marker_makes_it_a_test_copy(self):
        from studio import paths as P

        self.assertTrue(P.test_copy())
        self.assertTrue(P.dry_system())
        self.marker.unlink()
        self.assertFalse(P.test_copy())
        self.assertFalse(P.dry_system())

    def test_nothing_on_the_computer_changes(self):
        import contextlib
        import io

        from studio import command, setup_flow, stats_schedule

        self.assertIn("test copy", command.enable())
        self.assertIn("test copy", command.disable())
        self.assertTrue(stats_schedule.enable().startswith(stats_schedule.TEST_COPY))
        self.assertIn(stats_schedule.TEST_COPY, stats_schedule.disable())
        self.assertEqual(stats_schedule.status(), "off")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            stats_schedule.main(["status"])
        self.assertIn(stats_schedule.TEST_COPY, out.getvalue())
        shortcut = setup_flow.Item("shortcut", "Desktop shortcut", "a ReelForge icon on your desktop", False)
        self.assertIn("test copy", setup_flow.apply(shortcut))


class HalfMadeSetup(unittest.TestCase):
    """A setup that stopped part way (its window closed while Python was making .venv) leaves a .venv that has
    Python but no pip and no packages. Opening ReelForge then asks the launchers to repair it (exit code 3) instead
    of crashing on the first import, and setup makes that .venv again."""

    ROOT = Path(__file__).resolve().parent.parent

    @classmethod
    def setUpClass(cls):
        import subprocess
        import sys
        import tempfile

        cls.tmp = tempfile.TemporaryDirectory()
        venv = Path(cls.tmp.name) / ".venv"
        base = getattr(sys, "_base_executable", sys.executable)
        subprocess.run([base, "-m", "venv", "--without-pip", str(venv)], check=True, capture_output=True)
        cls.bare = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def launcher(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("reelforge_launcher", self.ROOT / "bin" / "reelforge.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)         # its checks run only when it's run as the program
        return module

    def test_reelforge_on_a_bare_python_asks_for_repair(self):
        import subprocess

        r = subprocess.run([str(self.bare), str(self.ROOT / "bin" / "reelforge.py")], capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(r.returncode, self.launcher().REPAIR, r.stdout + r.stderr)
        self.assertIn("stopped part way", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_setup_makes_that_venv_again(self):
        import sys

        from studio import bootstrap

        with mock.patch.object(bootstrap, "VENV_PY", self.bare):
            self.assertFalse(bootstrap._healthy())
        with mock.patch.object(bootstrap, "VENV_PY", Path(sys.executable)):    # the tests' own Python has pip
            self.assertTrue(bootstrap._healthy())

    def test_the_package_list_keeps_up_with_requirements(self):
        import re

        launcher = self.launcher()
        imported_as = {"pillow": "PIL"}
        wanted = set()
        for line in (self.ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            if m := re.match(r"\s*([A-Za-z0-9_.-]+)", line.split("#")[0]):
                wanted.add(imported_as.get(m.group(1).lower(), m.group(1).lower()))
        self.assertLessEqual(wanted, set(launcher.PACKAGES))
        self.assertEqual(launcher.missing(), [])          # the tests' own Python has them all


class SetupPlan(unittest.TestCase):
    def test_missing_tools_are_listed(self):
        from studio import setup_flow
        with mock.patch.object(setup_flow.tools, "find_blender", return_value=None), \
                mock.patch.object(setup_flow.tools, "blender_downloadable", return_value=True), \
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
