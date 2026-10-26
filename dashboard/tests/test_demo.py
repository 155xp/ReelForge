"""Demo mode's made-up numbers hang together, every notification it makes leads somewhere, and a test copy says
TEST in the header (dashboard.demo, dashboard.service). The cards, the bell and a notification's × are tested in
ui/test/widgets.test.ts."""

from __future__ import annotations

import statistics
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from dashboard import analytics, db, demo, notify, trends
from dashboard.tests.window import Window, plain


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

    def test_every_notification_leads_somewhere(self):
        posts = {f"{p['platform']}|{p['post_id']}" for p in db.posts_latest()}
        for n in notify.recent():
            to = notify.target(n)
            self.assertIn(to.tab, ("overview", "videos", "publish", "accounts", "updates"), n)
            self.assertTrue(to.post in posts if to.post else to.file or to.card or to.account or to.tab == "updates",
                            n)


class TestCopyHeader(unittest.TestCase):
    """A test copy (TEST-COPY.txt in the ReelForge folder) says TEST in the header and the window title. The title is
    just ReelForge (or ReelForge TEST) whatever the channel is called."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        db.init(Path(tmp.name) / "demo.db")
        demo.seed()

    def test_test_badge(self):
        from dashboard import config, service

        def run(test_copy: bool) -> tuple[str, str]:
            with mock.patch.object(service, "TEST_COPY", test_copy):
                cfg = {**config.load_config(), "name": "Night Physics"}  # what older onboarding wrote there
                w = Window(cfg, demo.platforms())
                self.addCleanup(w.close)
                return w.init["title"], plain(w.view("header")["line"])

        title, header = run(True)
        self.assertEqual(title, "ReelForge TEST")
        self.assertTrue(header.startswith(" TEST "), header)
        title, header = run(False)
        self.assertEqual(title, "ReelForge")
        self.assertNotIn("TEST", header)


if __name__ == "__main__":
    unittest.main()
