"""The Stats tab (dashboard/stats_tab.py): views, followers and likes added up across the platforms you count, over time,
from ReelForge's readings, with the gaps between them estimated; the platforms you leave out; the ranges; and what the
window is sent. The window's own tab (the pills, the ranges, the hover read-out) is tested in ui/test/stats.test.tsx."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard import db, demo, stats_tab, sync, trends
from dashboard.config import PLATFORM_KEYS
from dashboard.service import NOTHING_CONNECTED
from dashboard.stats_tab import StatsTab, Totals, between, frame_for, level_at, spaced
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

    def test_a_gap_is_estimated_from_the_readings_either_side(self):
        p = pts((20, 100), (19, 110), (5, 300), (4, 320))
        self.assertEqual(between(p, NOW - timedelta(hours=12)), 205)  # halfway from 110 to 300
        self.assertEqual(between(p, NOW - timedelta(hours=5)), 300)
        self.assertIsNone(between(p, NOW - timedelta(hours=21)))  # nothing before the first reading to go by
        self.assertIsNone(between(p, NOW - timedelta(hours=1)))  # nor after the newest

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

    def test_a_gap_in_every_platforms_readings_is_an_estimate(self):
        """The computer was off for 7 hours: the total carries on through the gap, along the straight line between
        the readings either side, and that stretch (just that) is an estimate."""
        hours = [h for h in range(30) if not 8 <= h <= 14]
        each = {"a": pts(*((h, 1000 - h) for h in hours)), "b": pts(*((h, 50 - h) for h in hours))}
        t = Totals(each, ["a", "b"], self.frame())
        self.assertEqual(len(t.runs()), 1)  # no hole
        gap = NOW - timedelta(hours=11)
        self.assertAlmostEqual(t.at(gap), 989 + 39)
        self.assertTrue(t.guessed(gap))
        self.assertIsNone(t.measured(gap))  # the numbers over the chart leave it out
        # the estimate runs from the last reading before the gap to the first after it
        before, after = NOW - timedelta(hours=15), NOW - timedelta(hours=7)
        self.assertEqual(t.measured(before), 985 + 35)
        self.assertEqual(t.spans(t.runs()[0]), [[t.xs[t.index[before]], t.xs[t.index[after]]]])
        # the hover read-out: how much of each hour is estimated, whether its total is, and whose numbers were
        slots = t.slots()
        i = t.fr.index(gap.astimezone())
        self.assertTrue(slots[i]["estimated"])
        self.assertEqual(slots[i]["share"], 1)
        self.assertEqual(slots[i]["est"], ["a", "b"])
        last = slots[t.fr.index(after.astimezone())]  # 5 to 6, read again from 20 past
        self.assertFalse(last["estimated"])
        self.assertAlmostEqual(last["share"], 1 / 3)
        read = slots[t.fr.index((NOW - timedelta(hours=3)).astimezone())]
        self.assertFalse(read["estimated"])
        self.assertEqual((read["share"], read["est"]), (0, []))
        # what the gap gained is spread over its hours, so no hour after it jumps
        gains = [g for g in t.gains("a") if g is not None]
        self.assertAlmostEqual(max(gains), 1)

    def test_one_platforms_own_gap_is_estimated_and_the_total_is_when_its_most_of_it(self):
        """A log-in that ran out for a while: that platform's number is estimated through its gap (no jump when its
        reads come back), but the total only counts as an estimate while that platform is most of it."""
        every, paused = range(30), [h for h in range(30) if not 8 <= h <= 14]
        gap = NOW - timedelta(hours=11)
        small = Totals({"big": pts(*((h, 1000 - h) for h in every)), "small": pts(*((h, 50 - h) for h in paused))},
                       ["big", "small"], self.frame())
        self.assertAlmostEqual(small.at(gap), 989 + 39)  # not held at its last reading (35) until it jumps
        self.assertFalse(small.guessed(gap))
        self.assertFalse(any(small.estimated))
        self.assertEqual(small.slots()[small.fr.index(gap.astimezone())]["est"], ["small"])
        big = Totals({"big": pts(*((h, 1000 - h) for h in paused)), "small": pts(*((h, 50 - h) for h in every))},
                     ["big", "small"], self.frame())
        self.assertTrue(big.guessed(gap))
        self.assertIsNone(big.measured(gap))
        self.assertTrue(big.slots()[big.fr.index(gap.astimezone())]["estimated"])

    def test_nothing_is_estimated_after_the_newest_reading(self):
        """There's nothing on the far side to go by: not read for the last 5 hours (the computer is off now), the
        total stops at the last reading."""
        t = Totals({"a": pts(*((h, 1000 - h) for h in range(5, 30)))}, ["a"], self.frame())
        self.assertIsNone(t.at(NOW - timedelta(hours=1)))
        self.assertFalse(any(t.estimated))
        # the newest reading holds while it's recent (trends.GAP): to the next hour, 40 minutes on, and no further
        self.assertEqual(t.moments[t.known[-1]], datetime(2026, 10, 27, 8, tzinfo=UTC))

    def test_the_best_hour_or_day_is_a_measured_one(self):
        """An estimate spreads what a gap gained evenly over it, so it can't be the best hour or day."""
        # 10 an hour, but 800 while the computer was off for 8 hours: 100 an hour, more than any hour read
        hours = [h for h in range(30) if not 8 <= h <= 14]
        each = {"a": pts(*((h, 1000 - 10 * (h - 15) if h >= 15 else 1800 + 10 * (7 - h)) for h in hours))}
        t = Totals(each, ["a"], self.frame())
        self.assertTrue(StatsTab().totals_best(t, False).startswith("best hour +10 at "))
        # a night the computer was off, its midnight in the gap: both days it splits are left out
        midnight = datetime.combine((NOW - timedelta(days=2)).astimezone().date(), datetime.min.time()).astimezone()
        off, on = midnight - timedelta(hours=4), midnight + timedelta(hours=6)
        stamps = [NOW - timedelta(hours=h) for h in range(5 * 24)]
        readings = sorted((s, 10 * (s - stamps[-1]) / HOUR + (1000 if s >= on else 0))
                          for s in stamps if not off < s < on)
        t = Totals({"a": readings}, ["a"], frame_for("7d", None, NOW))
        best = StatsTab().totals_best(t, True)
        self.assertTrue(best.startswith("best day +2"), best)  # 240 a day (250 over a daylight-saving change)
        self.assertLess(int(best.split()[2].replace(",", "")), 300)

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
        self.assertEqual(tab_for("5"), "totals")  # Stats is 5th by default
        self.assertEqual(tab_for("totals"), "totals")
        self.assertIsNone(tab_for("stats"))  # reelforge stats is the hourly job

    def test_the_charts_and_their_breakdowns(self):
        w = self.open()
        v = w.view("totals")
        self.assertEqual(v["range"], "all")
        self.assertEqual([t["key"] for t in v["toggles"]], list(PLATFORM_KEYS))
        self.assertTrue(all(t["counted"] and t["has"] for t in v["toggles"]))
        self.assertIn("ALL", plain(v["ranges"]))
        self.assertEqual(list(v["metrics"]), ["views", "followers", "likes"])
        for metric in ("views", "followers", "likes"):
            m = v["metrics"][metric]
            self.assertFalse(m.get("empty"))
            self.assertTrue(m["series"] and all(s["style"] == "area" for s in m["series"]))
            # the demo is read every hour: nothing to estimate, and no key to the hatching over the chart
            self.assertTrue(all(s["est"] == [] for s in m["series"]))
            self.assertFalse(any(h["estimated"] or h["share"] or h["est"] for h in m["hover"] if h))
            self.assertNotIn("estimated", text(m["title"]))
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

    def test_a_night_the_computer_was_off_is_estimated_here_and_on_the_other_charts(self):
        """No readings for most of a night two days ago: every chart carries on through it, hatched from the last
        reading before it to the first after it, with the key to the hatching over it; the Overview's 7D bars and the
        Accounts tab's followers charts fill it in with an estimate too."""
        night = datetime.now(UTC) - timedelta(days=2)
        with db.connect() as c:  # the demo reads on the hour: nine hours between the readings either side
            c.execute("DELETE FROM account_stats WHERE ts > ? AND ts < ?",
                      (night.isoformat(timespec="seconds"), (night + timedelta(hours=8)).isoformat(timespec="seconds")))
        v = self.open().view("totals")
        for metric in ("views", "followers", "likes"):
            m = v["metrics"][metric]
            self.assertEqual(len(m["series"]), 1)  # no hole
            (a, b), = m["series"][0]["est"]
            self.assertAlmostEqual((b - a) * m["step_h"], 9, places=3)
            self.assertTrue(any(h and h["estimated"] for h in m["hover"]))
            self.assertIn("╱╱ estimated", text(m["title"]))
        w = self.open(tab="overview")
        w.call("set_range", "7d")
        bars = w.view("trends")["metrics"]["views"]["variants"][0]
        self.assertEqual(bars["step_h"], 6)
        self.assertTrue(any(g > 0 for s in bars["series"] for g in s["guess"]))
        # and each account's followers chart on the Accounts tab: hatched, its hover read-out an estimate
        w = self.open(tab="accounts")
        chart = next(p for p in w.view("accounts")["panels"] if p["key"] == "tiktok")["chart"]
        (a, b), = chart["series"][0]["est"]
        self.assertEqual([i for i, guess in enumerate(chart["guessed"]) if guess], list(range(a, b)))
        self.assertTrue(all(chart["values"][i] is not None for i in range(a, b)))

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
