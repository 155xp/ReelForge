"""Snapshots turned into what the charts show: gains per hour (or day), running totals and the numbers on top.

Platforms report lifetime totals, so a gain is the difference between two readings. Bars show only what was
measured: readings taken close together share their rise between the hours they span. Nothing is made up for a gap
(the computer was off): its hours stay empty, and what was gained meanwhile counts in the totals and the numbers over
the chart, not as a bar. With the hourly background job (reelforge stats on) gaps only happen while the computer is
off. A total that dips (YouTube's sum of visible videos sometimes does) is held at its highest reading, so a dip and
recovery isn't counted twice.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

from . import analytics, db

# Range chips on the Overview: (label, span, bucket)
RANGES = {
    "24h": ("24H", timedelta(hours=24), timedelta(hours=1)),
    "48h": ("48H", timedelta(hours=48), timedelta(hours=1)),
    "7d": ("7D", timedelta(days=7), timedelta(hours=6)),
    "30d": ("30D", timedelta(days=30), timedelta(days=1)),
}
# Bucket sizes a chart falls back to when it's too narrow for a bar per bucket (every bar needs a column and a
# one-column gap): the range's own size first, then neighbouring buckets combined, coarsest last.
FIT_STEPS = {
    "24h": [timedelta(hours=h) for h in (1, 2, 3, 4, 6, 8, 12)],
    "48h": [timedelta(hours=h) for h in (1, 2, 3, 4, 6, 8, 12, 24)],
    "7d": [timedelta(hours=h) for h in (6, 12, 24)],
    "30d": [timedelta(days=d) for d in (1, 2, 3, 5, 6, 10)],
}
# Readings further apart than this (or than one bucket, whichever is longer) leave a gap: no bar is drawn for it.
GAP = timedelta(minutes=95)
STALE = timedelta(hours=2)  # a platform not read for this long doesn't count towards "now X/h"

Points = list[tuple[datetime, float]]  # (UTC time, running highest value), oldest first


@dataclass
class Frame:
    """The time axis: buckets that end with the one now is in (which is still filling up)."""

    starts: list[datetime]  # bucket starts, local time, oldest first
    ends: list[datetime]
    now: datetime  # local time
    step: timedelta  # the nominal bucket size (a 6-hour or daily bucket can run an hour long or short over DST)

    @property
    def n(self) -> int:
        return len(self.starts)

    @property
    def hourly(self) -> bool:
        return self.step <= timedelta(hours=1)

    @property
    def daily(self) -> bool:
        return self.step >= timedelta(days=1)

    def unit(self) -> str:
        """What one bucket is, for labels: "h", "6h", "day" or "2 days"."""
        if self.daily:
            days = round(self.step / timedelta(days=1))
            return "day" if days == 1 else f"{days} days"
        hours = round(self.step.total_seconds() / 3600)
        return "h" if hours == 1 else f"{hours}h"

    def index(self, t: datetime) -> int | None:
        """The bucket a moment falls in, or None if it's outside the frame."""
        i = bisect_right(self.starts, t) - 1
        return i if 0 <= i < self.n and t < self.ends[i] else None


def frame(key: str, now: datetime | None = None) -> Frame:
    _, span, step = RANGES[key]
    return frame_span(span, step, now)


def frame_since(start: datetime, now: datetime | None = None) -> Frame:
    """A frame that covers `start` to now: hours for under 2 days of history, 6 hours under 2 weeks, else days."""
    now = now or analytics.now()
    age = max(now - start, timedelta(0))
    step = timedelta(hours=1) if age < timedelta(days=2) else timedelta(hours=6) if age < timedelta(days=14) \
        else timedelta(days=1)
    # One bucket more than the age needs, since the first and last buckets are partial.
    return frame_span(step * max(math.ceil(age / step) + 1, 2), step, now)


def frame_fit(key: str, columns: int, now: datetime | None = None) -> Frame:
    """The range's frame with buckets wide enough for its bars in `columns` columns: the finest bucket size that
    gives every bar two columns and a gap, or failing that one column and a gap (thin bars with gaps of one or two
    columns look ragged), combining 2, 3, 4 ... of the range's own buckets into one. Combined buckets start at round
    times, so the first one starts at or before the range's own first bucket: nothing in the range is left out."""
    _, span, own = RANGES[key]
    first = frame_span(span, own, now).starts[0]
    frames = []
    for step in FIT_STEPS[key]:
        fr = frame_span(span + step, step, now)
        keep = next(i for i in range(fr.n) if fr.ends[i] > first)
        frames.append(Frame(fr.starts[keep:], fr.ends[keep:], fr.now, step))
    return next((fr for per in (3, 2) for fr in frames if fr.n * per <= columns), frames[-1])


def frame_span(span: timedelta, step: timedelta, now: datetime | None = None) -> Frame:
    now = (now or analytics.now()).astimezone()
    n = max(round(span / step), 1)
    if step >= timedelta(days=1):
        # Whole local days, built from dates so each midnight gets its own daylight-saving offset. Buckets of k days
        # end with the one that holds today.
        k = max(round(step / timedelta(days=1)), 1)
        today = now.date()
        days = [today + timedelta(days=1 - k * (n - j)) for j in range(n + 1)]
        bounds = [datetime.combine(d, time()).astimezone() for d in days]
    elif step == timedelta(hours=1):
        # Hours are counted on the UTC clock, so a daylight-saving change never makes a 2-hour or 0-hour bucket.
        cur = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        bounds = [(cur - step * (n - 1 - i)).astimezone() for i in range(n + 1)]
    else:
        # Longer buckets start at round local hours (12, 6, 12, 6 for 6 hours), counted on the wall clock so they
        # stay put across a daylight-saving change (the bucket the change falls in runs an hour long or short).
        hours = round(step.total_seconds() / 3600)
        wall = now.replace(tzinfo=None, minute=0, second=0, microsecond=0)
        wall -= timedelta(hours=wall.hour % hours)
        bounds = [(wall - step * (n - 1 - i)).astimezone() for i in range(n + 1)]
    return Frame(bounds[:-1], bounds[1:], now, step)


def points(rows, field: str, hold: bool = True) -> Points:
    """Account rows (oldest first) -> readings of one field, each held at the highest value so far
    (hold=False: as read, so a drop such as unfollows shows)."""
    out: Points = []
    top = None
    for r in rows:
        v = r[field]
        if v is None:
            continue
        top = v if top is None or not hold else max(top, v)
        out.append((db.parse(r["ts"]), float(top)))
    return out


def _time(p: tuple[datetime, float]) -> datetime:
    return p[0]


def value_at(pts: Points, t: datetime) -> float | None:
    """The reading at a moment, joining readings with straight lines; None before the first one."""
    if not pts or t < pts[0][0]:
        return None
    if t >= pts[-1][0]:
        return pts[-1][1]
    i = bisect_right(pts, t, key=_time)
    (t0, v0), (t1, v1) = pts[i - 1], pts[i]
    return v0 + (v1 - v0) * ((t - t0) / (t1 - t0))


@dataclass
class Bucketed:
    """One platform's gains per bucket (None: nothing was measured in it) and its total at the bucket's end."""

    gains: list[float | None]
    gaps: list[bool]  # part of the bucket fell in a gap between readings, so its bar leaves something out
    totals: list[float | None]


def bucket(pts: Points, fr: Frame) -> Bucketed:
    """What the readings measured, bucket by bucket: readings close together share their rise between the buckets
    they span, by time. A gap is left out: its buckets stay empty, and what was gained during it shows in the totals
    and the numbers over the chart (Summary.gained), not as a bar."""
    n = fr.n
    gains: list[float | None] = [None] * n
    gaps = [False] * n
    longest = max(GAP, fr.step)  # 30-day buckets don't count once-a-day readings (old history is thinned) as gaps
    f0, f1 = fr.starts[0], fr.ends[-1]

    def add(i: int, amount: float) -> None:
        gains[i] = (gains[i] or 0.0) + amount

    first = max(bisect_right(pts, f0, key=_time) - 1, 0)  # the last reading before the frame starts
    for (t0, v0), (t1, v1) in zip(pts[first:], pts[first + 1:]):
        if t0 >= f1:
            break
        if t1 <= f0:
            continue
        span = (t1 - t0).total_seconds()
        if t1 - t0 > longest:
            i = fr.index(max(t0, f0))
            while i is not None and i < n and fr.starts[i] < t1:
                gaps[i] = True
                i += 1
            continue
        rise = max(v1 - v0, 0.0)
        if span == 0:  # two readings at the same moment
            if (i := fr.index(t1)) is not None:
                add(i, rise)
            continue
        i = fr.index(max(t0, f0))
        while i is not None and i < n and fr.starts[i] < t1:
            overlap = (min(fr.ends[i], t1) - max(fr.starts[i], t0)).total_seconds()
            if overlap > 0:
                add(i, rise * overlap / span)
            i += 1
    totals = [value_at(pts, min(fr.ends[i], pts[-1][0])) if gains[i] is not None else None for i in range(n)]
    return Bucketed(gains, gaps, totals)


@dataclass
class Summary:
    """The numbers over a chart: total now, gained in the range, the pace now, the best bucket, vs before."""

    latest: float | None = None
    gained: float | None = None
    previous: float | None = None  # gained over the same length of time just before the range, when known
    pace: float | None = None  # per hour over the last hour of readings
    best: float | None = None
    best_at: datetime | None = None
    per_bucket: list[float | None] = field(default_factory=list)

    @property
    def change(self) -> float | None:
        """Gained vs the time before, as a fraction (+0.18 = 18% more)."""
        if self.gained is None or not self.previous:
            return None
        return self.gained / self.previous - 1


def summarise(per_platform: dict[str, Points], fr: Frame) -> Summary:
    """Add up several platforms' readings into one Summary (each platform's own points, summed per bucket)."""
    buckets = {k: bucket(p, fr) for k, p in per_platform.items()}
    per_bucket: list[float | None] = []
    for i in range(fr.n):
        vals = [b.gains[i] for b in buckets.values() if b.gains[i] is not None]
        per_bucket.append(sum(vals) if vals else None)
    s = Summary(per_bucket=per_bucket)
    latest = [p[-1][1] for p in per_platform.values() if p]
    s.latest = sum(latest) if latest else None
    start = fr.starts[0].astimezone(timezone.utc)
    # Gained in the range is the change in the totals, so it counts the gaps the bars leave out.
    gained = [p[-1][1] - (value_at(p, start) if p[0][0] <= start else p[0][1])
              for p in per_platform.values() if p and p[-1][0] > start]
    s.gained = sum(gained) if gained else None
    known = [i for i in range(fr.n) if per_bucket[i] is not None]
    if known:
        best = max(known, key=lambda i: per_bucket[i])
        s.best, s.best_at = per_bucket[best], fr.starts[best]
    # The same length of time just before the range (the range so far: it ends now, not at the end of its last
    # bucket), counted only when every platform has readings from before it.
    before = start - (fr.now.astimezone(timezone.utc) - start)
    prev = []
    for p in per_platform.values():
        if not p:
            continue
        if p[0][0] > before + timedelta(hours=1):
            prev = None
            break
        a, b = value_at(p, before), value_at(p, start)
        a = p[0][1] if a is None else a
        prev.append((b if b is not None else a) - a)
    s.previous = sum(prev) if prev else None
    # Pace: the last hour of each platform's readings, per hour, from platforms read in the last couple of hours.
    pace = []
    now = fr.now.astimezone(timezone.utc)
    for p in per_platform.values():
        if len(p) < 2 or now - p[-1][0] > STALE:
            continue
        end = p[-1][0]
        a = value_at(p, end - timedelta(hours=1))
        if a is None:
            a, hours = p[0][1], max((end - p[0][0]).total_seconds() / 3600, 0.25)
        else:
            hours = 1.0
        pace.append((p[-1][1] - a) / hours)
    s.pace = sum(pace) if pace else None
    return s


def change(rows, field: str, hours: float, now: datetime | None = None, hold: bool | None = None) -> float | None:
    """How much an account field changed over the last `hours`: the latest reading minus the value at that
    moment (read between the readings either side of it). None without readings from both before and since then.
    Views and likes are held at their highest reading (as on the charts); followers can go down."""
    hold = field != "followers" if hold is None else hold
    readings = points(rows, field, hold)
    if len(readings) < 2:
        return None
    cut = (now or analytics.now()) - timedelta(hours=hours)
    if readings[0][0] > cut or readings[-1][0] <= cut:
        return None
    return readings[-1][1] - value_at(readings, cut)


def since_first(rows, field: str) -> float | None:
    """How much an account field changed since its first reading."""
    values = [r[field] for r in rows if r[field] is not None]
    return float(values[-1] - values[0]) if len(values) >= 2 else None


STOP = {"what", "if", "your", "the", "a", "an", "in", "of", "to", "every", "would", "happen", "you", "is", "was",
        "were", "and", "or", "my", "for", "on", "at", "it", "had", "has", "have", "got", "get", "be", "this", "that",
        "with", "how", "why", "when", "do", "does", "did", "i", "we", "our", "his", "her", "their"}


def short_title(title: str, others: list[str]) -> str:
    """The words that tell an episode apart: "What if your car's speed doubled every 2 seconds?" -> "car's speed"."""
    def words(t: str) -> list[str]:
        t = re.sub(r"https?://\S+|#\w+|@\w+", " ", t)
        return [w.strip("?!.,:;\"'()[]“”‘’") for w in t.split()]

    def stem(w: str) -> str:
        w = w.lower().removesuffix("'s").removesuffix("’s")
        return w[:-1] if len(w) > 3 and w.endswith("s") else w

    common: dict[str, int] = {}
    for t in others:
        for w in {stem(x) for x in words(t)}:
            common[w] = common.get(w, 0) + 1
    # Words most titles share are the series' template ("what if your ... doubled every second").
    shared = {w for w, n in common.items() if n >= max(2, len(others) * 0.4)}
    plain = [w for w in words(title) if w and w.lower() not in STOP and not w.isdigit()]
    keep = [w for w in plain if stem(w) not in shared]
    return " ".join((keep or plain or words(title))[:2])[:24]


def distinct_title(title: str, others: list[str]) -> str:
    """The title without the opening words most titles share, for a narrow column: among "What if your car's speed
    doubled every 2 seconds?", "What if your net worth doubled every second?" and so on, "Car's speed doubled every
    2 seconds?". Titles that don't share an opening stay whole."""
    words = title.split()
    starts = [t.lower().split() for t in others]
    n = 0
    while n < len(words) - 1:
        head = [w.lower() for w in words[:n + 1]]
        if sum(s[:n + 1] == head for s in starts) < max(2, 0.6 * len(starts)):
            break
        n += 1
    rest = " ".join(words[n:])
    return rest[:1].upper() + rest[1:] if n else title
