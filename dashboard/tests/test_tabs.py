"""The order of the tabs along the top (dashboard/tabs.py): Overview first and Settings and Updates last until you pick
another order on the Settings tab, the order you pick kept for every profile and made whole whatever its file says,
Publish never in it (it's the green button at the right of the header), the numbers after reelforge following it, and
the window's Python side keeping a new order, showing one another window kept, and keeping nothing in the demo. Moving
the tabs on screen is tested in ui/test/settings.test.tsx, and the Publish button in ui/test/dashboard.test.tsx."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dashboard import config, db, demo, sync, tabs
from dashboard.config import PLATFORM_KEYS
from dashboard.service import HELP, KEYS
from dashboard.settings_tab import SettingsTab
from dashboard.tests.window import Window

MOVED = ("updates", "settings", "overview", "videos", "compare", "accounts", "totals")


class Folder(unittest.TestCase):
    """A ReelForge folder of its own for the order (tabs.HERE and config.APP_DIR: the window's code and data/)."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for patch in (mock.patch.object(tabs, "HERE", self.dir), mock.patch.object(config, "APP_DIR", self.dir)):
            patch.start()
            self.addCleanup(patch.stop)

    def kept(self) -> object:
        return json.loads(tabs.order_file().read_text(encoding="utf-8"))


class OrderTest(Folder):
    def test_overview_starts_at_the_far_left_and_1_to_7_follow_the_order(self):
        self.assertEqual(tabs.order(), tabs.DEFAULT_ORDER)
        self.assertEqual(tabs.DEFAULT_ORDER, ("overview", "videos", "compare", "totals", "accounts", "settings",
                                              "updates"))  # DJ's pick (2026-10-27), with Publish now a button
        self.assertEqual(sorted(tabs.DEFAULT_ORDER + (tabs.PUBLISH,)), sorted(tabs.TAB_IDS))
        self.assertEqual([tabs.tab_for(str(i)) for i in range(1, 8)], list(tabs.DEFAULT_ORDER))
        self.assertIsNone(tabs.tab_for("8"))
        self.assertEqual(tabs.tab_for("publish"), "publish")  # by name: it has no number
        self.assertIn("[1-7 |", tabs.USAGE)

    def test_an_order_you_pick_is_kept_and_the_numbers_follow_it_but_not_the_names(self):
        self.assertEqual(tabs.save_order(list(MOVED)), MOVED)
        self.assertEqual(self.kept(), {"order": list(MOVED)})
        self.assertEqual(tabs.order(), MOVED)
        self.assertEqual([tabs.tab_for(str(i)) for i in range(1, 8)], list(MOVED))
        self.assertEqual([tabs.tab_for(w) for w in ("publish", "post", "Settings", "totals", "notifications")],
                         ["publish", "publish", "settings", "totals", "overview"])
        for nothing in ("0", "8", "9", "-1", "²", "1.5", "", "stats"):
            self.assertIsNone(tabs.tab_for(nothing), nothing)

    def test_the_default_order_again_removes_the_file_so_a_later_default_applies(self):
        tabs.save_order(list(MOVED))
        self.assertEqual(tabs.save_order(list(tabs.DEFAULT_ORDER)), tabs.DEFAULT_ORDER)
        self.assertFalse(tabs.order_file().exists())
        tabs.save_order(list(MOVED))
        self.assertEqual(tabs.save_order(None), tabs.DEFAULT_ORDER)  # Reset to default
        self.assertFalse(tabs.order_file().exists())
        self.assertEqual(tabs.save_order(None), tabs.DEFAULT_ORDER)  # and again, with nothing to remove

    def test_whatever_the_file_says_each_tab_shows_once(self):
        tabs.order_file().parent.mkdir(parents=True)
        for text in ("not JSON", '"publish"', '{"order": 3}', "[]", '{"order": ["nope"]}'):
            tabs.order_file().write_text(text, encoding="utf-8")
            self.assertEqual(tabs.order(), tabs.DEFAULT_ORDER, text)
        tabs.order_file().write_text(json.dumps({"order": ["updates", "publish", "overview", "updates", "nope", 7]}),
                                     encoding="utf-8")
        self.assertEqual(tabs.order(), ("updates", "overview", "videos", "compare", "totals", "accounts", "settings"))

    def test_an_order_kept_before_publish_had_its_button_just_loses_publish(self):
        tabs.order_file().parent.mkdir(parents=True)
        kept = ["accounts", "overview", "videos", "compare", "publish", "totals", "settings", "updates"]  # 1.0.8's
        tabs.order_file().write_text(json.dumps({"order": kept}), encoding="utf-8")
        self.assertEqual(tabs.order(), ("accounts", "overview", "videos", "compare", "totals", "settings", "updates"))
        self.assertEqual([tabs.tab_for(str(i)) for i in range(4, 8)], ["compare", "totals", "settings", "updates"])
        self.assertIsNone(tabs.tab_for("8"))
        tabs.order_file().write_text(json.dumps({"order": ["overview", "videos", "compare", "publish", "totals",
                                                           "accounts", "settings", "updates"]}), encoding="utf-8")
        self.assertEqual(tabs.order(), tabs.DEFAULT_ORDER)  # 1.0.8's default, kept by hand: today's default

    def test_a_tab_a_later_version_adds_goes_after_the_one_it_follows_by_default(self):
        older = ["updates", "settings", "overview", "videos", "compare", "publish", "accounts"]  # before Stats
        self.assertEqual(tabs.tidy(older), ("updates", "settings", "overview", "videos", "compare", "totals",
                                            "accounts"))
        self.assertEqual(tabs.tidy(tabs.DEFAULT_ORDER[1:]), tabs.DEFAULT_ORDER)  # nothing before it: first


class Side(SettingsTab):
    """The Settings tab's half of a window's Python side, on its own: what it sends the window is kept."""

    def __init__(self, demo: bool = False) -> None:
        self.demo = demo
        self.sent: list[tuple[str, object]] = []
        self.load_tab_order()

    def emit(self, event: str, data: object = None) -> None:
        self.sent.append((event, data))

    def notify(self, body: str, title: str = "", severity: str = "information", timeout: float = 5) -> None:
        self.sent.append(("toast", body))


class KeepTest(Folder):
    def test_a_new_order_is_kept_and_the_next_window_opens_with_it(self):
        here = Side()
        self.assertEqual(here.tab_order, tabs.DEFAULT_ORDER)
        self.assertEqual(here.set_tab_order(list(MOVED)), list(MOVED))
        self.assertEqual(self.kept(), {"order": list(MOVED)})
        self.assertEqual(Side().tab_order, MOVED)
        here.follow_tab_order()
        self.assertEqual(here.sent, [])  # its own change: the window shows it already
        self.assertEqual(here.set_tab_order(None), list(tabs.DEFAULT_ORDER))
        self.assertFalse(tabs.order_file().exists())

    def test_another_window_moving_a_tab_shows_here(self):
        here, there = Side(), Side()
        there.set_tab_order(list(MOVED))
        here.follow_tab_order()
        self.assertEqual(here.sent, [("order", {"order": list(MOVED)})])
        here.follow_tab_order()
        self.assertEqual(len(here.sent), 1)  # once
        there.set_tab_order(None)
        here.follow_tab_order()
        self.assertEqual(here.sent[-1], ("order", {"order": list(tabs.DEFAULT_ORDER)}))

    def test_an_order_that_cant_be_kept_goes_back_and_says_why(self):
        here = Side()
        with mock.patch.object(tabs, "save_order", side_effect=PermissionError("in use")):
            self.assertEqual(here.set_tab_order(list(MOVED)), list(tabs.DEFAULT_ORDER))
        self.assertEqual(here.sent, [("toast", "Couldn't change the tab order: in use"),
                                     ("order", {"order": list(tabs.DEFAULT_ORDER)})])
        self.assertEqual(here.tab_order, tabs.DEFAULT_ORDER)

    def test_the_demo_starts_on_the_default_order_and_keeps_nothing(self):
        tabs.save_order(list(MOVED))  # this computer's own order: not the demo's
        here = Side(demo=True)
        self.assertEqual(here.tab_order, tabs.DEFAULT_ORDER)
        backwards = list(reversed(tabs.DEFAULT_ORDER))
        self.assertEqual(here.set_tab_order(backwards), backwards)
        self.assertEqual(here.set_tab_order(list(MOVED)), list(MOVED))
        self.assertEqual(here.sent, [("toast", "Demo mode: this order isn't kept.")])  # once
        self.assertEqual(self.kept(), {"order": list(MOVED)})  # as it was
        here.follow_tab_order()
        self.assertEqual(len(here.sent), 1)


class WindowTest(Folder):
    """What the window starts with, and its help."""

    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(setattr, db, "_path", db._path)
        self.cfg = {"refresh_minutes": 0, "videos_dir": str(self.dir / "none"),
                    "episodes_dir": str(self.dir / "none"), "completed_dir": str(self.dir / "none"),
                    **{key: {} for key in PLATFORM_KEYS}}
        db.init(self.dir / "demo.db")
        demo.seed()
        for state in (sync._attempted, sync.last_errors):
            state.clear()
            self.addCleanup(state.clear)

    def test_the_window_starts_with_the_order_and_the_default(self):
        w = Window(self.cfg, demo.platforms())
        self.addCleanup(w.close)
        self.assertEqual(w.init["order"], list(tabs.DEFAULT_ORDER))
        self.assertEqual(w.init["default_order"], list(tabs.DEFAULT_ORDER))
        self.assertEqual(w.call("set_tab_order", list(MOVED)), list(MOVED))
        self.assertEqual(w.toasts(), ["Demo mode: this order isn't kept."])

    def test_the_help_has_every_tab_once_and_leaves_the_numbers_to_the_window(self):
        about = {topic[2]: topic for topic in HELP if len(topic) > 2}
        self.assertEqual(sorted(about), sorted(tabs.TAB_IDS))
        for title, text, *_ in HELP:
            self.assertNotRegex(title, r"\d", title)
            self.assertNotRegex(text, r"\(\d\)|tab \d", title)
        self.assertIn("order of the tabs", about["settings"][1])
        self.assertIn("green button", about["publish"][1])
        self.assertEqual(dict(KEYS)["1-7"], "switch tabs")
        self.assertIn("Publish", dict(KEYS)["u"])


if __name__ == "__main__":
    unittest.main()
