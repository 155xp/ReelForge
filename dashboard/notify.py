"""Notifications: what happened while you weren't looking, in the drawer on the left (n, or the bell).

  an update        a newer ReelForge is out (once per version)
  a milestone      followers on a platform, views across every platform, or one video's views passing a round number
  a video          a finished video turned up, ready to post from the Publish tab
  a log-in         Instagram or X logged ReelForge's browser out
  taking off       a new video doing 3x your typical one
  a badge          a video or today moving up to a better "top X% of yours" badge (see badges.py)

They're kept in the stats database, so the hourly background refresh adds them while ReelForge is closed, and the
bell shows a red dot until you've read them. Each has a key, so the same event is never told twice.
"""

from __future__ import annotations

from . import db

KINDS = {  # kind -> (icon, colour, the tab it opens)
    "update": ("↑", "#7aa2f7", "updates"),
    "milestone": ("★", "#ffcc33", "overview"),
    "video": ("▶", "#3dff9a", "publish"),
    "login": ("!", "#ff4d5e", "accounts"),
    "hot": ("▲", "#ff8a3d", "videos"),
    "badge": ("◆", "#ffcc33", "videos"),
    "info": ("·", "#8b93a1", None),
}
KEEP = 300  # read notifications older than the newest KEEP are dropped when the database is tidied

FOLLOWERS = (100, 500, 1_000, 5_000) + tuple(int(m * 10 ** e) for e in range(4, 10) for m in (1, 2.5, 5))
TOTAL_VIEWS = tuple(10 ** e for e in range(3, 12))
VIDEO_VIEWS = tuple(10 ** e for e in range(3, 10))


def add(kind: str, title: str, body: str = "", key: str | None = None, tab: str | None = None,
        ts: str | None = None, read: bool = False) -> bool:
    """Add a notification, unless one with the same key is already there. Returns whether it was added."""
    tab = tab if tab is not None else KINDS.get(kind, KINDS["info"])[2]
    with db.connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO notifications (ts, kind, key, title, body, tab, read) VALUES (?,?,?,?,?,?,?)",
            (ts or db.now_iso(), kind, key, title, body, tab, int(read)))
        return cur.rowcount > 0


def release(key: str) -> None:
    """Let a once-only notification happen again later (say, a log-in that works again and then breaks again)."""
    with db.connect() as c:
        c.execute("UPDATE notifications SET key = NULL WHERE key = ?", (key,))


def unread() -> int:
    with db.connect() as c:
        return c.execute("SELECT COUNT(*) FROM notifications WHERE read = 0").fetchone()[0]


def recent(limit: int = 80) -> list[dict]:
    """Newest first."""
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))]


def newest_id() -> int:
    with db.connect() as c:
        return c.execute("SELECT COALESCE(MAX(id), 0) FROM notifications").fetchone()[0]


def since(after_id: int) -> list[dict]:
    """Notifications added after `after_id`, oldest first (for the pop-ups when a refresh adds some)."""
    with db.connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM notifications WHERE id > ? ORDER BY id", (after_id,))]


def mark_read(note_id: int) -> None:
    with db.connect() as c:
        c.execute("UPDATE notifications SET read = 1 WHERE id = ?", (note_id,))


def mark_all_read() -> None:
    with db.connect() as c:
        c.execute("UPDATE notifications SET read = 1 WHERE read = 0")


def tidy(keep: int = KEEP) -> None:
    with db.connect() as c:
        c.execute("""DELETE FROM notifications WHERE read = 1 AND id NOT IN (
                       SELECT id FROM notifications ORDER BY id DESC LIMIT ?)""", (keep,))


def short(n: float) -> str:
    """1000 -> 1K, 2500000 -> 2.5M: how milestones are named."""
    for size, unit in ((10 ** 9, "B"), (10 ** 6, "M"), (10 ** 3, "K")):
        if n >= size:
            v = n / size
            return f"{v:.1f}".rstrip("0").rstrip(".") + unit
    return f"{n:,.0f}"


def level(value: float | None, marks: tuple[int, ...]) -> int:
    """The highest mark reached, or 0."""
    return max((m for m in marks if value is not None and value >= m), default=0)


def check_milestones(names: dict[str, str], fresh: set[str] = frozenset()) -> int:
    """After a refresh: one notification for each milestone passed since the last check. Returns how many.

    names: platform key -> name, for the platforms just read. fresh: those read for the first time; their numbers
    become the starting point quietly, so a new account (or the very first check) doesn't set off a flood. A video
    first seen on an account that was already being read starts from zero, so a post that's already past 1K by its
    first reading still counts.
    """
    marks: dict = db.get_meta("milestones", None) or {}
    seeding = "_seeded" not in marks
    latest = db.latest_accounts()
    told = 0

    def passed(key: str, value, steps, quiet: bool) -> int:
        nonlocal told
        lv = level(value, steps)
        if key not in marks or quiet:
            marks[key] = max(marks.get(key, 0), lv)
            return 0
        if lv > marks[key]:
            marks[key] = lv
            return lv
        return 0

    for key, name in names.items():
        row = latest.get(key)
        if row is None or row["followers"] is None:
            continue
        m = passed(f"followers:{key}", row["followers"], FOLLOWERS, seeding or key in fresh)
        if m and add("milestone", f"{name} passed {short(m)} followers",
                     f"You have {row['followers']:,} followers on {name}.", key=f"milestone:followers:{key}:{m}"):
            told += 1

    views = [r["views"] for r in latest.values() if r["views"] is not None]
    if views:
        total = sum(views)
        m = passed("views:total", total, TOTAL_VIEWS, seeding or bool(fresh))
        if m and add("milestone", f"{short(m)} views in total",
                     f"Your videos have {total:,} views across every platform.", key=f"milestone:views:{m}"):
            told += 1

    for p in db.posts_latest():
        key, views = p["platform"], p["views"]
        if key not in names or views is None:
            continue
        mk = f"video:{key}|{p['post_id']}"
        quiet = seeding or key in fresh
        if mk not in marks and not quiet:
            marks[mk] = 0  # new on an account already being read: it starts from zero
        m = passed(mk, views, VIDEO_VIEWS, quiet)
        title = (p["episode"] or p["title"] or "A video").strip().splitlines()[0][:70]
        if m and add("milestone", f"A video passed {short(m)} views on {names[key]}", title,
                     key=f"milestone:video:{key}|{p['post_id']}:{m}"):
            told += 1
    marks["_seeded"] = 1
    db.set_meta("milestones", {k: v for k, v in marks.items() if v or not k.startswith("video:")})
    return told


def check_videos(cfg: dict) -> int:
    """A notification for each finished video that wasn't there at the last look. The first look only takes stock."""
    from . import videos

    files = videos.find(cfg)
    names = [f.name.lower() for f in files]
    known = db.get_meta("known_videos", None)
    told = 0
    if known is not None:
        seen = set(known)
        for f in files:
            if f.name.lower() in seen:
                continue
            try:
                caption = videos.meta(f, cfg)[0].get("caption") or f.stem
            except Exception:
                caption = f.stem
            if add("video", "A new video is ready to post", f"{caption[:70]} ({f.name})",
                   key=f"video:{f.name.lower()}"):
                told += 1
        names = list(dict.fromkeys([*known, *names]))
    db.set_meta("known_videos", names[-500:])
    return told


def update_available(version: str) -> bool:
    return add("update", f"ReelForge {version} is out", "Open Updates (6) to update and restart in one click.",
               key=f"update:{version}")
