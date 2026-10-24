"""Reusable pieces of the ReelForge window: the logo, the bell and its drawer, chart panels, bar lists,
platform cards and account panels."""

from __future__ import annotations

import os

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.color import Color
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, OptionList, Sparkline, Static

from .analytics import fmt_ago, fmt_delta, fmt_num
from .charts import Plot
from .platforms import Platform

BACKGROUND = "#0a0c0f"
MUTED = "#8b93a1"
GOOD = "#3dff9a"
BAD = "#ff4d5e"
TYPICAL = "#ffb020"  # the "typical video" line: amber, unlike any platform colour
EIGHTHS = " ▏▎▍▌▋▊▉"
SHORT = {"tiktok": "TT", "youtube": "YT", "instagram": "IG", "x": "X"}
# REELFORGE_SCREENSHOTS=1 is for the README's pictures of the demo: no DEMO badge and no "demo data" lines, so they
# show what a set-up account looks like. Trying the demo yourself always shows them.
SCREENSHOTS = os.environ.get("REELFORGE_SCREENSHOTS", "").strip() == "1"

def dim(hex_color: str, amount: float = 0.65) -> str:
    return Color.parse(hex_color).blend(Color.parse(BACKGROUND), amount).hex


def tag(p: Platform) -> Text:
    return Text(f"● {SHORT.get(p.key, p.key)}", style=f"bold {p.color}")


def clickable(action: str) -> Style:
    """Style that makes text run an app action when clicked inside an ActionText.

    It uses its own "act" key rather than Textual's "@click", which restyles link text and would
    wipe out colours like the platform ones.
    """
    return Style.from_meta({"act": f"app.{action}"})


def legend(platforms, hidden: set[str] = frozenset(), toggle: str = "toggle_line", short: bool = False) -> Text:
    """Platform key for a chart; click a name to hide or show it (hidden ones are struck through)."""
    out = Text()
    for p in platforms:
        off = p.key in hidden
        style = Style(color="#4a515c", strike=True) if off else Style(color=p.color, bold=True)
        name = SHORT.get(p.key, p.key) if short else p.name
        out.append(f"■ {name}", style=style + clickable(f"{toggle}('{p.key}')"))
        out.append("  ")
    return out


def chip(label: str, action: str, active: bool = False) -> Text:
    """A small button inside text: runs an app action when clicked. Active chips show a selected state."""
    if active:
        return Text(f" {label} ", style=Style(bold=True, color="#ffffff", bgcolor="#1f5c45"))
    return Text(f" {label} ", style=Style(color="#c9d1d9", bgcolor="#1c222b") + clickable(action))


def chips(*items, gap: str = " ") -> Text:
    """Several chips in a row: each item is (label, action) or (label, action, active)."""
    out = Text()
    for i, item in enumerate(items):
        if i:
            out.append(gap)
        out.append_text(chip(*item))
    return out


def fit(parts: list[tuple[Text, int]], width: int) -> Text:
    """Join title parts, leaving out the least important (highest number) ones until it fits `width`. If even the
    ones that always show (0) don't fit, the last of them go too, so nothing is cut off halfway (a number, a button);
    only a first part wider than everything is cut."""
    keep = list(parts)
    while len(keep) > 1 and sum(t.cell_len for t, _ in keep) > width:
        keep.pop(max(range(len(keep)), key=lambda i: (keep[i][1], i)))
    out = Text()
    for t, _ in keep:
        out.append_text(t)
    out.truncate(max(width, 1))
    return out


class ActionText(Static):
    """A Static whose text can carry clickable() spans, and can be given as (text, importance) parts that are
    fitted to its width (the least important go first when it's narrow)."""

    _parts = None  # [(text, importance)], or a function of the width that returns them

    def set_parts(self, parts) -> None:
        self._parts = parts
        self._fit()

    def _fit(self) -> None:
        width = self.content_region.width or 1000
        self.update(fit(self._parts(width) if callable(self._parts) else self._parts, width))

    def on_resize(self) -> None:
        if self._parts:
            self._fit()

    async def on_click(self, event: events.Click) -> None:
        action = event.style.meta.get("act") if event.style else None
        if action:
            event.stop()
            await self.app.run_action(action)


def score_text(score: float | None) -> Text:
    if score is None:
        return Text("—", style=MUTED, justify="right")
    style = f"bold {GOOD}" if score >= 2 else GOOD if score >= 1.2 else BAD if score < 0.6 else ""
    return Text(f"{score:.1f}×", style=style, justify="right")


def num(n, style: str = "") -> Text:
    return Text(fmt_num(n), style=style, justify="right")


def short_num(n: float | None) -> str:
    """A number in as few characters as it reads in: 13K, 9.4K, 1K, 1.2M (fmt_num keeps more digits)."""
    if n is None:
        return "—"
    if abs(n) >= 999_500:
        v, suffix = n / 1_000_000, "M"
    elif abs(n) >= 999.5:
        v, suffix = n / 1_000, "K"
    else:
        return f"{n:.0f}"
    return (f"{v:.0f}" if abs(v) >= 9.95 else f"{v:.1f}".rstrip("0").rstrip(".")) + suffix


CARD_LABELS = ("followers", "views", "likes")


def card_lines(values: dict, changes: dict, width: int) -> list[Text]:
    """A card's followers, views and likes, each with its 24-hour change, made to fit the width without cutting
    anything off. As the card narrows, the margin goes first, then the " 24h" after each change, then the changes
    get shorter (+1.03K -> +1K), then the totals (12.9K -> 13K), then the lining up, then the changes, then the
    labels."""

    def build(value_fmt, change_fmt, suffix: str, margin: int | None, aligned: bool,
              labels: bool = True) -> list[Text]:
        shown = {k: value_fmt(values.get(k)) for k in CARD_LABELS}
        number_w = 0 if margin is None else max(len(s) for s in shown.values()) + margin  # None: not lined up
        lines = []
        for k in CARD_LABELS:
            line = Text(f"{shown[k]:>{number_w}}", style="bold")
            if labels:
                line.append(" " + (f"{k:<9}" if aligned else k), style=MUTED)
            n = changes.get(k) if change_fmt else None
            if n:
                sign = "+" if n > 0 else "−"
                line.append(f" {sign}{change_fmt(abs(n))}{suffix}", style=GOOD if n > 0 else BAD)
            lines.append(line)
        return lines

    for step in ((fmt_num, fmt_num, " 24h", 2, True), (fmt_num, fmt_num, " 24h", 0, True),
                 (fmt_num, fmt_num, "", 0, True), (fmt_num, short_num, "", 0, True),
                 (short_num, short_num, "", 0, True), (short_num, short_num, "", 0, False),
                 (short_num, short_num, "", None, False), (short_num, None, "", 0, True),
                 (short_num, None, "", None, False)):
        lines = build(*step)
        if all(line.cell_len <= width for line in lines):
            return lines
    return [line if line.cell_len <= width else Text() for line in build(short_num, None, "", 0, False, False)]


def wrap_lines(text: Text, width: int) -> list[Text]:
    """Each line of the text, wrapped at spaces to fit the width (a word too long for it is left out)."""
    out = []
    for line in text.split("\n"):
        while line.cell_len > width:
            cut = line.plain.rfind(" ", 0, width + 1)
            if cut <= 0:
                break
            out.append(line[:cut])
            line = line[cut + 1:]
        if line.cell_len <= width:
            out.append(line)
    return out


def change_text(n: float | None, suffix: str = "") -> Text:
    """+1.2K in green, −40 in red, nothing for no change."""
    if not n:
        return Text("")
    return Text(f"{fmt_delta(n)}{suffix}", style=GOOD if n > 0 else BAD)


WHITE = "#ffffff"  # the anvil's colour


def anvil_rows() -> list[Text]:
    """ReelForge's anvil, three rows tall (from the kit's logo; a plain stand-in if that can't be loaded)."""
    try:
        from studio import logo

        return logo.rich_text(logo.anvil()).split("\n")
    except Exception:
        return [Text(row, style=WHITE) for row in ("▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀", "    ▀▀███████▀  ", "     ▄▄████▄▄▄  ")]


class Logo(Static):
    """ReelForge's anvil in the top-left corner (just the anvil: no name beside or under it)."""

    def __init__(self, **kwargs):
        super().__init__(Text("\n").join(Text.assemble(" ", row, " ") for row in anvil_rows()), **kwargs)


class Bell(Static):
    """The notifications button at the header's right end: one line, the height of the header's text, with a red dot
    while something is unread. Click it, or press n, to open the drawer."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.unread = 0

    def show(self, unread: int) -> None:
        self.unread = unread
        self.tooltip = f"{unread} new notification{'s' if unread != 1 else ''} (n)" if unread else "Notifications (n)"
        self.update(self._draw())

    def _draw(self) -> Text:
        out = Text("🔔")
        out.append("●" if self.unread else " ", style=f"bold {BAD}")
        return out

    def on_mount(self) -> None:
        self.show(self.unread)

    async def on_click(self, event: events.Click) -> None:
        event.stop()
        await self.app.run_action("toggle_drawer")


class VideoList(OptionList):
    """The Publish tab's video list: right-click a video for its menu (the Remove button above does the same)."""

    class Menu(Message):
        def __init__(self, option_id: str):
            super().__init__()
            self.option_id = option_id

    async def _on_click(self, event: events.Click) -> None:
        if event.button == 3:  # right button
            index = event.style.meta.get("option")
            if index is not None and not self.get_option_at_index(index).disabled:
                self.highlighted = index
                self.post_message(self.Menu(self.get_option_at_index(index).id))
            return
        await super()._on_click(event)


class ChartPanel(Vertical):
    """A titled chart that shows a hint instead of an empty grid when there's nothing to draw yet.

    The title can be a list of (text, importance) parts: 0 always shows, higher numbers go first when the
    panel is too narrow for all of them.
    """

    EMPTY = "Not enough history yet. ReelForge saves a snapshot on every refresh, so this fills in as it runs."

    def __init__(self, title: str | Text = "", **kwargs):
        super().__init__(classes="box chart", **kwargs)
        self._title = title
        self._parts: list[tuple[Text, int]] | None = None

    def compose(self) -> ComposeResult:
        yield ActionText(self._title, classes="box-title")
        yield Plot()
        yield Static(self.EMPTY, classes="empty")

    @property
    def plot(self) -> Plot:
        return self.query_one(Plot)

    def set_title(self, title: str | Text | list[tuple[Text, int]]) -> None:
        if isinstance(title, list):
            self._parts = title
            width = self.content_region.width or 1000
            title = fit(title, width)
        else:
            self._parts = None
        self.query_one(".box-title", Static).update(title)

    def on_resize(self) -> None:
        if self._parts:
            self.set_title(self._parts)

    def draw(self, draw_fn, slots: float) -> None:
        """draw_fn(width, height, hovered slot) -> (rows, layout); see charts.bars and charts.lines."""
        self.plot.display, self.query_one(".empty", Static).display = True, False
        self.plot.show(draw_fn, slots)

    def show_empty(self, hint: str | None = None) -> None:
        self.plot.display = False
        empty = self.query_one(".empty", Static)
        empty.display = True
        empty.update(hint or self.EMPTY)


class Bars(Widget):
    """Sections of horizontal bars: one row per platform, scaled to the section's largest value."""

    DEFAULT_CSS = "Bars { height: auto; }"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sections: list[tuple[str, list[tuple[str, float, str, str]]]] = []

    def show(self, sections: list[tuple[str, list[tuple[str, float, str, str]]]]) -> None:
        """sections: (title, [(label, value, color, value text), ...])"""
        self.sections = sections
        self.refresh(layout=True)

    def get_content_height(self, container, viewport, width: int) -> int:
        return sum(len(rows) + 2 for _, rows in self.sections) or 1

    def render(self) -> Text:
        label_w, value_w = 11, 18
        bar_w = max(self.size.width - label_w - value_w, 4)
        out = Text()
        for title, rows in self.sections:
            out.append(title + "\n", style=f"bold {MUTED}")
            top = max((v for _, v, _, _ in rows), default=0) or 1
            for label, value, color, shown in rows:
                n = max(value, 0) / top * bar_w
                # Whole cells in background colour (no seams between them, in a terminal or a screenshot), then
                # the last eighth-wide piece.
                part = EIGHTHS[int((n % 1) * 8)] if (n % 1) * 8 >= 1 else ""
                out.append(f"{label:<{label_w}}", style=color)
                out.append(" " * int(n), style=Style(bgcolor=color))
                out.append(part.ljust(bar_w - int(n)), style=color)
                out.append(f" {shown}\n")
            out.append("\n")
        return out


class _Card(Vertical):
    """Followers, views and likes with their 24-hour change, and views per hour underneath."""

    def __init__(self, color: str, **kwargs):
        super().__init__(classes="card", **kwargs)
        self.color = color

    def compose(self) -> ComposeResult:
        yield Static(classes="card-body")
        yield Sparkline([0], min_color=dim(self.color), max_color=self.color, classes="card-spark")
        yield Static(classes="card-caption")

    def on_mount(self) -> None:
        self.styles.border = ("round", self.color)
        self.styles.border_title_color = self.color

    _body = None  # the width -> lines the card shows
    _captions: tuple[str, ...] = ()
    _titles: tuple[str, ...] = ()  # the name on the border, then shorter ones for a narrow card

    def numbers(self, values: dict, changes: dict) -> None:
        self._body = lambda width: card_lines(values, changes, width)
        self.fit()

    def message(self, text: Text) -> None:
        self._body = lambda width: wrap_lines(text, width)
        self.fit()

    def spark(self, gains: list[float], captions: tuple[str, ...] = ()) -> None:
        """Views per hour, with the first of the captions that fits under it."""
        spark = self.query_one(Sparkline)
        # A sparkline of all zeros draws as solid blocks, so only show it once views are coming in.
        spark.display = any(gains)
        spark.data = gains or [0]
        self._captions = captions if any(gains) else ()
        self.fit()

    def fit(self) -> None:
        """Nothing on a card is ever cut off: its lines get shorter as the card narrows (worked out from the card's
        own width, which is known before its lines' is)."""
        width = self.outer_size.width  # the whole card, border and all
        if not width:
            return  # not laid out yet; on_resize fits it
        pad = 0 if width < 18 else 1  # a narrow card gives its padding to the numbers
        if self.styles.padding.left != pad:
            self.styles.padding = (0, pad)
        inner = max(width - 2 - 2 * pad, 0)  # inside the border and the padding
        if self._titles:
            self.border_title = next((t for t in self._titles if len(t) + 6 <= width), self._titles[-1])
        if self._body:
            self.query_one(".card-body", Static).update(Text("\n").join(self._body(inner)))
        caption = next((c for c in self._captions if cell_len(c) <= inner), "")
        self.query_one(".card-caption", Static).update(Text(caption, style=MUTED))

    def on_resize(self) -> None:
        self.fit()


class PlatformCard(_Card):
    def __init__(self, platform: Platform):
        super().__init__(platform.color, id=f"card-{platform.key}")
        self.platform = platform
        self._titles = (platform.name, SHORT.get(platform.key, platform.name))
        self.border_title = platform.name

    def show(self, latest, changes: dict, gains: list[float], captions: tuple[str, ...] = ()) -> None:
        p = self.platform
        if latest is not None:
            self.numbers(dict(latest), changes)
        elif not p.has_stats:
            how = "log in once" if p.browser_stats and p.public_handle else "add your handle"
            self.message(Text.assemble(("not tracking yet\n", MUTED), ("Accounts tab: ", MUTED), (how, "bold")))
        else:
            self.message(Text("waiting for the first refresh", style=MUTED))
        self.spark(gains, captions)


class TotalCard(_Card):
    """Followers, views and likes added up across every platform."""

    def __init__(self):
        super().__init__(GOOD, id="card-total")
        self._titles = ("All platforms", "All")
        self.border_title = "All platforms"

    def show(self, totals: dict, changes: dict, gains: list[float], tracked: int,
             captions: tuple[str, ...] = ()) -> None:
        if tracked:
            self.numbers(totals, changes)
        else:
            self.message(Text("no stats yet", style=MUTED))
        self.spark(gains, captions)


class AccountPanel(Vertical):
    """Where one platform's stats come from, how fresh they are, and its log-in / profile / refresh buttons."""

    def __init__(self, platform: Platform, demo: bool):
        super().__init__(classes="account", id=f"acct-{platform.key}")
        self.platform, self.demo = platform, demo
        # The README's pictures show the demo as a set-up account would look (see SCREENSHOTS).
        self.pretend = demo and SCREENSHOTS
        self.logs_in = platform.browser_stats and not demo or self.pretend and platform.key in ("instagram", "x")
        self.border_title = platform.name

    def compose(self) -> ComposeResult:
        # The buttons come right after the status lines, so a short window never pushes them out of sight;
        # the followers chart at the bottom takes whatever room is left.
        key = self.platform.key
        yield Static(classes="acct-body")
        with Horizontal(classes="acct-buttons"):
            if self.logs_in:
                yield Button("Log in", id=f"login-{key}", classes="login-btn", variant="primary")
            yield Button("Open profile", id=f"profile-{key}", classes="profile-btn")
            yield Button("Refresh now", id=f"refresh-{key}", classes="refresh-btn",
                         disabled=self.demo and not self.pretend)
            # Only while ReelForge can't read this platform itself (see show()).
            yield Button("Type in stats", id=f"log-{key}", classes="log-btn")
        yield Static(classes="acct-note")
        yield Static(classes="acct-chart-title")
        yield Plot(classes="acct-chart")

    def on_mount(self) -> None:
        self.styles.border = ("round", self.platform.color)
        self.styles.border_title_color = self.platform.color

    def show(self, latest, info: dict) -> None:
        """info: posts (videos tracked), since (first reading), error (last failed read), due (next refresh)."""
        p = self.platform
        source = "demo" if self.demo and not self.pretend else p.stats_source
        if self.pretend and self.logs_in:
            source = "browser"  # what Instagram and X say once you've logged in
        body = Text()
        if source == "demo":
            body.append("● demo data\n", style=f"bold {GOOD}")
        elif source == "browser":
            body.append(f"● reading {p.handle} through ReelForge's browser\n", style=f"bold {GOOD}")
        elif source == "public":
            body.append(f"● public stats for {p.handle}\n", style=f"bold {GOOD}")
        elif not p.public_handle:
            body.append(f'○ add handle = "@you" under [{p.key}] in config.toml\n', style=f"bold {MUTED}")
        else:
            body.append("○ press Log in once to start tracking\n", style=f"bold {p.color}")
        body.append(f"last refresh {fmt_ago(latest['ts'] if latest else None)}", style=MUTED)
        if info.get("due"):
            body.append(f" · next {info['due']}", style=MUTED)
        body.append("\n")
        if info.get("posts"):
            body.append(f"{info['posts']} videos tracked", style=MUTED)
            if info.get("since"):
                body.append(f" · history since {info['since']}", style=MUTED)
            body.append("\n")
        if info.get("error"):
            body.append(f"last read failed: {info['error']}\n", style=BAD)
        body.rstrip()
        self.query_one(".acct-body", Static).update(body)
        note = "Demo data, made up on this PC." if self.demo and not self.pretend else p.setup_note
        self.query_one(".acct-note", Static).update(Text(note, style=MUTED))
        if self.logs_in:
            self.query_one(f"#login-{p.key}", Button).label = "Log in again" if source == "browser" else "Log in"
        self.query_one(f"#profile-{p.key}", Button).disabled = not p.public_handle and not self.pretend
        self.query_one(f"#log-{p.key}", Button).display = not p.has_stats
        # Followers over time, when there's enough history to draw: (heading, draw, slots, describe(slot)).
        plot, title = self.query_one(Plot), self.query_one(".acct-chart-title", Static)
        self._chart = info.get("chart")
        plot.display = title.display = bool(self._chart)
        if self._chart:
            heading, draw, slots, describe = self._chart
            title.update(heading if plot.hover is None else describe(plot.hover))
            plot.show(draw, slots)

    def on_plot_hovered(self, event: Plot.Hovered) -> None:
        """Pointing at the followers chart shows the number then."""
        event.stop()
        chart = getattr(self, "_chart", None)
        if chart:
            self.query_one(".acct-chart-title", Static).update(chart[0] if event.slot is None else chart[3](event.slot))
