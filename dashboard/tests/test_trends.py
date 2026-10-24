"""Gains per bucket, frames, headline numbers and episode short names (dashboard.trends)."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from dashboard import trends

UTC = timezone.utc


def rows(*readings):
    """[(iso time, value)] -> account rows with one field, "views"."""
    return [{"ts": ts, "views": v, "followers": v} for ts, v in readings]


class FrameTest(unittest.TestCase):
    def test_hourly_frame_ends_with_the_current_hour(self):
        now = datetime(2026, 10, 24, 0, 50, tzinfo=UTC)
        fr = trends.frame("24h", now)
        self.assertEqual(fr.n, 24)
        self.assertTrue(fr.hourly)
        self.assertLessEqual(fr.starts[-1], now.astimezone())
        self.assertGreater(fr.ends[-1], now.astimezone())
        for a, b in zip(fr.starts, fr.ends):
            self.assertEqual(b - a, timedelta(hours=1))
            self.assertEqual((a.minute, a.second), (0, 0))

    def test_six_hour_buckets_start_on_local_quarter_days(self):
        fr = trends.frame("7d", datetime(2026, 10, 24, 0, 50, tzinfo=UTC))
        self.assertEqual(fr.n, 28)
        self.assertEqual(fr.unit(), "6h")
        self.assertTrue(all(s.hour % 6 == 0 for s in fr.starts))

    def test_daily_buckets_start_at_local_midnight_across_a_clock_change(self):
        fr = trends.frame("30d", datetime(2026, 11, 10, 15, 0, tzinfo=UTC))
        self.assertEqual(fr.n, 30)
        self.assertTrue(fr.daily)
        self.assertTrue(all((s.hour, s.minute) == (0, 0) for s in fr.starts))
        self.assertEqual(fr.starts[-1].date(), datetime(2026, 11, 10, 15, 0, tzinfo=UTC).astimezone().date())

    def test_index(self):
        fr = trends.frame("24h", datetime(2026, 10, 24, 0, 50, tzinfo=UTC))
        self.assertEqual(fr.index(fr.starts[3] + timedelta(minutes=5)), 3)
        self.assertIsNone(fr.index(fr.starts[0] - timedelta(minutes=1)))


class BucketTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 0, 50, tzinfo=UTC)
        self.fr = trends.frame("24h", self.now)

    def test_points_hold_the_highest_reading(self):
        pts = trends.points(rows(("2026-10-23T10:00:00+00:00", 5000), ("2026-10-23T10:30:00+00:00", 5217),
                                 ("2026-10-23T11:00:00+00:00", 5119), ("2026-10-23T11:30:00+00:00", 5250)), "views")
        self.assertEqual([v for _, v in pts], [5000, 5217, 5217, 5250])

    def test_bars_show_only_what_was_measured(self):
        r = rows(("2026-10-23T12:00:00+00:00", 100), ("2026-10-23T13:00:00+00:00", 400),
                 ("2026-10-23T18:00:00+00:00", 1400), ("2026-10-24T00:30:00+00:00", 2000))
        pts = trends.points(r, "views")
        b = trends.bucket(pts, self.fr)
        known = [g for g in b.gains if g is not None]
        self.assertAlmostEqual(sum(known), 300, places=6)       # only 12:00 -> 13:00 was read closely
        first = next(i for i, g in enumerate(b.gains) if g is not None)
        self.assertEqual(self.fr.starts[first].astimezone(UTC).hour, 12)
        # 13:00 -> 18:00 has no readings in between (the computer was off): those hours stay empty, nothing is
        # made up, no bar carries the gap...
        i = self.fr.index(datetime(2026, 10, 23, 15, 10, tzinfo=UTC).astimezone())
        self.assertIsNone(b.gains[i])
        self.assertTrue(b.gaps[i])
        self.assertFalse(b.gaps[first])
        j = self.fr.index(datetime(2026, 10, 23, 18, 0, tzinfo=UTC).astimezone())
        self.assertIsNone(b.gains[j])
        # ...and the numbers over the chart still count everything.
        self.assertAlmostEqual(trends.summarise({"tiktok": pts}, self.fr).gained, 1900, places=6)

    def test_summary(self):
        a = rows(("2026-10-23T01:00:00+00:00", 0), ("2026-10-23T23:50:00+00:00", 1000),
                 ("2026-10-24T00:50:00+00:00", 1600))
        s = trends.summarise({"tiktok": trends.points(a, "views")}, self.fr)
        self.assertEqual(s.latest, 1600)
        self.assertAlmostEqual(s.pace, 600, places=6)
        self.assertIsNotNone(s.best)
        self.assertIsNone(s.previous)  # no readings from the 24 hours before the range
        self.assertIsNone(s.change)

    def test_change_reads_between_readings(self):
        r = rows(("2026-10-22T00:00:00+00:00", 0), ("2026-10-23T12:00:00+00:00", 3600),
                 ("2026-10-24T00:00:00+00:00", 4000))
        now = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
        # 24 hours before "now" is 2026-10-23 00:00, two thirds of the way from 0 to 3600.
        self.assertAlmostEqual(trends.change(r, "views", 24, now), 4000 - 2400, places=6)
        self.assertIsNone(trends.change(r[1:], "views", 48, now))
        self.assertEqual(trends.since_first(r, "views"), 4000)


class ShortTitleTest(unittest.TestCase):
    def test_template_words_are_dropped(self):
        titles = ["What if your kite's speed doubled every 2 seconds?",
                  "What if your ladder's height doubled every 2 seconds?",
                  "What if your pumpkin doubled in size every 2 seconds?",
                  "What if your piggy bank doubled every second?",
                  "What if your likes doubled every second?"]
        self.assertEqual([trends.short_title(t, titles) for t in titles],
                         ["kite's speed", "ladder's height", "pumpkin size", "piggy bank", "likes"])

    def test_a_lone_title_keeps_its_words(self):
        self.assertTrue(trends.short_title("Gravity flipped for 10 seconds", ["Gravity flipped for 10 seconds"]))

    def test_distinct_title_drops_the_opening_most_titles_share(self):
        titles = ["What if your kite's speed doubled every 2 seconds?",
                  "What if your piggy bank doubled every second?", "What if gravity flipped?"]
        self.assertEqual([trends.distinct_title(t, titles) for t in titles],
                         ["Kite's speed doubled every 2 seconds?", "Piggy bank doubled every second?",
                          "Gravity flipped?"])
        # Titles without a shared opening stay whole, and a title is never emptied.
        self.assertEqual(trends.distinct_title("I tried cooking pasta", ["I tried cooking pasta", "Day 3 of 100"]),
                         "I tried cooking pasta")
        self.assertEqual(trends.distinct_title("What if", ["What if", "What if"]), "If")
        self.assertEqual(trends.distinct_title("", ["What if"]), "")


class RegressionTest(unittest.TestCase):
    """Cases the adversarial pass found."""

    def test_same_pace_reads_as_no_change(self):
        now = datetime(2026, 10, 20, 15, 1, tzinfo=UTC)
        pts = [(now - timedelta(minutes=30 * k), 50.0 * (1000 - k)) for k in range(1000, -1, -1)]  # 3 weeks
        for key in ("24h", "48h", "7d"):
            s = trends.summarise({"t": pts}, trends.frame(key, now))
            self.assertAlmostEqual(s.change, 0.0, places=6)

    def test_range_before_isnt_the_lifetime_total(self):
        fr = trends.frame("24h", datetime(2026, 10, 24, 0, 50, tzinfo=UTC))
        first = fr.starts[0] - (fr.ends[-1] - fr.starts[0]) + timedelta(minutes=30)
        pts = [(first + timedelta(hours=h), 5000.0 + 10 * h) for h in range(48)]
        s = trends.summarise({"yt": pts}, fr)
        self.assertLess(s.previous, 300)

    def test_stale_platform_doesnt_count_towards_now(self):
        now = datetime(2026, 10, 24, 0, 50, tzinfo=UTC)
        tiktok = [(now - timedelta(hours=h), 100.0 * (100 - h)) for h in range(100, -1, -1)]
        x = [(now - timedelta(days=7, hours=h), 500.0 * (100 - h)) for h in range(100, -1, -1)]
        s = trends.summarise({"tiktok": tiktok, "x": x}, trends.frame("24h", now))
        self.assertAlmostEqual(s.pace, 100.0)

    def test_six_hour_buckets_stay_on_round_hours_after_a_clock_change(self):
        for now in (datetime(2026, 11, 3, 17, tzinfo=UTC), datetime(2026, 11, 1, 7, 30, tzinfo=UTC),
                    datetime(2026, 3, 10, 12, tzinfo=UTC)):
            fr = trends.frame("7d", now)
            self.assertTrue(all(s.hour % 6 == 0 for s in fr.starts), [s.hour for s in fr.starts])
            self.assertEqual(fr.unit(), "6h")

    def test_daily_frame_starting_on_a_short_day_is_still_daily(self):
        fr = trends.frame("30d", datetime(2026, 4, 6, 16, tzinfo=UTC))
        self.assertTrue(fr.daily)
        self.assertEqual(fr.unit(), "day")

    def test_frame_since_covers_the_start(self):
        now = datetime(2026, 10, 24, 14, 0, tzinfo=UTC)
        for start in (now - timedelta(hours=1, minutes=30), now - timedelta(days=15, hours=12)):
            fr = trends.frame_since(start, now)
            self.assertLessEqual(fr.starts[0], start.astimezone())

    def test_no_bars_after_a_platform_stops_being_read(self):
        now = datetime(2026, 10, 24, 0, 50, tzinfo=UTC)
        fr = trends.frame("24h", now)
        pts = [(now - timedelta(hours=10 - h), 100.0 * h) for h in range(5)]  # last reading 6 hours ago
        b = trends.bucket(pts, fr)
        self.assertTrue(all(g is None for g in b.gains[-5:]))


if __name__ == "__main__":
    unittest.main()
