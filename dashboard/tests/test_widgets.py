"""The Overview's cards and titles never cut anything off, and demo mode's made-up numbers hang together
(dashboard.widgets, dashboard.demo)."""

from __future__ import annotations

import asyncio
import statistics
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from rich.text import Text

from dashboard import analytics, db, demo, trends, widgets

VALUES = {"followers": 12_900, "views": 1_234_567, "likes": 98_765}
CHANGES = {"followers": 1_030, "views": 19_400, "likes": -40}


class CardTest(unittest.TestCase):
    def test_short_numbers(self):
        for n, text in ((None, "—"), (999, "999"), (1_030, "1K"), (9_940, "9.9K"), (12_900, "13K"),
                        (999_600, "1M"), (1_234_567, "1.2M"), (-19_400, "-19K")):
            self.assertEqual(widgets.short_num(n), text)

    def test_card_lines_always_fit(self):
        for width in range(0, 60):
            for line in widgets.card_lines(VALUES, CHANGES, width):
                self.assertLessEqual(line.cell_len, width, (width, line.plain))
                self.assertNotIn("…", line.plain)

    def test_card_lines_shorten_in_order(self):
        def lines(width):
            return [line.plain for line in widgets.card_lines(VALUES, CHANGES, width)]

        self.assertEqual(lines(40)[0], "  12.9K followers +1.03K 24h")  # room for everything
        self.assertEqual(lines(24)[0], "12.9K followers +1.03K")  # the " 24h" goes first
        self.assertEqual(lines(21), ["12.9K followers +1K", "1.23M views     +19K", "98.8K likes     −40"])
        self.assertEqual(lines(13), ["13K followers", "1.2M views", "99K likes"])  # labels outlast the changes
        self.assertEqual(lines(5), [" 13K", "1.2M", " 99K"])

    def test_messages_wrap_instead_of_cutting_off(self):
        text = Text("not tracking yet\nAccounts tab: add your handle")
        self.assertEqual([t.plain for t in widgets.wrap_lines(text, 20)],
                         ["not tracking yet", "Accounts tab: add", "your handle"])

    def test_titles_drop_whole_parts(self):
        parts = [(Text("LIKES  "), 0), (Text("198.6K total   "), 0), (Text("+38K in 24h"), 1)]
        self.assertEqual(widgets.fit(parts, 30).plain, "LIKES  198.6K total   ")
        self.assertEqual(widgets.fit(parts, 12).plain, "LIKES  ")  # not "LIKES  198.6"


class DemoTest(unittest.TestCase):
    """Demo mode's history in a scratch database."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "demo.db")
        demo.seed()

    def test_totals_add_up(self):
        posts = db.posts_latest()
        for key, row in db.latest_accounts().items():
            self.assertEqual(row["views"], sum(p["views"] for p in posts if p["platform"] == key))
            self.assertGreater(row["followers"], 0)

    def test_the_last_day_has_spikes_and_quiet_nights(self):
        now = analytics.now()
        fr = trends.frame("24h", now)
        since = (now - timedelta(days=3)).isoformat(timespec="seconds")
        per_hour = [0.0] * fr.n
        for key in demo.PROFILES:
            for i, g in enumerate(trends.bucket(trends.points(db.account_series(key, since), "views"), fr).gains):
                per_hour[i] += g or 0
        hours = per_hour[:-1]  # the hour under way is still filling up
        typical = statistics.median(hours)
        posted = [db.parse(e["first_post"]).astimezone() for e in db.episodes() if e["first_post"]]
        recent = [t for t in posted if fr.starts[0] <= t < fr.starts[-1] - timedelta(hours=2)]
        self.assertGreaterEqual(len(recent), 1)
        for t in recent:  # each post makes a spike: its next few hours beat the hours before it at least twice over
            i = fr.index(t)
            self.assertGreater(max(hours[i:i + 3]), 2 * max(hours[max(0, i - 3):i], default=0.0), t)
        self.assertLess(min(hours), typical / 2)  # and the night is quiet

    def test_notifications_name_real_videos(self):
        titles = {e["title"] for e in db.episodes()}
        with db.connect() as c:
            notes = [dict(r) for r in c.execute("SELECT * FROM notifications ORDER BY id")]
        self.assertEqual([n["ts"] for n in notes], sorted(n["ts"] for n in notes))  # oldest first, as they happened
        for n in notes:
            if n["kind"] == "hot" or n["title"].startswith("A video passed"):
                self.assertTrue(any(n["body"].startswith(t[:40]) for t in titles), n)


class AppFitTest(unittest.TestCase):
    """The demo in the real window, at a few sizes: no card line or title is wider than its space."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "demo.db")
        demo.seed()

    def test_overview_fits(self):
        from textual.widgets import Static

        from dashboard import config
        from dashboard.app import ReelForge
        from dashboard.charts import Plot

        async def run(size, drawer):
            app = ReelForge(config.load_config(), demo.platforms(), demo=True, drawer=drawer)
            async with app.run_test(size=size) as pilot:
                await pilot.pause(0.5)
                for w in app.query(".card-body, .card-caption, .box-title").results(Static):
                    if not w.region.width:
                        continue  # on a tab that isn't showing
                    content = w.content if isinstance(w.content, Text) else Text(str(w.content))
                    for line in content.split("\n"):
                        self.assertLessEqual(line.cell_len, w.content_region.width, (size, drawer, line.plain))
                for card in app.query(".card"):
                    self.assertLessEqual(len(card.border_title) + 6, card.outer_size.width, (size, card.border_title))
                for plot in app.query("#views-chart Plot, #followers-chart Plot, #likes-chart Plot").results(Plot):
                    lay = plot.layout_
                    if lay is not None:
                        self.assertLessEqual(lay.slots * 2, lay.pw, (size, drawer, plot.parent.id))

        for size, drawer in (((110, 40), False), ((150, 45), True), ((200, 52), True)):
            asyncio.run(run(size, drawer))


if __name__ == "__main__":
    unittest.main()
