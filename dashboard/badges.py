"""Badges: "Top 5% of your TikTok videos for views", "Today: your best day yet for new YouTube followers".

Every badge compares you with yourself, from the numbers ReelForge has stored, so it's always true:
  - a video against your other videos on the same platform, for views, likes, shares and views in its first day
    (the reading 23-26 hours after it went up);
  - today so far against your earlier days, for new followers and views on each platform (days ReelForge was only
    partly reading, or had to estimate, are left out).
Percentages ("top 25%", "top 10%", "top 5%", "top 1%") need at least 10 videos or days to compare; before that a
badge only says "your best ... yet", and only when it really is the best. Ties count against you: a video tied with
others is ranked below all of them, so "top 10%" always holds.

There are no badges against other creators. No platform publishes how big its creators' accounts are, and the best
outside sources checked (October 2026) can't back a "top X% of creators" claim:
  - YouTube: McGrady et al., "Dialing for Videos: A Random Sample of YouTube", Journal of Quantitative Description:
    Digital Media 3 (2023), https://doi.org/10.51685/jqd.2023.022, gives only the median (61 subscribers) and the
    share with any subscribers (90.5%) for the channels behind 10,016 randomly found public videos; no percentiles.
  - TikTok: Pew Research Center, "What we know about TikTok content creators" (February 2025) covers only accounts
    with 5,000+ followers that a panel of U.S. adults follows, in broad bands.
Instagram and X: nothing comparable. A made-up yardstick would be untrue, so badges stay with your own numbers.

The badge on show is on the Overview (the account's) and the Videos tab (the highlighted video's). Moving up to a
better tier (top 25% -> 10% -> 5% -> 1% -> best yet) adds one notification per video or day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from rich.text import Text

from . import analytics, db, notify, trends
from .analytics import fmt_num

MIN_COMPARE = 10  # videos or days needed before a badge may say a percentage
MIN_BEST = 3      # videos or days needed before "your best ... yet" (one or two isn't much of a record)
TIERS = ((0.01, "top 1%"), (0.05, "top 5%"), (0.10, "top 10%"), (0.25, "top 25%"))
BEST = 5  # tier numbers: 5 best yet, 4 top 1%, 3 top 5%, 2 top 10%, 1 top 25%, 0 none
VIDEO_METRICS = {"views": "views", "likes": "likes", "shares": "shares", "first_day": "views in their first day"}
DAY_METRICS = {"followers": "new {name} followers", "views": "{name} views"}
DAYS = 60
HOW = ("Badges compare you with yourself, from the numbers ReelForge has stored: a video against your other videos "
       "on the same platform, today against your earlier days. Percentages need at least 10 to compare, and ties "
       "count against you.")


@dataclass
class Badge:
    subject: str   # "video:<platform>|<post id>" or "day:<platform>:<date>"
    metric: str
    tier: int      # BEST, or 4..1 for top 1% .. top 25%
    text: str      # what the badge says
    detail: str    # the numbers behind it, e.g. "#2 of 41"


def rank(value: float, others: list[float]) -> tuple[int, int, int]:
    """(tier, position, how many) for `value` among itself and `others`. Ties rank below: the position is one more
    than every other value at least as high."""
    n = len(others) + 1
    ahead = sum(1 for o in others if o >= value)
    pos = ahead + 1
    if not ahead and n >= MIN_BEST and value > 0:
        return BEST, pos, n
    if n >= MIN_COMPARE:
        for i, (share, _) in enumerate(TIERS):
            if pos <= share * n:
                return 4 - i, pos, n
    return 0, pos, n


def tier_name(tier: int) -> str:
    return "best yet" if tier == BEST else TIERS[4 - tier][1] if 1 <= tier <= 4 else ""


def first_day_views() -> dict[tuple[str, str], int]:
    """Each post's views at its first reading 23-26 hours after it went up (posts without one are left out)."""
    out: dict[tuple[str, str], int] = {}
    with db.connect() as c:
        for platform, post_id, views in c.execute(
                """SELECT s.platform, s.post_id, s.views FROM post_stats s
                   JOIN posts p ON p.platform = s.platform AND p.post_id = s.post_id
                   WHERE s.views IS NOT NULL AND p.published_at IS NOT NULL
                     AND (julianday(s.ts) - julianday(p.published_at)) * 24 BETWEEN 23 AND 26
                   ORDER BY s.platform, s.post_id, s.ts"""):
            out.setdefault((platform, post_id), views)
    return out


def _value(post: dict, metric: str, first_day: dict) -> float | None:
    if metric == "first_day":
        return first_day.get((post["platform"], post["post_id"]))
    return post.get(metric)


def video_badges(post: dict, posts: list[dict], first_day: dict, platforms: dict) -> list[Badge]:
    """The badges one video has earned against your other videos on its platform, best first."""
    p = platforms.get(post["platform"])
    if p is None:
        return []
    out = []
    for metric, phrase in VIDEO_METRICS.items():
        mine = _value(post, metric, first_day)
        if mine is None:
            continue
        others = [v for q in posts if q["platform"] == post["platform"] and q["post_id"] != post["post_id"]
                  and (v := _value(q, metric, first_day)) is not None]
        tier, pos, n = rank(mine, others)
        if not tier:
            continue
        what = f"{p.name} video" if tier == BEST else f"{p.name} videos"
        text = (f"Your best {what} yet for {phrase}" if tier == BEST
                else f"Top {tier_name(tier)[4:]} of your {what} for {phrase}")
        out.append(Badge(f"video:{post['platform']}|{post['post_id']}", metric, tier, text,
                         f"{fmt_num(mine)} · #{pos} of {n}"))
    return sorted(out, key=lambda b: -b.tier)


def day_gains(rows, field: str, now=None) -> tuple[float | None, list[float]]:
    """(today's gain so far, earlier whole days' gains) from an account's readings, leaving out days ReelForge was
    only partly reading (a gap between readings: the day's bar would leave something out)."""
    pts = trends.points(rows, field)
    if len(pts) < 2:
        return None, []
    fr = trends.frame_span(timedelta(days=DAYS), timedelta(days=1), now)
    b = trends.bucket(pts, fr)
    first, last = pts[0][0], pts[-1][0]
    earlier = [g for i, g in enumerate(b.gains[:-1])
               if g is not None and not b.gaps[i] and first <= fr.starts[i] and fr.ends[i] <= last]
    today = b.gains[-1] if b.gains and not b.gaps[-1] and first <= fr.starts[-1] else None
    return today, earlier


def account_badges(account_rows: dict, platforms: dict, now=None) -> list[Badge]:
    """Today's badges for each platform (new followers, views), best first."""
    out = []
    date = (now or analytics.now()).astimezone().date().isoformat()
    for key, p in platforms.items():
        for field, phrase in DAY_METRICS.items():
            today, earlier = day_gains(account_rows.get(key, []), field, now)
            if not today:
                continue
            tier, pos, n = rank(today, earlier)
            if not tier:
                continue
            what = phrase.format(name=p.name)
            text = (f"Today: your best day yet for {what}" if tier == BEST
                    else f"Today: top {tier_name(tier)[4:]} of your days for {what}")
            out.append(Badge(f"day:{key}:{date}", field, tier, text, f"+{fmt_num(today)} so far · #{pos} of {n}"))
    return sorted(out, key=lambda b: -b.tier)


def badge_text(b: Badge) -> Text:
    color = "#ffcc33" if b.tier >= 3 else "#e8eaed"
    out = Text("★ " if b.tier == BEST else "▲ ", style=f"bold {color}")
    out.append(b.text, style=f"bold {color}" if b.tier >= 3 else "bold")
    out.append(f"  {b.detail}   ", style="#8b93a1")
    return out


def notify_new(posts: list[dict], first_day: dict, account_rows: dict, platforms: dict) -> int:
    """One notification for each video or day that moved up to a better badge since the last look. The first look
    only takes stock, and so does a platform's first: nothing old is announced as new. Returns how many."""
    marks: dict = db.get_meta("badge_tiers", None) or {}
    seeding = "_seeded" not in marks
    told = 0
    found: dict[str, list[Badge]] = {}
    for post in posts:
        for b in video_badges(post, posts, first_day, platforms):
            found.setdefault(b.subject, []).append(b)
    for b in account_badges(account_rows, platforms):
        found.setdefault(b.subject, []).append(b)
    for key in platforms:
        seen = f"seen:{key}"
        if seen not in marks:
            marks[seen] = 1
            for subject in [s for s in found if s.split(":", 1)[1].startswith((key + "|", key + ":"))]:
                for b in found.pop(subject):
                    marks[f"{b.subject}:{b.metric}"] = b.tier
    for subject, got in found.items():
        better = [b for b in got if b.tier > marks.get(f"{b.subject}:{b.metric}", 0)]
        for b in got:
            marks[f"{b.subject}:{b.metric}"] = max(b.tier, marks.get(f"{b.subject}:{b.metric}", 0))
        if seeding or not better:
            continue
        top = max(better, key=lambda b: b.tier)
        title = top.text if top.subject.startswith("day:") else f"{top.text}!"
        body = top.detail
        if top.subject.startswith("video:"):
            post = next((q for q in posts if f"video:{q['platform']}|{q['post_id']}" == top.subject), None)
            if post:
                body = f"{(post.get('episode') or post.get('title') or 'A video')[:60]} · {top.detail}"
        if notify.add("badge", title, body, key=f"badge:{top.subject}:{top.metric}:{top.tier}",
                      tab="videos" if top.subject.startswith("video:") else "overview"):
            told += 1
    marks["_seeded"] = 1
    # Old days' marks aren't needed once the day is over: keep videos' and the last few days'.
    days = sorted({k.split(":")[2] for k in marks if k.startswith("day:")})[-3:]
    db.set_meta("badge_tiers", {k: v for k, v in marks.items() if not k.startswith("day:") or k.split(":")[2] in days})
    return told
