"""Performance maths: engagement, score against your typical post, curves, episode matching, formatting."""

from __future__ import annotations

import math
import re
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median

from . import db

# A post's views over time: (snapshot times, views at each), oldest first.
Curve = tuple[list[datetime], list[int]]
Series = dict[tuple[str, str], Curve]
NO_CURVE: Curve = ([], [])

# Ages (hours) at which "typical" is measured; scores interpolate between them.
AGES = (1, 2, 3, 4, 6, 8, 12, 18, 24, 36, 48, 72, 96, 120, 168, 240, 336, 504, 720)
RECENT = 60  # "typical" means typical of your last 60 videos on that platform
HISTORY_DAYS = 120  # curves are only loaded for videos this recent


def now() -> datetime:
    return datetime.now(timezone.utc)


def history_since() -> str:
    return (now() - timedelta(days=HISTORY_DAYS)).isoformat(timespec="seconds")


def parse_series(raw: dict[tuple[str, str], list[tuple[str, int]]]) -> Series:
    return {k: ([db.parse(ts) for ts, _ in pts], [v for _, v in pts]) for k, pts in raw.items()}


def _curve(parsed: Series, p: dict) -> Curve:
    return parsed.get((p["platform"], p["post_id"]), NO_CURVE)


def enrich(posts: list[dict], parsed: Series) -> list[dict]:
    """Add age, engagement, share rate, views/hour and score to each post.

    score = views / what your typical video had at the same age (the median of your last 60 posts
    across every platform, from snapshots), so one yardstick covers the whole channel. Without
    enough history it falls back to the median of their current views. 1.0× is a typical post; 3× is a hit.
    """
    t = now()
    for p in posts:
        views = p["views"] or 0
        likes, comments, shares = p["likes"] or 0, p["comments"] or 0, p["shares"] or 0
        p["published"] = db.parse(p["published_at"])
        p["age_h"] = max((t - p["published"]).total_seconds() / 3600, 0.1)
        # Some sources only give views; then engagement is unknown, not 0%.
        known = any(p[k] is not None for k in ("likes", "comments", "shares"))
        p["eng"] = ((likes + comments + shares) / views if views else 0.0) if known else None
        p["share_rate"] = (shares / views if views else 0.0) if p["shares"] is not None else None
        p["vph"] = views / p["age_h"]

    _score(posts, posts, parsed, "score")
    # The same yardstick within each platform: is this a good TikTok (or X) post for TikTok (or X)?
    for platform in {p["platform"] for p in posts}:
        _score([p for p in posts if p["platform"] == platform], posts, parsed, "pscore")
    return posts


def _score(group: list[dict], posts: list[dict], parsed: Series, field: str) -> None:
    """views / typical views at the same age within `group`; the median of current views without history."""
    recent = sorted(group, key=lambda q: q["published"], reverse=True)[:RECENT]
    # With plenty of videos one shared curve is fine; with few, leave each video out of its own.
    shared = _typical(recent, parsed) if len(recent) > 15 else None
    views = sorted(q["views"] or 0 for q in group)
    for p in group:
        typical = shared if shared is not None else _typical([q for q in recent if q is not p], parsed)
        base = _at_age(typical, p["age_h"])
        if base is None:
            if len(views) > 15:
                base = median(views)
            else:
                others = list(views)
                others.remove(p["views"] or 0)
                base = median(others) if others else 0
        p[field] = (p["views"] or 0) / base if base else None


def _typical(group: list[dict], parsed: Series) -> list[float | None]:
    """Median views at each of AGES across a group of posts (None where fewer than 2 have data)."""
    out = []
    for age in AGES:
        vals = [v for q in group
                if q["age_h"] >= age and (v := views_at(_curve(parsed, q), q["published"], age)) is not None]
        out.append(median(vals) if len(vals) >= 2 else None)
    return out


def _at_age(typical: list[float | None], age: float) -> float | None:
    """Typical views at any age, interpolating between AGES on a log scale."""
    points = [(a, v) for a, v in zip(AGES, typical) if v]
    if not points or age > points[-1][0] * 1.5:
        return None
    if age <= points[0][0]:
        return points[0][1] * age / points[0][0]
    for (a0, v0), (a1, v1) in zip(points, points[1:]):
        if a0 <= age <= a1:
            return v0 + (v1 - v0) * (math.log(age) - math.log(a0)) / (math.log(a1) - math.log(a0))
    return points[-1][1]


def views_at(curve: Curve, pub: datetime, age_h: float) -> float | None:
    """Interpolated views a post had age_h hours after publishing, or None if we have no data there."""
    times, views = curve
    if not times:
        return None
    target = pub + timedelta(hours=age_h)
    if target < times[0]:
        # Before the first snapshot: count up from 0 at publish time, but only if that snapshot came
        # soon after publishing, otherwise the straight line would be a guess.
        lead = (times[0] - pub).total_seconds()
        if lead > 6 * 3600 or target < pub:
            return None
        return views[0] * (target - pub).total_seconds() / lead if lead else float(views[0])
    if target > times[-1]:
        return None
    i = bisect_left(times, target)
    if times[i] == target:
        return float(views[i])
    t0, t1 = times[i - 1], times[i]
    return views[i - 1] + (views[i] - views[i - 1]) * ((target - t0) / (t1 - t0))


def typical_curve(posts: list[dict], parsed: Series, platform: str | None, max_age_h: float, steps: int = 36,
                  exclude: dict | None = None) -> tuple[list[float], list[float]]:
    """Median views-by-age across recent posts (one platform's, or all with platform=None)."""
    group = sorted((q for q in posts if platform in (None, q["platform"]) and q is not exclude),
                   key=lambda q: q["published"], reverse=True)[:RECENT]
    # Prefer posts old enough to cover the whole range, so the median isn't taken over a
    # shrinking set (which makes the curve dip at the end).
    mature = [q for q in group if q["age_h"] >= max_age_h]
    if len(mature) >= 3:
        group = mature
    xs, ys = [], []
    for i in range(1, steps + 1):
        age = max_age_h * i / steps
        vals = [v for q in group if (v := views_at(_curve(parsed, q), q["published"], age)) is not None]
        if len(vals) >= 2:
            xs.append(age)
            ys.append(median(vals))
    return xs, ys


def post_curve(post: dict, parsed: Series) -> tuple[list[float], list[float]]:
    """A post's own views against hours since it went up."""
    times, views = _curve(parsed, post)
    xs = [(t - post["published"]).total_seconds() / 3600 for t in times]
    ys = [float(v) for v in views]
    if xs and xs[0] <= 6:
        xs, ys = [0.0, *xs], [0.0, *ys]
    return xs, ys


def interp(xs: list[float], ys: list[float], x: float) -> float:
    i = bisect_left(xs, x)
    if i <= 0:
        return ys[0]
    if i >= len(xs):
        return ys[-1]
    x0, x1 = xs[i - 1], xs[i]
    return ys[i - 1] + (ys[i] - ys[i - 1]) * ((x - x0) / (x1 - x0) if x1 > x0 else 1)


# --- matching the same video across platforms -------------------------------------------

# Titles in a series read alike ("What if your <X> doubled every <N> second(s)?"), so whole captions are mostly the
# same words ("savings doubled every second" and "subscribers doubled every second" are 84% alike). Captions are compared
# word by word instead, each word weighted by how few episodes use it (inverse document frequency over the titles and
# video file names): a word every episode has weighs nothing, so <X> decides. A caption's score for an episode is the
# share of the title's weight it contains, file name words counting as title words. Measured on a 5-episode series,
# captions that keep <X> (extra words, hashtags glued on, car's / cars, doubles / doubled) score 0.85-1.0 for their
# episode and at most 0.15 for any other. A new video in the same template scores at most 0.57 for an old episode
# (house vs balloon: "doubled in size"), as does a caption that drops part of <X>; those go by the upload window. One
# that only swaps a template word (tripled) scores 1.0, but that episode has its post on the platform already.
MATCH_SCORE = 0.7  # a caption names an episode when it scores this much for it...
MATCH_MARGIN = 0.3  # ...and at least this much more than for any other
KEEP_SCORE = 0.5  # a post stays in its episode while it scores this there and no episode is named instead
TWIN_SCORE = 0.8  # posts on two platforms are one new video when 80% of their words (by weight) are the same
FIXED_LINKS = ("hand", "publish")  # never re-checked: your own choice, and posts ReelForge made for an episode
_STOP = frozenset((
    "a an and are as at be but by can do does for from has have how i if in into is it its me my no not of on or our "
    "so than that the their them then there these they this to too us was we were what when where which who why will "
    "with would you your").split())


def _key(text: str | None) -> str:
    """First line, lowercased, without hashtags, links, apostrophes (car's = cars) or other punctuation."""
    first = re.sub(r"['’‘]", "", (text or "").strip().split("\n")[0].lower())
    first = re.sub(r"https?://\S+|#\w+", " ", first)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", first).split())[:80]


def _stem(word: str) -> str:
    """cars -> car, doubles / doubled / doubling / double -> doubl, flipped -> flip: rewordings keep their words."""
    if len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    for end in ("ing", "ed"):
        if word.endswith(end) and len(word) - len(end) >= 3:
            word = word[:-len(end)]
            if word[-1] == word[-2] and word[-1] not in "aeiouls":  # flipp(ed)
                word = word[:-1]
            break
    return word[:-1] if len(word) > 3 and word.endswith("e") else word


def _words(text: str | None) -> frozenset[str]:
    """The words that can tell videos apart: no hashtags, links, @handles, little words or epNN."""
    text = re.sub(r"https?://\S+|[#@]\w+", " ", re.sub(r"['’‘]", "", (text or "").lower()))
    words = (w for w in re.findall(r"[a-z0-9]+", text) if w not in _STOP and not (w[:2] == "ep" and w[2:].isdigit()))
    return frozenset(map(_stem, words))


class _Matcher:
    """Scores captions against a set of episodes, indexed so that a year of posts takes a moment."""

    def __init__(self, episodes: list[dict]) -> None:
        episodes = sorted(episodes, key=lambda e: (e["created_at"] or "", e["id"]))
        self.order = {e["id"]: i for i, e in enumerate(episodes)}  # oldest first, which wins a tie
        self.by_key: dict[str, list[int]] = {}
        self.words: dict[int, frozenset[str]] = {}
        titles: dict[int, frozenset[str]] = {}
        df: dict[str, int] = {}
        for e in episodes:
            if key := _key(e["title"]):
                self.by_key.setdefault(key, []).append(e["id"])
            titles[e["id"]] = _words(e["title"])
            # The video's file name counts too: ...\ep07_snowball_doubling.mp4 -> snowball doubling.
            self.words[e["id"]] = titles[e["id"]] | (_words(Path(e["video"]).stem) if e["video"] else frozenset())
            for w in self.words[e["id"]]:
                df[w] = df.get(w, 0) + 1
        n = len(episodes)
        self.idf = {w: math.log(n / k) for w, k in df.items()}
        self.unseen = math.log(n + 2)  # a word no episode has, which only counts when comparing posts
        self.whole = {eid: self.weight(t) or self.weight(self.words[eid]) for eid, t in titles.items()}
        # A rare word lists the episodes that have it, a common one those that don't. A caption only touches a few
        # lists, and an episode it doesn't touch has just the caption's common words.
        self.having: dict[str, list[int]] = {w: [] for w, k in df.items() if k <= n / 2}
        self.lacking: dict[str, list[int]] = {w: [] for w, k in df.items() if n / 2 < k < n}
        for eid, words in self.words.items():
            for w in words:
                if w in self.having:
                    self.having[w].append(eid)
            for w, lacking in self.lacking.items():
                if w not in words:
                    lacking.append(eid)
        self.lightest = sorted((e for e in self.whole if self.whole[e]), key=lambda e: (self.whole[e], self.order[e]))

    def weight(self, words: frozenset[str]) -> float:
        return sum(self.idf.get(w, self.unseen) for w in sorted(words))  # sorted: the same sum on every run

    def score(self, words: frozenset[str], eid: int) -> float:
        """The share of an episode's title weight found among a caption's words."""
        whole = self.whole.get(eid)
        return round(min(1.0, self.weight(words & self.words[eid]) / whole), 6) if whole else 0.0

    def top(self, words: frozenset[str]) -> tuple[float, int | None, float]:
        """A caption's best score, the episode it's for, and the next best score."""
        words = sorted(words)
        base = sum(self.idf[w] for w in words if w in self.lacking)
        extra: dict[int, float] = {}
        for w in words:
            for eid in self.having.get(w, ()):
                extra[eid] = extra.get(eid, 0.0) + self.idf[w]
            for eid in self.lacking.get(w, ()):
                extra[eid] = extra.get(eid, 0.0) - self.idf[w]
        untouched = (e for e in self.lightest if e not in extra)  # of these, the lightest titles score best
        extra.update((eid, 0.0) for eid, _ in zip(untouched, range(2)))
        best = second = 0.0
        best_id = None
        for eid, x in extra.items():
            score = (base + x) / self.whole[eid] if self.whole[eid] else 0.0
            if score > best:
                best, second, best_id = score, best, eid
            elif score > second:
                second = score
        return round(min(best, 1.0), 6), best_id, round(min(second, 1.0), 6)

    def match(self, key: str, words: frozenset[str]) -> tuple[list[int], float]:
        """The episodes a caption names: each one with its first line (oldest first), else the one its words clearly
        point to, if any. Also the best score."""
        if key in self.by_key:
            return self.by_key[key], 1.0
        best, eid, second = self.top(words)
        return ([eid] if best >= MATCH_SCORE and round(best - second, 6) >= MATCH_MARGIN else []), best

    def alike(self, a: frozenset[str], b: frozenset[str]) -> float:
        """How alike two captions are by weighted words: 1 when they have the same distinctive words."""
        union = self.weight(a | b)
        return round(self.weight(a & b) / union, 6) if union else 0.0


def caption_matches(posts: list, episodes: list) -> dict[tuple[str, str], list[int]]:
    """(platform, post_id) -> the episodes each post's caption names; db checks older links against it."""
    m = _Matcher([dict(e) for e in episodes])
    return {(p["platform"], p["post_id"]): m.match(_key(p["title"]), _words(p["title"]))[0] for p in posts}


def _upload_pick(at: datetime | None, opened: list[tuple]) -> str | None:
    """File name of the video whose upload page was opened on the post's platform up to 6 hours before it went up
    (the last one); one opened up to 30 minutes after (clock skew) counts only when none came before.
    opened: (when, upload id, file name), oldest first."""
    if at is None:
        return None
    i = bisect_left(opened, (at - timedelta(hours=6),))
    near = []
    while i < len(opened) and opened[i][0] <= at + timedelta(minutes=30):
        near.append(opened[i])
        i += 1
    before = [u for u in near if u[0] <= at]
    return (before[-1] if before else near[0])[2] if near else None


def _place(posts: list[dict], episodes: list[dict], links: dict) -> tuple[dict, list[dict]]:
    """One pass of auto_link: each post's (episode_id, link), and the new episodes twins would get."""
    m = _Matcher(episodes)
    files: dict[str, list[int]] = {}
    for e in sorted(episodes, key=lambda e: m.order[e["id"]]):
        if e["video"]:
            files.setdefault(Path(e["video"]).name.lower(), []).append(e["id"])
    placed = dict(links)
    taken = {(eid, ref[0]) for ref, (eid, how) in links.items() if how in FIXED_LINKS and eid is not None}
    claims, named = [], set()
    for p in posts:
        ref = p["ref"]
        current, how = links[ref]
        if how in FIXED_LINKS:
            continue
        placed[ref] = (None, None)
        found, best = m.match(p["key"], p["words"])
        if found:
            named.add(ref)
            claims += [(4 if p["key"] in m.by_key else 3, best, eid, p) for eid in found]
        elif current is not None:
            kept = m.score(p["words"], current)
            if kept >= KEEP_SCORE and kept >= best - MATCH_MARGIN:  # no clear answer, and it still fits where it is
                claims.append((2, kept, current, p))
        claims += [(1, 0.0, eid, p) for eid in files.get(p["upload"], ())]
    # One post per platform per episode, strongest claim first. On a tie the post already there keeps it (and a post
    # stays in the episode it is in), then the one posted first, then the older episode.
    claims.sort(key=lambda c: (-c[0], -round(c[1], 6), c[2] != links[c[3]["ref"]][0], c[3]["published_at"] or "",
                               c[3]["ref"], m.order[c[2]]))
    for tier, _, eid, p in claims:
        ref = p["ref"]
        if placed[ref][0] is None and (eid, ref[0]) not in taken:
            taken.add((eid, ref[0]))
            current, how = links[ref]
            placed[ref] = (eid, how if eid == current and how else "upload" if tier == 1 else "caption")
    # Posts on 2+ platforms within 72 hours that match each other but name no episode get a new one.
    pool = sorted((p for p in posts if placed[p["ref"]] == (None, None) and p["ref"] not in named
                   and p["words"] and p["at"]), key=lambda p: (p["at"], p["ref"]))
    times = [p["at"] for p in pool]
    twins, next_id = [], min([0, *m.order]) - 1
    for p in pool:
        if placed[p["ref"]][0] is not None:
            continue
        group = {p["platform"]: p}
        i = bisect_left(times, p["at"] - timedelta(hours=72))
        while i < len(pool) and times[i] <= p["at"] + timedelta(hours=72):
            q = pool[i]
            if q["platform"] not in group and placed[q["ref"]][0] is None \
                    and m.alike(p["words"], q["words"]) >= TWIN_SCORE:
                group[q["platform"]] = q
            i += 1
        if len(group) > 1:
            first = p["title"].strip().split("\n")[0]
            title = " ".join(re.sub(r"https?://\S+|#\w+", " ", first).split()) or first  # the caption, no hashtags
            twins.append({"id": next_id, "title": title[:120], "video": None, "created_at": p["published_at"]})
            for q in group.values():
                placed[q["ref"]] = (next_id, "twin")
            next_id -= 1
    return placed, twins


def auto_link() -> int:
    """File posts under episodes: by caption, else by the upload page opened just before, else as twins.

    Every post not linked by hand (or by ReelForge when it posted) is checked again on each run, so fixes reach old
    mistakes
    too, and an episode gets at most one post per platform. Returns how many posts changed episode.
    """
    opened: dict[str, list[tuple]] = {}
    for u in db.uploads(None):
        if u["status"] in ("ok", "manual") and u["video"]:
            opened.setdefault(u["platform"], []).append((db.parse(u["ts"]), u["id"], Path(u["video"]).name.lower()))
    for rows in opened.values():
        rows.sort()
    posts = []
    for row in db.all_posts():
        at, title = db.parse(row["published_at"]) if row["published_at"] else None, row["title"]
        posts.append(dict(row, ref=(row["platform"], row["post_id"]), key=_key(title), words=_words(title), at=at,
                          upload=_upload_pick(at, opened.get(row["platform"], []))))
    was = {p["ref"]: (p["episode_id"], p["link"]) for p in posts}
    episodes, links, made = [dict(e) for e in db.episodes()], was, []
    for _ in range(5):  # an episode made for twins is matched by caption on the next pass
        links, twins = _place(posts, episodes + made, links)
        made += twins
        if not twins:
            break
    changes = [(*ref, *was[ref], *links[ref]) for ref in links if links[ref] != was[ref]]
    return db.relink(changes, {e["id"]: (e["title"], e["created_at"]) for e in made})


# --- formatting ---------------------------------------------------------------------------

def fmt_num(n: float | None) -> str:
    if n is None:
        return "—"
    a = abs(n)
    if a >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if a >= 10_000:
        return f"{n / 1_000:.1f}K"
    if a >= 1_000:
        return f"{n / 1_000:.2f}K"
    return f"{n:.0f}"


def fmt_delta(n: float | None) -> str:
    if n is None:
        return ""
    return ("+" if n >= 0 else "−") + fmt_num(abs(n))


def fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def fmt_age(hours: float) -> str:
    if hours < 1:
        return f"{hours * 60:.0f}m"
    if hours < 48:
        return f"{hours:.0f}h"
    return f"{hours / 24:.0f}d"


def fmt_clock(t: datetime) -> str:
    """12-hour time: 2:05 PM."""
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def fmt_ago(ts: str | None) -> str:
    if not ts:
        return "never"
    return fmt_age((now() - db.parse(ts)).total_seconds() / 3600) + " ago"
