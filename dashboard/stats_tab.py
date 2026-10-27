"""The Stats tab (8): your followers and your likes added up across the platforms you count, over time.

Each platform reports its own running total, read on every refresh. The tab adds them up at each moment of its time
axis where ReelForge was reading (level_at: between two readings close together, the straight line joining them;
past the newest one, the newest while it's recent). A platform whose reads stopped meanwhile (a log-in ran out, say)
counts with its last reading, as on the Overview's tiles; a gap in every platform's readings (the computer was off)
leaves the total out for that stretch rather than drawing a line across it. There's no total from before a counted
platform's first reading: leave that platform out to see further back. Followers are taken as read, so unfollows
show; likes are held at their highest reading, as on the other charts (trends.points).

A mixin of the window's service (dashboard/service.py): the tab calls these, and "totals" is the view it draws. The
tab's id is "totals" because `reelforge stats` is the hourly job's command; `reelforge 8` or `reelforge totals`
opens it.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from datetime import datetime, time, timedelta, timezone

from studio.bridge import rpc

from . import db, trends
from .analytics import fmt_age, fmt_clock
from .view import BAD, GOOD, MUTED, SHORT, Text, act, chip, parts

METRICS = ("followers", "likes")
# The ranges at the top right: (label, span, bucket). All runs from the first moment there's a total.
RANGES = {
    "24h": ("24H", timedelta(hours=24), timedelta(hours=1)),
    "48h": ("48H", timedelta(hours=48), timedelta(hours=1)),
    "7d": ("7D", timedelta(days=7), timedelta(hours=1)),
    "30d": ("30D", timedelta(days=30), timedelta(hours=6)),
    "all": ("ALL", None, None),
}
ALL_STEPS = [timedelta(hours=h) for h in (1, 2, 3, 6, 12)] + [timedelta(days=d) for d in (1, 2, 7)]
MOST_SLOTS = 180  # All's buckets: the finest that keep it to this many
STALE = timedelta(hours=3)  # a platform not read for this long says when it last was, in its breakdown
LATE = timedelta(hours=12)  # a counted platform whose readings start this much after the others' gets a note
TOTAL = "#e8eaed"  # the total's colour: the window's own white, as on the All platforms tile
# How far apart db.compact leaves old account readings: the newest of each 3 hours once they're 14 days old, of each
# day after 26 days and of each week after 72. Readings two of those blocks apart are thinned history, not a gap.
THINNED = ((timedelta(days=72), timedelta(weeks=1)), (timedelta(days=26), timedelta(days=1)),
           (timedelta(days=14), timedelta(hours=3)))


def spaced(t0: datetime, step: timedelta, now: datetime) -> timedelta:
    """How long after a reading at t0 the next one can come before the stretch between them is a gap: trends.GAP, a
    bucket, or two of thinned history's blocks at t0's age, whichever is longest."""
    age = now - t0
    thin = next((2 * block for older, block in THINNED if age >= older), timedelta(0))
    return max(trends.GAP, step, thin)


def level_at(pts: trends.Points, t: datetime, step: timedelta, now: datetime) -> float | None:
    """A platform's running total at moment t, from its readings (oldest first): between two readings close enough
    together (spaced), the straight line joining them; at or after the newest, the newest while it's recent. None
    before the first reading, and in a gap."""
    if not pts or t < pts[0][0]:
        return None
    i = bisect_right(pts, t, key=lambda p: p[0])
    t0, v0 = pts[i - 1]
    if t == t0:  # a reading right then (the last one before a gap, say)
        return v0
    if i == len(pts):
        return v0 if t - t0 <= spaced(t0, step, now) else None
    t1, v1 = pts[i]
    if t1 - t0 > spaced(t0, step, now):
        return None
    return v0 + (v1 - v0) * ((t - t0) / (t1 - t0))


def last_at(pts: trends.Points, t: datetime) -> float | None:
    """A platform's last reading at or before moment t (None before its first)."""
    i = bisect_right(pts, t, key=lambda p: p[0])
    return pts[i - 1][1] if i else None


def gap_edges(pts: trends.Points, start: datetime, end: datetime, step: timedelta, now: datetime) -> list[datetime]:
    """The readings either side of each gap between start and end, so a total runs right up to a gap's edge."""
    out = []
    first = max(bisect_right(pts, start, key=lambda p: p[0]) - 1, 0)
    for (t0, _), (t1, _) in zip(pts[first:], pts[first + 1:]):
        if t0 >= end:
            break
        if t1 - t0 > spaced(t0, step, now):
            out += [t for t in (t0, t1) if start < t < end]
    return out


def frame_for(key: str, first: datetime | None, now: datetime | None = None) -> trends.Frame:
    """A range's time axis: its span in its own buckets; for All, from `first` (the first moment there's a total) to
    now, in the finest buckets that keep it to MOST_SLOTS."""
    _, span, step = RANGES[key]
    now = (now or datetime.now(timezone.utc)).astimezone()
    if span is not None:
        return trends.frame_span(span, step, now)
    first = first or now
    age = max(now - first, timedelta(hours=1))
    step = next((s for s in ALL_STEPS if age / s < MOST_SLOTS), ALL_STEPS[-1])
    n = max(math.ceil(age / step), 1)
    fr = trends.frame_span(step * n, step, now)
    while fr.starts[0] > first:  # the buckets end with the one now is in: one more, so the first reading is in one
        n += 1
        fr = trends.frame_span(step * n, step, now)
    return fr


def place(fr: trends.Frame, t: datetime) -> float:
    """Where a moment sits on the time axis, in buckets (bucket i runs from i to i + 1)."""
    i = fr.index(t)
    if i is None:
        return 0.0 if t < fr.starts[0] else float(fr.n)
    return i + (t - fr.starts[i]) / (fr.ends[i] - fr.starts[i])


def when(t: datetime, now: datetime) -> str:
    """A moment after a number: at 8 PM, at 8 PM Tue, on Oct 24."""
    t, now = t.astimezone(), now.astimezone()
    clock = fmt_clock(t).replace(":00", "")
    if t.date() == now.date():
        return f"at {clock}"
    if now - t < timedelta(days=6):
        return f"at {clock} {t:%a}"
    return f"on {t:%b} {t.day}"


def since(t: datetime, now: datetime) -> str:
    """Since a moment: since 9 AM, since Tue 9 AM, since Oct 22."""
    t, now = t.astimezone(), now.astimezone()
    clock = fmt_clock(t).replace(":00", "")
    if t.date() == now.date():
        return f"since {clock}"
    if now - t < timedelta(days=2):
        return f"since {t:%a} {clock}"
    return f"since {t:%b} {t.day}"


def exact(n: float | None) -> str:
    """A count in full, the way the Stats tab shows them: 21,034."""
    return "—" if n is None else f"{round(n):,}"


def signed(n: float | None) -> str:
    """+1,203 or −40 (or nothing)."""
    if n is None:
        return ""
    n = round(n)
    return f"{'+' if n >= 0 else '−'}{abs(n):,}"


class Totals:
    """One metric added up over a frame: the moments it's drawn through (each bucket's start, the first moment
    there's a total, either side of each gap, and now), where each one sits on the axis, every platform's reading
    then (its last one while it wasn't being read) and the counted platforms' added up: None where none of them was
    being read, or one hadn't been read yet."""

    def __init__(self, pts: dict[str, trends.Points], counted: list[str], fr: trends.Frame):
        self.fr, self.pts, self.counted = fr, pts, counted
        self.now = now = fr.now.astimezone(timezone.utc)
        start = fr.starts[0]
        firsts = [pts[k][0][0] for k in counted if pts.get(k)]
        # The first moment every counted platform has a reading (None: one of them has none at all).
        self.first = max(firsts) if counted and len(firsts) == len(counted) else None
        moments = {*fr.starts, fr.now}
        if self.first is not None and start < self.first < fr.now:
            moments.add(self.first)
        for k in counted:
            moments.update(gap_edges(pts.get(k, []), start, fr.now, fr.step, now))
        self.moments = sorted(moments)
        self.xs = [place(fr, t) for t in self.moments]
        self.each = {k: [self.reading(k, t) for t in self.moments] for k in pts}
        self.total = [self.at(t) for t in self.moments]
        self.known = [j for j, v in enumerate(self.total) if v is not None]
        self.index = {t: j for j, t in enumerate(self.moments)}

    def reading(self, key: str, t: datetime) -> float | None:
        """A platform's number at moment t: as read (level_at), or while it wasn't being read, its last reading."""
        pts = self.pts.get(key, [])
        v = level_at(pts, t, self.fr.step, self.now)
        return last_at(pts, t) if v is None else v

    def at(self, t: datetime) -> float | None:
        """The total at any moment: None in a gap in every counted platform's readings, or before one's first."""
        pts = [self.pts.get(k, []) for k in self.counted]
        if not any(level_at(p, t, self.fr.step, self.now) is not None for p in pts):
            return None
        vals = [self.reading(k, t) for k in self.counted]
        return sum(vals) if all(v is not None for v in vals) else None

    def runs(self) -> list[list[int]]:
        """The moments with a total, in unbroken runs (a gap between them)."""
        out: list[list[int]] = []
        for j in self.known:
            if out and out[-1][-1] == j - 1:
                out[-1].append(j)
            else:
                out.append([j])
        return out

    def slots(self) -> list[dict | None]:
        """Each bucket for the hover read-out: the total at its last moment with one (its end, or now), what it gained
        in the bucket and each counted platform's reading then; None for a bucket with no total."""
        last: dict[int, int] = {}
        for j in self.known:
            last[max(math.ceil(self.xs[j]) - 1, 0)] = j
        out: list[dict | None] = []
        for i in range(self.fr.n):
            j = last.get(i)
            if j is None:
                out.append(None)
                continue
            b = self.index.get(self.fr.starts[i])
            begin = self.total[b] if b is not None and b != j else None
            out.append({"total": self.total[j], "gain": None if begin is None else self.total[j] - begin,
                        "each": {k: self.each[k][j] for k in self.counted}})
        return out

    def gains(self, key: str) -> list[float | None]:
        """What one platform gained in each bucket (its reading at the bucket's end, or now, less at its start)."""
        vals = self.each[key]
        bounds = [self.index[t] for t in self.fr.starts] + [self.index[self.fr.now]]
        out: list[float | None] = []
        for a, b in zip(bounds, bounds[1:]):
            out.append(vals[b] - vals[a] if vals[a] is not None and vals[b] is not None else None)
        return out


class StatsTab:
    """The Stats tab's half of the window's service."""

    totals_range = "all"
    left_out: frozenset[str] = frozenset()  # platforms you've left out of the totals (ticked off at the top)
    totals_frame: trends.Frame | None = None

    def load_totals_choices(self) -> None:
        """The range and the platforms left out, as you left them (each profile keeps its own)."""
        saved = db.get_meta("totals_range", "all")
        self.totals_range = saved if saved in RANGES else "all"
        out = db.get_meta("totals_left_out", [])
        self.left_out = frozenset(k for k in out if isinstance(k, str)) if isinstance(out, list) else frozenset()

    @rpc
    def set_totals_range(self, key: str) -> None:
        if key in RANGES and key != self.totals_range:
            self.totals_range = key
            self.update_totals()
            self._save_totals("totals_range", key)

    @rpc
    def count_platform(self, key: str) -> None:
        """Tick or untick a platform at the top: in the totals, or left out of them."""
        if key not in self.platforms:
            return
        self.left_out = self.left_out ^ {key}
        self.update_totals()
        self._save_totals("totals_left_out", sorted(self.left_out))

    def _save_totals(self, key: str, value) -> None:
        try:
            db.set_meta(key, value)
        except Exception:  # a busy database: the choice holds in this window, and saves next time
            pass

    def update_totals(self) -> None:
        """The tab's view: the platforms you can count, the ranges, and the followers and likes charts."""
        now = datetime.now(timezone.utc)
        history = getattr(self, "account_history", {})
        ranges = Text()
        for key, (label, _, _) in RANGES.items():
            ranges.append_text(chip(label, act("set_totals_range", key), key == self.totals_range))
            ranges.append(" ")
        toggles = []
        for p in self.platforms.values():
            rows = history.get(p.key, [])
            has = any(r[m] is not None for r in rows for m in METRICS)
            toggles.append({"key": p.key, "name": p.name, "short": SHORT.get(p.key, p.key), "color": p.color,
                            "counted": p.key not in self.left_out, "has": has})
        metrics = {m: self.totals_metric(m, history, now) for m in METRICS}
        self.emit("totals", {"range": self.totals_range, "ranges": ranges.json(), "toggles": toggles,
                             "metrics": metrics})

    def totals_metric(self, metric: str, history: dict, now: datetime) -> dict:
        """One chart and its breakdown: the counted platforms added up over the range, as filled runs (broken at
        gaps), the hover read-out for each bucket, marks where videos went up, the numbers over the chart, and every
        platform's number now, gain in the range and share."""
        from .service import NOTHING_CONNECTED, slot_info

        hold = metric != "followers"  # unfollows show; a dip in likes is held, as on the other charts
        pts = {k: trends.points(history.get(k, []), metric, hold) for k in self.platforms}
        counted = [k for k in self.platforms if k not in self.left_out and pts[k]]
        name = metric.upper()
        if not self.platforms:
            return {"name": name, "empty": NOTHING_CONNECTED}
        if not counted:
            empty = ("Every platform is left out of the totals: tick one above to add it up." if
                     all(k in self.left_out for k in self.platforms) else
                     f"No {metric} read yet: they show up here after the next refresh.")
            return {"name": name, "empty": empty, **self.totals_rows(pts, None)}
        first = max(pts[k][0][0] for k in counted)
        fr = frame_for(self.totals_range, first, now)
        self.totals_frame = fr
        t = Totals(pts, counted, fr)
        out = {"name": name, "n": fr.n, "step_h": fr.step.total_seconds() / 3600, "slots": slot_info(fr),
               **self.totals_rows(pts, t)}
        if len(t.known) < 2:
            out["empty"] = ("Not enough readings yet: ReelForge reads your stats on every refresh, so this fills in "
                            "as it runs." if self.totals_range == "all" else
                            f"Not enough readings in the last {_span_words(self.totals_range)}: pick a longer range.")
            return out
        out["series"] = [{"key": "total", "name": "added up", "color": TOTAL, "xs": [t.xs[j] for j in run],
                          "ys": [t.total[j] for j in run], "style": "area"} for run in t.runs()]
        out["hover"] = t.slots()
        out["marks"] = [{"x": x, "label": label} for x, label in self.post_marks(fr)]
        out["title"] = self.totals_title(name, t, pts)
        out["note"] = self.totals_note(t, pts)
        return out

    def totals_title(self, name: str, t: Totals, pts: dict) -> list:
        """The numbers over a chart: the total now, what it gained over the range, a day (or an hour) on average, vs
        the same time before, and the best day (or hour)."""
        fr, a, b = t.fr, t.known[0], t.known[-1]
        latest = sum(pts[k][-1][1] for k in t.counted)  # the newest readings, as the Overview's tiles add them up
        items = [(Text(f"{name}  ", "bold"), 0), (Text.assemble((exact(latest), "bold"), (" total   ", MUTED)), 0)]
        gained = t.total[b] - t.total[a]
        start = t.moments[a]
        span = (f"in {RANGES[self.totals_range][0].lower()}" if self.totals_range != "all" and start == fr.starts[0]
                else since(start, t.now))
        items.append((Text.assemble((signed(gained), GOOD if gained >= 0 else BAD), (f" {span}   ", MUTED)), 1))
        hours = (t.moments[b] - start).total_seconds() / 3600
        if hours >= 1:
            daily = hours > 48
            pace = gained / hours * (24 if daily else 1)
            items.append((Text(f"{signed(pace)} {'a day' if daily else 'an hour'}   ", MUTED), 2))
        if self.totals_range != "all" and start == fr.starts[0]:
            before = t.at(start - (fr.now - start))
            if before is not None and t.total[a] - before > 0:
                change = gained / (t.total[a] - before) - 1
                up = change >= 0
                items.append((Text(f"{'▲' if up else '▼'} {abs(change) * 100:.0f}% vs the "
                                   f"{RANGES[self.totals_range][0].lower()} before   ", GOOD if up else BAD), 3))
        best = self.totals_best(t, hours > 48)
        if best:
            items.append((Text(best, MUTED), 4))
        return parts(items)

    def totals_best(self, t: Totals, daily: bool) -> str | None:
        """The day (or, on a range of two days or less, the hour) that added the most, while there are two to
        compare."""
        a, b = t.moments[t.known[0]], t.moments[t.known[-1]]
        if daily:
            local = a.astimezone()
            day = datetime.combine(local.date() + timedelta(days=1), time()).astimezone()
            cuts = [a]
            while day < b:
                cuts.append(day)
                day = datetime.combine(day.date() + timedelta(days=1), time()).astimezone()
            cuts.append(b)
            # Whole days only, and today so far: the first part-day isn't a day.
            spans = [(cuts[i], cuts[i + 1]) for i in range(1 if len(cuts) > 2 else 0, len(cuts) - 1)]
            found = []
            for s, e in spans:
                v0, v1 = t.at(s), t.at(e)
                if v0 is not None and v1 is not None:
                    found.append((v1 - v0, s))
            if len(found) < 2:
                return None
            gain, s = max(found, key=lambda f: (f[0], f[1]))
            if gain <= 0:
                return None
            today = t.now.astimezone().date()
            which = ("today" if s.astimezone().date() == today else
                     "yesterday" if s.astimezone().date() == today - timedelta(days=1) else
                     f"on {s.astimezone():%b} {s.astimezone().day}")
            return f"best day {signed(gain)} {which}"
        if not t.fr.hourly:
            return None
        found = [(h["gain"], i) for i, h in enumerate(t.slots()) if h and h["gain"] is not None]
        if len(found) < 2:
            return None
        gain, i = max(found, key=lambda f: (f[0], f[1]))
        return f"best hour {signed(gain)} {when(t.fr.starts[i], t.now)}" if gain > 0 else None

    def totals_note(self, t: Totals, pts: dict) -> list | None:
        """While a counted platform's readings start well after the others' (LATE, or three buckets), the totals start
        with it: say so, and how to see further back."""
        if t.first is None or len(t.counted) < 2:
            return None
        late = [k for k in t.counted if pts[k][0][0] == t.first]
        earliest = min(pts[k][0][0] for k in t.counted)
        if t.first - earliest < max(LATE, 3 * t.fr.step) or t.first <= t.fr.starts[0] and self.totals_range != "all":
            return None
        names = [self.platforms[k].name for k in late]
        whose = " and ".join(f"{n}'s" for n in names) + (" first reading" if len(names) == 1 else " first readings")
        return Text.assemble((f"The totals start {_moment(t.first, t.now)}, with {whose}: leave ", MUTED),
                             (" and ".join(names), "bold"), (" out to see further back.", MUTED)).json()

    def totals_rows(self, pts: dict, t: Totals | None) -> dict:
        """The breakdown beside a chart: every connected platform's number now, what it gained over the chart's span
        (the counted ones over the same stretch as the total, so they add up to it), its share of the total, its gains
        bucket by bucket and, once it hasn't been read for a while, when it last was; and the counted platforms added
        up."""
        rows = []
        counted = t.counted if t else []
        latest = {k: p[-1][1] for k, p in pts.items() if p}
        whole = sum(latest[k] for k in counted) if counted else None
        a, b = (t.known[0], t.known[-1]) if t and len(t.known) >= 2 else (None, None)
        for key, p in self.platforms.items():
            row = {"key": key, "name": p.name, "short": SHORT.get(key, key), "color": p.color,
                   "counted": key in counted, "left_out": key in self.left_out, "value": latest.get(key),
                   "gained": None, "share": None, "gains": [], "stale": None}
            if pts.get(key) and t is not None and t.now - pts[key][-1][0] >= STALE:
                row["stale"] = f"last read {fmt_age((t.now - pts[key][-1][0]).total_seconds() / 3600)} ago"
            if t is not None:
                vals = t.each.get(key, [])
                if key in counted and a is not None:
                    row["gained"] = vals[b] - vals[a]
                else:  # over the range, from its first reading in it to its last
                    known = [v for v in vals if v is not None]
                    row["gained"] = known[-1] - known[0] if len(known) >= 2 else None
                row["gains"] = t.gains(key)
            if key in counted and whole:
                row["share"] = latest[key] / whole
            rows.append(row)
        gained = t.total[b] - t.total[a] if a is not None else None
        return {"rows": rows, "total": {"value": whole, "gained": gained}}


def _span_words(key: str) -> str:
    return {"24h": "24 hours", "48h": "48 hours", "7d": "7 days", "30d": "30 days"}.get(key, key)


def _moment(t: datetime, now: datetime) -> str:
    """When the totals start: today at 9 AM, Tue 9 AM, Oct 22 9 AM."""
    t, now = t.astimezone(), now.astimezone()
    clock = fmt_clock(t).replace(":00", "")
    if t.date() == now.date():
        return f"today at {clock}"
    if now - t < timedelta(days=6):
        return f"{t:%a} {clock}"
    return f"{t:%b} {t.day} {clock}"
