"""The Compare tab's Episodes list on demo data: newest first until you pick Oldest or Most views beside it (Most views
adds up each episode's views on every platform and shows them), the platform scoreboard always on top, the picked
episode still picked, and the order kept for the next window (dashboard.service). Clicking the choices is tested in
ui/test/dashboard.test.tsx."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dashboard import analytics, config, db, demo
from dashboard.tests.window import Window, plain


class EpisodeSortTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "demo.db")
        demo.seed()
        self.cfg = config.load_config()

    def window(self) -> Window:
        w = Window(self.cfg, demo.platforms(), tab="compare")
        self.addCleanup(w.close)
        w.until(lambda: w.view("episodes") is not None)
        return w

    @staticmethod
    def listed(w: Window) -> list[str]:
        return [i["id"] for i in w.view("episodes")["items"]]

    @staticmethod
    def chosen(w: Window) -> str:
        """The choice beside the list that's picked: the one that isn't a button."""
        return next(s[0].strip() for s in w.view("episodes")["sort"] if s[0].strip() and len(s) < 3)

    def test_newest_first_then_oldest_first(self):
        w = self.window()
        newest = [f"ep-{e['id']}" for e in db.episodes()]  # newest first
        self.assertEqual(self.chosen(w), "Newest")
        self.assertEqual(self.listed(w), ["board", *newest])
        w.call("sort_episodes", "oldest")
        self.assertEqual(self.chosen(w), "Oldest")
        self.assertEqual(self.listed(w), ["board", *reversed(newest)])

    def test_most_views_adds_up_every_platform_and_shows_it(self):
        w = self.window()
        w.call("sort_episodes", "views")
        self.assertEqual(self.chosen(w), "Most views")
        views: dict[int, int] = {}
        for p in db.posts_latest():
            views[p["episode_id"]] = views.get(p["episode_id"], 0) + (p["views"] or 0)
        ids = self.listed(w)[1:]
        totals = [views[int(i[3:])] for i in ids]
        self.assertEqual(totals, sorted(totals, reverse=True))
        self.assertGreater(totals[0], totals[-1])
        for item, total in zip(w.view("episodes")["items"][1:], totals):
            line = plain(item["lines"][0])
            self.assertIn(f" {analytics.fmt_num(total)} ", line)
            self.assertLessEqual(len(line), 38, line)  # with the platforms on it, inside the 44-column panel

    def test_the_scoreboard_stays_on_top_and_the_picked_episode_stays_picked(self):
        w = self.window()
        last = self.listed(w)[-1]
        w.call("pick_episode", last)
        for key in ("views", "oldest", "newest"):
            w.call("sort_episodes", key)
            self.assertEqual(self.listed(w)[0], "board")
            self.assertEqual(w.view("episodes")["selected"], last)

    def test_the_next_window_keeps_the_order(self):
        first = self.window()
        first.call("sort_episodes", "views")
        first.close()
        w = self.window()
        self.assertEqual(self.chosen(w), "Most views")
        w.call("sort_episodes", "nonsense")  # not one of the choices: nothing changes
        self.assertEqual(self.chosen(w), "Most views")
        self.assertEqual(db.get_meta("episode_sort"), "views")


if __name__ == "__main__":
    unittest.main()
