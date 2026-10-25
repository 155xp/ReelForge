"""Clicking a notification shows what it's about, in the real window on demo data: the video on the Videos tab (its
platform's videos showing, scrolled into view), the finished video on Publish, the platform's panel on Accounts or
card on the Overview, and the Updates tab; also when that tab is open already. Clicking its × (or Delete) deletes it
for good instead, and Clear all deletes every one (dashboard.app, dashboard.notify)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from textual.color import Color
from textual.widgets import DataTable, Input, OptionList, TabbedContent

from dashboard import app as app_module
from dashboard import db, demo, notify, widgets
from dashboard.app import ReelForge
from dashboard.config import PLATFORM_KEYS
from dashboard.platforms.base import Account, Post
from dashboard.widgets import Bell, NoteList

SIZE = (160, 45)  # with the drawer open, the Videos table is narrower than its columns, as on a laptop


def rows_in_sight(table: DataTable) -> range:
    """The rows a DataTable shows: one line each, under its header."""
    top = round(table.scroll_y)
    return range(top, top + table.scrollable_content_region.height - table.header_height)


def border(widget) -> tuple[str, Color]:
    return widget.styles.border.top


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

    def run_app(self, scenario, tab: str = "overview") -> ReelForge:
        """Open ReelForge on `tab` with the drawer open, then run `scenario(app, pilot)`."""
        app = ReelForge(self.cfg, demo.platforms(), demo=True, tab=tab, drawer=True)

        async def main() -> None:
            async with app.run_test(size=SIZE) as pilot:
                await pilot.pause(0.3)
                await scenario(app, pilot)

        asyncio.run(main())
        return app

    @staticmethod
    async def click(app: ReelForge, pilot, key: str | None, title: str | None = None) -> dict:
        """Click the notification with this key (or title) in the drawer."""
        note = next(n for n in notify.recent() if (n["key"] == key if key else n["title"] == title))
        box = app.query_one("#notes", OptionList)
        index = box.get_option_index(f"note-{note['id']}")
        box.highlighted = index  # scrolls it into sight
        await pilot.pause()
        await pilot.click(box, offset=(6, box._index_to_line[index] - round(box.scroll_y)))
        await pilot.pause(0.3)
        return note

    @staticmethod
    async def click_x(app: ReelForge, pilot, key: str | None, title: str | None = None) -> dict:
        """Click the middle of the × on this notification's right side (scrolled into sight, not highlighted)."""
        note = next(n for n in notify.recent() if (n["key"] == key if key else n["title"] == title))
        box = app.query_one("#notes", NoteList)
        index = box.get_option_index(f"note-{note['id']}")
        line = box._index_to_line[index] + (box._heights[index] - 2) // 2  # its middle line (the gap under it aside)
        if not box.scroll_y <= line < box.scroll_y + box.scrollable_content_region.height:
            box.scroll_to(y=line, animate=False)
            await pilot.pause()
        x = box.scrollable_content_region.right - box.region.x - 1 - widgets.X_WIDTH // 2  # the middle of the ×
        await pilot.click(box, offset=(x, line - round(box.scroll_y)))
        await pilot.pause(0.3)
        return note

    @staticmethod
    def tools(app: ReelForge) -> str:
        """The buttons under the drawer's heading."""
        return app.query_one("#drawer-tools").content.plain

    @staticmethod
    def shown(app: ReelForge) -> list[str]:
        """The notifications in the drawer, by title."""
        ids = [o.id for o in app.query_one("#notes", NoteList).options]
        titles = {f"note-{n['id']}": n["title"] for n in notify.recent()}
        return [titles.get(i, "?") for i in ids]

    def test_the_x_deletes_it_for_good_without_opening_it(self):
        unread = notify.unread()

        async def scenario(app, pilot):
            box = app.query_one("#notes", NoteList)
            before = self.shown(app)
            box.highlighted = len(before) - 1  # the oldest, below it
            await pilot.pause()
            await self.click_x(app, pilot, self.hot)
            self.assertEqual(app.query_one(TabbedContent).active, "overview")  # it didn't open the video
            self.assertEqual(self.shown(app)[box.highlighted], before[-1])  # nor move the highlight
            after = self.shown(app)
            self.assertEqual(len(after), len(before) - 1)
            self.assertNotIn(self.hot, [n["key"] for n in notify.recent()])
            self.assertEqual(app.query_one("#bell", Bell).unread, unread - 1)  # it was unread
            # The next refresh finds the video still taking off: it stays deleted.
            notify.add("hot", "Taking off on TikTok", "The newest video is doing 4.4× your typical video.", key=self.hot)
            app.show_new_notes()
            await pilot.pause()
            self.assertEqual(self.shown(app), after)

        self.run_app(scenario)

        async def reopened(app, pilot):  # and the next time ReelForge opens
            self.assertNotIn("?", self.shown(app))
            self.assertNotIn(self.hot, [n["key"] for n in notify.recent()])

        self.run_app(reopened)

    def test_deleting_one_far_down_leaves_the_list_where_it_is(self):
        for i in range(30):
            notify.add("info", f"Older news {i}", "Something that happened a while ago.")

        async def scenario(app, pilot):
            box = app.query_one("#notes", NoteList)
            box.highlighted = self.shown(app).index("Older news 10")  # far down the list
            box.scroll_to(y=box._index_to_line[box.highlighted - 1] - 1, animate=False)  # with the one above it
            await pilot.pause(0.2)
            top, picked = round(box.scroll_y), box.highlighted_option.id
            self.assertGreater(top, 20)
            above = self.shown(app)[box.highlighted - 1]
            await self.click_x(app, pilot, None, above)
            self.assertNotIn(above, self.shown(app))
            self.assertEqual(round(box.scroll_y), top)  # no jump back to the top
            self.assertEqual(box.highlighted_option.id, picked)  # still on "Older news 10"
            self.assertEqual(app.query_one(TabbedContent).active, "overview")

        self.run_app(scenario)

    def test_delete_deletes_the_highlighted_one(self):
        async def scenario(app, pilot):
            box = app.query_one("#notes", NoteList)
            box.focus()
            box.highlighted = 1
            await pilot.pause()
            second, third = self.shown(app)[1:3]
            await pilot.press("delete")
            await pilot.pause(0.2)
            self.assertNotIn(second, self.shown(app))
            self.assertEqual(self.shown(app)[box.highlighted], third)  # the next one is highlighted now
            self.assertIs(app.focused, box)
            self.assertEqual(app.query_one(TabbedContent).active, "overview")

        self.run_app(scenario)

    def test_deleting_them_all_leaves_nothing_yet(self):
        async def scenario(app, pilot):
            box = app.query_one("#notes", NoteList)
            for title in self.shown(app):
                await self.click_x(app, pilot, None, title)
            self.assertEqual(notify.recent(), [])
            self.assertEqual(box.option_count, 1)
            self.assertTrue(box.get_option_at_index(0).disabled)
            self.assertIn("Nothing yet", str(box.get_option_at_index(0).prompt))
            self.assertEqual(app.query_one("#bell", Bell).unread, 0)

        self.run_app(scenario)

    def test_clear_all_deletes_them_all_for_good(self):
        async def scenario(app, pilot):
            box = app.query_one("#notes", NoteList)
            self.assertIn("Mark all read", self.tools(app))  # some are unread
            await pilot.click("#drawer-tools", offset=(self.tools(app).index("Clear all") + 2, 0))
            await pilot.pause(0.3)
            self.assertEqual(notify.recent(), [])
            self.assertIn("Nothing yet", str(box.get_option_at_index(0).prompt))
            self.assertEqual(app.query_one("#bell", Bell).unread, 0)
            self.assertEqual(self.tools(app).strip(), "")  # nothing left to read or clear
            self.assertEqual(app.query_one(TabbedContent).active, "overview")
            # The next refresh finds the same video still taking off: it stays cleared. Something new still shows.
            notify.add("hot", "Taking off on TikTok", "The newest video is doing 4.4× your typical video.", key=self.hot)
            notify.add("info", "Something new", "It happened after Clear all.")
            app.show_new_notes()
            await pilot.pause()
            self.assertEqual(self.shown(app), ["Something new"])
            self.assertEqual(self.tools(app).strip(), "Mark all read    Clear all")

        self.run_app(scenario)

    def test_taking_off_shows_the_video(self):
        post = self.hot.split(":", 1)[1]

        async def scenario(app, pilot):
            note = await self.click(app, pilot, self.hot)
            table = app.query_one("#videos-table", DataTable)
            self.assertEqual(app.query_one(TabbedContent).active, "videos")
            self.assertEqual(app.filter, post.split("|")[0])  # only that platform's videos
            self.assertEqual(app._cursor_key(table), post)
            self.assertIn(table.cursor_row, rows_in_sight(table))
            self.assertIs(app.focused, table)
            self.assertEqual(app.detail_state[0]["post_id"], post.split("|")[1])  # its chart underneath
            self.assertTrue(next(n for n in notify.recent() if n["id"] == note["id"])["read"])

        self.run_app(scenario)

    def test_a_video_far_down_the_list_scrolls_into_view_when_videos_is_open_already(self):
        # Saved by an older ReelForge with the Overview as its tab.
        notify.add("milestone", "A video passed 1K views on TikTok", "Old video 59",
                   key="milestone:video:tiktok|old-59:1000", tab="overview")

        async def scenario(app, pilot):
            table = app.query_one("#videos-table", DataTable)
            await pilot.click(table, offset=(10, 3))  # another video highlighted, the list at the top
            app.action_set_filter("youtube")
            await pilot.pause(0.2)
            self.assertEqual(round(table.scroll_y), 0)
            await self.click(app, pilot, "milestone:video:tiktok|old-59:1000")
            self.assertEqual(app.query_one(TabbedContent).active, "videos")
            self.assertEqual(app.filter, "tiktok")
            self.assertEqual(app._cursor_key(table), "tiktok|old-59")
            self.assertGreater(table.cursor_row, 40)  # the lowest score of 69 TikTok videos: far down the list
            self.assertIn(table.cursor_row, rows_in_sight(table))
            # Clicking another one moves the highlight there, and the list back up.
            await self.click(app, pilot, self.hot)
            self.assertEqual(app._cursor_key(table), self.hot.split(":", 1)[1])
            self.assertIn(table.cursor_row, rows_in_sight(table))
            # And from another tab, with the Videos list waiting to be rebuilt.
            app.action_tab("compare")
            app.action_set_filter("")
            app.stale.add("videos")
            await pilot.pause(0.2)
            await self.click(app, pilot, "milestone:video:tiktok|old-59:1000")
            self.assertEqual(app._cursor_key(table), "tiktok|old-59")
            self.assertIn(table.cursor_row, rows_in_sight(table))

        self.run_app(scenario, tab="videos")

    def test_follower_milestone_frames_the_account_for_a_few_seconds(self):
        async def scenario(app, pilot):
            panel = app.query_one("#acct-tiktok")
            self.assertEqual(border(panel), ("round", Color.parse(panel.color)))
            await self.click(app, pilot, "milestone:followers:tiktok:10000")
            self.assertEqual(app.query_one(TabbedContent).active, "accounts")
            self.assertTrue(panel.has_class("picked"))
            self.assertEqual(border(panel), ("heavy", Color.parse(widgets.PICKED)))
            self.assertFalse(app.query_one("#acct-youtube").has_class("picked"))
            await pilot.pause(1.2)
            self.assertFalse(panel.has_class("picked"))
            self.assertEqual(border(panel), ("round", Color.parse(panel.color)))

        with mock.patch.object(app_module, "PICKED_FOR", 1.0):
            self.run_app(scenario, tab="accounts")

    def test_log_in_notes_frame_the_platform_and_focus_log_in(self):
        notify.add("login", "Log in to Instagram again", "Instagram wants you to log in again.", key="login:instagram")
        notify.release("login:instagram")  # it worked again since: the key is gone, the title still says which
        notify.add("login", "Log in to X again", "X logged ReelForge out.", key="login:x")

        async def scenario(app, pilot):
            await self.click(app, pilot, "login:x")
            self.assertEqual(app.query_one(TabbedContent).active, "accounts")
            self.assertTrue(app.query_one("#acct-x").has_class("picked"))
            self.assertEqual(app.focused.id, "login-x")
            await self.click(app, pilot, None, "Log in to Instagram again")
            self.assertTrue(app.query_one("#acct-instagram").has_class("picked"))
            self.assertFalse(app.query_one("#acct-x").has_class("picked"))  # one at a time
            self.assertEqual(app.focused.id, "login-instagram")

        with mock.patch.object(widgets, "SCREENSHOTS", True):  # Instagram and X with Log in buttons, as when set up
            self.run_app(scenario)

    def test_ready_to_post_picks_the_file_from_anywhere(self):
        notify.add("video", "A new video is ready to post", "Older (older.mp4)", key="video:older.mp4")

        async def scenario(app, pilot):
            files = app.query_one("#file-list", OptionList)
            for start in ("overview", "publish"):
                app.action_tab(start)
                await pilot.pause(0.2)
                app.pick(Path(self.cfg["videos_dir"]) / "middle.mp4")  # another video picked before
                await self.click(app, pilot, "video:older.mp4")
                self.assertEqual(app.query_one(TabbedContent).active, "publish")
                self.assertEqual(app.selected_file.name, "older.mp4", start)
                self.assertEqual(Path(files.get_option_at_index(files.highlighted).id).name, "older.mp4", start)
                self.assertEqual(app.query_one("#f-caption", Input).value, "Older", start)
                self.assertIs(app.focused, files)
            await self.click(app, pilot, "video:newest.mp4")  # the demo's own note: the newest video
            self.assertEqual(app.selected_file.name, "newest.mp4")

        self.run_app(scenario)

    def test_day_badges_and_totals_frame_overview_cards(self):
        notify.add("badge", "Today: your best day yet for new YouTube followers", "+40 so far · #1 of 9",
                   key="badge:day:youtube:2026-10-24:followers:5")
        notify.add("milestone", "1M views in total", "Your videos have 1,000,000 views.", key="milestone:views:1000000")

        async def scenario(app, pilot):
            await self.click(app, pilot, "badge:day:youtube:2026-10-24:followers:5")
            self.assertEqual(app.query_one(TabbedContent).active, "overview")
            self.assertTrue(app.query_one("#card-youtube").has_class("picked"))
            await self.click(app, pilot, "milestone:views:1000000")
            self.assertTrue(app.query_one("#card-total").has_class("picked"))
            self.assertFalse(app.query_one("#card-youtube").has_class("picked"))

        self.run_app(scenario, tab="videos")

    def test_updates_and_videos_that_are_gone(self):
        notify.add("hot", "Taking off on TikTok", "A deleted video", key="hot:tiktok|deleted")
        notify.add("video", "A new video is ready to post", "Gone (gone.mp4)", key="video:gone.mp4")
        said: list[str] = []

        async def scenario(app, pilot):
            app.notify = lambda message, **kw: said.append(message)
            await self.click(app, pilot, next(n["key"] for n in notify.recent() if n["kind"] == "update"))
            self.assertEqual(app.query_one(TabbedContent).active, "updates")
            await self.click(app, pilot, "hot:tiktok|deleted")
            self.assertEqual(app.query_one(TabbedContent).active, "videos")
            await self.click(app, pilot, "video:gone.mp4")
            self.assertEqual(app.query_one(TabbedContent).active, "publish")

        self.run_app(scenario)
        self.assertEqual(said, ["That video isn't on the Videos tab any more.",
                                "gone.mp4 isn't in your video folders any more."])


if __name__ == "__main__":
    unittest.main()
