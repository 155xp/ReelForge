"""Clicking a notification shows what it's about, on demo data: the video on the Videos tab (its platform's videos
showing, it highlighted and the table given the keyboard), the finished video on Publish, the platform's panel on
Accounts or card on the Overview, and the Updates tab; also when that tab is open already. Its × deletes it for good
instead, and Clear all deletes every one (dashboard.service, dashboard.notify). How the drawer and the tables
behave under the mouse is tested in ui/test/dashboard.test.tsx."""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dashboard import db, demo, notify
from dashboard.config import PLATFORM_KEYS
from dashboard.platforms.base import Account, Post
from dashboard.tests.window import Window, plain


class NoteClickTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        root = Path(tmp.name)
        folder = root / "videos"
        folder.mkdir()
        for i, name in enumerate(("older.mp4", "middle.mp4", "newest.mp4")):
            (folder / name).write_bytes(b"x")
            os.utime(folder / name, (time.time() - 600 + i * 60,) * 2)
        self.cfg = {"refresh_minutes": 0, "videos_dir": str(folder), "episodes_dir": str(root / "none"),
                    "completed_dir": str(root / "none"), **{key: {} for key in PLATFORM_KEYS}}
        db.init(root / "demo.db")
        demo.seed(video=demo.newest_video(self.cfg))
        # Plenty of older TikTok videos, so the list is longer than the window.
        now = datetime.now(timezone.utc)
        db.record_snapshot("tiktok", Account("@yourchannel", 12_000), [
            Post(f"old-{i}", f"Old video {i}", None, db.to_iso(now - timedelta(days=20, hours=i)), views=900 - i,
                 likes=20, comments=2, shares=1) for i in range(60)])
        # The demo's own notes depend on the time of day, so these two are always there.
        newest = max(e["id"] for e in db.episodes())  # the demo's posts are "<platform>-<episode id>"
        self.hot = f"hot:tiktok|tiktok-{newest}"
        notify.add("hot", "Taking off on TikTok", "The newest video is doing 4.2× your typical video.", key=self.hot)
        notify.add("milestone", "TikTok passed 10K followers", "You have 10,021 followers on TikTok.",
                   key="milestone:followers:tiktok:10000")
        # At some hours the demo has told the same news already and marked it read; the × tests need it unread.
        with db.connect() as c:
            c.execute("UPDATE notifications SET read = 0 WHERE key = ?", (self.hot,))

    def window(self, tab: str = "overview", **options) -> Window:
        w = Window(self.cfg, demo.platforms(), tab=tab, drawer=True, **options)
        self.addCleanup(w.close)
        w.call("drawer_opened")
        return w

    @staticmethod
    def note(key: str | None, title: str | None = None) -> dict:
        return next(n for n in notify.recent() if (n["key"] == key if key else n["title"] == title))

    def click(self, w: Window, key: str | None, title: str | None = None) -> dict:
        """Click the notification with this key (or title) in the drawer; the window opens the tab it's sent to."""
        note = self.note(key, title)
        w.call("open_note", note["id"])
        tab = w.view("tab")
        if tab:
            w.call("tab_opened", tab["tab"])
        return note

    @staticmethod
    def shown(w: Window) -> list[str]:
        """The notifications in the drawer, by title."""
        return [plain(n["title"]) for n in w.view("notes")["items"]]

    def test_the_x_deletes_it_for_good_without_opening_it(self):
        w = self.window()
        unread = w.view("notes")["unread"]
        before = self.shown(w)
        w.forget()
        w.call("delete_note", self.note(self.hot)["id"])
        self.assertIsNone(w.view("tab"))  # it didn't open the video
        after = self.shown(w)
        self.assertEqual(len(after), len(before) - 1)
        self.assertNotIn(self.hot, [n["key"] for n in notify.recent()])
        self.assertEqual(w.view("notes")["unread"], unread - 1)  # it was unread: the bell's dot follows
        # The next refresh finds the video still taking off: it stays deleted.
        notify.add("hot", "Taking off on TikTok", "The newest video is doing 4.4× your typical video.", key=self.hot)
        w.svc.show_new_notes()
        w.pump(0.05)
        self.assertEqual(self.shown(w), after)
        # And the next time ReelForge opens.
        again = self.window()
        self.assertNotIn(self.hot, [n["key"] for n in notify.recent()])
        self.assertEqual(self.shown(again), after)

    def test_deleting_them_all_leaves_nothing_yet(self):
        w = self.window()
        for n in notify.recent():
            w.call("delete_note", n["id"])
        notes = w.view("notes")
        self.assertEqual((notify.recent(), notes["items"], notes["unread"]), ([], [], 0))
        self.assertIn("Nothing yet", notes["empty"])
        self.assertEqual(plain(notes["tools"]), "")  # nothing left to read or clear

    def test_clear_all_deletes_them_all_for_good(self):
        w = self.window()
        self.assertIn("Mark all read", plain(w.view("notes")["tools"]))  # some are unread
        w.forget()
        w.call("clear_notes")
        notes = w.view("notes")
        self.assertEqual((notify.recent(), notes["items"], notes["unread"]), ([], [], 0))
        self.assertEqual(plain(notes["tools"]).strip(), "")
        self.assertIsNone(w.view("tab"))
        # The next refresh finds the same video still taking off: it stays cleared. Something new still shows.
        notify.add("hot", "Taking off on TikTok", "The newest video is doing 4.4× your typical video.", key=self.hot)
        notify.add("info", "Something new", "It happened after Clear all.")
        w.svc.show_new_notes()
        w.pump(0.05)
        self.assertEqual(self.shown(w), ["Something new"])
        self.assertEqual(plain(w.view("notes")["tools"]).strip(), "Mark all read    Clear all")

    def test_taking_off_shows_the_video(self):
        post = self.hot.split(":", 1)[1]
        w = self.window()
        note = self.click(w, self.hot)
        self.assertEqual(w.view("tab"), {"tab": "videos"})
        self.assertEqual(w.svc.filter, post.split("|")[0])  # only that platform's videos
        videos = w.view("videos")
        self.assertEqual((videos["select"], videos["focus"]), (post, True))  # highlighted, with the keyboard
        self.assertTrue(all(r["key"].startswith("tiktok|") for r in videos["rows"]))
        self.assertEqual(w.view("detail")["key"], post)  # its chart underneath
        self.assertTrue(self.note(None, note["title"])["read"])

    def test_a_video_far_down_the_list_when_videos_is_open_already(self):
        # Saved by an older ReelForge with the Overview as its tab.
        notify.add("milestone", "A video passed 1K views on TikTok", "Old video 59",
                   key="milestone:video:tiktok|old-59:1000", tab="overview")
        w = self.window("videos")
        w.call("set_filter", "youtube")
        self.click(w, "milestone:video:tiktok|old-59:1000")
        self.assertEqual(w.svc.filter, "tiktok")
        keys = [r["key"] for r in w.view("videos")["rows"]]
        self.assertEqual(w.view("videos")["select"], "tiktok|old-59")
        self.assertGreater(keys.index("tiktok|old-59"), 40)  # the lowest score of 69 TikTok videos: far down
        self.click(w, self.hot)  # another one moves the highlight there
        self.assertEqual(w.view("videos")["select"], self.hot.split(":", 1)[1])
        # And from another tab, with the Videos list waiting to be rebuilt.
        w.call("tab_opened", "compare")
        w.call("set_filter", "")
        w.svc.stale.add("videos")
        self.click(w, "milestone:video:tiktok|old-59:1000")
        self.assertEqual(w.view("videos")["select"], "tiktok|old-59")

    def test_follower_milestone_frames_the_account(self):
        w = self.window("accounts")
        w.forget()
        self.click(w, "milestone:followers:tiktok:10000")
        self.assertEqual(w.view("tab"), {"tab": "accounts"})
        self.assertEqual(w.sent("pick"), [{"id": "acct-tiktok"}])  # the window frames it for a few seconds

    def test_log_in_notes_frame_the_platform_and_give_log_in_the_keyboard(self):
        notify.add("login", "Log in to Instagram again", "Instagram wants you to log in again.", key="login:instagram")
        notify.release("login:instagram")  # it worked again since: the key is gone, the title still says which
        notify.add("login", "Log in to X again", "X logged ReelForge out.", key="login:x")
        w = self.window(screenshots=True)  # Instagram and X with Log in buttons, as when set up
        self.click(w, "login:x")
        self.assertEqual(w.view("tab"), {"tab": "accounts"})
        self.assertEqual((w.view("pick"), w.view("focus")), ({"id": "acct-x"}, {"id": "login-x"}))
        self.assertTrue(next(p for p in w.view("accounts")["panels"] if p["key"] == "x")["logs_in"])
        self.click(w, None, "Log in to Instagram again")
        self.assertEqual((w.view("pick"), w.view("focus")), ({"id": "acct-instagram"}, {"id": "login-instagram"}))

    def test_ready_to_post_picks_the_file_from_anywhere(self):
        notify.add("video", "A new video is ready to post", "Older (older.mp4)", key="video:older.mp4")
        w = self.window()
        for start in ("overview", "publish"):
            w.call("tab_opened", start)
            w.call("pick_file", str(Path(self.cfg["videos_dir"]) / "middle.mp4"))  # another video picked before
            w.forget()
            self.click(w, "video:older.mp4")
            self.assertEqual(w.view("tab"), {"tab": "publish"}, start)
            self.assertEqual(Path(w.view("files")["selected"]).name, "older.mp4", start)
            self.assertEqual((Path(w.view("form")["file"]).name, w.view("form")["caption"]), ("older.mp4", "Older"))
            self.assertEqual(w.view("focus"), {"id": "file-list"})
        self.click(w, "video:newest.mp4")  # the demo's own note: the newest video
        self.assertEqual(w.svc.selected_file.name, "newest.mp4")

    def test_day_badges_and_totals_frame_overview_cards(self):
        notify.add("badge", "Today: your best day yet for new YouTube followers", "+40 so far · #1 of 9",
                   key="badge:day:youtube:2026-10-24:followers:5")
        notify.add("milestone", "1M views in total", "Your videos have 1,000,000 views.", key="milestone:views:1000000")
        w = self.window("videos")
        self.click(w, "badge:day:youtube:2026-10-24:followers:5")
        self.assertEqual((w.view("tab"), w.view("pick")), ({"tab": "overview"}, {"id": "card-youtube"}))
        self.click(w, "milestone:views:1000000")
        self.assertEqual(w.view("pick"), {"id": "card-total"})

    def test_updates_and_videos_that_are_gone(self):
        notify.add("hot", "Taking off on TikTok", "A deleted video", key="hot:tiktok|deleted")
        notify.add("video", "A new video is ready to post", "Gone (gone.mp4)", key="video:gone.mp4")
        w = self.window()
        w.forget()
        self.click(w, next(n["key"] for n in notify.recent() if n["kind"] == "update"))
        self.assertEqual(w.view("tab"), {"tab": "updates"})
        self.click(w, "hot:tiktok|deleted")
        self.assertEqual(w.view("tab"), {"tab": "videos"})
        self.click(w, "video:gone.mp4")
        self.assertEqual(w.view("tab"), {"tab": "publish"})
        self.assertEqual([t for t in w.toasts() if "any more" in t],
                         ["That video isn't on the Videos tab any more.",
                          "gone.mp4 isn't in your video folders any more."])


if __name__ == "__main__":
    unittest.main()
