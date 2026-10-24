"""SQLite store: stat snapshots over time, posts, episodes, the upload log and your notifications.

Platforms mostly report lifetime totals, so every refresh writes a snapshot row. The charts
are built from those snapshots; the longer ReelForge runs, the more history it has.
"""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    video TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    episode_id INTEGER REFERENCES episodes(id),
    title TEXT,
    url TEXT,
    published_at TEXT,
    last_ts TEXT, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER,
    link TEXT,
    PRIMARY KEY (platform, post_id)
);
CREATE TABLE IF NOT EXISTS post_stats (
    platform TEXT NOT NULL,
    post_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER, saves INTEGER
);
CREATE INDEX IF NOT EXISTS post_stats_by_post ON post_stats (platform, post_id, ts);
CREATE TABLE IF NOT EXISTS account_stats (
    platform TEXT NOT NULL,
    ts TEXT NOT NULL,
    handle TEXT,
    followers INTEGER, views INTEGER, likes INTEGER, posts INTEGER
);
CREATE INDEX IF NOT EXISTS account_stats_by_platform ON account_stats (platform, ts);
CREATE INDEX IF NOT EXISTS posts_by_published ON posts (published_at);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS post_stats_by_ts ON post_stats (ts);
CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    platform TEXT NOT NULL,
    video TEXT,
    status TEXT,
    post_id TEXT,
    url TEXT,
    message TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT UNIQUE,
    title TEXT NOT NULL,
    body TEXT,
    tab TEXT,
    read INTEGER NOT NULL DEFAULT 0
);
"""

_path: Path | None = None


LATEST_COLUMNS = ("last_ts", "views", "likes", "comments", "shares", "saves")
# How a post got its episode (posts.link): you chose it, its caption matched, it went up just after you opened that
# video's upload page, posts on two platforms matched each other, or ReelForge posted it (or you typed in its numbers).
# NULL: not linked. auto_link re-checks every link except hand and publish ones.
LINKS = ("hand", "caption", "upload", "twin", "publish")
BACKUPS_KEPT = 7


def init(path: Path) -> None:
    global _path
    path.parent.mkdir(parents=True, exist_ok=True)
    _path = path
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
        have = {r["name"] for r in db.execute("PRAGMA table_info(posts)")}
    if not have.issuperset((*LATEST_COLUMNS, "link")):
        _migrate()


def _migrate() -> None:
    """Add the columns an older database lacks, after saving a copy of it (see backup)."""
    from .analytics import caption_matches  # imported here because analytics imports this module

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")  # a second ReelForge starting at the same moment waits here, then finds it done
        have = {r["name"] for r in db.execute("PRAGMA table_info(posts)")}
        missing = [c for c in LATEST_COLUMNS if c not in have]
        if not missing and "link" in have:
            return
        backup("schema")
        # Each post keeps its latest numbers too, so listing posts never scans the history.
        for c in missing:
            db.execute(f"ALTER TABLE posts ADD COLUMN {c} {'TEXT' if c == 'last_ts' else 'INTEGER'}")
        if missing:
            db.execute("""UPDATE posts SET (last_ts, views, likes, comments, shares, saves) = (
                            SELECT ts, views, likes, comments, shares, saves FROM post_stats s
                            WHERE s.platform = posts.platform AND s.post_id = posts.post_id
                            ORDER BY ts DESC LIMIT 1)""")
        if "link" not in have:
            db.execute("ALTER TABLE posts ADD COLUMN link TEXT")
            # Older links weren't marked. One the caption matcher agrees with was a caption match; any other was
            # made by hand (like an X post captioned as one video that is really another).
            linked = db.execute("SELECT * FROM posts WHERE episode_id IS NOT NULL").fetchall()
            named = caption_matches(linked, db.execute("SELECT * FROM episodes").fetchall())
            db.executemany("UPDATE posts SET link = ? WHERE platform = ? AND post_id = ?",
                           [("caption" if p["episode_id"] in named[p["platform"], p["post_id"]] else "hand",
                             p["platform"], p["post_id"]) for p in linked])


def backup(why: str) -> Path:
    """Copy the database next to itself as stats.db.bak-<YYYYmmdd-HHMMSS>-<why>, consistent even while it's in use."""
    target = _path.with_name(f"{_path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}-{why}")
    with closing(sqlite3.connect(_path, timeout=10)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    return target


@contextmanager
def connect():
    # Short-lived connections so refresh and upload threads never share one.
    db = sqlite3.connect(_path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA synchronous=NORMAL")
    try:
        with db:
            yield db
    finally:
        db.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def to_iso(value) -> str:
    """Normalise a datetime, unix timestamp or ISO string to a UTC ISO string."""
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, timezone.utc)
    elif isinstance(value, str):
        # Meta sends +0000 offsets; fromisoformat wants +00:00.
        dt = datetime.fromisoformat(re.sub(r"([+-]\d\d)(\d\d)$", r"\1:\2", value.replace("Z", "+00:00")))
    else:
        dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def record_snapshot(platform: str, account, posts: list, ts: str | None = None,
                    conn: sqlite3.Connection | None = None) -> None:
    """Store one refresh: the account totals plus every post's current numbers.

    A read that misses numbers never wipes known ones: a post keeps its last known counts and its views never go down
    (RSS counts lag and dip), while post_stats keeps what was read. Without the platform's own totals, the account gets
    the sum over every post ReelForge knows there (one page load only shows the newest), or its last totals if no posts
    came.
    """
    ts = ts or now_iso()
    if conn is None:
        with connect() as db:
            _record(db, platform, account, posts, ts)
    else:
        _record(conn, platform, account, posts, ts)  # the demo writes its history in one go


def _record(db: sqlite3.Connection, platform: str, account, posts: list, ts: str) -> None:
    db.executemany(
        """INSERT INTO posts (platform, post_id, title, url, published_at,
                              last_ts, views, likes, comments, shares, saves)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT (platform, post_id) DO UPDATE SET
             title = COALESCE(NULLIF(excluded.title, ''), posts.title),
             url = COALESCE(excluded.url, posts.url),
             published_at = excluded.published_at,
             last_ts = excluded.last_ts,
             views = COALESCE(MAX(excluded.views, posts.views), excluded.views, posts.views),
             likes = COALESCE(excluded.likes, posts.likes), comments = COALESCE(excluded.comments, posts.comments),
             shares = COALESCE(excluded.shares, posts.shares), saves = COALESCE(excluded.saves, posts.saves)""",
        [(platform, p.post_id, p.title, p.url, to_iso(p.published_at),
          ts, p.views, p.likes, p.comments, p.shares, p.saves) for p in posts],
    )
    db.executemany(
        "INSERT INTO post_stats VALUES (?,?,?,?,?,?,?,?)",
        [(platform, p.post_id, ts, p.views, p.likes, p.comments, p.shares, p.saves) for p in posts],
    )
    # Typed-in numbers (manual-<episode> posts) and the platform's own posts are never added together.
    typed = bool(posts) and all(p.post_id.startswith("manual-") for p in posts)
    totals = []
    for field, given in (("views", account.views), ("likes", account.likes)):
        if given is None and posts:
            given = db.execute(
                f"SELECT SUM({field}) FROM posts WHERE platform = ? AND (post_id LIKE 'manual-%') = ?",
                (platform, typed)).fetchone()[0]
        if given is None:
            given = (db.execute(
                f"SELECT {field} FROM account_stats WHERE platform = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
                (platform, ts)).fetchone() or [None])[0]
        totals.append(given)
    db.execute(
        "INSERT INTO account_stats VALUES (?,?,?,?,?,?,?)",
        (platform, ts, account.handle, account.followers, *totals, account.posts),
    )


def latest_accounts() -> dict[str, sqlite3.Row]:
    with connect() as db:
        rows = db.execute(
            """SELECT * FROM account_stats a
               WHERE ts = (SELECT MAX(ts) FROM account_stats WHERE platform = a.platform)"""
        ).fetchall()
    return {r["platform"]: r for r in rows}


def account_before(platform: str, ts: str) -> sqlite3.Row | None:
    with connect() as db:
        return db.execute(
            "SELECT * FROM account_stats WHERE platform = ? AND ts <= ? ORDER BY ts DESC LIMIT 1",
            (platform, ts),
        ).fetchone()


def account_series(platform: str, since: str) -> list[sqlite3.Row]:
    with connect() as db:
        return db.execute(
            "SELECT ts, followers, views, likes FROM account_stats WHERE platform = ? AND ts >= ? ORDER BY ts",
            (platform, since),
        ).fetchall()


def posts_latest() -> list[dict]:
    """Every known post with its latest numbers (NULL until its first refresh) and how it got its episode (link)."""
    with connect() as db:
        rows = db.execute(
            """SELECT p.platform, p.post_id, p.episode_id, p.link, p.title, p.url, p.published_at, p.last_ts AS ts,
                      p.views, p.likes, p.comments, p.shares, p.saves, e.title AS episode
               FROM posts p LEFT JOIN episodes e ON e.id = p.episode_id"""
        ).fetchall()
    return [dict(r) for r in rows]


def platforms_with_posts_since(since: str) -> set[str]:
    with connect() as db:
        return {r[0] for r in db.execute("SELECT DISTINCT platform FROM posts WHERE published_at >= ?", (since,))}


def get_meta(key: str, default=None):
    with connect() as db:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row["value"])
    except ValueError:  # older versions stored compacted_at as a bare string
        return row["value"]


def set_meta(key: str, value) -> None:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))


def post_series(since: str) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """(platform, post_id) -> [(ts, views), ...], oldest first, for posts published since `since`.

    Older posts don't need their curves: scores and typical curves come from recent videos. A reading
    without a view count is skipped, and a count that dips (YouTube's feed lags its pages) is held at its
    highest, so curves never step down.
    """
    out: dict[tuple[str, str], list[tuple[str, int]]] = {}
    with connect() as db:
        for platform, post_id, ts, views in db.execute(
                """SELECT s.platform, s.post_id, s.ts, s.views FROM post_stats s
                   JOIN posts p ON p.platform = s.platform AND p.post_id = s.post_id
                   WHERE p.published_at >= ? AND s.views IS NOT NULL
                   ORDER BY s.platform, s.post_id, s.ts""", (since,)):
            pts = out.setdefault((platform, post_id), [])
            pts.append((ts, max(views, pts[-1][1]) if pts else views))
    return out


# Old snapshots get thinned out, keeping the last one in each time bucket: full detail for 2 days,
# then one per 3 hours, one per day after 2 weeks, one per week after 2 months.
_BUCKETS = (
    (2, "substr(ts, 1, 10) || '.' || (CAST(substr(ts, 12, 2) AS INTEGER) / 3)"),
    (14, "substr(ts, 1, 10)"),
    (60, "strftime('%Y-%W', substr(ts, 1, 19))"),
)


def compact(min_hours: float = 20) -> int:
    """Thin out old snapshots and save the daily backup (at most once every `min_hours`). Returns rows removed."""
    now = datetime.now(timezone.utc)
    last = get_meta("compacted_at")
    if last and now - parse(last) < timedelta(hours=min_hours):
        return 0
    removed = 0
    with connect() as db:
        for days, bucket in _BUCKETS:
            cut = (now - timedelta(days=days)).isoformat(timespec="seconds")
            removed += db.execute(
                f"""DELETE FROM post_stats WHERE ts < ? AND rowid NOT IN (
                      SELECT MAX(rowid) FROM post_stats WHERE ts < ? GROUP BY platform, post_id, {bucket})""",
                (cut, cut)).rowcount
            account_cut = (now - timedelta(days=days + 12)).isoformat(timespec="seconds")
            removed += db.execute(
                f"""DELETE FROM account_stats WHERE ts < ? AND rowid NOT IN (
                      SELECT MAX(rowid) FROM account_stats WHERE ts < ? GROUP BY platform, {bucket})""",
                (account_cut, account_cut)).rowcount
        # Read notifications beyond the newest 300 go too (notify.tidy does the same).
        db.execute("""DELETE FROM notifications WHERE read = 1 AND id NOT IN (
                        SELECT id FROM notifications ORDER BY id DESC LIMIT 300)""")
        db.execute("PRAGMA optimize")
    set_meta("compacted_at", now.isoformat(timespec="seconds"))
    daily_backup()
    return removed


def daily_backup(keep: int = BACKUPS_KEPT) -> Path | None:
    """Save data/backups/stats-YYYYMMDD.db unless today's is there, and keep the newest `keep`.

    Never raises: a failed backup only means there is none today. Returns today's backup, or None.
    """
    try:
        folder = _path.parent / "backups"
        folder.mkdir(exist_ok=True)
        target = folder / f"{_path.stem}-{datetime.now():%Y%m%d}.db"
        if not target.exists():
            part = target.with_suffix(".part")  # renamed once complete, so a half-written file never counts
            part.unlink(missing_ok=True)
            with connect() as db:
                db.execute("VACUUM INTO ?", (str(part),))
            part.replace(target)
        ours = sorted(f for f in folder.iterdir() if re.fullmatch(rf"{re.escape(_path.stem)}-\d{{8}}\.db", f.name))
        for old in ours[:-keep]:
            old.unlink()
        return target
    except Exception:
        return None


def episodes() -> list[sqlite3.Row]:
    with connect() as db:
        return db.execute(
            """SELECT e.*, COALESCE(MIN(p.published_at), e.created_at) AS first_post
               FROM episodes e LEFT JOIN posts p ON p.episode_id = e.id
               GROUP BY e.id ORDER BY first_post DESC"""
        ).fetchall()


def episode_for_video(name: str) -> sqlite3.Row | None:
    """The newest episode made from a video with this file name, whichever folder the file was in then."""
    name = Path(name).name.lower()
    with connect() as db:
        rows = db.execute("SELECT * FROM episodes WHERE video IS NOT NULL ORDER BY id DESC").fetchall()
    return next((e for e in rows if Path(e["video"]).name.lower() == name), None)


def create_episode(title: str, video: str | None = None, created_at: str | None = None) -> int:
    with connect() as db:
        cur = db.execute(
            "INSERT INTO episodes (title, video, created_at) VALUES (?,?,?)",
            (title, video, created_at or now_iso()),
        )
        return cur.lastrowid


def add_post(platform: str, post_id: str, episode_id: int | None, title: str, url: str | None,
             published_at: str | None = None) -> None:
    """A post ReelForge made itself (pushed, or manual-<episode id> for typed-in numbers), so its episode is known."""
    link = "publish" if episode_id is not None else None
    with connect() as db:
        db.execute(
            """INSERT INTO posts (platform, post_id, episode_id, title, url, published_at, link) VALUES (?,?,?,?,?,?,?)
               ON CONFLICT (platform, post_id) DO UPDATE SET
                 episode_id = COALESCE(excluded.episode_id, posts.episode_id),
                 link = COALESCE(excluded.link, posts.link)""",
            (platform, post_id, episode_id, title, url, published_at or now_iso(), link),
        )


def link_post(platform: str, post_id: str, episode_id: int | None, how: str | None = "caption") -> None:
    """File a post under an episode, noting how (see LINKS). None for either unlinks it, for auto_link to decide."""
    if episode_id is None or how is None:
        episode_id = how = None
    elif how not in LINKS:
        raise ValueError(f"unknown link {how!r}")
    with connect() as db:
        db.execute("UPDATE posts SET episode_id = ?, link = ? WHERE platform = ? AND post_id = ?",
                   (episode_id, how, platform, post_id))


def set_post_episode(platform: str, post_id: str, episode_id: int | None) -> None:
    """Your choice of episode for a post; None means it isn't an episode. auto_link never changes either."""
    with connect() as db:
        db.execute("UPDATE posts SET episode_id = ?, link = 'hand' WHERE platform = ? AND post_id = ?",
                   (episode_id, platform, post_id))


def relink(changes: list[tuple], new_episodes: dict[int, tuple[str, str]]) -> int:
    """Apply what auto_link worked out, in one go. Returns how many posts changed episode.

    changes: (platform, post_id, episode_id, link as read, episode_id, link to set). A post that changed since it was
    read (you linked it by hand meanwhile) is left alone. A negative episode_id is a key of new_episodes: the
    (title, created_at) of an episode to create.
    """
    if not changes:
        return 0
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        now = {(r[0], r[1]): (r[2], r[3]) for r in db.execute("SELECT platform, post_id, episode_id, link FROM posts")}
        todo = [c for c in changes if now.get((c[0], c[1])) == (c[2], c[3])]
        ids = {k: db.execute("INSERT INTO episodes (title, created_at) VALUES (?,?)", v).lastrowid
               for k, v in new_episodes.items() if any(c[4] == k for c in todo)}
        db.executemany("UPDATE posts SET episode_id = ?, link = ? WHERE platform = ? AND post_id = ?",
                       [(ids.get(c[4], c[4]), c[5], c[0], c[1]) for c in todo])
    return sum(c[2] != c[4] for c in todo)


def all_posts() -> list[sqlite3.Row]:
    with connect() as db:
        return db.execute("SELECT * FROM posts ORDER BY published_at, platform, post_id").fetchall()


def linked_posts() -> list[sqlite3.Row]:
    with connect() as db:
        return db.execute("SELECT * FROM posts WHERE episode_id IS NOT NULL").fetchall()


def unlinked_posts() -> list[sqlite3.Row]:
    """Posts with no episode, except those you marked as not an episode."""
    with connect() as db:
        return db.execute(
            "SELECT * FROM posts WHERE episode_id IS NULL AND link IS NOT 'hand' ORDER BY published_at"
        ).fetchall()


def log_upload(platform: str, video: str, status: str, post_id: str | None = None,
               url: str | None = None, message: str = "") -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO uploads (ts, platform, video, status, post_id, url, message) VALUES (?,?,?,?,?,?,?)",
            (now_iso(), platform, video, status, post_id, url, message),
        )


def uploads(limit: int | None = 30) -> list[sqlite3.Row]:
    """The upload log, newest first; limit=None gives all of it."""
    limit = -1 if limit is None else limit
    with connect() as db:
        return db.execute("SELECT * FROM uploads ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
