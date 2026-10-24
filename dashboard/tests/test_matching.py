"""Posts matched to episodes (analytics.auto_link) and the store under it (dashboard.db): links, totals, backups."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from dashboard import analytics, db

T0 =datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc)
EPISODES = r"C:\Users\me\Desktop\my channel\episodes"
# The five episodes so far: title, video slug, minutes after T0 that they went up.
REAL = {
    "kite": ("What if your kite's speed doubled every 2 seconds?", "ep02_kite_doubling", 0),
    "jump": ("What if your jump's height doubled every 2 seconds?", "ep03_jump_doubling", 420),
    "snowball": ("What if your snowball doubled in size every 2 seconds?", "ep04_snowball_doubling", 430),
    "savings": ("What if your savings doubled every second?", "ep05_savings_doubling", 1200),
    "subscribers": ("What if your subscribers doubled every second?", "ep06_subscribers_doubling", 1205),
}
# How each platform's caption reads once it's posted.
CAPTIONS = {"tiktok": "{} #fyp#whatif#space#physics#simulation", "instagram": "{} #fyp #whatif #space #physics",
            "youtube": "{} #shorts", "x": "{} https://t.co/0000000000"}
ALL_FOUR = Counter(dict.fromkeys(CAPTIONS, 1))
X_SNOWBALL = "1999999999999999999"  # the snowball video on X, captioned like the jump one; linked by hand


def at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat(timespec="seconds")


def video(slug: str) -> str:
    return f"{EPISODES}\\{slug}\\final\\{slug}.mp4"


def post(post_id: str, title: str, minutes: float, views: int | None = None, likes: int | None = None):
    return SimpleNamespace(post_id=post_id, title=title, url=None, published_at=at(minutes), views=views, likes=likes,
                           comments=None, shares=None, saves=None)


def read(platform: str, posts: list, views: int | None = None, likes: int | None = None,
         minutes: float | None = None) -> None:
    """One refresh of a platform, stored the way sync.refresh stores it."""
    account = SimpleNamespace(handle="@yourchannel", followers=100, views=views, likes=likes, posts=None)
    db.record_snapshot(platform, account, posts, at(minutes) if minutes is not None else None)


def where(platform: str, post_id: str) -> tuple:
    """(episode_id, link) of a post."""
    with db.connect() as c:
        return tuple(c.execute("SELECT episode_id, link FROM posts WHERE platform = ? AND post_id = ?",
                               (platform, post_id)).fetchone())


def per_episode() -> dict[int, Counter]:
    """Episode id -> how many of its posts each platform has."""
    out = {e["id"]: Counter() for e in db.episodes()}
    for p in db.linked_posts():
        out.setdefault(p["episode_id"], Counter())[p["platform"]] += 1
    return out


def real_world(order: tuple[str, ...] = tuple(REAL)) -> dict[str, int]:
    """The five episodes, created in `order`, and their 20 posts as the first refresh stores them: none linked."""
    ids = {name: db.create_episode(REAL[name][0], video(REAL[name][1]), at(-60 + i)) for i, name in enumerate(order)}
    for k, platform in enumerate(CAPTIONS):
        posts = []
        for name, (title, _, minutes) in REAL.items():
            if (platform, name) == ("x", "snowball"):
                posts.append(post(X_SNOWBALL, CAPTIONS["x"].format(REAL["jump"][0]), 1050))
            else:
                posts.append(post(f"{platform}-{name}", CAPTIONS[platform].format(title), minutes + k))
        read(platform, posts)
    return ids


class DbTest(unittest.TestCase):
    """Each test gets a fresh database in a temporary folder."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        self.dir = Path(tmp.name)
        db.init(self.dir / "stats.db")


class RealEpisodesTest(DbTest):
    def assert_in_place(self, ids: dict[str, int]) -> None:
        for name, eid in ids.items():
            for platform in CAPTIONS:
                post_id = X_SNOWBALL if (platform, name) == ("x", "snowball") else f"{platform}-{name}"
                self.assertEqual(where(platform, post_id)[0], eid, f"{platform} {name}")
        self.assertEqual(list(per_episode().values()), [ALL_FOUR] * 5)

    def test_subscribers_episode_created_first(self):
        ids = real_world(("subscribers", "savings", "snowball", "jump", "kite"))
        db.set_post_episode("x", X_SNOWBALL, ids["snowball"])
        self.assertEqual(analytics.auto_link(), 19)
        self.assert_in_place(ids)
        self.assertEqual(analytics.auto_link(), 0)

    def test_savings_posts_filed_under_subscribers_move_back(self):
        ids = real_world()
        db.set_post_episode("x", X_SNOWBALL, ids["snowball"])
        analytics.auto_link()
        for platform in CAPTIONS:  # what an older first-match version did: the titles are 84% alike
            db.link_post(platform, f"{platform}-savings", ids["subscribers"])
        self.assertEqual(per_episode()[ids["subscribers"]], ALL_FOUR + ALL_FOUR)
        self.assertEqual(analytics.auto_link(), 4)
        self.assert_in_place(ids)
        self.assertEqual(where("tiktok", "tiktok-savings"), (ids["savings"], "caption"))
        self.assertEqual(analytics.auto_link(), 0)

    def test_hand_link_never_moves(self):
        ids = real_world()
        db.set_post_episode("x", X_SNOWBALL, ids["snowball"])
        for _ in range(3):
            analytics.auto_link()
            self.assertEqual(where("x", X_SNOWBALL), (ids["snowball"], "hand"))
        self.assertEqual(where("x", "x-jump"), (ids["jump"], "caption"))

    def test_second_post_on_a_platform_does_not_double_link(self):
        ids = real_world()
        analytics.auto_link()
        # Without the hand link, the jump-captioned snowball post can't join jump: it has its X post.
        self.assertEqual(where("x", X_SNOWBALL), (None, None))
        read("tiktok", [post("tiktok-kite-again", CAPTIONS["tiktok"].format(REAL["kite"][0]), 3000)])
        self.assertEqual(analytics.auto_link(), 0)
        self.assertEqual(where("tiktok", "tiktok-kite-again"), (None, None))
        # An older version linked both; the first post keeps its place and the other one leaves.
        db.link_post("tiktok", "tiktok-kite-again", ids["kite"])
        self.assertEqual(analytics.auto_link(), 1)
        self.assertEqual(where("tiktok", "tiktok-kite"), (ids["kite"], "caption"))
        self.assertEqual(where("tiktok", "tiktok-kite-again"), (None, None))
        self.assertEqual(per_episode()[ids["kite"]], ALL_FOUR)
        self.assertEqual(analytics.auto_link(), 0)

    def test_not_an_episode_stays_unlinked(self):
        ids = real_world()
        analytics.auto_link()
        db.set_post_episode("tiktok", "tiktok-kite", None)
        for _ in range(2):
            self.assertEqual(analytics.auto_link(), 0)
            self.assertEqual(where("tiktok", "tiktok-kite"), (None, "hand"))
        self.assertNotIn("tiktok-kite", [p["post_id"] for p in db.unlinked_posts()])
        db.link_post("tiktok", "tiktok-kite", None)  # back to automatic
        self.assertIn("tiktok-kite", [p["post_id"] for p in db.unlinked_posts()])
        self.assertEqual(analytics.auto_link(), 1)
        self.assertEqual(where("tiktok", "tiktok-kite"), (ids["kite"], "caption"))

    def test_posts_linked_when_published_are_left_alone(self):
        ids = real_world()
        db.add_post("facebook", "pushed", ids["snowball"], REAL["snowball"][0], None, at(500))
        read("facebook", [post("pushed", REAL["kite"][0], 500)])  # its caption now reads like the kite video
        analytics.auto_link()
        self.assertEqual(where("facebook", "pushed"), (ids["snowball"], "publish"))

    def test_equal_scores_keep_the_episode_a_post_is_in(self):
        ids = real_world()
        analytics.auto_link()
        read("facebook", [post("fb", "What if your subscribers' savings doubled every second?", 3000)])
        self.assertEqual(analytics.auto_link(), 0)  # it names both, so neither
        self.assertEqual(where("facebook", "fb"), (None, None))
        for name in ("savings", "subscribers"):  # never moved to the other one, whichever id is higher
            db.link_post("facebook", "fb", ids[name])
            self.assertEqual(analytics.auto_link(), 0)
            self.assertEqual(where("facebook", "fb"), (ids[name], "caption"))

    def test_same_title_twice_keeps_each_post_where_it_is(self):
        title = REAL["kite"][0]
        first = db.create_episode(title, video("ep02_kite_doubling"), at(-60))
        again = db.create_episode(title, r"C:\x\completed videos\ep02 - kite\ep02_kite_doubling.mp4", at(-30))
        read("tiktok", [post("tt", title, 0)])
        read("youtube", [post("yt", title, 1)])
        db.link_post("tiktok", "tt", again)
        self.assertEqual(analytics.auto_link(), 1)
        self.assertEqual(where("tiktok", "tt"), (again, "caption"))
        self.assertEqual(where("youtube", "yt"), (first, "caption"))  # a new post takes the older one
        self.assertEqual(analytics.auto_link(), 0)


class CaptionTest(unittest.TestCase):
    """Rewordings name their episode; new videos in the same template name none (see MATCH_SCORE)."""

    def setUp(self) -> None:
        episodes = [{"id": i, "title": t, "video": video(v), "created_at": at(m)} for i, (t, v, m) in
                    enumerate(REAL.values(), 1)]
        self.matcher = analytics._Matcher(episodes)
        self.ids = dict(zip(REAL, range(1, 6)))

    def named(self, caption: str) -> list[int]:
        return self.matcher.match(analytics._key(caption), analytics._words(caption))[0]

    def test_first_line_ignores_hashtags_links_and_apostrophes(self):
        self.assertEqual(analytics._key("What if your kite's speed doubled every 2 seconds?#fyp#whatif#spa\nmore"),
                         analytics._key("what if your kites speed doubled every 2 seconds https://t.co/x"))

    def test_rewordings_name_their_episode(self):
        for caption, name in (
                ("What if your kites speed doubled every 2 secs? Wait for the end #fyp#whatif#spa", "kite"),
                ("POV: your kite’s speed doubles every two seconds", "kite"),
                ("Your jump height doubles every 2 seconds", "jump"),
                ("What if a snowball doubled in size every 2 seconds?! #fyp", "snowball"),
                ("What if your savings doubled every single second? It gets crazy", "savings"),
                ("What if your life-savings kept doubling every second?", "savings"),
                ("What if your subscriber count doubled every second?", "subscribers"),
                ("subscribers doubling", "subscribers")):
            self.assertEqual(self.named(caption), [self.ids[name]], caption)

    def test_new_videos_and_mixed_captions_name_nothing(self):
        for caption in ("What if your pizza doubled every 2 seconds?", "What if gravity doubled every second?",
                        "What if your house doubled in size every 2 seconds?",
                        "What if your bank account doubled every second?",
                        "What if your subscribers' savings doubled every second?", "doubled every 2 seconds",
                        "Follow for more", "#fyp #whatif", ""):
            self.assertEqual(self.named(caption), [], caption)


class UploadWindowTest(DbTest):
    def opened(self, platform: str, file_name: str, minutes: float) -> None:
        """The owner opened a platform's upload page for a video (as ReelForge logs it)."""
        with db.connect() as c:
            c.execute("INSERT INTO uploads (ts, platform, video, status, message) VALUES (?,?,?,?,?)",
                      (at(minutes), platform, file_name, "manual", "opened the upload page"))

    def test_empty_caption_links_by_file_name_from_another_folder(self):
        shipped = (r"C:\Users\me\Desktop\my channel\completed videos\ep05_savings_doubling - What if your "
                   r"savings doubled every second\ep05_savings_doubling.mp4")
        worth = db.create_episode(REAL["savings"][0], shipped, at(-30))
        db.create_episode(REAL["snowball"][0], video("ep04_snowball_doubling"), at(-60))
        self.opened("instagram", "ep04_snowball_doubling.mp4", -40)  # not the last one before the post
        self.opened("instagram", "ep05_savings_doubling.mp4", -10)
        self.opened("tiktok", "ep04_snowball_doubling.mp4", -5)  # another platform
        read("instagram", [post("ig", "", 0)])
        self.assertEqual(analytics.auto_link(), 1)
        self.assertEqual(where("instagram", "ig"), (worth, "upload"))
        self.assertEqual(analytics.auto_link(), 0)

    def test_window_is_six_hours_before_or_half_an_hour_after(self):
        worth = db.create_episode(REAL["savings"][0], video("ep05_savings_doubling"), at(-30))
        self.opened("instagram", "ep05_savings_doubling.mp4", 0)
        read("instagram", [post("late", "", 6 * 60 + 5), post("early", "", -20)])
        analytics.auto_link()
        self.assertEqual(where("instagram", "early"), (worth, "upload"))  # opened just after it (clock skew)
        self.assertEqual(where("instagram", "late"), (None, None))  # over 6 hours later


class TwinsTest(DbTest):
    def test_new_video_on_two_platforms_gets_one_episode(self):
        real_world()
        analytics.auto_link()
        count = len(db.episodes())
        read("tiktok", [post("tt-pizza", "What if your pizza doubled every 2 seconds? #fyp #whatif", 5000)])
        read("youtube", [post("yt-pizza", "What if your pizza doubled every 2 seconds? #shorts", 5003)])
        self.assertEqual(analytics.auto_link(), 2)
        self.assertEqual(len(db.episodes()), count + 1)
        pizza = next(e for e in db.episodes() if "pizza" in e["title"])
        self.assertEqual(pizza["title"], "What if your pizza doubled every 2 seconds?")
        self.assertEqual(where("tiktok", "tt-pizza"), (pizza["id"], "twin"))
        self.assertEqual(where("youtube", "yt-pizza"), (pizza["id"], "twin"))
        self.assertEqual(analytics.auto_link(), 0)
        # The X post four days later joins it by its caption.
        read("x", [post("x-pizza", "What if your pizza doubled every 2 seconds? https://t.co/p", 5000 + 4 * 1440)])
        self.assertEqual(analytics.auto_link(), 1)
        self.assertEqual(where("x", "x-pizza"), (pizza["id"], "caption"))
        self.assertEqual(len(db.episodes()), count + 1)

    def test_one_platform_alone_makes_no_episode(self):
        caption = "What if your pizza doubled every 2 seconds?"
        read("tiktok", [post("a", caption, 0), post("b", caption, 60)])
        self.assertEqual(analytics.auto_link(), 0)
        self.assertEqual(db.episodes(), [])


OLD_SCHEMA = """
CREATE TABLE episodes (id INTEGER PRIMARY KEY, title TEXT NOT NULL, video TEXT, created_at TEXT NOT NULL);
CREATE TABLE posts (platform TEXT NOT NULL, post_id TEXT NOT NULL, episode_id INTEGER REFERENCES episodes(id),
                    title TEXT, url TEXT, published_at TEXT, PRIMARY KEY (platform, post_id));
CREATE TABLE post_stats (platform TEXT NOT NULL, post_id TEXT NOT NULL, ts TEXT NOT NULL,
                         views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER);
CREATE TABLE account_stats (platform TEXT NOT NULL, ts TEXT NOT NULL, handle TEXT,
                            followers INTEGER, views INTEGER, likes INTEGER, posts INTEGER);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE uploads (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, platform TEXT NOT NULL, video TEXT, status TEXT,
                      post_id TEXT, url TEXT, message TEXT);
"""


class MigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        self.dir = Path(tmp.name)

    def test_old_database_is_backed_up_once_and_its_links_marked(self):
        path = self.dir / "stats.db"
        with closing(sqlite3.connect(path)) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(OLD_SCHEMA)
            ids = {name: c.execute("INSERT INTO episodes (title, video, created_at) VALUES (?,?,?)",
                                   (title, video(slug), at(minutes - 5))).lastrowid
                   for name, (title, slug, minutes) in REAL.items()}
            for platform in CAPTIONS:
                for name, (title, _, minutes) in REAL.items():
                    post_id, caption = f"{platform}-{name}", CAPTIONS[platform].format(title)
                    if (platform, name) == ("x", "snowball"):
                        post_id, caption = X_SNOWBALL, CAPTIONS["x"].format(REAL["jump"][0])
                    c.execute("INSERT INTO posts VALUES (?,?,?,?,?,?)",
                              (platform, post_id, ids[name], caption, None, at(minutes)))
                    c.execute("INSERT INTO post_stats VALUES (?,?,?,?,?,?,?,?)",
                              (platform, post_id, at(minutes + 60), 100, 5, 1, 0, None))
            c.execute("INSERT INTO posts VALUES ('tiktok', 'other', NULL, 'Follow for more', NULL, ?)", (at(9),))
            c.commit()
        db.init(path)
        backups = list(self.dir.glob("stats.db.bak-*-schema"))
        self.assertEqual(len(backups), 1)
        with closing(sqlite3.connect(backups[0])) as c:  # taken before the change
            self.assertNotIn("link", [r[1] for r in c.execute("PRAGMA table_info(posts)")])
        with db.connect() as c:
            rows = {r["post_id"]: r for r in c.execute("SELECT * FROM posts")}
        self.assertEqual(rows[X_SNOWBALL]["link"], "hand")
        self.assertEqual(Counter(r["link"] for r in rows.values()), Counter({"caption": 19, "hand": 1, None: 1}))
        self.assertEqual((rows["tiktok-kite"]["views"], rows["tiktok-kite"]["last_ts"]), (100, at(60)))
        self.assertEqual(analytics.auto_link(), 0)
        db.init(path)
        self.assertEqual(list(self.dir.glob("stats.db.bak-*")), backups)
        with closing(sqlite3.connect(backups[0])) as c:  # and not rewritten
            self.assertNotIn("link", [r[1] for r in c.execute("PRAGMA table_info(posts)")])

    def test_new_database_needs_no_backup(self):
        db.init(self.dir / "stats.db")
        db.init(self.dir / "stats.db")
        self.assertEqual([f.name for f in self.dir.iterdir() if ".bak" in f.name], [])


class SnapshotTest(DbTest):
    def account(self, platform: str = "tiktok") -> tuple:
        a = db.latest_accounts()[platform]
        return a["views"], a["likes"]

    def test_totals_count_every_known_post(self):
        read("tiktok", [post("a", "A", 0, views=100, likes=10), post("b", "B", 1, views=50, likes=5)], minutes=60)
        self.assertEqual(self.account(), (150, 15))
        read("tiktok", [post("a", "A", 0, views=120, likes=12)], minutes=120)  # b fell off the first page
        self.assertEqual(self.account(), (170, 17))
        read("tiktok", [post("a", "A", 0, views=130, likes=13)], views=1000, minutes=180)  # its own total wins
        self.assertEqual(self.account(), (1000, 18))

    def test_a_read_without_posts_keeps_the_last_totals(self):
        read("tiktok", [post("a", "A", 0, views=100, likes=10)], minutes=60)
        read("tiktok", [], minutes=120)  # the profile loaded, the video list didn't (a captcha)
        self.assertEqual(db.latest_accounts()["tiktok"]["ts"], at(120))
        self.assertEqual(self.account(), (100, 10))

    def test_missing_or_lower_counts_never_replace_known_ones(self):
        read("youtube", [post("v", "V", 0, views=2514, likes=40)], minutes=60)
        read("youtube", [post("v", "V", 0, views=2497, likes=None)], minutes=120)  # RSS counts lag and dip
        latest = next(p for p in db.posts_latest() if p["post_id"] == "v")
        self.assertEqual((latest["views"], latest["likes"], latest["ts"]), (2514, 40, at(120)))
        with db.connect() as c:
            rows = c.execute("SELECT views, likes FROM post_stats WHERE post_id = 'v' ORDER BY ts").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(2514, 40), (2497, None)])  # snapshots stay as read
        read("youtube", [post("v", "V", 0, views=2600, likes=41)], minutes=180)
        latest = next(p for p in db.posts_latest() if p["post_id"] == "v")
        self.assertEqual((latest["views"], latest["likes"]), (2600, 41))

    def test_typed_in_and_read_numbers_are_not_added_together(self):
        eid = db.create_episode("E", None, at(0))
        db.add_post("x", f"manual-{eid}", eid, "E", None, at(0))
        read("x", [post(f"manual-{eid}", "E", 0, views=500)], minutes=60)
        self.assertEqual(self.account("x")[0], 500)
        read("x", [post("1234", "E", 0, views=40)], minutes=120)  # X connected: its own posts from now on
        self.assertEqual(self.account("x")[0], 40)


class CompactTest(DbTest):
    def test_compacted_at_written_bare_by_older_versions_still_reads(self):
        with db.connect() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('compacted_at', ?)", (db.now_iso(),))
        self.assertEqual(db.compact(), 0)  # it ran less than 20 hours ago
        self.assertIsInstance(db.get_meta("compacted_at"), str)
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(timespec="seconds")
        with db.connect() as c:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('compacted_at', ?)", (two_days_ago,))
        db.compact()
        with db.connect() as c:
            stored = c.execute("SELECT value FROM meta WHERE key = 'compacted_at'").fetchone()[0]
        self.assertGreater(db.parse(json.loads(stored)), db.parse(two_days_ago))

    def test_daily_backup_keeps_the_newest_seven(self):
        folder = self.dir / "backups"
        folder.mkdir()
        for day in range(1, 10):
            (folder / f"stats-202601{day:02d}.db").write_bytes(b"older")
        (folder / "notes.txt").write_text("not a backup")
        db.compact(min_hours=0)
        today = folder / f"stats-{datetime.now():%Y%m%d}.db"
        with closing(sqlite3.connect(today)) as c:
            self.assertIn("posts", [r[0] for r in c.execute("SELECT name FROM sqlite_master")])
        kept = sorted(f.name for f in folder.glob("stats-*.db"))
        self.assertEqual(kept, [f"stats-202601{day:02d}.db" for day in range(4, 10)] + [today.name])
        self.assertTrue((folder / "notes.txt").exists())
        stamp = today.stat().st_mtime_ns
        db.compact(min_hours=0)  # once a day: today's stays as it is
        self.assertEqual(today.stat().st_mtime_ns, stamp)

    def test_failed_backup_never_stops_compaction(self):
        (self.dir / "backups").write_text("a file where the folder should be")
        db.compact(min_hours=0)
        self.assertIsNotNone(db.get_meta("compacted_at"))


class ApiTest(DbTest):
    def test_link_post_notes_how_and_none_unlinks(self):
        eid = db.create_episode("E", None, at(0))
        read("tiktok", [post("p", "E", 0)])
        db.link_post("tiktok", "p", eid, "upload")
        self.assertEqual(where("tiktok", "p"), (eid, "upload"))
        db.link_post("tiktok", "p", eid, None)
        self.assertEqual(where("tiktok", "p"), (None, None))
        db.link_post("tiktok", "p", eid)
        self.assertEqual(where("tiktok", "p"), (eid, "caption"))
        db.link_post("tiktok", "p", None)
        self.assertEqual(where("tiktok", "p"), (None, None))
        with self.assertRaises(ValueError):
            db.link_post("tiktok", "p", eid, "manual")

    def test_add_post_marks_publish_and_posts_latest_shows_it(self):
        eid = db.create_episode("E", None, at(0))
        db.add_post("tiktok", "pushed", eid, "E", None)
        db.add_post("tiktok", "pushed", None, "E", None)  # no episode given: the link stays
        self.assertEqual(where("tiktok", "pushed"), (eid, "publish"))
        self.assertEqual([p["link"] for p in db.posts_latest()], ["publish"])

    def test_episode_for_video_goes_by_file_name_newest_first(self):
        db.create_episode("E", video("ep05_savings_doubling"))
        moved = db.create_episode("E", r"C:\x\completed videos\ep05 - E\EP05_Savings_Doubling.mp4")
        self.assertEqual(db.episode_for_video("ep05_savings_doubling.mp4")["id"], moved)
        self.assertEqual(db.episode_for_video(video("ep05_savings_doubling"))["id"], moved)
        self.assertIsNone(db.episode_for_video("ep06_subscribers_doubling.mp4"))


@unittest.skipIf(os.environ.get("REELFORGE_SKIP_TIMING"), "REELFORGE_SKIP_TIMING is set")
class YearOfPostsTest(DbTest):
    """A year at two videos a day: 730 episodes and 2,920 posts, some reworded or without a caption."""

    def test_a_year_is_matched_quickly(self):
        nouns = ("car phone house dog cat pizza balloon elevator tree river bike boat plane train rocket bridge tower "
                 "city island cake coffee laptop guitar shoe hat lamp clock garden pool robot drone ship wallet bank "
                 "planet moon star cloud volcano castle").split()
        things = ("speed size weight price battery height temperature value volume age length power signal "
                  "brightness noise gravity storage memory wifi").split()
        pairs = [(n, t) for t in things for n in nouns][:730]
        episodes, posts, uploads = [], {p: [] for p in CAPTIONS}, []
        for i, (noun, thing) in enumerate(pairs):
            every = "second" if i % 4 == 0 else f"{2 + i % 3} seconds"
            title, slug = f"What if your {noun}'s {thing} doubled every {every}?", f"ep{i:03d}_{noun}_{thing}"
            start = 720 * i  # two videos a day
            episodes.append((i + 1, title, video(slug), at(start)))
            for k, platform in enumerate(CAPTIONS):
                caption = CAPTIONS[platform].format(title)
                if platform == "tiktok" and i % 10 == 3:
                    caption = f"Your {noun}'s {thing} doubles every {every} #fyp"
                if platform == "instagram" and i % 10 == 7:
                    caption = ""
                posts[platform].append(post(f"{platform}-{i}", caption, start + 10 + 5 * k, views=100 * k, likes=k))
                uploads.append((at(start + 5 + 5 * k), platform, f"{slug}.mp4", "manual"))
        with db.connect() as c:
            c.executemany("INSERT INTO episodes (id, title, video, created_at) VALUES (?,?,?,?)", episodes)
            c.executemany("INSERT INTO uploads (ts, platform, video, status) VALUES (?,?,?,?)", uploads)
        for platform, items in posts.items():
            read(platform, items)

        started = time.perf_counter()
        first = analytics.auto_link()
        first_s = time.perf_counter() - started
        started = time.perf_counter()
        again = analytics.auto_link()
        again_s = time.perf_counter() - started
        sys.stderr.write(f"\n  a year of posts: first run {first_s:.3f}s ({first} linked), "
                         f"then {again_s:.3f}s per refresh ... ")
        self.assertEqual(first, 2920)
        self.assertEqual(again, 0)
        self.assertEqual(list(per_episode().values()), [ALL_FOUR] * 730)
        self.assertLess(again_s, 0.5)


if __name__ == "__main__":
    unittest.main()
