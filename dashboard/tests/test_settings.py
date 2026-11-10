"""The Settings tab's On this computer panel (dashboard/settings_tab.py): Background refresh, the hourly stats read, has
a switch wherever this window can turn it on and off, and the switch says which it wants (pressing it twice the same
way leaves it as asked, not flipped back); the other rows keep their buttons. Restart closes the window with exit code
75, which the launchers take to start ReelForge again, and the window's launcher says it's restarting, not updating.
Copy prompt for your AI, under the channel's answers, copies the prompt that starts your AI on the channel. Pressing
them on screen is tested in ui/test/settings.test.tsx."""

from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest import mock

from dashboard import __main__ as launcher
from dashboard import config, db, demo, desktop, videos
from dashboard.settings_tab import RESTART, SettingsTab
from dashboard.tests.window import Window
from studio import command, shortcut, stats_schedule, tui, ui
from studio import paths as P

ON = "on: your stats update every hour, even with ReelForge closed"
OFF = "off: your stats update only while ReelForge is open"


def computer(stack: ExitStack, stats: Callable[[], str]) -> None:
    """A computer ReelForge may change (not a test copy, not STUDIO_DRY_SYSTEM), with its look-ups made up: the hourly
    job's state from `stats`, the reelforge command on and ReelForge's icon there."""
    for patch in (mock.patch.object(P, "test_copy", lambda: False), mock.patch.object(P, "dry_system", lambda: False),
                  mock.patch.object(stats_schedule, "status", stats), mock.patch.object(command, "status", lambda: "on"),
                  mock.patch.object(shortcut, "label", lambda: ("ReelForge's icon", "open ReelForge without typing a "
                                                                "command", None)),
                  mock.patch.object(shortcut, "ours", lambda: True)):
        stack.enter_context(patch)


class RowsTest(unittest.TestCase):
    def rows(self, stats: str) -> list[dict]:
        with ExitStack() as stack:
            computer(stack, lambda: stats)
            return SettingsTab.computer_rows(SimpleNamespace(demo=False))

    def test_background_refresh_is_a_switch_for_the_hourly_stats_read(self):
        on = self.rows("on")
        self.assertEqual([r["label"] for r in on], ["Background refresh", "The reelforge command", "ReelForge's icon",
                                                    "ReelForge's folder"])
        self.assertEqual({k: on[0][k] for k in ("key", "on", "switch", "button", "value")},
                         {"key": "stats", "on": True, "switch": True, "button": "", "value": ON})
        off = self.rows("off")[0]
        self.assertEqual((off["on"], off["switch"], off["value"]), (False, True, OFF))
        self.assertEqual([r["button"] for r in on[1:3]], ["Turn off", f"Move to the {desktop.BIN}"])  # unchanged

    def test_the_folder_is_green_in_its_own_folder_and_has_move_where_it_can_go_there(self):
        from studio import move

        opens = f"Open in {desktop.FILES}"   # always there, wherever ReelForge is
        with mock.patch.object(move, "home", lambda: P.ROOT):
            row = self.rows("on")[-1]
        self.assertEqual({k: row[k] for k in ("key", "on", "button", "move", "value")},
                         {"key": "folder", "on": True, "button": opens, "move": "", "value": str(P.ROOT)})
        with mock.patch.object(move, "home", lambda: Path(tempfile.gettempdir()) / "ReelForge"):
            with mock.patch.object(move, "problem", lambda *a, **k: ""):   # somewhere else, and it can go there
                row = self.rows("on")[-1]
            self.assertEqual((row["on"], row["button"], row["move"], row["value"]), (False, opens, "Move…", str(P.ROOT)))
            with mock.patch.object(move, "problem", lambda *a, **k: "a test copy stays where it is"):
                row = self.rows("on")[-1]
            self.assertEqual((row["on"], row["button"], row["move"], row["value"]), (False, opens, "", str(P.ROOT)))
        demo = SettingsTab.computer_rows(SimpleNamespace(demo=True))[-1]
        self.assertEqual((demo["key"], demo["on"], demo["button"], demo["move"]), ("folder", True, opens, ""))
        self.assertIn("you", demo["value"])   # made up, like the rest of the demo

    def test_open_opens_reelforges_own_folder_and_the_demo_only_says_so(self):
        notes = []
        tab = SimpleNamespace(demo=False, notify=lambda msg, **k: notes.append(msg))
        with mock.patch.object(desktop, "open_folder") as opened:
            SettingsTab.open_reelforge_folder(tab)
            opened.assert_called_once_with(P.ROOT)
            self.assertEqual(notes, [])
            with mock.patch.object(desktop, "open_folder", side_effect=OSError("no Explorer")):
                SettingsTab.open_reelforge_folder(tab)
            self.assertIn("no Explorer", notes[-1])
            tab.demo = True
            SettingsTab.open_reelforge_folder(tab)
            opened.assert_called_once()   # the demo opens nothing
            self.assertIn(desktop.FILES, notes[-1])

    def test_no_switch_where_this_window_cant_change_it(self):
        for state, said in (("other", "on, for another ReelForge folder"),
                            ("unsupported", "not available on this computer")):
            row = self.rows(state)[0]
            self.assertEqual((row["switch"], row["button"], row["value"]), (False, "", said))
        with mock.patch.object(P, "test_copy", lambda: True):  # a test copy leaves the computer's job alone
            row = SettingsTab.computer_rows(SimpleNamespace(demo=False))[0]
        self.assertEqual((row["label"], row["switch"], row["value"]), ("Background refresh", False,
                                                                       "left alone in a test copy"))

    def test_the_demo_shows_it_on(self):
        row = SettingsTab.computer_rows(SimpleNamespace(demo=True))[0]
        self.assertEqual((row["label"], row["on"], row["switch"], row["value"]), ("Background refresh", True, True, ON))


class ToggleTest(unittest.TestCase):
    def test_the_switch_asks_for_on_or_off_and_a_button_for_the_other_one(self):
        done = []
        with mock.patch.object(stats_schedule, "enable", lambda: done.append("on") or "on"), \
                mock.patch.object(stats_schedule, "disable", lambda: done.append("off") or "off"), \
                mock.patch.object(stats_schedule, "status", lambda: "on"):
            SettingsTab._toggle("stats", False)
            SettingsTab._toggle("stats", False)  # pressed off twice: off, not back on
            SettingsTab._toggle("stats", True)
            SettingsTab._toggle("stats")  # a button: whichever it isn't (it's on, so off)
        self.assertEqual(done, ["off", "off", "on", "off"])


class WindowTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "demo.db")
        demo.seed()
        self.w = Window(config.load_config(), demo.platforms(), tab="settings")
        self.addCleanup(self.w.close)

    def stats_row(self) -> dict | None:
        rows = (self.w.view("settings") or {}).get("computer")
        return rows[0] if rows else None

    def test_the_demo_changes_nothing(self):
        with mock.patch.object(stats_schedule, "disable") as off:
            self.w.call("settings_toggle", "stats", False)
            self.w.pump(0.3)
        off.assert_not_called()
        self.assertIn("Demo mode: nothing is changed.", self.w.toasts())

    def test_the_switch_turns_the_hourly_read_off_and_on_again(self):
        w = self.w
        self.assertTrue(w.until(lambda: self.stats_row() is not None))
        self.assertTrue(self.stats_row()["on"])
        job = {"on": True}

        def turn(on: bool) -> str:
            job["on"] = on
            return "Your stats will update every 60 minutes." if on else "Background stats are off."

        with ExitStack() as stack:
            computer(stack, lambda: "on" if job["on"] else "off")
            stack.enter_context(mock.patch.object(stats_schedule, "enable", lambda: turn(True)))
            stack.enter_context(mock.patch.object(stats_schedule, "disable", lambda: turn(False)))
            w.svc.demo = False  # as on a channel that's set up, with the computer's look-ups made up above
            w.forget()
            w.call("settings_toggle", "stats", False)
            self.assertTrue(w.until(lambda: (self.stats_row() or {}).get("on") is False, 10), w.sent("settings"))
            self.assertFalse(job["on"])
            self.assertEqual(self.stats_row()["value"], OFF)
            self.assertIn("Background stats are off.", w.toasts())
            w.call("settings_toggle", "stats", True)
            self.assertTrue(w.until(lambda: (self.stats_row() or {}).get("on") is True, 10), w.sent("settings"))
            self.assertTrue(job["on"])
            self.assertEqual(self.stats_row()["value"], ON)

    def test_copy_prompt_for_your_ai_copies_the_prompt_first_time_setup_gave_you(self):
        with mock.patch.object(desktop, "copy", return_value=True) as copy:
            self.w.call("copy_ai_prompt")
            copy.assert_not_called()  # the demo's channel is made up: nothing to copy
            self.assertIn("In your own ReelForge, this copies the prompt that starts your AI on your channel.",
                          self.w.toasts())
            self.w.svc.demo = False  # as on a channel that's set up
            with mock.patch("studio.settings.load", lambda path=None: {"channel": {"name": "Night Physics"}}), \
                    mock.patch.object(videos, "find", lambda cfg: []):
                self.w.call("copy_ai_prompt")
            first = copy.call_args.args[0]
            with mock.patch("studio.settings.load", lambda path=None: {"channel": {"name": "Night Physics"}}), \
                    mock.patch.object(videos, "find", lambda cfg: [Path("ep01.mp4")]):
                self.w.call("copy_ai_prompt")
            next_ = copy.call_args.args[0]
        self.assertTrue(first.startswith("I make videos for my channel, Night Physics, with ReelForge. My ReelForge "
                                         f"folder is:\n{P.ROOT}\n\nWork in that folder from now on."))
        self.assertTrue(first.endswith("Then make my first video."))
        self.assertTrue(next_.endswith("Then make my next video."))  # it has made one already
        self.assertIn("Paste it into Claude Code, Codex or any AI that can work with files on this computer.",
                      self.w.toasts())

    def test_restart_closes_the_window_for_the_launcher_to_open_again(self):
        self.w.call("restart")
        self.assertTrue(self.w.until(lambda: bool(self.w.sent("exit"))))
        self.assertEqual(self.w.sent("exit"), [{"code": RESTART, "result": {"restart": True}}])
        self.assertEqual(RESTART, 75)  # what bin/reelforge.cmd and bin/reelforge start ReelForge again on
        self.assertIn("Restarting ReelForge…", self.w.toasts())


class LauncherTest(unittest.TestCase):
    """dashboard/__main__.py main: what it says when the window closes with 75, before the launcher opens it again."""

    def said(self, result: object) -> tuple[int, str]:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        out = io.StringIO()
        with mock.patch.object(config, "load_config", lambda: {}), \
                mock.patch.object(config, "APP_DIR", Path(tmp.name) / "dashboard"), \
                mock.patch.object(tui, "set_title", lambda title: None), \
                mock.patch.object(launcher, "_terminal_profile", lambda: None), \
                mock.patch.object(ui, "run", lambda screen, options: (75, result)), \
                mock.patch("studio.profiles.get", lambda key: True), redirect_stdout(out):
            code = launcher.main([])
        return code, out.getvalue().strip()

    def test_restart_says_restarting_and_an_update_says_it_updated(self):
        self.assertEqual(self.said({"restart": True}), (75, "Restarting ReelForge…"))
        self.assertEqual(self.said(None), (75, "ReelForge updated itself; starting it again…"))


if __name__ == "__main__":
    unittest.main()
