"""Best time to post (dashboard.besttime), every video's views 1, 6 and 24 hours in (analytics.views_after,
db.early_series) and compaction keeping each video's first day of readings, plus the CSV export and the Publish tab's
card in the real window on demo data."""

from __future__ import annotations

import asyncio
import csv
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from rich.text import Text

from dashboard import analytics, besttime, db
from dashboard.widgets import SHORT

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
    """The CSV export and the Publish tab's card, in the real window on demo data."""

    def test_csv_has_when_each_post_went_up_and_its_early_views(self):
        from dashboard import config, demo, desktop
        from dashboard.app import ReelForge
        from dashboard.config import PLATFORM_KEYS

        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        root = Path(tmp.name)
        cfg = {"refresh_minutes": 0, "videos_dir": str(root / "none"), "episodes_dir": str(root / "none"),
               "completed_dir": str(root / "none"), **{key: {} for key in PLATFORM_KEYS}}
        db.init(root / "demo.db")
        demo.seed()
        app = ReelForge(cfg, demo.platforms(), demo=True, tab="publish")

        async def main() -> dict[str, str]:
            async with app.run_test(size=(200, 56)) as pilot:
                await pilot.pause(0.3)
                app.action_export_csv()
                return {key: str(app.query_one(f"#best-{key}").render()) for key in app.platforms}

        with mock.patch.object(config, "DATA_DIR", root), mock.patch.object(desktop, "reveal") as reveal:
            lines = asyncio.run(main())
        with reveal.call_args[0][0].open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        posts = sorted(app.posts, key=lambda q: q["published_at"], reverse=True)
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
        for key, text in lines.items():
            self.assertTrue(text.startswith(f"● {SHORT[key]}"), text)
            self.assertTrue(any(s in text for s in ("not enough videos yet", "no clear best time yet", "next:")),
                            text)


if __name__ == "__main__":
    unittest.main()
