"""Best time to post (dashboard.besttime), every video's views 1, 6, 12 and 24 hours in (analytics.views_after,
views_due, db.early_series) and compaction keeping each video's first day of readings, plus the CSV export, the Videos
tab's Views 12h and the Publish tab's card, from the window's Python side on demo data."""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dashboard import analytics, besttime, db
from dashboard.tests.window import Window, plain
from dashboard.view import SHORT, Text

PUB = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def curve(*points: tuple[float, int]) -> analytics.Curve:
    """Readings as (hours after PUB, views)."""
    return [PUB + timedelta(hours=h) for h, _ in points], [v for _, v in points]


def local(hour: int, days_ago: int) -> datetime:
    """A quarter past `hour` on this computer's clock, `days_ago` days back."""
    return (datetime.now() - timedelta(days=days_ago)).replace(hour=hour, minute=15, second=0, microsecond=0) \
        .astimezone()


def videos(*first_days: tuple[int, float | None], platform: str = "tiktok") -> list[dict]:
    """Posts as (local hour it went up, views in its first day)."""
    return [{"platform": platform, "post_id": f"{platform}-{i}", "published": local(hour, 3 + i),
             "after": {1: None, 6: None, 24: views}} for i, (hour, views) in enumerate(first_days)]


def line(bt: besttime.BestTime, now: datetime | None = None) -> str:
    return "".join(t.plain for t, _ in besttime.parts(bt, Text("● TT"), now))


class ViewsAfterTest(unittest.TestCase):
    def test_between_readings_close_together(self):
        c = curve((0.5, 100), (1.5, 300), (5.5, 900), (6.5, 1100), (23, 4000), (25, 5000))
        self.assertEqual(analytics.views_after(c, PUB, 1), 200)
        self.assertEqual(analytics.views_after(c, PUB, 6), 1000)
        self.assertEqual(analytics.views_after(c, PUB, 24), 4500)
        self.assertEqual(analytics.views_after(curve((24, 777), (25, 800)), PUB, 24), 777)

    def test_going_up_counts_as_no_views(self):
        self.assertEqual(analytics.views_after(curve((1.25, 500)), PUB, 1), 400)

    def test_no_line_across_a_gap(self):
        # The computer slept from 4 to 20 hours in: 6 hours in isn't known, 24 hours in is.
        c = curve((0.5, 50), (1, 100), (4, 600), (20, 3000), (23.5, 3500), (24.5, 3600))
        self.assertIsNone(analytics.views_after(c, PUB, 6))
        self.assertEqual(analytics.views_after(c, PUB, 24), 3550)
        self.assertIsNone(analytics.views_after(curve((2, 500)), PUB, 1))  # first read 2 hours in
        self.assertIsNone(analytics.views_after(curve((20, 900), (27.5, 1000)), PUB, 24))

    def test_not_that_old_yet(self):
        self.assertIsNone(analytics.views_after(curve((1, 10), (8, 90)), PUB, 24))
        self.assertIsNone(analytics.views_after(analytics.NO_CURVE, PUB, 1))

    def test_twelve_hours_in_reads_across_up_to_3_hours(self):
        self.assertEqual(analytics.views_after(curve((10.5, 1000), (13, 1500)), PUB, 12), 1300)
        self.assertIsNone(analytics.views_after(curve((10, 1000), (13.5, 1500)), PUB, 12))


class ViewsDueTest(unittest.TestCase):
    """Whether a video's views 12 hours in are still to come, or ReelForge missed them."""

    def due(self, c: analytics.Curve, at_hours: float) -> bool:
        return analytics.views_due(c, PUB, 12, PUB + timedelta(hours=at_hours))

    def test_until_the_video_is_that_old(self):
        self.assertTrue(self.due(curve((1, 10), (5, 90)), 6))
        self.assertTrue(self.due(analytics.NO_CURVE, 11.9))

    def test_after_it_until_the_next_reading_is_too_late(self):
        c = curve((10, 100), (11.5, 140))
        self.assertTrue(self.due(c, 12.5))
        self.assertTrue(self.due(c, 14.5))  # a reading now would be 3 hours after the last
        self.assertFalse(self.due(c, 14.6))
        self.assertFalse(self.due(analytics.NO_CURVE, 12.5))  # not read in its first 12 hours at all

    def test_not_once_its_been_read_since(self):
        self.assertFalse(self.due(curve((11.5, 140), (12.5, 160)), 13))  # views_after has the number
        self.assertFalse(self.due(curve((4, 60), (20, 400)), 21))  # read across a gap: missed for good

    def test_each_post_gets_its_views_and_whats_still_to_come(self):
        t = analytics.now().replace(microsecond=0)
        posts = [{"platform": "tiktok", "post_id": "old", "published": t - timedelta(hours=30)},
                 {"platform": "tiktok", "post_id": "new", "published": t - timedelta(hours=5)}]
        early = {("tiktok", "old"): curve((0.5, 10), (6, 300), (11, 500), (13, 700))}
        early = {k: ([posts[0]["published"] + (s - PUB) for s in ts], vs) for k, (ts, vs) in early.items()}
        analytics.add_early_views(posts, early)
        self.assertEqual(posts[0]["after"], {1: None, 6: 300, 12: 600, 24: None})
        # The new one wasn't read in its first hour and a half: its views 1 hour in are missed, the rest are to come.
        self.assertEqual((posts[0]["due"], posts[1]["due"]), (set(), {6, 12, 24}))


class TwelveHourCellTest(unittest.TestCase):
    """The Videos tab's Views 12h cell."""

    def cell(self, views: float | None, due: bool, age_h: float) -> str:
        from dashboard.service import _after

        return _after({"after": {12: views}, "due": {12} if due else set(), "age_h": age_h}, 12).plain

    def test_the_number_once_known(self):
        self.assertEqual(self.cell(1234.4, False, 30), "1.23K")

    def test_when_it_comes_in(self):
        self.assertEqual(self.cell(None, True, 7), "in 5h")
        self.assertEqual(self.cell(None, True, 11.5), "in 30m")
        self.assertEqual(self.cell(None, True, 11.9999), "in 1m")
        self.assertEqual(self.cell(None, True, 12.4), "soon")

    def test_a_dash_when_the_readings_missed_it(self):
        self.assertEqual(self.cell(None, False, 40), "—")


class FirstDayKeptTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "stats.db")

    def test_compaction_keeps_every_reading_of_a_videos_first_27_hours(self):
        pub = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=20)
        account = SimpleNamespace(handle="@me", followers=1, views=None, likes=None, posts=None)
        for i in range(3 * 48):  # a reading every 30 minutes for 3 days, from 10 minutes after it went up
            db.record_snapshot("tiktok", account, [SimpleNamespace(
                post_id="v", title="What if", url=None, published_at=db.to_iso(pub), views=100 * i, likes=None,
                comments=None, shares=None, saves=None)], db.to_iso(pub + timedelta(minutes=10 + 30 * i)))
        db.compact(min_hours=0)
        with db.connect() as c:
            kept = [db.parse(r[0]) for r in c.execute("SELECT ts FROM post_stats ORDER BY ts")]
        first = [t for t in kept if t < pub + timedelta(hours=db.FIRST_HOURS)]
        self.assertEqual(len(first), 54)
        self.assertLess(len(kept) - len(first), 6)  # the 2 days after it: about one a day
        early = db.early_series()
        self.assertEqual([db.parse(ts) for ts, _ in early["tiktok", "v"]], first)
        posts = [{"platform": "tiktok", "post_id": "v", "published": pub}]
        analytics.add_early_views(posts, analytics.parse_series(early))
        for hours, views in ((1, 166.67), (6, 1166.67), (24, 4766.67)):
            self.assertAlmostEqual(posts[0]["after"][hours], views, places=1)


class BestTimeTest(unittest.TestCase):
    def test_names_the_part_of_the_day_clearly_ahead(self):
        bt = besttime.best_times(videos((21, 100), (22, 120), (9, 50), (10, 60)), ["tiktok"])["tiktok"]
        self.assertEqual(bt.slot, 5)
        self.assertEqual((bt.typical(5), bt.others), (110, 55))
        now = local(19, 0)  # 7:15 PM
        self.assertEqual(line(bt, now), "● TT  8 PM–12 AM  110 vs 55 other times  next: today 8 PM")

    def test_not_enough_videos_until_two_parts_have_two_each(self):
        bt = besttime.best_times(videos((21, 100), (22, 120), (23, 130), (9, 50)), ["tiktok"])["tiktok"]
        self.assertIsNone(bt.slot)
        self.assertEqual(line(bt), "● TT  not enough videos yet  8 PM–12 AM 120 (3 videos)")
        self.assertEqual(line(besttime.best_times([], ["tiktok"])["tiktok"]), "● TT  not enough videos yet")

    def test_close_parts_are_no_clear_best_yet(self):
        bt = besttime.best_times(videos((21, 100), (22, 110), (9, 94), (10, 100)), ["tiktok"])["tiktok"]
        self.assertIsNone(bt.slot)
        self.assertEqual(line(bt), "● TT  no clear best time yet  8 PM–12 AM 105, 8 AM–12 PM 97")

    def test_only_videos_with_a_known_first_day_and_their_own_platform_count(self):
        posts = videos((21, 100), (22, 120), (9, None), (10, None)) + videos((9, 50), (10, 60), platform="youtube")
        found = besttime.best_times(posts, ["tiktok", "youtube"])
        self.assertEqual(found["tiktok"].known, {5: [100, 120]})
        self.assertEqual(found["youtube"].known, {2: [50, 60]})

    def test_parts_of_the_day_and_when_they_come_round(self):
        self.assertEqual([besttime.slot_label(s) for s in range(6)],
                         ["12–4 AM", "4–8 AM", "8 AM–12 PM", "12–4 PM", "4–8 PM", "8 PM–12 AM"])
        self.assertEqual(besttime.next_time(5, local(19, 0)), "today 8 PM")
        self.assertEqual(besttime.next_time(5, local(21, 0)), "now, until 12 AM")
        self.assertEqual(besttime.next_time(1, local(9, 0)), "tomorrow 4 AM")
        self.assertEqual(besttime.next_time(2, local(0, 0)), "today 8 AM")


class AppTest(unittest.TestCase):
    """The CSV export, the Videos tab's Views 12h and the Publish tab's card, on demo data."""

    def demo_window(self, tab: str) -> tuple[Window, Path]:
        from dashboard import demo
        from dashboard.config import PLATFORM_KEYS

        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        root = Path(tmp.name)
        cfg = {"refresh_minutes": 0, "videos_dir": str(root / "none"), "episodes_dir": str(root / "none"),
               "completed_dir": str(root / "none"), **{key: {} for key in PLATFORM_KEYS}}
        db.init(root / "demo.db")
        demo.seed()
        w = Window(cfg, demo.platforms(), tab=tab)
        self.addCleanup(w.close)
        return w, root

    @staticmethod
    def column(view: dict, key: str) -> tuple[dict, list[tuple[str, str]]]:
        at = [c["key"] for c in view["columns"]].index(key)
        return view["columns"][at], [(r["key"], plain(r["cells"][at])) for r in view["rows"]]

    def test_videos_tab_has_each_videos_views_12_hours_in(self):
        from dashboard.service import _after

        w, _ = self.demo_window("videos")
        w.call("sort_videos", "views_12h")  # clicking its header
        column, cells = self.column(w.view("videos"), "views_12h")
        self.assertEqual(w.svc.sort, ("views_12h", True))  # sorted by it, most first
        self.assertEqual(plain(column["label"]), "Views 12h ▼")
        self.assertGreaterEqual(column["width"], len("Views 12h ▼"))  # the arrow shows
        posts = [w.svc._post_for(key) for key, _ in cells]
        self.assertEqual(len(cells), len(w.svc.posts))
        self.assertEqual([text for _, text in cells], [_after(p, 12).plain for p in posts])
        known = [p["after"][12] for p in posts if p["after"][12] is not None]
        self.assertGreater(len(known), 4)  # the demo reads every hour, so every video 12 hours old has its number
        self.assertEqual(known, sorted(known, reverse=True))
        self.assertTrue(all(p["after"][12] is None for p in posts[len(known):]))  # the rest go last

    def test_top_performers_have_their_views_12_hours_in(self):
        from dashboard.service import _after

        w, _ = self.demo_window("overview")
        w.call("sort_top", "views_12h")
        column, cells = self.column(w.view("top"), "views_12h")
        self.assertEqual(w.svc.top_sort, ("views_12h", True))
        self.assertEqual(plain(column["label"]), "12h ▼")
        posts = [w.svc._post_for(key) for key, _ in cells]
        self.assertEqual([text for _, text in cells], [_after(p, 12).plain for p in posts])
        known = [p["after"][12] for p in posts if p["after"][12] is not None]
        self.assertGreater(len(known), 4)
        self.assertEqual(known, sorted(known, reverse=True))

    def test_csv_has_when_each_post_went_up_and_its_early_views(self):
        from dashboard import config, desktop

        out = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(out.cleanup)
        with mock.patch.object(config, "DATA_DIR", Path(out.name)), mock.patch.object(desktop, "reveal") as reveal:
            w, _ = self.demo_window("publish")
            w.call("export_csv")
        lines = [plain([seg for part in line for seg in part[0]]) for line in w.view("best")["lines"]]
        with reveal.call_args[0][0].open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        posts = sorted(w.svc.posts, key=lambda q: q["published_at"], reverse=True)
        self.assertEqual(len(rows), len(posts))
        for row, p in zip(rows, posts):
            when = p["published"].astimezone()
            self.assertEqual((row["posted"], row["posted_weekday"], row["posted_hour"]),
                             (f"{when:%Y-%m-%d %H:%M}", f"{when:%A}", str(when.hour)))
            self.assertEqual(datetime.fromisoformat(row["posted_utc"].replace("Z", "+00:00")),
                             p["published"].replace(microsecond=0))
            for hours in analytics.AFTER_HOURS:
                views = p["after"][hours]
                self.assertEqual(row[f"views_after_{hours}h"], "" if views is None else str(round(views)))
        known = [r["views_after_24h"] for r in rows]
        self.assertTrue(any(known) and not all(known))  # the newest videos aren't a day old yet
        for key, text in zip(w.svc.platforms, lines):
            self.assertTrue(text.startswith(f"● {SHORT[key]}"), text)
            self.assertTrue(any(s in text for s in ("not enough videos yet", "no clear best time yet", "next:")),
                            text)


if __name__ == "__main__":
    unittest.main()
