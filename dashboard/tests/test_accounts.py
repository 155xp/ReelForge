"""Only connected platforms show anywhere in ReelForge, and the Accounts tab connects and disconnects them
(dashboard.platforms.base.Platform.connected, dashboard.service): a platform you haven't connected has no card, chart
key, Videos filter, upload button, best-time line or notification, and connecting it switches all of that on in place.
The window's own Accounts tab (the Connect box, Sign up, Disconnect) is tested in ui/test/dashboard.test.tsx."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from dashboard import config, db, demo, notify, sync
from dashboard import service as service_module
from dashboard.config import PLATFORM_KEYS
from dashboard.platforms import Instagram, TikTok, X, YouTube, browser, build, connected
from dashboard.service import NOTHING_CONNECTED, Dashboard
from dashboard.tests.window import Window, plain


def text(parts: list | None) -> str:
    """The text of (segments, importance) parts."""
    return "".join(plain(p[0]) for p in parts or [])


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


class WindowTest(unittest.TestCase):
    """A window's Python side on demo data, with some platforms not connected."""

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

    def open(self, platforms, tab: str | None = "overview", demo_mode: bool = True) -> Window:
        w = Window(self.cfg, platforms, demo=demo_mode, tab=tab, drawer=True)
        self.addCleanup(w.close)
        return w

    @staticmethod
    def panel(w: Window, key: str) -> dict:
        return next(p for p in w.view("accounts")["panels"] if p["key"] == key)

    @staticmethod
    def cards(w: Window) -> list[str]:
        return [c["id"] for c in w.view("cards")["cards"]]

    @staticmethod
    def buttons(w: Window) -> list[str]:
        """The platforms with upload buttons on Publish (the window draws them from this view)."""
        return [p["key"] for p in w.view("platforms")["platforms"]]

    def test_only_the_connected_ones_anywhere(self):
        self.forget("instagram", "x")
        notify.add("milestone", "X passed 1K followers", "You have 1,000 followers on X.",
                   key="milestone:followers:x:1000")
        notify.add("milestone", "TikTok passed 50K followers", "You have 50,000 followers on TikTok.",
                   key="milestone:followers:tiktok:50000")
        w = self.open(demo.platforms(unconnected=("instagram", "x")))
        self.assertEqual(list(w.svc.platforms), ["tiktok", "youtube"])
        self.assertEqual(self.cards(w), ["total", "tiktok", "youtube"])
        self.assertEqual(self.buttons(w), ["tiktok", "youtube"])
        self.assertEqual(len(w.view("best")["lines"]), 2)
        header = plain(w.view("header")["line"])
        self.assertIn("TikTok", header)
        self.assertNotIn("Instagram", header)
        key = plain(w.view("trends")["legend"])
        self.assertIn("YouTube", key)
        self.assertNotIn("Instagram", key)
        titles = [plain(n["title"]) for n in w.view("notes")["items"]]
        self.assertIn("TikTok passed 50K followers", titles)
        self.assertNotIn("X passed 1K followers", titles)
        w.call("tab_opened", "videos")
        filters = text(w.view("videos")["hint"])
        self.assertIn("YouTube", filters)
        self.assertNotIn("Instagram", filters)
        self.assertEqual({p["platform"] for p in w.svc.posts}, {"tiktok", "youtube"})
        self.assertEqual(self.panel(w, "x")["state"], "off")
        self.assertIsNone(self.panel(w, "x")["disconnect"])
        self.assertIn("Connect Instagram or X here", text(w.view("accounts")["hint"]))
        # Without X's button, the caption has a copy button of its own.
        copied = []
        with mock.patch.object(service_module.desktop, "copy", lambda t: copied.append(t) or True):
            w.call("copy_field", "copy-caption-alone", "What if your coffee doubled every 2 seconds?", "")
        self.assertEqual(copied, ["What if your coffee doubled every 2 seconds?"])

    def test_everything_shows_for_four_connected_platforms(self):
        """A ReelForge with all four connected: nothing is hidden and Accounts has no hint."""
        w = self.open(demo.platforms())
        self.assertEqual(list(w.svc.platforms), list(PLATFORM_KEYS))
        self.assertEqual(self.cards(w), ["total", *PLATFORM_KEYS])
        self.assertEqual(self.buttons(w), list(PLATFORM_KEYS))
        for key in PLATFORM_KEYS:
            self.assertEqual(self.panel(w, key)["state"], "on")
            self.assertTrue(self.panel(w, key)["disconnect"])
        self.assertIsNone(w.view("accounts")["hint"])

    def test_one_platform_is_its_own_total(self):
        self.forget("youtube", "instagram", "x")
        w = self.open(demo.platforms(unconnected=("youtube", "instagram", "x")))
        self.assertEqual(self.cards(w), ["tiktok"])

    def test_nothing_connected_opens_on_accounts(self):
        self.forget(*PLATFORM_KEYS)
        w = self.open(demo.platforms(unconnected=PLATFORM_KEYS), tab=None)
        self.assertEqual(w.init["tab"], "accounts")
        self.assertIn("No accounts connected yet", plain(w.view("header")["line"]))
        self.assertIn("Make a Gmail first", text(w.view("accounts")["hint"]))
        for key in PLATFORM_KEYS:
            panel = self.panel(w, key)
            self.assertEqual(panel["state"], "off")
            self.assertTrue(panel["signup"])
        self.assertEqual(self.cards(w), ["total"])
        self.assertIn("no accounts connected yet", plain(w.view("cards")["cards"][0]["message"]))
        self.assertEqual(w.view("trends")["metrics"]["views"]["empty"], NOTHING_CONNECTED)
        self.assertEqual(self.buttons(w), [])
        for tab in ("videos", "compare", "publish", "updates"):  # every tab copes with no platform at all
            w.call("tab_opened", tab)

    def test_hiding_every_platform_empties_the_charts(self):
        """Every platform hidden in the chart keys: each chart says how to show one again, and showing one brings its
        numbers back."""
        w = self.open(demo.platforms())
        for key in list(w.svc.platforms):
            w.call("toggle_line", key)
        for metric in ("views", "followers", "likes"):
            self.assertIn("Every platform is hidden", w.view("trends")["metrics"][metric]["empty"])
        w.call("toggle_line", "tiktok")
        self.assertTrue(w.view("trends")["metrics"]["views"]["variants"])

    def test_sign_up_guides(self):
        w = self.open(demo.platforms(unconnected=("x",)))
        guide = w.call("signup_guide", "x")
        self.assertTrue(guide["account"])
        self.assertTrue(guide["steps"][0].startswith("Press Open X sign-up"))
        self.assertIn("one log-in", guide["steps"][-1])
        self.assertFalse(w.call("signup_guide", "gmail")["account"])
        opened = []
        with mock.patch.object(service_module.signup, "open_page", opened.append):
            w.call("open_signup", "x")
        self.assertEqual(opened, ["https://x.com/i/flow/signup"])

    def real_platforms(self, handles: dict[str, str]):
        """TikTok, YouTube, Instagram and X as they are, on a config.toml in the scratch folder."""
        path = self.root / "config.toml"
        shutil.copy(config.APP_DIR / "config.example.toml", path)
        self.logged_in: dict[str, bool] = {}
        for patch in (mock.patch.object(config, "CONFIG_PATH", path),
                      mock.patch.object(browser, "logged_in", lambda key: self.logged_in.get(key, False)),
                      mock.patch.object(Dashboard, "start_updates", lambda self: None)):  # nothing asks GitHub
            patch.start()
            self.addCleanup(patch.stop)
        for key, handle in handles.items():
            config.save_handle(key, handle)
        fresh = config.load_config()
        self.cfg.update({key: fresh[key] for key in PLATFORM_KEYS})
        return build(self.cfg)

    def test_connect_and_disconnect_in_place(self):
        """A handle and Connect saves it and switches the platform on everywhere; Disconnect hides it again and keeps
        its stats. Nothing is read from the internet here: the reads are stood in for."""
        self.forget("youtube", "instagram", "x")
        every = self.real_platforms({"tiktok": "@mine"})
        reads, logins = [], []

        def no_read(platforms, cfg, *args, **kwargs):
            reads.append(sorted(platforms))
            return sync.Result()

        with mock.patch.object(sync, "refresh", no_read), \
                mock.patch.object(Dashboard, "_browser_login", lambda self, p: logins.append(p.key)):
            w = self.open(every, demo_mode=False)
            self.assertEqual(list(w.svc.platforms), ["tiktok"])
            self.assertEqual(self.cards(w), ["tiktok"])  # one platform: its own card is the total
            # A typo first: nothing is saved, and the panel says why.
            self.assertIn("isn't a handle", w.call("connect", "youtube", "my channel!"))
            self.assertEqual(config.load_config()["youtube"].get("handle", ""), "")
            # A pasted link works.
            self.assertIsNone(w.call("connect", "youtube", "https://www.youtube.com/@NewChannel"))
            self.assertTrue(w.until(lambda: "youtube" in w.svc.platforms))
            self.assertEqual(config.load_config()["youtube"]["handle"], "@NewChannel")
            self.assertEqual(list(w.svc.platforms), ["tiktok", "youtube"])
            self.assertEqual(self.buttons(w), ["tiktok", "youtube"])
            self.assertEqual(self.panel(w, "youtube")["state"], "on")
            self.assertTrue(w.until(lambda: ["youtube"] in reads))  # its first read, straight away
            # Instagram: the handle, then its one log-in.
            self.assertIsNone(w.call("connect", "instagram", "@mine"))
            self.assertTrue(w.until(lambda: logins == ["instagram"]))
            self.assertEqual(self.panel(w, "instagram")["state"], "login")
            self.assertNotIn("instagram", w.svc.platforms)
            self.logged_in["instagram"] = True  # the log-in went through
            w.call("follow_connections")
            self.assertIn("instagram", w.svc.platforms)
            self.assertIn("instagram", self.cards(w))
            # Disconnect TikTok: hidden everywhere, its stats kept.
            self.assertEqual(w.call("disconnect_info", "tiktok")["title"], "DISCONNECT TIKTOK?")
            w.call("disconnect", "tiktok")
            self.assertTrue(w.until(lambda: "tiktok" not in w.svc.platforms))
            self.assertEqual(config.load_config()["tiktok"]["handle"], "")
            self.assertNotIn("tiktok", self.cards(w))
            self.assertNotIn("tiktok", self.buttons(w))
            self.assertEqual(self.panel(w, "tiktok")["state"], "off")
            self.assertIn("tiktok", db.stored_platforms())

    def test_another_window_connecting_shows_here(self):
        """Every ReelForge window follows a platform connected (or disconnected) in another one."""
        self.forget("x")
        every = self.real_platforms({"tiktok": "@mine", "youtube": "@mine", "instagram": "@mine"})
        self.logged_in.update(instagram=True, x=True)
        with mock.patch.object(sync, "refresh", lambda *a, **k: sync.Result()):
            w = self.open(every, demo_mode=False)
            self.assertNotIn("x", w.svc.platforms)
            config.save_handle("x", "@mine")  # as another window's Connect does
            w.svc.config_seen = None  # (the file's time may not have moved within this second)
            self.assertTrue(w.until(lambda: "x" in w.svc.platforms))
            self.assertIn("x", self.cards(w))


if __name__ == "__main__":
    unittest.main()
