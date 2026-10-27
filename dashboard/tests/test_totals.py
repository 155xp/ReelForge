"""The Stats tab (dashboard/stats_tab.py): followers and likes added up across the platforms you count, over time,
from real readings only; the platforms you leave out; the ranges; and what the window is sent. The window's own tab
(the pills, the ranges, the hover read-out) is tested in ui/test/stats.test.tsx."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard import db, demo, stats_tab, sync, trends
from dashboard.config import PLATFORM_KEYS
from dashboard.service import NOTHING_CONNECTED
from dashboard.stats_tab import Totals, frame_for, level_at, spaced
from dashboard.tabs import tab_for
from dashboard.tests.window import Window, plain

UTC = timezone.utc
NOW = datetime(2026, 10, 27, 12, 20, tzinfo=UTC)
HOUR = timedelta(hours=1)


def pts(*readings) -> trends.Points:
    """[(hours before NOW, value)] -> readings, oldest first."""
    return sorted((NOW - timedelta(hours=h), float(v)) for h, v in readings)


def text(parts: list | None) -> str:
    """The text of (segments, importance) parts."""
    return "".join(plain(p[0]) for p in parts or [])


class LevelTest(unittest.TestCase):
    """A platform's running total at a moment, from its readings."""

    def test_between_readings_close_together_the_line_joining_them(self):
        p = pts((3, 100), (2, 140), (1, 160))
        self.assertEqual(level_at(p, NOW - timedelta(hours=2.5), HOUR, NOW), 120)
        self.assertEqual(level_at(p, NOW - timedelta(hours=2), HOUR, NOW), 140)

    def test_nothing_before_the_first_reading_or_in_a_gap(self):
        p = pts((20, 100), (19, 110), (5, 300), (4, 320))
        self.assertIsNone(level_at(p, NOW - timedelta(hours=21), HOUR, NOW))
        self.assertIsNone(level_at(p, NOW - timedelta(hours=10), HOUR, NOW))  # the computer was off

    def test_the_newest_holds_while_its_recent(self):
        p = pts((2, 100), (0.5, 120))
        self.assertEqual(level_at(p, NOW, HOUR, NOW), 120)
        self.assertIsNone(level_at(pts((5, 100), (4, 120)), NOW, HOUR, NOW))  # not read for 4 hours

    def test_thinned_history_isnt_a_gap(self):
        """db.compact keeps one reading every 3 hours after 14 days, one a day after 26 and one a week after 72."""
        for days, apart in ((15, timedelta(hours=5)), (30, timedelta(days=1, hours=20)), (80, timedelta(days=12))):
            t0 = NOW - timedelta(days=days)
            self.assertGreaterEqual(spaced(t0, HOUR, NOW), apart)
            p = [(t0, 100.0), (t0 + apart, 200.0)]
            self.assertIsNotNone(level_at(p, t0 + apart / 2, HOUR, NOW))
        self.assertEqual(spaced(NOW - timedelta(days=3), HOUR, NOW), trends.GAP)  # recent: every gap counts


class TotalsTest(unittest.TestCase):
    """The counted platforms added up at each moment of a frame."""

    def frame(self, key="24h"):
        return frame_for(key, None, NOW)

    def test_adds_up_the_counted_platforms_only(self):
        each = {"a": pts(*((h, 1000 - 10 * h) for h in range(30))), "b": pts(*((h, 50) for h in range(30))),
                "c": pts(*((h, 7) for h in range(30)))}
        t = Totals(each, ["a", "b"], self.frame())
        self.assertEqual(t.total[-1], 1000 + 50)
        self.assertEqual(t.total[0], t.each["a"][0] + t.each["b"][0])
        self.assertEqual(len(t.runs()), 1)
        self.assertEqual(t.xs[0], 0.0)
        self.assertTrue(t.fr.n - 1 < t.xs[-1] < t.fr.n)  # now: part of the way through the last bucket

    def test_a_gap_in_every_platforms_readings_breaks_the_total(self):
        hours = [h for h in range(30) if not 8 <= h <= 14]  # the computer off for 7 hours
        each = {"a": pts(*((h, 1000 - h) for h in hours)), "b": pts(*((h, 50 - h) for h in hours))}
        t = Totals(each, ["a", "b"], self.frame())
        runs = t.runs()
        self.assertEqual(len(runs), 2)
        gap = (NOW - timedelta(hours=11)).astimezone()
        j = t.moments.index(min(t.moments, key=lambda m: abs(m - gap)))
        self.assertIsNone(t.total[j])
        # each run reaches right up to the gap's edges (the last reading before it, the first after)
        self.assertEqual(t.moments[runs[0][-1]], NOW - timedelta(hours=15))
        self.assertEqual(t.moments[runs[1][0]], NOW - timedelta(hours=7))

    def test_a_platform_whose_reads_stopped_counts_with_its_last_reading(self):
        """A log-in that ran out, say: as on the Overview's tiles, the total keeps its last number."""
        each = {"a": pts(*((h, 1000 - h) for h in range(30))), "x": pts(*((h, 5) for h in range(20, 30)))}
        t = Totals(each, ["a", "x"], self.frame())
        self.assertEqual(len(t.runs()), 1)
        self.assertEqual(t.total[-1], 1000 + 5)

    def test_no_total_before_a_counted_platforms_first_reading(self):
        each = {"a": pts(*((h, 1000 - h) for h in range(30))), "b": pts(*((h, 50) for h in range(10)))}
        t = Totals(each, ["a", "b"], self.frame())
        self.assertEqual(t.first, NOW - timedelta(hours=9))
        self.assertEqual(t.moments[t.known[0]], t.first)
        self.assertTrue(all(v is None for v in t.total[:t.known[0]]))

    def test_each_bucket_for_the_hover_read_out(self):
        each = {"a": pts(*((h, 1000 - 10 * h) for h in range(30)))}
        t = Totals(each, ["a"], self.frame())
        slots = t.slots()
        self.assertEqual(len(slots), t.fr.n)
        self.assertAlmostEqual(slots[5]["gain"], 10)  # 10 an hour
        self.assertEqual(slots[-1]["total"], 1000)  # the last one: now
        self.assertEqual(set(slots[-1]["each"]), {"a"})
        self.assertAlmostEqual(sum(g for g in t.gains("a") if g is not None), t.total[-1] - t.total[0])


class FrameTest(unittest.TestCase):
    def test_all_runs_from_the_first_total_in_the_finest_buckets_that_fit(self):
        for age, step in ((timedelta(hours=30), HOUR), (timedelta(days=11), timedelta(hours=2)),
                          (timedelta(days=60), timedelta(hours=12)), (timedelta(days=400), timedelta(days=7))):
            fr = frame_for("all", NOW - age, NOW)
            self.assertEqual(fr.step, step)
            self.assertLessEqual(fr.starts[0], NOW - age)
            self.assertGreater(fr.starts[1], NOW - age)  # no empty bucket before it
            self.assertLessEqual(fr.n, stats_tab.MOST_SLOTS)

    def test_the_fixed_ranges(self):
        for key, n, step in (("24h", 24, HOUR), ("48h", 48, HOUR), ("7d", 168, HOUR), ("30d", 120, 6 * HOUR)):
            fr = frame_for(key, None, NOW)
            self.assertEqual((fr.n, fr.step), (n, step))


class WindowTest(unittest.TestCase):
    """The tab's view, on demo data."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        root = Path(tmp.name)
        self.cfg = {"refresh_minutes": 0, "videos_dir": str(root / "none"), "episodes_dir": str(root / "none"),
                    "completed_dir": str(root / "none"), **{key: {} for key in PLATFORM_KEYS}}
        db.init(root / "demo.db")
        demo.seed()
        for state in (sync._attempted, sync.last_errors):
            state.clear()
            self.addCleanup(state.clear)

    def open(self, platforms=None, tab: str = "totals") -> Window:
        w = Window(self.cfg, platforms or demo.platforms(), tab=tab)
        self.addCleanup(w.close)
        return w

    def test_the_tab_has_a_number_and_a_name_but_not_stats(self):
        self.assertEqual(tab_for("8"), "totals")
        self.assertEqual(tab_for("totals"), "totals")
        self.assertIsNone(tab_for("stats"))  # reelforge stats is the hourly job

    def test_both_charts_and_their_breakdowns(self):
        w = self.open()
        v = w.view("totals")
        self.assertEqual(v["range"], "all")
        self.assertEqual([t["key"] for t in v["toggles"]], list(PLATFORM_KEYS))
        self.assertTrue(all(t["counted"] and t["has"] for t in v["toggles"]))
        self.assertIn("ALL", plain(v["ranges"]))
        for metric in ("followers", "likes"):
            m = v["metrics"][metric]
            self.assertFalse(m.get("empty"))
            self.assertTrue(m["series"] and all(s["style"] == "area" for s in m["series"]))
            self.assertEqual(len(m["hover"]), m["n"])
            self.assertEqual(len(m["slots"]), m["n"])
            self.assertTrue(text(m["title"]).startswith(metric.upper()))
            rows = m["rows"]
            # the counted platforms' gains add up to the total's, and their shares to all of it
            self.assertAlmostEqual(sum(r["gained"] for r in rows), m["total"]["gained"], places=3)
            self.assertAlmostEqual(sum(r["share"] for r in rows), 1.0, places=6)
            self.assertAlmostEqual(sum(r["value"] for r in rows), m["total"]["value"], places=3)
            self.assertAlmostEqual(m["series"][-1]["ys"][-1], m["total"]["value"], places=3)
        self.assertIn("total", text(v["metrics"]["followers"]["title"]))

    def test_leaving_a_platform_out_and_back_in(self):
        w = self.open()
        before = w.view("totals")["metrics"]["followers"]["total"]["value"]
        x = next(r for r in w.view("totals")["metrics"]["followers"]["rows"] if r["key"] == "x")["value"]
        w.call("count_platform", "x")
        v = w.view("totals")
        self.assertEqual([t["key"] for t in v["toggles"] if not t["counted"]], ["x"])
        m = v["metrics"]["followers"]
        self.assertAlmostEqual(m["total"]["value"], before - x)
        row = next(r for r in m["rows"] if r["key"] == "x")
        self.assertFalse(row["counted"])
        self.assertTrue(row["left_out"])
        self.assertIsNone(row["share"])
        self.assertNotIn("x", m["hover"][-1]["each"])
        # kept for the next window
        self.assertEqual(db.get_meta("totals_left_out"), ["x"])
        self.assertFalse(next(t for t in self.open().view("totals")["toggles"] if t["key"] == "x")["counted"])
        w.call("count_platform", "x")
        self.assertTrue(all(t["counted"] for t in w.view("totals")["toggles"]))
        self.assertAlmostEqual(w.view("totals")["metrics"]["followers"]["total"]["value"], before)

    def test_everything_left_out(self):
        w = self.open()
        for key in PLATFORM_KEYS:
            w.call("count_platform", key)
        m = w.view("totals")["metrics"]["likes"]
        self.assertIn("left out", m["empty"])
        self.assertNotIn("series", m)
        self.assertEqual(len(m["rows"]), 4)

    def test_the_ranges(self):
        w = self.open()
        w.call("set_totals_range", "24h")
        m = w.view("totals")["metrics"]["followers"]
        self.assertEqual((m["n"], m["step_h"]), (24, 1.0))
        self.assertIn("in 24h", text(m["title"]))
        self.assertEqual(db.get_meta("totals_range"), "24h")
        self.assertEqual(self.open().view("totals")["range"], "24h")
        w.call("set_totals_range", "7d")
        self.assertEqual(w.view("totals")["metrics"]["likes"]["n"], 168)
        w.call("set_totals_range", "nonsense")
        self.assertEqual(w.view("totals")["range"], "7d")

    def test_marks_where_videos_went_up(self):
        m = self.open().view("totals")["metrics"]["followers"]
        self.assertTrue(m["marks"])
        self.assertTrue(all(0 <= mark["x"] <= m["n"] for mark in m["marks"]))

    def test_only_built_while_its_open(self):
        w = self.open(tab="overview")
        self.assertIsNone(w.view("totals"))
        w.call("tab_opened", "totals")
        self.assertIsNotNone(w.view("totals"))

    def test_nothing_connected(self):
        w = self.open(demo.platforms(unconnected=PLATFORM_KEYS))
        if w.svc.tab != "totals":
            w.call("tab_opened", "totals")
        v = w.view("totals")
        self.assertEqual(v["toggles"], [])
        self.assertEqual(v["metrics"]["followers"]["empty"], NOTHING_CONNECTED)

    def test_a_platform_read_from_later_on_says_the_totals_start_with_it(self):
        start = (datetime.now(UTC) - timedelta(days=3)).isoformat(timespec="seconds")
        with db.connect() as c:
            c.execute("DELETE FROM account_stats WHERE platform = 'x' AND ts < ?", (start,))
        w = self.open()
        m = w.view("totals")["metrics"]["followers"]
        self.assertIn("with X's first reading", plain(m["note"]))
        w.call("count_platform", "x")
        self.assertIsNone(w.view("totals")["metrics"]["followers"]["note"])

    def test_a_platform_not_read_for_a_while_says_when_it_last_was(self):
        cut = (datetime.now(UTC) - timedelta(hours=30)).isoformat(timespec="seconds")
        with db.connect() as c:
            c.execute("DELETE FROM account_stats WHERE platform = 'x' AND ts > ?", (cut,))
            # The demo reads on the hour: X's last reading moves to the cut, so it's 30h old whatever the minute.
            c.execute("UPDATE account_stats SET ts = ? WHERE platform = 'x' AND ts = "
                      "(SELECT MAX(ts) FROM account_stats WHERE platform = 'x')", (cut,))
        m = self.open().view("totals")["metrics"]["followers"]
        x = next(r for r in m["rows"] if r["key"] == "x")
        self.assertTrue(x["counted"])
        self.assertEqual(x["stale"], "last read 30h ago")
        self.assertIsNone(next(r for r in m["rows"] if r["key"] == "tiktok")["stale"])
        self.assertIsNotNone(m["hover"][-1])  # the total still runs to now, with X's last reading


if __name__ == "__main__":
    unittest.main()
