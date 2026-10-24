"""Demo mode: made-up but realistic history so ReelForge can be tried before any account is set up.

It uses its own database (data/demo.db, rebuilt on every launch) and never touches the network.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from . import db, notify
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

# reach: views a typical episode ends up with; tau: hours until ~63% of them have arrived
PROFILES = {
    "tiktok": dict(reach=140_000, tau=20, follow=0.006, like=0.085, comment=0.004, share=0.012, save=None),
    "youtube": dict(reach=70_000, tau=40, follow=0.004, like=0.045, comment=0.002, share=0.004, save=None),
    "instagram": dict(reach=45_000, tau=14, follow=0.005, like=0.060, comment=0.003, share=0.015, save=0.010),
    "x": dict(reach=9_000, tau=6, follow=0.002, like=0.020, comment=0.002, share=0.004, save=0.003),
}
HANDLES = {key: "@yourchannel" for key in ("tiktok", "youtube", "instagram", "x")}
START_FOLLOWERS = {"tiktok": 300, "youtube": 120, "instagram": 200, "x": 80}
# What seed() made up for each post: (platform, post id) -> (title, published, reach multiplier, rates). A refresh
# grows every post along the same curve, so the charts carry on smoothly instead of jumping.
_SEEDED: dict[tuple[str, str], tuple[str, datetime, float, dict]] = {}
SAMPLE_UPDATE = ("1.1.0", "## What's new\n\n- Sample release notes: this is demo mode, so nothing is downloaded.\n"
                          "- A real update downloads the new version and restarts ReelForge in one click.")


def _views(key: str, published: datetime, mix: float, t: datetime) -> int:
    """A post's views at time t: most of its reach arrives over the first day or two, then it levels off."""
    prof = PROFILES[key]
    age = (t - published).total_seconds() / 3600
    return int(prof["reach"] * mix * (1 - math.exp(-age / prof["tau"]))) if age > 0 else 0


def _post(key: str, post_id: str, title: str, published: str, views: int, rates: dict) -> Post:
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


def seed(days: int = 11) -> None:
    rng = random.Random(7)
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    _SEEDED.clear()

    episodes = []
    for i, title in enumerate(TITLES):
        published = (start + timedelta(days=i + 1)).replace(hour=13)  # ~9 am US Eastern
        if published > now - timedelta(hours=2):
            break
        quality = rng.lognormvariate(0, 0.5) * (2.8 if i == 0 else 1.0)  # episode 1 took off
        eid = db.create_episode(title, f"ep{i + 1:02d}.mp4", db.to_iso(published))
        mix = {key: quality * rng.lognormvariate(0, 0.35) for key in PROFILES}
        rates = {
            key: {r: prof[r] * rng.uniform(0.7, 1.3) if prof[r] else None for r in ("like", "comment", "share", "save")}
            for key, prof in PROFILES.items()
        }
        for key in PROFILES:
            db.add_post(key, f"{key}-{eid}", eid, title, None, db.to_iso(published))
            _SEEDED[(key, f"{key}-{eid}")] = (title, published, mix[key], rates[key])
        episodes.append((eid, title, published, mix, rates))

    t = start
    with db.connect() as conn:  # one transaction: a few hundred snapshots in well under a second
        while t <= now:
            for key, prof in PROFILES.items():
                posts = []
                for eid, title, published, mix, rates in episodes:
                    if t <= published:
                        continue
                    views = _views(key, published, mix[key], t)
                    posts.append(_post(key, f"{key}-{eid}", title, db.to_iso(published), views, rates[key]))
                followers = START_FOLLOWERS[key] + int(sum(p.views for p in posts) * prof["follow"])
                db.record_snapshot(key, Account(HANDLES[key], followers, posts=len(posts)), posts,
                                   ts=db.to_iso(t), conn=conn)
            t += timedelta(hours=1)  # as if ReelForge had been open the whole time
    _sample_notifications(now, [e[1] for e in episodes])


def _sample_notifications(now: datetime, titles: list[str]) -> None:
    """A few of what the drawer shows, some read and some not, and the milestone starting points (so the demo's
    own refreshes don't announce every round number at once)."""
    notify.check_milestones({cls.key: cls.name for cls in ORDER}, {cls.key for cls in ORDER})
    if not titles:
        return
    best, newest = titles[0], titles[-1]
    for kind, title, body, hours, read in (
            ("milestone", "TikTok passed 5K followers", "You have 5,240 followers on TikTok.", 30, True),
            ("hot", "Taking off on YouTube", f"{newest[:60]} is doing 3.4× your typical video.", 9, True),
            ("milestone", "A video passed 100K views on TikTok", best[:70], 5, False),
            ("update", f"ReelForge {SAMPLE_UPDATE[0]} is out", "Open Updates (6) to update and restart in one click.",
             2, False),
            ("video", "A new video is ready to post", "What if the speed of sound was 5 mph? (ep11.mp4)", 0.5, False)):
        notify.add(kind, title, body, ts=db.to_iso(now - timedelta(hours=hours)), read=read)


class DemoPlatform(Platform):
    """Stands in for a real platform: grows the seeded numbers a little on each refresh."""

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
        return False  # the demo never opens Edge, so it keeps the normal refresh timing

    @property
    def handle(self) -> str:
        return HANDLES[self.key]

    def fetch(self) -> tuple[Account, list[Post]]:
        """Each post a little further along its own seeded curve, with its own like/comment/share rates."""
        prof = PROFILES[self.key]
        now = datetime.now(timezone.utc)
        posts = [_post(key, post_id, title, db.to_iso(published), _views(key, published, mix, now), rates)
                 for (key, post_id), (title, published, mix, rates) in _SEEDED.items() if key == self.key]
        followers = START_FOLLOWERS[self.key] + int(sum(p.views for p in posts) * prof["follow"])
        return Account(HANDLES[self.key], followers, posts=len(posts)), posts


def platforms() -> dict[str, Platform]:
    return {cls.key: DemoPlatform(cls) for cls in ORDER}
