"""Automatic refresh can be disabled for public and browser readers alike."""

import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from dashboard import analytics, db, sync


class RefreshSchedule(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(sync._attempted, {}, clear=True)
        patch.start()
        self.addCleanup(patch.stop)

    def test_disabled_auto_refresh_never_becomes_due(self):
        old = db.to_iso(analytics.now() - timedelta(days=1))
        for browser in (False, True):
            p = SimpleNamespace(key="test", uses_browser=browser, has_stats=True)
            for last in (None, old):
                for fresh in (False, True):
                    with self.subTest(browser=browser, last=last, fresh=fresh):
                        self.assertFalse(sync.due(p, {"refresh_minutes": 0}, last, False, fresh))
                        self.assertIsNone(sync.next_read(p, {"refresh_minutes": 0}, last, fresh))
                        self.assertTrue(sync.due(p, {"refresh_minutes": 0}, last, True, fresh))

    def test_enabled_auto_refresh_and_manual_throttles_still_apply(self):
        now = analytics.now()
        for browser, minutes in ((False, 2), (True, 10)):
            p = SimpleNamespace(key="test", uses_browser=browser, has_stats=True)
            self.assertTrue(sync.due(p, {"refresh_minutes": 30}, None, False))
            self.assertFalse(sync.due(p, {"refresh_minutes": 0}, db.to_iso(now), True))
            old = db.to_iso(now - timedelta(minutes=minutes))
            self.assertTrue(sync.due(p, {"refresh_minutes": 0}, old, True))
            self.assertIsNotNone(sync.next_read(p, {"refresh_minutes": 30}, old))
