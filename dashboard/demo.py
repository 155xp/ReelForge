"""Demo mode: made-up but believable history, so ReelForge can be tried before any account is set up.

It uses its own database (data/demo.db, rebuilt on every launch) and never touches the network. Views follow the day
in this computer's time zone (quiet at night, busiest in the evening), and each post gets a burst of views in its first
hours that dies down over the day: quickest on X, slowest on YouTube. The newest posts went up a few hours ago, about a
day ago and about two days ago, so the 24-hour and 48-hour charts have something to show.
"""

from __future__ import annotations

import math
import random
import zlib
from datetime import datetime, time, timedelta, timezone

from . import analytics, db, notify
from .platforms import ORDER, Platform
from .platforms.base import Account, Post

TITLES = [
    "What if your coffee doubled in size every 2 seconds?",
    "What if friction disappeared for 5 seconds?",
    "What if everyone on Earth jumped at once?",
    "What if the Moon was twice as close?",
    "What if your jump doubled in height every 2 seconds?",
    "What if a snowball doubled every 2 seconds?",
    "What if colour disappeared for 5 seconds?",
    "What if the world dropped to 5 FPS?",
    "What if a raindrop doubled in size every second?",
    "What if the speed of sound was 5 mph?",
]

# reach: views a typical episode ends up with. `burst` of them come in its first hours (the most in hour `peak`), the
# rest trickle in for days, halving every `half` hours. follow, like ...: per view.
PROFILES = {
    "tiktok": dict(reach=140_000, burst=0.55, peak=1.5, half=36, follow=0.006, like=0.085, comment=0.004,
                   share=0.012, save=None),
    "youtube": dict(reach=70_000, burst=0.45, peak=3.0, half=96, follow=0.004, like=0.045, comment=0.002,
                    share=0.004, save=None),
    "instagram": dict(reach=45_000, burst=0.6, peak=1.2, half=30, follow=0.005, like=0.060, comment=0.003,
                      share=0.015, save=0.010),
    "x": dict(reach=9_000, burst=0.8, peak=0.6, half=8, follow=0.002, like=0.020, comment=0.002, share=0.004,
              save=0.003),
}
# How busy each hour of the day is, in local time: quiet overnight, a lunchtime bump, busiest in the evening.
DAY = (0.55, 0.40, 0.30, 0.24, 0.22, 0.25, 0.35, 0.50, 0.65, 0.75, 0.82, 0.92,
       1.00, 1.00, 0.97, 1.02, 1.12, 1.28, 1.42, 1.50, 1.48, 1.35, 1.10, 0.80)
POST_AT = (11, 19)  # the demo channel posts at 11 am or 7 pm
# Which of those slots (0 = the newest at least a few hours ago) got a post, newest first: two in the last day, one
# about two days ago, then about one a day.
PICKS = (0, 1, 3, 5, 7, 10, 12, 15, 18)
# How each episode did (1: a typical one): the first took off, the rest landed around typical, and the newest few
# did well enough to make a clear spike on the charts.
QUALITY = (2.8, 0.8, 1.15, 0.9, 0.7, 1.0, 1.0, 1.3, 1.25)
HANDLES = {key: "@yourchannel" for key in ("tiktok", "youtube", "instagram", "x")}
START_FOLLOWERS = {"tiktok": 300, "youtube": 120, "instagram": 200, "x": 80}
# What seed() made up for each post: (platform, post id) -> (title, published, views at the end of each hour since,
# per-view rates). A refresh reads every post further along the same curve, so the charts carry on smoothly.
_SEEDED: dict[tuple[str, str], tuple[str, datetime, list[float], dict]] = {}
_START: dict[str, float] = {}  # followers before the first post
SAMPLE_UPDATE = ("1.1.0", "## What's new\n\n- Sample release notes: this is demo mode, so nothing is downloaded.\n"
                          "- A real update downloads the new version and restarts ReelForge in one click.")
# The same, as the README's pictures show it (REELFORGE_SCREENSHOTS=1): notes like a real release's.
SCREENSHOT_NOTES = ("## What's new\n\n- A sharper logo in Windows Terminal.\n"
                    "- Charts that read right at every window size: narrow ones combine hours.\n"
                    "- Notifications sit behind the bell at the top right.")


def _schedule(now: datetime, count: int) -> list[datetime]:
    """When the posts went up (UTC, oldest first): PICKS of the 11 am and 7 pm slots before now, local time."""
    local = now.astimezone()
    slots: list[datetime] = []
    day = local.date()
    while len(slots) <= max(PICKS):
        for hour in sorted(POST_AT, reverse=True):
            t = datetime.combine(day, time(hour)).astimezone()
            if t <= local - timedelta(hours=2.5):  # the newest has a few hours of numbers already
                slots.append(t)
        day -= timedelta(days=1)
    return [slots[i].astimezone(timezone.utc) for i in reversed(PICKS[:count])]


def _burst(a: float, peak: float) -> float:
    """The share of a post's burst that arrives per hour, `a` hours after it went up (a gamma curve, shape 1.5)."""
    theta = 2 * peak
    return math.sqrt(a / theta) * math.exp(-a / theta) / (theta * math.gamma(1.5)) if a > 0 else 0.0


def _curve(key: str, post_id: str, published: datetime, mix: float, hours: int) -> list[float]:
    """A post's views at the end of each hour after it went up (index 0: as it went up). Busier in the evening than at
    night, with a little wobble from hour to hour."""
    prof = PROFILES[key]
    decay = math.log(2) / prof["half"]
    mean = sum(DAY) / 24
    rng = random.Random(zlib.crc32(f"{key}:{post_id}".encode()))
    wobble, total, out = 0.0, 0.0, [0.0]
    for j in range(hours):
        a = j + 0.5
        share = prof["burst"] * _burst(a, prof["peak"]) + (1 - prof["burst"]) * decay * math.exp(-decay * a)
        busy = DAY[(published + timedelta(hours=a)).astimezone().hour] / mean
        wobble = 0.5 * wobble + rng.gauss(0, 0.13)
        total += prof["reach"] * mix * share * busy * math.exp(wobble)
        out.append(total)
    return out


def _views(curve: list[float], published: datetime, t: datetime) -> int:
    """A post's views at moment t, between the hourly points of its curve."""
    a = (t - published).total_seconds() / 3600
    if a <= 0:
        return 0
    j = int(a)
    if j + 1 >= len(curve):
        return int(curve[-1])
    return int(curve[j] + (curve[j + 1] - curve[j]) * (a - j))


def _post(post_id: str, title: str, published: str, views: int, rates: dict) -> Post:
    return Post(
        post_id=post_id,
        title=title,
        url=None,
        published_at=published,
        views=views,
        likes=int(views * rates["like"]),
        comments=int(views * rates["comment"]),
        shares=int(views * rates["share"]),
        saves=int(views * rates["save"]) if rates["save"] else None,
    )


def _read(key: str, t: datetime) -> tuple[Account, list[Post]]:
    """What the platform would have shown at moment t: every post so far, and the followers they brought in."""
    posts, followers = [], _START.get(key, START_FOLLOWERS[key])
    for (k, post_id), (title, published, curve, rates) in _SEEDED.items():
        if k == key and published < t:
            views = _views(curve, published, t)
            followers += views * rates["follow"]
            posts.append(_post(post_id, title, db.to_iso(published), views, rates))
    return Account(HANDLES[key], int(followers), posts=len(posts)), posts


def seed(days: int = 11, video: tuple[str, str] | None = None) -> None:
    """video: (file name, caption) of a real finished video, the newest on the Publish tab, for the "ready to post"
    notification; without one it names a made-up episode."""
    rng = random.Random(7)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now.replace(minute=0, second=0) - timedelta(days=days)
    _SEEDED.clear()
    _START.clear()

    count = len(TITLES) - 1  # the last one is still waiting on the Publish tab
    times = [t for t in _schedule(now, count) if t > start]
    hours = days * 24 + 24 * 14  # far enough ahead that refreshes follow the curves for two weeks
    posted = []
    for i, (title, published) in enumerate(zip(TITLES, times)):
        quality = QUALITY[i] if i < len(QUALITY) else 1.0
        mix = {key: quality * rng.lognormvariate(0, 0.3) for key in PROFILES}
        if i == len(times) - 1:
            mix["youtube"] *= 3  # the newest is doing well on YouTube too
        eid = db.create_episode(title, f"ep{i + 1:02d}.mp4", db.to_iso(published))
        for key, prof in PROFILES.items():
            post_id = f"{key}-{eid}"
            rates = {r: prof[r] * rng.uniform(0.7, 1.3) if prof[r] else None
                     for r in ("follow", "like", "comment", "share", "save")}
            db.add_post(key, post_id, eid, title, None, db.to_iso(published))
            _SEEDED[(key, post_id)] = (title, published, _curve(key, post_id, published, mix[key], hours), rates)
        posted.append((title, published))

    # TikTok passes 10K followers while the post from about a day ago takes off (see the notifications).
    if len(times) >= 2:
        at = times[-2] + timedelta(hours=1.5)
        before = 10_000 - (_read("tiktok", at)[0].followers - START_FOLLOWERS["tiktok"])
        if before >= START_FOLLOWERS["tiktok"]:
            _START["tiktok"] = before + 0.5

    stamps = [start + timedelta(hours=h) for h in range(days * 24 + 1)]  # hourly, as if ReelForge had been open
    if now - stamps[-1] >= timedelta(minutes=1):
        stamps.append(now)  # and a reading just now, so the hour under way has its bar
    with db.connect() as conn:  # one transaction: a few hundred snapshots in well under a second
        for t in stamps:
            for key in PROFILES:
                account, posts = _read(key, t)
                db.record_snapshot(key, account, posts, ts=db.to_iso(t), conn=conn)
    if video is None and count < len(TITLES):
        video = (f"ep{count + 1:02d}.mp4", TITLES[count])
    _sample_notifications(now, start, posted, video)


def newest_video(cfg: dict) -> tuple[str, str] | None:
    """(file name, caption) of the newest finished video on the Publish tab, for seed(), or None."""
    from . import videos

    newest = next(iter(videos.find(cfg)), None)
    return (newest.name, videos.meta(newest, cfg)[0]["caption"]) if newest else None


def _passed(value_at, marks, start: datetime, end: datetime) -> tuple[int, datetime, float] | None:
    """The last round number (one of marks) a value passed between start and end, checked hour by hour:
    (the round number, the first reading past it, the value then)."""
    found, prev, t = None, value_at(start), start
    while t < end:
        t = min(t + timedelta(hours=1), end)
        v = value_at(t)
        hit = [m for m in marks if prev < m <= v]
        if hit:
            found = (max(hit), t, v)
        prev = v
    return found


def _sample_notifications(now: datetime, start: datetime, posted: list[tuple[str, datetime]],
                          video: tuple[str, str] | None) -> None:
    """A few of what the drawer shows, some read and some not, worked out from the made-up numbers so they agree with
    the charts; and the milestone starting points (so the demo's own refreshes don't announce every round number at
    once). Each has the key a real one would have, so clicking it shows what it's about."""
    notify.check_milestones({cls.key: cls.name for cls in ORDER}, {cls.key for cls in ORDER})
    if not posted:
        return
    names = {cls.key: cls.name for cls in ORDER}
    notes = []  # (when, kind, title, body, read, key)
    followers = _passed(lambda t: _read("tiktok", t)[0].followers, notify.FOLLOWERS, start, now)
    if followers:
        m, t, v = followers
        notes.append((t, "milestone", f"TikTok passed {notify.short(m)} followers",
                      f"You have {int(v):,} followers on TikTok.", True, f"milestone:followers:tiktok:{m}"))
    # The newest video's best platform, scored the way ReelForge scores it (vs your typical video at the same age).
    newest, published = posted[-1]
    posts = analytics.enrich([p for p in db.posts_latest() if p["published_at"]],
                             analytics.parse_series(db.post_series(analytics.history_since())))
    hot = max((p for p in posts if p["title"] == newest and p["score"]), key=lambda p: p["score"], default=None)
    if hot and hot["score"] >= 3:  # what ReelForge itself calls taking off
        notes.append((min(published + timedelta(hours=3), now - timedelta(minutes=6)), "hot",
                      f"Taking off on {names[hot['platform']]}",
                      f"{newest[:60]} is doing {hot['score']:.1f}× your typical video.", True,
                      f"hot:{hot['platform']}|{hot['post_id']}"))  # the key a refresh would use, so it isn't told twice
    views = None  # the last time a video passed 100K views (or failing that, any round number) somewhere
    for marks in ((100_000,), notify.VIDEO_VIEWS):
        for (key, post_id), (title, published, curve, _) in _SEEDED.items():
            hit = _passed(lambda t: _views(curve, published, t), marks, published, now)
            if hit and (views is None or hit[1] > views[1]):
                views = (hit[0], hit[1], key, post_id, title)
        if views:
            break
    if views:
        m, t, key, post_id, title = views
        notes.append((t, "milestone", f"A video passed {notify.short(m)} views on {names[key]}", title[:70], False,
                      f"milestone:video:{key}|{post_id}:{m}"))
    notes.append((now - timedelta(hours=2), "update", f"ReelForge {SAMPLE_UPDATE[0]} is out",
                  "Open Updates (6) to update and restart in one click.", False, f"update:{SAMPLE_UPDATE[0]}"))
    if video:
        name, caption = video
        notes.append((now - timedelta(minutes=30), "video", "A new video is ready to post",
                      f"{caption[:70]} ({name})", False, f"video:{name.lower()}"))
    for when, kind, title, body, read, key in sorted(notes, key=lambda n: n[0]):  # the drawer: newest first
        notify.add(kind, title, body, key=key, ts=db.to_iso(when), read=read)


class DemoPlatform(Platform):
    """Stands in for a real platform: each refresh reads the seeded posts a little further along their curves."""

    def __init__(self, real: type[Platform]):
        super().__init__({})
        self.key, self.name, self.color, self.setup_note = real.key, real.name, real.color, real.setup_note

    @property
    def logged_in(self) -> bool:
        return True

    @property
    def stats_source(self) -> str | None:
        return "public"

    @property
    def uses_browser(self) -> bool:
        return False  # the demo never opens a browser, so it keeps the normal refresh timing

    @property
    def handle(self) -> str:
        return HANDLES[self.key]

    def fetch(self) -> tuple[Account, list[Post]]:
        return _read(self.key, datetime.now(timezone.utc))


def platforms() -> dict[str, Platform]:
    return {cls.key: DemoPlatform(cls) for cls in ORDER}
