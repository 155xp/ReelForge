"""Best time to post: the part of the day each platform's videos have done best in, from your own numbers.

A video counts with its views in its first day (24 hours after it went up, from the readings either side of that
moment: analytics.views_after), under the part of the day it went up in, in this computer's time zone: 12–4 AM,
4–8 AM, 8 AM–12 PM, 12–4 PM, 4–8 PM or 8 PM–12 AM. A part of the day counts once 2 of its videos are known, and a
platform needs 2 parts that count before one can be the best: the one whose typical (median) video got the most
views, and only when that's at least a fifth more than the next part's. Until then the card says there aren't enough
videos yet, or that no time is clearly better yet, with the numbers so far. Your newest 60 videos with a known first
day count, so the answer follows your channel as it grows.

With few videos, which video it was matters more than when it went up, so it's a time to try more than a rule. Like
the badges, it only ever compares you with yourself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from rich.text import Text

from . import analytics
from .analytics import fmt_clock, fmt_hours
from .widgets import MUTED, short_num

SLOT_HOURS = 4  # the day in six parts
MIN_VIDEOS = 2  # known videos a part of the day needs to count
MIN_SLOTS = 2   # parts that count before one can be the best
MARGIN = 1.2    # the best part's typical video beats the next part's by at least a fifth


@dataclass
class BestTime:
    slot: int | None = None  # the best part of the day (0 is 12–4 AM ... 5 is 8 PM–12 AM), once there is one
    known: dict[int, list[float]] = field(default_factory=dict)  # part of the day -> its videos' first-day views

    def typical(self, slot: int) -> float:
        return median(self.known[slot])

    def ranked(self, counting: bool = True) -> list[int]:
        """The parts of the day with videos (only those that count, unless counting=False), best first."""
        return sorted((s for s, v in self.known.items() if len(v) >= MIN_VIDEOS or not counting),
                      key=lambda s: (-self.typical(s), s))

    @property
    def others(self) -> float | None:
        """The typical first-day views of the videos outside the best part of the day."""
        rest = [v for s, vs in self.known.items() if s != self.slot for v in vs]
        return median(rest) if rest else None


def best_times(posts: list[dict], platforms) -> dict[str, BestTime]:
    """Each platform's best part of the day so far. Posts need "published" and "after" (analytics.add_early_views)."""
    out = {}
    for key in platforms:
        known = sorted((p for p in posts if p["platform"] == key and p.get("after", {}).get(24) is not None),
                       key=lambda p: p["published"], reverse=True)[:analytics.RECENT]
        bt = BestTime()
        for p in known:
            bt.known.setdefault(slot_of(p["published"]), []).append(p["after"][24])
        ranked = bt.ranked()
        if len(ranked) >= MIN_SLOTS and bt.typical(ranked[0]) > 0 \
                and bt.typical(ranked[0]) >= MARGIN * bt.typical(ranked[1]):
            bt.slot = ranked[0]
        out[key] = bt
    return out


def slot_of(t: datetime) -> int:
    """The part of the day a moment falls in, in this computer's time zone."""
    return t.astimezone().hour // SLOT_HOURS


def slot_label(slot: int) -> str:
    """12–4 AM, 8 AM–12 PM, 8 PM–12 AM."""
    start = datetime(2000, 1, 1) + timedelta(hours=slot * SLOT_HOURS)
    return fmt_hours(start, start + timedelta(hours=SLOT_HOURS))


def next_time(slot: int, now: datetime | None = None) -> str:
    """When a part of the day next comes round: "now, until 12 AM", "today 8 PM" or "tomorrow 8 AM"."""
    now = (now or analytics.now()).astimezone()
    start = now.replace(hour=slot * SLOT_HOURS, minute=0, second=0, microsecond=0)
    if slot_of(now) == slot:
        return f"now, until {_hour(start + timedelta(hours=SLOT_HOURS))}"
    if start <= now:
        start += timedelta(days=1)
    return f"{'today' if start.date() == now.date() else 'tomorrow'} {_hour(start)}"


def parts(bt: BestTime, tag: Text, now: datetime | None = None) -> list[tuple[Text, int]]:
    """A platform's line on the card as (text, importance) parts: widgets.fit leaves out the highest numbers first."""
    head = tag.copy()
    head.append(" " * max(6 - head.cell_len, 2))  # the lines start level: "● TT  ", "● X   "
    if bt.slot is not None:
        return [(head, 0), (Text(slot_label(bt.slot), style="bold"), 0),
                (Text(f"  {short_num(bt.typical(bt.slot))}", style="bold"), 1),
                (Text(f" vs {short_num(bt.others)} other times", style=MUTED), 3),
                (Text(f"  next: {next_time(bt.slot, now)}", style=MUTED), 2)]
    ranked = bt.ranked()
    if len(ranked) >= MIN_SLOTS:  # the two closest, with their typical first-day views
        a, b = ranked[:2]
        return [(head, 0), (Text("no clear best time yet", style=MUTED), 0),
                (Text(f"  {slot_label(a)} {short_num(bt.typical(a))}", style=MUTED), 2),
                (Text(f", {slot_label(b)} {short_num(bt.typical(b))}", style=MUTED), 3)]
    out = [(head, 0), (Text("not enough videos yet", style=MUTED), 0)]
    if bt.known:  # the numbers so far, for the part of the day with the most videos
        s = max(bt.known, key=lambda s: (len(bt.known[s]), bt.typical(s)))
        n = len(bt.known[s])
        out.append((Text(f"  {slot_label(s)} {short_num(bt.typical(s))} ({n} video{'s' * (n > 1)})",
                         style=MUTED), 2))
    return out


def _hour(t: datetime) -> str:
    return fmt_clock(t).replace(":00", "")
