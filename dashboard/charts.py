"""Charts drawn in text: stacked bars and lines, with round-number axes, event marks and a hover read-out.

Bars are all the same width with a one-column gap between them (a caller too narrow for that combines buckets
first: trends.frame_fit). A stacked bar is drawn in whole cells of background colour, which Windows Terminal (and
screenshots) show without seams: each cell takes the colour of the platform that fills most of it, so no thin
slivers or lines appear inside a stack, and only the top cell uses an eighth block (▁▂▃▄▅▆▇) so the bar's height
lands within 1/8 of a row. Lines use thin box-drawing strokes; running totals can be drawn as a filled area with a
smooth top edge instead. The x axis is in "slots" (buckets of time, or hours since posting).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from . import analytics

BACKGROUND = "#0a0c0f"
AXIS = "#4a515c"
LABEL = "#8b93a1"
GRID = "#1a1f27"
HOVER = "#1a212b"
MARK = "#ffcc33"
EIGHTHS = " ▁▂▃▄▅▆▇█"
LADDER = (1, 2, 2.5, 5)  # round steps: 1, 2, 2.5 or 5 times a power of ten


def _hex(color: str) -> str:
    c = color.lstrip("#")
    return "".join(ch * 2 for ch in c) if len(c) == 3 else c


def blend(color: str, amount: float, into: str = BACKGROUND) -> str:
    """color moved `amount` of the way towards `into` (0 = unchanged, 1 = into)."""
    a, b = _hex(color), _hex(into)
    mix = [round(int(a[i:i + 2], 16) * (1 - amount) + int(b[i:i + 2], 16) * amount) for i in (0, 2, 4)]
    return "#{:02x}{:02x}{:02x}".format(*mix)


def _decimals(x: float) -> int:
    """How many decimals (up to 3) it takes to write x exactly."""
    return next((d for d in range(4) if abs(round(x, d) - x) < 1e-9 * max(abs(x), 1)), 3)


def fmt_tick(v: float, step: float | None = None) -> str:
    """Axis numbers: 0, 250, 2.5K, 10K, 1.2M. With the axis step given, every label on the axis stays distinct
    (52,340 and 52,345 rather than two "52.34K")."""
    if not math.isfinite(v):
        return "?"
    if abs(v) < 1e-9:
        return "0"
    step = step if step and math.isfinite(step) and step > 0 else None
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= size * 0.9995 and (step is None or step >= size / 100):
            d = 2 if step is None else _decimals(step / size)
            text = f"{v / size:.{d}f}"
            text = text.rstrip("0").rstrip(".") if "." in text else text
            return text + suffix
    d = 0 if step is None or step >= 1 else _decimals(step)
    return f"{v:,.{d}f}" if step is not None else (f"{v:.2f}".rstrip("0").rstrip(".") or "0")


def nice_step(span: float, count: int) -> float:
    """A 1, 2, 2.5 or 5 x 10^n step that cuts span into about `count` pieces."""
    if not span > 0 or not math.isfinite(span):
        return 1.0
    raw = span / max(count, 1)
    mag = 10 ** math.floor(math.log10(raw))
    return next(m * mag for m in (*LADDER, 10) if m * mag >= raw * (1 - 1e-12))


def nice_range(lo: float, hi: float, count: int, whole: bool = True) -> tuple[float, float, float]:
    """(bottom, top, step) covering lo..hi in round steps, about `count` of them with the least space wasted;
    whole: whole-number steps only (for counts)."""
    if not (math.isfinite(lo) and math.isfinite(hi)):
        lo, hi = 0.0, 1.0
    if hi - lo < (1 if whole else max(abs(hi), 1) * 1e-9):
        hi = lo + 1
    mag = math.floor(math.log10(nice_step(hi - lo, count)))
    best = None
    for k in (mag - 1, mag, mag + 1):
        for m in LADDER:
            step = m * 10 ** k
            if whole and (step < 1 or abs(step - round(step)) > 1e-9):
                continue
            bottom, top = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step
            steps = round((top - bottom) / step)
            if steps < 1 or steps > max(count * 2, 2):
                continue
            score = abs(steps - count) * 0.5 + (top - bottom - (hi - lo)) / (hi - lo)  # few steps off, little waste
            if best is None or score < best[0] - 1e-9:
                best = (score, bottom, top, step)
    if best is None:
        step = max(round(nice_step(hi - lo, count)), 1) if whole else nice_step(hi - lo, count)
        return math.floor(lo / step) * step, math.ceil(hi / step) * step, step
    return best[1], best[2], best[3]


@dataclass
class Series:
    """One coloured thing on a chart: a value per slot for bars, or (x, y) points for a line."""

    key: str
    name: str
    color: str
    values: list[float | None] = field(default_factory=list)  # bars: one per slot
    faint: list[bool] = field(default_factory=list)  # bars: slots drawn dimmer (estimated or still filling)
    xs: list[float] = field(default_factory=list)  # lines: x in slots
    ys: list[float] = field(default_factory=list)
    fill: bool = False  # lines: shade the cells under the line
    style: str = "line"  # lines: "line", or "area" (filled, with a smooth top edge)


@dataclass
class Mark:
    """Something that happened at a moment (a video going up): a dotted line with a label at the top."""

    x: float  # in slots
    label: str


class Canvas:
    """A grid of cells: (char, fg, bg)."""

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.cells: dict[tuple[int, int], tuple[str, str | None, str | None]] = {}

    def put(self, r: int, c: int, ch: str, fg: str | None = None, bg: str | None = None) -> None:
        """Draw a character; with bg None the cell keeps the background it had."""
        if 0 <= r < self.h and 0 <= c < self.w:
            old = self.cells.get((r, c))
            self.cells[r, c] = (ch, fg, bg if bg is not None else (old[2] if old else None))

    def tint(self, r: int, c: int, bg: str) -> None:
        if 0 <= r < self.h and 0 <= c < self.w:
            ch, fg, _ = self.cells.get((r, c), (" ", None, None))
            self.cells[r, c] = (ch, fg, bg)

    def blank(self, r: int, c: int) -> bool:
        """Nothing drawn there: a grid line or the hover highlight doesn't count, a bar or an area does."""
        ch, _, bg = self.cells.get((r, c), (" ", None, None))
        return ch in (" ", "┈") and bg in (None, HOVER)

    def row(self, r: int) -> Text:
        """One row as styled text, with runs of same-coloured cells joined (it's redrawn as the mouse moves)."""
        out = Text()
        run, style = [], None
        for c in range(self.w):
            ch, fg, bg = self.cells.get((r, c), (" ", None, None))
            if (fg, bg) != style and run:
                out.append("".join(run), style=Style(color=style[0], bgcolor=style[1]))
                run = []
            run.append(ch)
            style = (fg, bg)
        if run:
            out.append("".join(run), style=Style(color=style[0], bgcolor=style[1]))
        return out


@dataclass
class Layout:
    """Where the plot sits in the widget, how values map to rows and slots to columns."""

    lw: int  # left label width; the axis column comes after it
    pw: int  # plot width
    ph: int  # plot height
    lo: float
    hi: float
    step: float
    per: float = 1.0  # columns per slot
    first: int = 0  # the first slot drawn (bars show only the newest slots when there are more than columns)
    slots: int = 0  # how many slots are drawn
    bar: int = 0  # bar charts: how many columns wide each bar is (the rest of its slot is the gap after it)

    def height(self, v: float) -> float:
        """v as a height above the plot bottom, in rows (0..ph)."""
        return (v - self.lo) / (self.hi - self.lo) * self.ph if self.hi > self.lo else 0.0

    def row(self, v: float) -> int:
        """The plot row a value falls in (0 = top)."""
        return min(max(self.ph - 1 - int(self.height(v) - 1e-9), 0), self.ph - 1) if v > self.lo else self.ph - 1

    def columns(self, slot: int) -> range:
        """The plot columns a slot is drawn in (at least one)."""
        j = slot - self.first
        c0 = int(j * self.per)
        return range(c0, max(int((j + 1) * self.per), c0 + 1))

    def col(self, x: float) -> int:
        """The plot column of x (in slots). On a bar chart it's a column of x's own bar, never the gap after it,
        so a mark or an axis label lands on the bar it belongs to."""
        if not self.bar:
            return int((x - self.first) * self.per)
        j = math.floor(x)
        return self.columns(j).start + min(int((x - j) * self.bar), self.bar - 1)

    def slot_at(self, c: int) -> int | None:
        """The slot drawn in plot column c: the exact inverse of columns()."""
        if not 0 <= c < self.pw or self.slots <= 0:
            return None
        j = min(int(c / self.per), self.slots - 1)
        while j > 0 and int(j * self.per) > c:
            j -= 1
        while j + 1 < self.slots and int((j + 1) * self.per) <= c:
            j += 1
        return self.first + j


def y_labels(lay: Layout) -> dict[int, str]:
    """Round-number labels by plot row: the top and bottom ones always, then the others that don't touch a
    label already placed."""
    steps = min(round((lay.hi - lay.lo) / lay.step), 200) if lay.step > 0 else 0
    values = [lay.hi - k * lay.step for k in range(steps + 1)]
    order = [0, steps, *range(1, steps)] if steps else [0]
    out: dict[int, str] = {}
    for k in order:
        r = 0 if k == 0 else lay.ph - 1 if k == steps else lay.row(values[k])
        if r not in out and all(abs(r - q) > 1 for q in out):
            out[r] = fmt_tick(values[k], lay.step)
    return dict(sorted(out.items()))


def _layout(w: int, h: int, lo: float, hi: float, whole: bool, xaxis: bool) -> Layout:
    ph = max(h - (2 if xaxis else 0), 1)
    lo, hi, step = nice_range(lo, hi, max(ph // 3, 2), whole)
    lw = max((cell_len(s) for s in y_labels(Layout(0, 0, ph, lo, hi, step)).values()), default=1) + 1
    return Layout(lw, max(w - lw - 1, 1), ph, lo, hi, step)


def _place(lay: Layout, slots: float, newest_first: bool = False) -> None:
    """Map slots to columns; bars that wouldn't each get a column and a gap keep only the newest slots that do."""
    n = int(math.ceil(slots))
    if newest_first and n * 2 > lay.pw:
        keep = max(lay.pw // 2, 1)
        lay.first, lay.slots, lay.per = n - keep, keep, lay.pw / keep
    else:
        lay.first, lay.slots, lay.per = 0, n, lay.pw / max(slots, 1e-9)


def _frame(canvas: Canvas, lay: Layout, xlabels, xaxis: bool) -> list[Text]:
    """The y labels and axis, the drawn plot, then the x axis and its labels.

    xlabels: [(x in slots, label)], or a function of the plot width that returns them.
    """
    if callable(xlabels):
        xlabels = xlabels(lay.pw)
    labels = y_labels(lay)
    rows = []
    for r in range(lay.ph):
        line = Text()
        if r in labels:
            line.append(f"{labels[r]:>{lay.lw - 1}} ", style=LABEL)
            line.append("┤", style=AXIS)
        else:
            line.append(" " * lay.lw + "│", style=AXIS)
        line.append_text(canvas.row(r))
        rows.append(line)
    if xaxis:
        axis, under, free = ["─"] * lay.pw, [" "] * lay.pw, 0
        for x, label in xlabels:
            c = lay.col(x)
            if not 0 <= c < lay.pw:
                continue
            axis[c] = "┬"
            start = min(max(c - len(label) // 2, 0), max(lay.pw - len(label), 0))
            if start >= free and start + len(label) <= lay.pw:
                under[start:start + len(label)] = label
                free = start + len(label) + 2
        rows.append(Text(" " * lay.lw + "└" + "".join(axis), style=AXIS))
        rows.append(Text(" " * (lay.lw + 1) + "".join(under)[:lay.pw], style=LABEL))
    return rows


def _grid(canvas: Canvas, lay: Layout) -> None:
    for r in y_labels(lay):
        if r < lay.ph - 1:
            for c in range(lay.pw):
                if canvas.blank(r, c):
                    canvas.put(r, c, "┈", GRID)


def _hover(canvas: Canvas, lay: Layout, slot: int | None) -> None:
    if slot is None or not lay.first <= slot < lay.first + lay.slots:
        return
    for c in lay.columns(slot):
        for r in range(lay.ph):
            canvas.tint(r, c, HOVER)


def _label(text: str, width: int = 28) -> str:
    """A mark label in single-width characters only (an emoji or CJK title would push the row out of line)."""
    return "".join(ch for ch in text if cell_len(ch) == 1)[:width].strip()


def _marks(canvas: Canvas, lay: Layout, marks: list[Mark]) -> None:
    """Dotted lines where videos went up (through empty cells only), each labelled along the top row.

    Marks that land within a couple of columns of each other share one line and one label. A label reads to the
    right of its mark, or to the left when there's no room on the right. When the labels don't all fit, they're all
    shortened alike (down to three letters and "…") until every mark has one; a mark with no room even then is left
    out, so there is never an arrow that doesn't say what it points at.
    """
    groups: list[tuple[int, list[str]]] = []
    for m in sorted(marks, key=lambda m: m.x):
        c = lay.col(m.x)
        if not 0 <= c < lay.pw:
            continue  # outside what's drawn
        if groups and c - groups[-1][0] <= 2:
            groups[-1][1].append(_label(m.label))
        else:
            groups.append((c, [_label(m.label)]))
    if not groups:
        return
    texts = [" + ".join(label for label in labels if label) for _, labels in groups]
    blank = [canvas.blank(0, k) for k in range(lay.pw)]

    def place(caps: list[int]) -> list[tuple[str, int] | None]:
        """Left to right, each label as long as its cap and the room allow: [(label, first column)] or None."""
        out, end = [], None  # end: the column just after the last label
        for (c, _), text, cap in zip(groups, texts, caps):
            # A label reading right starts one column after the last one; one reading left (ending in its arrow)
            # keeps three columns away, so two labels never run together as if they were one.
            after_r, after_l = (0, 0) if end is None else (end + 1, end + 3)
            right = left = 0  # blank columns from the mark rightwards, and leftwards
            while c >= after_r and c + right < lay.pw and blank[c + right]:
                right += 1
            while c - left >= after_l and blank[c - left]:
                left += 1
            room_r, room_l = min(cap, len(text), right - 2), min(cap, len(text), left - 2)
            keep = max(room_r, room_l)
            if not text or keep < min(4, len(text)):
                out.append(None)
                continue
            short = text if keep >= len(text) else text[:keep - 1].rstrip() + "…"
            spot = ("▼ " + short, c) if room_r >= keep else (short + " ▼", c - len(short) - 1)
            out.append(spot)
            end = spot[1] + len(spot[0])
        return out

    longest = max(len(t) for t in texts)
    best = place([longest] * len(texts))
    for cap in range(longest - 1, 3, -1):  # too crowded: shorten them all alike (the last one can use what's left)
        if all(best):
            break
        trial = place([cap] * (len(texts) - 1) + [longest])
        if sum(map(bool, trial)) > sum(map(bool, best)):
            best = trial
    for (c, _), spot in zip(groups, best):
        if spot is None:
            continue
        label, first = spot
        for r in range(1, lay.ph):
            if canvas.blank(r, c):
                canvas.put(r, c, "┊", blend(MARK, 0.5))
        for k, ch in enumerate(label):
            canvas.put(0, first + k, ch, MARK)


def bars(series: list[Series], slots: int, w: int, h: int, xlabels=(), marks: list[Mark] = (),
         hover: int | None = None, xaxis: bool = True) -> tuple[list[Text], Layout]:
    """Stacked bars, one per slot, series stacked bottom-up in the order given. Every bar is the same width with at
    least a one-column gap after it; a chart too narrow even for that shows only its newest bars."""
    xaxis = xaxis and h >= 5
    totals = [sum(v for s in series if i < len(s.values) and (v := s.values[i]) and math.isfinite(v))
              for i in range(slots)]
    peak = max(totals, default=0) or 1
    if marks:  # keep the top row clear of bars, so the marks' labels have somewhere to go
        rows = max(h - (2 if xaxis else 0), 2)
        peak *= rows / (rows - 1)
    lay = _layout(w, h, 0, peak, True, xaxis)
    _place(lay, slots, newest_first=True)
    canvas = Canvas(lay.pw, lay.ph)
    _hover(canvas, lay, hover)
    _grid(canvas, lay)
    gap = 1 if lay.per >= 2 else 0
    lay.bar = max(int(lay.per) - gap, 1)
    for i in range(lay.first, lay.first + lay.slots):
        c0 = lay.columns(i).start
        cols = range(c0, min(c0 + lay.bar, lay.pw))
        segments, top = [], 0.0  # (bottom, top, colour) in eighths of a row
        for s in series:
            v = s.values[i] if i < len(s.values) else None
            if not v or not math.isfinite(v):
                continue
            faint = i < len(s.faint) and s.faint[i]
            segments.append((top, top + lay.height(v) * 8, blend(s.color, 0.55) if faint else s.color))
            top = segments[-1][1]
        _stack(canvas, lay, cols, segments)
    if marks:
        _marks(canvas, lay, list(marks))
    return _frame(canvas, lay, xlabels, xaxis), lay


def _stack(canvas: Canvas, lay: Layout, cols: range, segments: list[tuple[float, float, str]]) -> None:
    """One stacked bar. Each whole cell is the colour of the segment that fills most of it, so a boundary between
    platforms lands on a cell edge and a platform too thin to see joins its neighbour (its number is still in the
    hover read-out); only the top cell keeps 1/8-row precision, as an eighth block. That top piece takes the colour
    of the cell under it unless one platform fills at least half a row of it, so it's never a thin line of another
    colour."""
    if not segments:
        return
    top = segments[-1][1]
    eighths = int(round(top))
    if eighths <= 0:
        return

    def colour(lo: float, hi: float) -> tuple[str, float]:
        """The colour covering most of lo..hi (eighths of a row), and how much of it it covers."""
        best, cover = segments[-1][2], 0.0
        for a, b, col in segments:
            if min(b, hi) - max(a, lo) > cover:
                best, cover = col, min(b, hi) - max(a, lo)
        return best, cover

    full, rest = divmod(eighths, 8)
    for k in range(min(full, lay.ph)):
        col = colour(8 * k, 8 * k + 8)[0]
        for c in cols:
            canvas.put(lay.ph - 1 - k, c, " ", None, col)
    if rest and full < lay.ph:
        col, cover = colour(8 * full, top)
        if full and cover < 4:
            col = colour(8 * full - 8, 8 * full)[0]
        for c in cols:
            canvas.put(lay.ph - 1 - full, c, EIGHTHS[rest], col)


def _hug(ys: list[float]) -> tuple[float, float]:
    """A y range that hugs the data, so change shows; it only starts at 0 when the data is near 0."""
    ys = [y for y in ys if math.isfinite(y)] or [0.0]
    lo, hi = min(ys), max(ys)
    if hi <= lo:
        return max(lo - 1, 0), hi + 1
    pad = (hi - lo) * 0.08
    lo = lo - pad if lo - pad > 0 else 0.0
    return lo, hi + pad * 0.5


def _sorted(s: Series) -> tuple[list[float], list[float]]:
    pts = sorted((x, y) for x, y in zip(s.xs, s.ys) if math.isfinite(x) and math.isfinite(y))
    return [x for x, _ in pts], [y for _, y in pts]


def _area(canvas: Canvas, lay: Layout, s: Series) -> None:
    """A filled area whose top edge lands within 1/8 of a row (for running totals: views so far)."""
    xs, ys = _sorted(s)
    if len(xs) < 2:
        return
    color = blend(s.color, 0.3)
    first = max(int((xs[0] - lay.first) * lay.per), 0)
    last = min(int(math.ceil((xs[-1] - lay.first) * lay.per)) - 1, lay.pw - 1)
    for c in range(first, last + 1):
        x = min(max((c + 0.5) / lay.per + lay.first, xs[0]), xs[-1])
        eighths = int(round(min(max(lay.height(analytics.interp(xs, ys, x)), 0.0), lay.ph) * 8))
        full, part = divmod(eighths, 8)
        for k in range(min(full, lay.ph)):
            canvas.put(lay.ph - 1 - k, c, " ", None, color)
        if part and full < lay.ph:
            canvas.put(lay.ph - 1 - full, c, EIGHTHS[part], color)


def _line(canvas: Canvas, lay: Layout, s: Series, fill: bool) -> None:
    xs, ys = _sorted(s)
    if not xs:
        return
    if len(xs) == 1:
        c = int((xs[0] - lay.first) * lay.per)
        if 0 <= c < lay.pw:
            canvas.put(lay.row(ys[0]), c, "●", s.color)
        return
    first = max(int((xs[0] - lay.first) * lay.per), 0)
    last = min(int(math.ceil((xs[-1] - lay.first) * lay.per)) - 1, lay.pw - 1)
    shade = blend(s.color, 0.86)
    prev = None
    for c in range(first, last + 1):
        x = min(max((c + 0.5) / lay.per + lay.first, xs[0]), xs[-1])
        r = lay.row(analytics.interp(xs, ys, x))
        if fill:
            for rr in range(r + 1, lay.ph):
                canvas.tint(rr, c, shade)
        if prev is None or r == prev:
            canvas.put(r, c, "─", s.color)
        else:
            up = r < prev
            canvas.put(prev, c, "╯" if up else "╮", s.color)
            canvas.put(r, c, "╭" if up else "╰", s.color)
            for rr in range(min(r, prev) + 1, max(r, prev)):
                canvas.put(rr, c, "│", s.color)
        prev = r


def lines(series: list[Series], slots: float, w: int, h: int, xlabels=(), marks: list[Mark] = (),
          hover: int | None = None, zero: bool = False, whole: bool = True,
          xaxis: bool = True) -> tuple[list[Text], Layout]:
    """Lines (or areas) on an x axis of `slots` slots. The y range hugs the data (zero=True starts it at 0)."""
    xaxis = xaxis and h >= 5
    ys = [y for s in series for y in s.ys if math.isfinite(y)]
    lo, hi = ((0.0, max(ys)) if zero else _hug(ys)) if ys else (0.0, 1.0)
    lay = _layout(w, h, lo, hi, whole, xaxis)
    _place(lay, slots)
    canvas = Canvas(lay.pw, lay.ph)
    _hover(canvas, lay, hover)
    _grid(canvas, lay)
    for s in sorted(series, key=lambda s: s.style != "area"):  # areas first, lines over them
        if s.style == "area" and len(s.xs) > 1:
            _area(canvas, lay, s)
        else:
            _line(canvas, lay, s, s.fill)
    if marks:
        _marks(canvas, lay, list(marks))
    return _frame(canvas, lay, xlabels, xaxis), lay


def clock_labels(starts: list[datetime], pw: int, step_h: float | None = None) -> list[tuple[float, str]]:
    """Labels for a time axis of buckets: round hours ("6 PM", the weekday at midnight) or dates.

    step_h: the buckets' nominal size in hours (a bucket can run an hour long or short over a clock change).
    """
    n = len(starts)
    if n < 2:
        return []
    if not step_h:  # the commonest of the first few bucket lengths, so a clock-change day doesn't decide it
        gaps = [round((b - a).total_seconds() / 3600) for a, b in zip(starts[:4], starts[1:5])]
        step_h = max(set(gaps), key=gaps.count)
    per = pw / n
    out = []
    if step_h >= 24:
        every = next((k for k in (1, 2, 3, 5, 7, 14) if k * per >= 8), 30)
        for i, t in enumerate(starts):
            if (n - 1 - i) % every == 0:
                out.append((i + 0.5, f"{t:%b} {t.day}"))
        return out
    every = next((k for k in (1, 2, 3, 4, 6, 12, 24) if k / step_h * per >= 8 and k % step_h == 0), 48)
    for i, t in enumerate(starts):
        if every <= 24 and t.hour % every == 0 or every > 24 and t.hour == 0 and t.day % 2 == 0:
            out.append((i, t.strftime("%a") if t.hour == 0 else analytics.fmt_clock(t).replace(":00", "")))
    return out


def age_labels(hours: float, pw: int) -> list[tuple[float, str]]:
    """Labels for an hours-since-posting axis (x in hours): 0h, 6h, 12h ... or 1d, 2d ..."""
    per = pw / max(hours, 1e-9)
    every = next((k for k in (1, 2, 3, 6, 12, 24, 48, 96, 168) if k * per >= 7), 336)
    return [(float(x), f"{x // 24}d" if every >= 24 else f"{x}h") for x in range(0, int(hours) + 1, every)]


class Plot(Widget):
    """A chart that redraws to fit its size and reports which slot the mouse is over."""

    DEFAULT_CSS = "Plot { height: 1fr; }"

    class Hovered(Message):
        def __init__(self, plot: "Plot", slot: int | None):
            super().__init__()
            self.plot, self.slot = plot, slot

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.draw_fn = None  # (width, height, hovered slot) -> (rows, layout)
        self.slots = 0.0
        self.hover: int | None = None
        self.layout_: Layout | None = None

    def show(self, draw_fn, slots: float) -> None:
        self.draw_fn, self.slots = draw_fn, slots
        if self.hover is not None and self.hover >= slots:
            self.hover = None
        self.refresh()

    def render(self) -> Text:
        if not self.draw_fn or self.size.width < 10 or self.size.height < 4:
            self.layout_ = None
            return Text()
        rows, self.layout_ = self.draw_fn(self.size.width, self.size.height, self.hover)
        return Text("\n").join(rows)

    def slot_at(self, x: int) -> int | None:
        lay = self.layout_
        return lay.slot_at(x - lay.lw - 1) if lay else None

    def on_mouse_move(self, event: events.MouseMove) -> None:
        slot = self.slot_at(event.x)
        if slot != self.hover:
            self.hover = slot
            self.refresh()
            self.post_message(self.Hovered(self, slot))

    def on_leave(self, event: events.Leave) -> None:
        if self.hover is not None:
            self.hover = None
            self.refresh()
            self.post_message(self.Hovered(self, None))
