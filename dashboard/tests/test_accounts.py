"""Only connected platforms show anywhere in ReelForge, and the Accounts tab connects and disconnects them
(dashboard.platforms.base.Platform.connected, dashboard.app, dashboard.widgets.AccountPanel): a platform you haven't
connected has no card, chart key, Compare chart, Videos filter, upload button, best-time line or notification, and
connecting it switches all of that on in place."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from textual.widgets import Button, Input

from dashboard import app as app_module
from dashboard import config, db, demo, notify, sync
from dashboard.app import ReelForge
from dashboard.config import PLATFORM_KEYS
from dashboard.platforms import Instagram, TikTok, X, YouTube, browser, build, connected
from dashboard.widgets import AccountPanel

SIZE = (180, 50)


class ConnectedRule(unittest.TestCase):
    """Which platforms are on."""

    def test_a_handle_and_a_way_to_read_it(self):
        with mock.patch.object(browser, "logged_in", lambda key: False):
            self.assertFalse(TikTok({}).connected())
            self.assertTrue(TikTok({"handle": "@me"}).connected())
            self.assertTrue(YouTube({"handle": "me"}).connected())
            self.assertFalse(Instagram({"handle": "@me"}).connected())  # its one log-in is still to come
            self.assertTrue(Instagram({"handle": "@me"}).connected({"instagram"}))  # stats already: a lapsed log-in
            self.assertFalse(X({}).connected({"x"}))  # disconnected: its stats stay, hidden
        with mock.patch.object(browser, "logged_in", lambda key: True):
            self.assertTrue(X({"handle": "@me"}).connected())

    def test_in_reelforges_order(self):
        cfg = {"tiktok": {"handle": "@a"}, "youtube": {}, "instagram": {"handle": "@b"}, "x": {"handle": "@c"}}
        with mock.patch.object(browser, "logged_in", lambda key: key == "x"):
            self.assertEqual(list(connected(build(cfg))), ["tiktok", "x"])

    def test_what_a_notification_is_about(self):
        names = {"tiktok": "TikTok", "instagram": "Instagram", "x": "X"}
        about = lambda key, **note: notify.platform_of({"key": key, **note}, names)  # noqa: E731
        self.assertEqual(about("hot:instagram|123"), "instagram")
        self.assertEqual(about("milestone:video:x|9:1000"), "x")
        self.assertEqual(about("badge:day:tiktok:2026-10-25:views:10"), "tiktok")
        self.assertEqual(about("milestone:followers:youtube:1000"), "youtube")
        self.assertEqual(about("login:x"), "x")
        self.assertEqual(about(None, kind="login", title="Log in to Instagram again"), "instagram")
        for everyone in ("milestone:views:100000", "video:ep1.mp4", "update:1.0.5"):
            self.assertIsNone(about(everyone))


class Window(unittest.TestCase):
    """The real window on demo data, with some platforms not connected."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        self.root = root = Path(tmp.name)
        self.cfg = {"refresh_minutes": 0, "videos_dir": str(root / "none"), "episodes_dir": str(root / "none"),
                    "completed_dir": str(root / "none"), **{key: {} for key in PLATFORM_KEYS}}
        db.init(root / "demo.db")
        demo.seed()
        for state in (sync._attempted, sync.last_errors):
            state.clear()
            self.addCleanup(state.clear)

    def forget(self, *keys: str) -> None:
        """A channel that never had these connected: no stats for them."""
        with db.connect() as c:
            for table in ("account_stats", "post_stats", "posts", "uploads"):
                c.execute(f"DELETE FROM {table} WHERE platform IN ({','.join('?' * len(keys))})", keys)

    def run_app(self, platforms, scenario, tab: str | None = "overview", demo_mode: bool = True) -> ReelForge:
        app = ReelForge(self.cfg, platforms, demo=demo_mode, tab=tab, drawer=True)

        async def main() -> None:
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause(0.5)
                await scenario(app, pilot)

        asyncio.run(main())
        return app

    @staticmethod
    def shown(app: ReelForge, selector: str) -> bool:
        return app.query_one(selector).display

    def test_only_the_connected_ones_anywhere(self):
        self.forget("instagram", "x")
        notify.add("milestone", "X passed 1K followers", "You have 1,000 followers on X.",
                   key="milestone:followers:x:1000")
        notify.add("milestone", "TikTok passed 50K followers", "You have 50,000 followers on TikTok.",
                   key="milestone:followers:tiktok:50000")

        async def scenario(app: ReelForge, pilot) -> None:
            self.assertEqual(list(app.platforms), ["tiktok", "youtube"])
            for key in ("tiktok", "youtube"):
                for selector in (f"#card-{key}", f"#compare-{key}", f"#best-{key}", f"#open-{key}"):
                    self.assertTrue(self.shown(app, selector), selector)
            for key in ("instagram", "x"):
                for selector in (f"#card-{key}", f"#compare-{key}", f"#best-{key}", f"#open-{key}"):
                    self.assertFalse(self.shown(app, selector), selector)
            self.assertFalse(self.shown(app, "#copy-instagram"))
            self.assertTrue(self.shown(app, "#copy-caption-alone"))  # X's copy button is gone with it
            self.assertEqual(str(app.query_one("#open-all", Button).label), "Open all 2 →")
            header = app.query_one("#status").content.plain
            self.assertIn("TikTok", header)
            self.assertNotIn("Instagram", header)
            key = app.query_one("#trends-bar").content.plain
            self.assertIn("YouTube", key)
            self.assertNotIn("Instagram", key)
            titles = [n["title"] for n in notify.recent() if app.shows_note(n)]
            self.assertIn("TikTok passed 50K followers", titles)
            self.assertNotIn("X passed 1K followers", titles)
            app.action_tab("videos")
            await pilot.pause(0.3)
            filters = app.query_one("#videos-hint").content.plain
            self.assertIn("YouTube", filters)
            self.assertNotIn("Instagram", filters)
            self.assertEqual({p["platform"] for p in app.posts}, {"tiktok", "youtube"})
            self.assertEqual(app.query_one("#acct-x", AccountPanel).state, "off")
            # Without X's button, the caption has a copy button of its own.
            app.action_tab("publish")
            await pilot.pause(0.3)
            app.query_one("#f-caption", Input).value = "What if your coffee doubled every 2 seconds?"
            app.query_one("#copy-caption-alone", Button).press()  # (off to the right, beside the drawer)
            await pilot.pause(0.2)
            self.assertEqual(copied, ["What if your coffee doubled every 2 seconds?"])

        copied = []
        with mock.patch.object(app_module.desktop, "copy", lambda text: copied.append(text) or True):
            self.run_app(demo.platforms(unconnected=("instagram", "x")), scenario)

    def test_everything_shows_for_four_connected_platforms(self):
        """DJ's own ReelForge: all four connected, so nothing is hidden and Accounts has no hint."""

        async def scenario(app: ReelForge, pilot) -> None:
            self.assertEqual(list(app.platforms), list(PLATFORM_KEYS))
            for key in PLATFORM_KEYS:
                self.assertTrue(self.shown(app, f"#card-{key}"))
                self.assertEqual(app.query_one(f"#acct-{key}", AccountPanel).state, "on")
            self.assertEqual(str(app.query_one("#open-all", Button).label), "Open all 4 →")
            self.assertFalse(self.shown(app, "#copy-caption-alone"))
            self.assertFalse(self.shown(app, "#accounts-hint"))
            self.assertTrue(self.shown(app, "#card-total"))

        self.run_app(demo.platforms(), scenario)

    def test_nothing_connected_opens_on_accounts(self):
        self.forget(*PLATFORM_KEYS)

        async def scenario(app: ReelForge, pilot) -> None:
            self.assertEqual(app.query_one("TabbedContent").active, "accounts")
            self.assertIn("No accounts connected yet", app.query_one("#status").content.plain)
            self.assertIn("Make a Gmail first", app.query_one("#accounts-hint").content.plain)
            for key in PLATFORM_KEYS:
                panel = app.query_one(f"#acct-{key}", AccountPanel)
                self.assertEqual(panel.state, "off")
                self.assertTrue(panel.query(f"#handle-{key}") and panel.query(f"#signup-{key}"))
            app.action_tab("overview")
            await pilot.pause(0.3)
            self.assertIn("no accounts connected yet", str(app.query_one("#card-total .card-body").render()))
            self.assertEqual(str(app.query_one("#views-chart .empty").render()), app_module.NOTHING_CONNECTED)
            for tab in ("videos", "compare", "publish", "updates"):  # every tab copes with no platform at all
                app.action_tab(tab)
                await pilot.pause(0.3)
            self.assertFalse(self.shown(app, "#open-all") or self.shown(app, "#copy-caption-alone"))

        self.run_app(demo.platforms(unconnected=PLATFORM_KEYS), scenario, tab=None)

    def real_platforms(self, handles: dict[str, str]):
        """TikTok, YouTube, Instagram and X as they are, on a config.toml in the scratch folder."""
        path = self.root / "config.toml"
        shutil.copy(config.APP_DIR / "config.example.toml", path)
        self.logged_in: dict[str, bool] = {}
        for patch in (mock.patch.object(config, "CONFIG_PATH", path),
                      mock.patch.object(browser, "logged_in", lambda key: self.logged_in.get(key, False))):
            patch.start()
            self.addCleanup(patch.stop)
        for key, handle in handles.items():
            config.save_handle(key, handle)
        fresh = config.load_config()
        self.cfg.update({key: fresh[key] for key in PLATFORM_KEYS})
        return build(self.cfg)

    def test_connect_and_disconnect_in_place(self):
        """Typing a handle and pressing Connect saves it and switches the platform on everywhere; Disconnect hides it
        again and keeps its stats. Nothing is read from the internet here: the reads are stood in for."""
        self.forget("youtube", "instagram", "x")
        every = self.real_platforms({"tiktok": "@mine"})
        reads, logins = [], []

        def no_read(platforms, cfg, *args, **kwargs):
            reads.append(sorted(platforms))
            return sync.Result()

        async def scenario(app: ReelForge, pilot) -> None:
            self.assertEqual(list(app.platforms), ["tiktok"])
            self.assertFalse(self.shown(app, "#card-total"))  # one platform: its own card is the total
            app.action_tab("accounts")
            await pilot.pause(0.3)
            # A typo first: nothing is saved, and the panel says why.
            app.query_one("#handle-youtube", Input).value = "my channel!"
            await pilot.click("#connect-youtube")
            await pilot.pause(0.3)
            self.assertIn("isn't a handle", str(app.query_one("#acct-youtube .acct-error").render()))
            self.assertEqual(config.load_config()["youtube"].get("handle", ""), "")
            # A pasted link works.
            app.query_one("#handle-youtube", Input).value = "https://www.youtube.com/@NewChannel"
            await pilot.click("#connect-youtube")
            for _ in range(30):
                await pilot.pause(0.1)
                if "youtube" in app.platforms:
                    break
            self.assertEqual(config.load_config()["youtube"]["handle"], "@NewChannel")
            self.assertEqual(list(app.platforms), ["tiktok", "youtube"])
            self.assertTrue(self.shown(app, "#card-youtube") and self.shown(app, "#open-youtube"))
            self.assertEqual(app.query_one("#acct-youtube", AccountPanel).state, "on")
            await pilot.pause(0.3)
            self.assertIn(["youtube"], reads)  # its first read, straight away
            # Instagram: the handle, then its one log-in.
            app.query_one("#handle-instagram", Input).value = "@mine"
            await pilot.click("#connect-instagram")
            for _ in range(30):
                await pilot.pause(0.1)
                if logins:
                    break
            self.assertEqual(logins, ["instagram"])
            self.assertEqual(app.query_one("#acct-instagram", AccountPanel).state, "login")
            self.assertNotIn("instagram", app.platforms)
            self.logged_in["instagram"] = True  # the log-in went through
            await app.follow_connections()
            await pilot.pause(0.2)
            self.assertIn("instagram", app.platforms)
            self.assertTrue(self.shown(app, "#card-instagram"))
            # Disconnect TikTok: hidden everywhere, its stats kept.
            app.action_disconnect("tiktok")
            await pilot.pause(0.3)
            await pilot.click("#disconnect")
            for _ in range(30):
                await pilot.pause(0.1)
                if "tiktok" not in app.platforms:
                    break
            self.assertEqual(config.load_config()["tiktok"]["handle"], "")
            self.assertNotIn("tiktok", app.platforms)
            self.assertFalse(self.shown(app, "#card-tiktok") or self.shown(app, "#open-tiktok"))
            self.assertEqual(app.query_one("#acct-tiktok", AccountPanel).state, "off")
            self.assertIn("tiktok", db.stored_platforms())

        with mock.patch.object(sync, "refresh", no_read), \
                mock.patch.object(ReelForge, "run_browser_login", lambda self, p: logins.append(p.key)):
            self.run_app(every, scenario, demo_mode=False)

    def test_another_window_connecting_shows_here(self):
        """Every ReelForge window follows a platform connected (or disconnected) in another one."""
        self.forget("x")
        every = self.real_platforms({"tiktok": "@mine", "youtube": "@mine", "instagram": "@mine"})
        self.logged_in.update(instagram=True, x=True)

        async def scenario(app: ReelForge, pilot) -> None:
            self.assertNotIn("x", app.platforms)
            config.save_handle("x", "@mine")  # as another window's Connect does
            app.config_seen = None  # (the file's time may not have moved within this second)
            for _ in range(40):
                await pilot.pause(0.1)
                if "x" in app.platforms:
                    break
            self.assertIn("x", app.platforms)
            self.assertTrue(self.shown(app, "#card-x"))

        with mock.patch.object(sync, "refresh", lambda *a, **k: sync.Result()):
            self.run_app(every, scenario, demo_mode=False)


if __name__ == "__main__":
    unittest.main()
