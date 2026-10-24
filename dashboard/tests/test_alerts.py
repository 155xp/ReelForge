"""Notifications (dashboard.notify), badges (dashboard.badges) and the reelforge words that open tabs."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from dashboard import badges, db, notify
from dashboard.__main__ import TAB_IDS, main, tab_for

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
NAMES = {"tiktok": "TikTok", "youtube": "YouTube"}


def at(hours: float) -> str:
    return (T0 + timedelta(hours=hours)).isoformat(timespec="seconds")


def snapshot(platform: str, followers: int, posts: dict[str, int], hours: float = 0) -> None:
    """One refresh: the account's followers and each post's views."""
    account = SimpleNamespace(handle="@me", followers=followers, views=None, likes=None, posts=None)
    db.record_snapshot(platform, account, [
        SimpleNamespace(post_id=pid, title=f"What if the {pid} doubled?", url=None, published_at=at(-48), views=v,
                        likes=None, comments=None, shares=None, saves=None) for pid, v in posts.items()], at(hours))


class DbTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        self.dir = Path(tmp.name)
        db.init(self.dir / "stats.db")

    def titles(self) -> list[str]:
        return [n["title"] for n in notify.recent()]


class NotifyTest(DbTest):
    def test_same_key_is_told_once_until_released(self):
        self.assertTrue(notify.add("login", "Log in to X again", key="login:x"))
        self.assertFalse(notify.add("login", "Log in to X again", key="login:x"))
        notify.release("login:x")
        self.assertTrue(notify.add("login", "Log in to X again", key="login:x"))
        self.assertEqual(notify.unread(), 2)
        notify.mark_all_read()
        self.assertEqual(notify.unread(), 0)
        self.assertEqual(notify.recent()[0]["tab"], "accounts")  # a log-in opens the Accounts tab

    def test_since_lists_only_newer_ones(self):
        notify.add("info", "one")
        first = notify.newest_id()
        notify.add("info", "two")
        self.assertEqual([n["title"] for n in notify.since(first)], ["two"])

    def test_an_older_database_gets_the_table(self):
        path = self.dir / "old.db"
        with closing(sqlite3.connect(path)) as c:
            c.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
            c.commit()
        db.init(path)
        self.assertTrue(notify.add("info", "hello"))

    def test_short_names(self):
        self.assertEqual([notify.short(n) for n in (100, 1_000, 2_500, 25_000, 1_000_000, 2_500_000)],
                         ["100", "1K", "2.5K", "25K", "1M", "2.5M"])

    def test_the_tab_saved_is_where_it_goes(self):
        for kind, key, tab in (("milestone", "milestone:video:tiktok|1:1000", "videos"),
                               ("milestone", "milestone:followers:tiktok:1000", "accounts"),
                               ("milestone", "milestone:views:1000", "overview"),
                               ("badge", "badge:video:x|2:views:5", "videos"),
                               ("badge", "badge:day:x:2026-10-24:views:5", "overview"),
                               ("hot", "hot:youtube|3", "videos"), ("video", "video:a.mp4", "publish"),
                               ("update", "update:1.2.0", "updates"), ("info", None, None)):
            notify.add(kind, kind, key=key)
            self.assertEqual(notify.recent()[0]["tab"], tab, key)


class TargetTest(unittest.TestCase):
    """What clicking each kind of notification shows (notify.target)."""

    def target(self, kind: str, key: str | None, title: str = "", tab: str | None = None) -> notify.Target:
        return notify.target({"kind": kind, "key": key, "title": title, "tab": tab},
                             {"tiktok": "TikTok", "instagram": "Instagram", "x": "X"})

    def test_videos_open_on_the_videos_tab(self):
        self.assertEqual(self.target("hot", "hot:tiktok|7700257191629982989"),
                         notify.Target("videos", post="tiktok|7700257191629982989"))
        # Saved by an older ReelForge with the Overview as its tab.
        old = self.target("milestone", "milestone:video:instagram|4015229296325324708:1000", tab="overview")
        self.assertEqual(old, notify.Target("videos", post="instagram|4015229296325324708"))
        self.assertEqual(self.target("badge", "badge:video:youtube|AfeUh3eBYtw:first_day:5"),
                         notify.Target("videos", post="youtube|AfeUh3eBYtw"))
        self.assertEqual(self.target("milestone", "milestone:video:x|a:b:10000"),  # a colon in a post id is kept
                         notify.Target("videos", post="x|a:b"))

    def test_platforms_open_their_card_or_account(self):
        self.assertEqual(self.target("milestone", "milestone:followers:tiktok:10000"),
                         notify.Target("accounts", account="tiktok"))
        self.assertEqual(self.target("badge", "badge:day:youtube:2026-10-24:followers:5"),
                         notify.Target("overview", card="youtube"))
        self.assertEqual(self.target("milestone", "milestone:views:1000000"), notify.Target("overview", card="total"))
        self.assertEqual(self.target("login", "login:instagram"), notify.Target("accounts", account="instagram"))
        # A log-in that worked again since has lost its key: its title names the platform.
        self.assertEqual(self.target("login", None, "Log in to X again"), notify.Target("accounts", account="x"))
        self.assertEqual(self.target("login", None, "Log in to Myspace again"), notify.Target("accounts"))

    def test_files_updates_and_the_rest(self):
        self.assertEqual(self.target("video", "video:demo_doubling_duck.mp4"),
                         notify.Target("publish", file="demo_doubling_duck.mp4"))
        self.assertEqual(self.target("update", "update:1.1.0"), notify.Target("updates"))
        self.assertEqual(self.target("update", "updated:1.0.1"), notify.Target("updates"))
        self.assertEqual(self.target("info", None), notify.Target(None))
        self.assertEqual(self.target("milestone", None, tab="overview"), notify.Target("overview"))  # no key: its tab
        self.assertEqual(self.target("milestone", "milestone:video:nonsense", tab="overview"), notify.Target("overview"))


class MilestoneTest(DbTest):
    def test_first_look_only_takes_stock(self):
        snapshot("tiktok", 12_000, {"a": 150_000})
        self.assertEqual(notify.check_milestones(NAMES, set()), 0)  # nothing old is new
        self.assertEqual(notify.recent(), [])

    def test_passing_a_round_number_is_told_once(self):
        snapshot("tiktok", 900, {"a": 900}, hours=0)
        notify.check_milestones(NAMES, set())
        snapshot("tiktok", 1_200, {"a": 12_500}, hours=1)
        self.assertEqual(notify.check_milestones(NAMES, set()), 3)
        self.assertEqual(sorted(self.titles()), ["10K views in total", "A video passed 10K views on TikTok",
                                                 "TikTok passed 1K followers"])
        snapshot("tiktok", 1_300, {"a": 13_000}, hours=2)
        self.assertEqual(notify.check_milestones(NAMES, set()), 0)  # still past the same marks

    def test_jumping_several_marks_tells_the_highest(self):
        snapshot("tiktok", 90, {}, hours=0)
        notify.check_milestones(NAMES, set())
        snapshot("tiktok", 6_000, {}, hours=1)
        notify.check_milestones(NAMES, set())
        self.assertEqual(self.titles(), ["TikTok passed 5K followers"])

    def test_a_platform_read_for_the_first_time_is_quiet(self):
        snapshot("tiktok", 900, {"a": 10}, hours=0)
        notify.check_milestones(NAMES, set())
        snapshot("youtube", 50_000, {"y": 2_000_000}, hours=1)  # an account you've just added
        self.assertEqual(notify.check_milestones(NAMES, {"youtube"}), 0)
        snapshot("youtube", 50_500, {"y": 2_100_000, "z": 3_000}, hours=2)  # a new video on a known account
        notify.check_milestones(NAMES, set())
        self.assertEqual(self.titles(), ["A video passed 1K views on YouTube"])


class VideoNoteTest(DbTest):
    def test_new_finished_video(self):
        from dashboard import videos

        folder = self.dir / "videos"
        folder.mkdir()
        (folder / "first.mp4").write_bytes(b"x")
        cfg = {"videos_dir": str(folder), "episodes_dir": str(self.dir / "none"),
               "completed_dir": str(self.dir / "none2")}
        self.assertEqual([f.name for f in videos.find(cfg)], ["first.mp4"])
        self.assertEqual(notify.check_videos(cfg), 0)  # the first look takes stock
        (folder / "second.mp4").write_bytes(b"y")
        self.assertEqual(notify.check_videos(cfg), 1)
        self.assertEqual(notify.check_videos(cfg), 0)
        self.assertEqual(notify.recent()[0]["tab"], "publish")


class RankTest(unittest.TestCase):
    def test_tiers_need_ten_to_compare(self):
        others = [float(v) for v in range(1, 40)]  # 40 videos in all with this one
        self.assertEqual(badges.rank(100, others)[0], badges.BEST)
        self.assertEqual(badges.rank(38.5, others)[:2], (3, 2))  # 2nd of 40 = top 5%
        self.assertEqual(badges.rank(36.5, others)[:2], (2, 4))  # 4th of 40 = top 10%
        self.assertEqual(badges.rank(31.5, others)[:2], (1, 9))  # 9th of 40 = top 25%
        self.assertEqual(badges.rank(20, others)[0], 0)
        self.assertEqual(badges.rank(10, [5, 6, 7, 8])[0], badges.BEST)  # best of 5: true without percentages
        self.assertEqual(badges.rank(7.5, [5, 6, 7, 8])[0], 0)  # 2nd of 5: no percentage under 10 videos
        self.assertEqual(badges.rank(10, [5])[0], 0)  # best of 2 isn't much of a record

    def test_ties_count_against_you(self):
        self.assertEqual(badges.rank(10, [10, 1, 1, 1, 1, 1, 1, 1, 1])[:2], (1, 2))  # tied first: 2nd of 10
        self.assertEqual(badges.rank(10, [10] * 5 + [1] * 15)[0], 0)  # tied with 5 of 21: 6th, not top 25%

    def test_video_badge_words(self):
        platforms = {"tiktok": SimpleNamespace(name="TikTok")}
        posts = [{"platform": "tiktok", "post_id": str(i), "views": i * 100, "likes": 5, "shares": None}
                 for i in range(1, 21)]
        got = badges.video_badges(posts[-1], posts, {}, platforms)
        self.assertEqual([b.text for b in got], ["Your best TikTok video yet for views"])
        got = badges.video_badges(posts[-2], posts, {}, platforms)
        self.assertEqual([(b.text, b.detail) for b in got],
                         [("Top 10% of your TikTok videos for views", "1.90K · #2 of 20")])


class DayBadgeTest(unittest.TestCase):
    def rows(self, per_day: list[int], today: int) -> list[dict]:
        """Hourly readings: each earlier day gains per_day[i] followers evenly, today `today` so far."""
        now = datetime.now(timezone.utc).astimezone().replace(hour=18, minute=0, second=0, microsecond=0)
        start = (now - timedelta(days=len(per_day))).replace(hour=0)
        rows, total, t = [], 1000.0, start - timedelta(hours=1)
        rows.append({"ts": t.astimezone(timezone.utc).isoformat(timespec="seconds"), "followers": total,
                     "views": None})
        for gain in per_day + [today * 24 / 18]:
            for _ in range(24):
                t += timedelta(hours=1)
                if t > now:
                    break
                total += gain / 24
                rows.append({"ts": t.astimezone(timezone.utc).isoformat(timespec="seconds"),
                             "followers": round(total), "views": None})
        return rows, now

    def test_best_day_yet(self):
        rows, now = self.rows([10, 12, 9, 11], today=40)
        got = badges.account_badges({"tiktok": rows}, {"tiktok": SimpleNamespace(name="TikTok")}, now)
        self.assertEqual([b.text for b in got], ["Today: your best day yet for new TikTok followers"])

    def test_ordinary_day_has_no_badge(self):
        rows, now = self.rows([10, 12, 9, 11, 10, 12, 9, 11, 10, 12, 9, 11], today=8)
        self.assertEqual(badges.account_badges({"tiktok": rows}, {"tiktok": SimpleNamespace(name="TikTok")}, now),
                         [])


class BadgeNotesTest(DbTest):
    def test_moving_up_is_told_once_and_the_first_look_is_quiet(self):
        platforms = {"tiktok": SimpleNamespace(name="TikTok")}
        posts = [{"platform": "tiktok", "post_id": str(i), "views": i * 100, "likes": None, "shares": None,
                  "title": f"Video {i}", "episode": None} for i in range(1, 21)]
        self.assertEqual(badges.notify_new(posts, {}, {}, platforms), 0)
        posts.append({"platform": "tiktok", "post_id": "new", "views": 1_850, "likes": None, "shares": None,
                      "title": "The new one", "episode": None})
        self.assertEqual(badges.notify_new(posts, {}, {}, platforms), 1)  # top 25% (3rd of 21)
        posts[-1]["views"] = 5_000
        self.assertEqual(badges.notify_new(posts, {}, {}, platforms), 1)  # now the best yet
        self.assertEqual(badges.notify_new(posts, {}, {}, platforms), 0)
        self.assertEqual([n["title"] for n in notify.recent()],
                         ["Your best TikTok video yet for views!", "Top 25% of your TikTok videos for views!"])


class WordsTest(unittest.TestCase):
    def test_numbers_names_and_aliases(self):
        self.assertEqual([tab_for(str(i)) for i in range(1, 7)], list(TAB_IDS))
        self.assertEqual([tab_for(w) for w in ("Videos", "post", "upload", "logins", "update", "notifications")],
                         ["videos", "publish", "publish", "accounts", "updates", "overview"])
        self.assertIsNone(tab_for("7"))
        self.assertIsNone(tab_for("stats"))  # reelforge stats on/off is the background job, not a tab

    def test_unknown_word_is_refused_before_anything_starts(self):
        self.assertEqual(main(["banana"]), 2)


if __name__ == "__main__":
    unittest.main()
