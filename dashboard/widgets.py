"""Reusable pieces of the ReelForge window: the logo, the bell and its drawer, chart panels, bar lists,
platform cards and account panels."""

from __future__ import annotations

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
    """Join title parts, leaving out the least important (highest number) ones until it fits `width`."""
    keep = list(parts)
    while len(keep) > 1 and sum(t.cell_len for t, _ in keep) > width:
        worst = max(range(len(keep)), key=lambda i: (keep[i][1], i))
        if keep[worst][1] == 0:
            break
        keep.pop(worst)
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


def change_text(n: float | None, suffix: str = "") -> Text:
    """+1.2K in green, −40 in red, nothing for no change."""
    if not n:
        return Text("")
    return Text(f"{fmt_delta(n)}{suffix}", style=GOOD if n > 0 else BAD)


WHITE, RED = "#ffffff", "#f0362b"  # the logo's colours: "reel" white, "forge" red
BELL = (" ▄██▄ ", " ████ ", "▀▀██▀▀")  # a bell in half blocks, three rows tall


def anvil_rows() -> list[Text]:
    """ReelForge's anvil, three rows tall (from the kit's logo; a plain stand-in if that can't be loaded)."""
    try:
        from studio import logo

        return logo.rich_text(logo.anvil()).split("\n")
    except Exception:
        return [Text(row, style=WHITE) for row in ("▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀", "    ▀▀███████▀  ", "     ▄▄████▄▄▄  ")]


def brand(channel: str = "") -> Text:
    """The top-left corner: the anvil, "reelforge" in the logo's colours, and your channel's name under it."""
    out = []
    for i, row in enumerate(anvil_rows()):
        line = Text(" ")
        line.append_text(row)
        line.append("  ")
        if i == 1:
            line.append("reel", style=f"bold {WHITE}")
            line.append("forge", style=f"bold {RED}")
        elif i == 2 and channel:
            line.append(channel[:28], style=MUTED)
        out.append(line)
    return Text("\n").join(out)


class Logo(Static):
    """ReelForge's logo and your channel's name, in the top-left corner."""

    def __init__(self, name: str = "", **kwargs):
        super().__init__(brand(name), **kwargs)


class Bell(Static):
    """The notifications button: a bell with a red dot at its top right while something is unread (and how many,
    under the dot, when it's more than one). Click it, or press n, to open the drawer."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.unread = 0

    def show(self, unread: int) -> None:
        self.unread = unread
        self.tooltip = f"{unread} new notification{'s' if unread != 1 else ''} (n)" if unread else "Notifications (n)"
        self.update(self._draw())

    def _draw(self) -> Text:
        out = Text()
        color = "#e8eaed" if self.unread else "#6b7380"
        for i, row in enumerate(BELL):
            if i:
                out.append("\n")
            out.append(row, style=color)
            if i == 0 and self.unread:
                out.append("●", style=f"bold {BAD}")
            elif i == 1 and self.unread > 1:
                out.append(str(self.unread) if self.unread < 10 else "+", style=f"bold {BAD}")
            else:
                out.append(" ")
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
                bar = "█" * int(n) + (EIGHTHS[int((n % 1) * 8)] if (n % 1) * 8 >= 1 else "")
                out.append(f"{label:<{label_w}}", style=color)
                out.append(bar.ljust(bar_w), style=color)
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

    def numbers(self, values: dict, changes: dict) -> None:
        """Three lines that never wrap: the " 24h" after each change goes when the card is too narrow for it."""
        self._numbers = (values, changes)
        width = self.query_one(".card-body", Static).content_region.width or 1000
        shown = {label: fmt_num(values.get(label)) for label in ("followers", "views", "likes")}
        number_w = max(len(s) for s in shown.values()) + (2 if width >= 28 else 0)
        lines = []
        for label in ("followers", "views", "likes"):
            line = Text(f"{shown[label]:>{number_w}} ", style="bold")
            line.append(f"{label:<10}", style=MUTED)
            change = change_text(changes.get(label), " 24h")
            if line.cell_len + change.cell_len > width:
                change = change_text(changes.get(label))
            line.append_text(change)
            lines.append(line)
        self.query_one(".card-body", Static).update(Text("\n").join(lines))

    def on_resize(self) -> None:
        if getattr(self, "_numbers", None):
            self.numbers(*self._numbers)

    def message(self, text: Text) -> None:
        self._numbers = None
        self.query_one(".card-body", Static).update(text)

    def spark(self, gains: list[float], caption: str) -> None:
        spark = self.query_one(Sparkline)
        # A sparkline of all zeros draws as solid blocks, so only show it once views are coming in.
        spark.display = any(gains)
        spark.data = gains or [0]
        self.query_one(".card-caption", Static).update(Text(caption if any(gains) else "", style=MUTED))


class PlatformCard(_Card):
    def __init__(self, platform: Platform):
        super().__init__(platform.color, id=f"card-{platform.key}")
        self.platform = platform
        self.border_title = platform.name

    def show(self, latest, changes: dict, gains: list[float], caption: str = "") -> None:
        p = self.platform
        if latest is not None:
            self.numbers(dict(latest), changes)
        elif not p.has_stats:
            how = "log in once" if p.browser_stats and p.public_handle else "add your handle"
            self.message(Text.assemble(("not tracking yet\n", MUTED), ("Accounts tab: ", MUTED), (how, "bold")))
        else:
            self.message(Text("waiting for the first refresh", style=MUTED))
        self.spark(gains, caption)


class TotalCard(_Card):
    """Followers, views and likes added up across every platform."""

    def __init__(self):
        super().__init__(GOOD, id="card-total")
        self.border_title = "All platforms"

    def show(self, totals: dict, changes: dict, gains: list[float], tracked: int, caption: str = "") -> None:
        if tracked:
            self.numbers(totals, changes)
        else:
            self.message(Text("no stats yet", style=MUTED))
        self.spark(gains, caption)


class AccountPanel(Vertical):
    """Where one platform's stats come from, how fresh they are, and its log-in / profile / refresh buttons."""

    def __init__(self, platform: Platform, demo: bool):
        super().__init__(classes="account", id=f"acct-{platform.key}")
        self.platform, self.demo = platform, demo
        self.border_title = platform.name

    def compose(self) -> ComposeResult:
        # The buttons come right after the status lines, so a short window never pushes them out of sight;
        # the followers chart at the bottom takes whatever room is left.
        key = self.platform.key
        yield Static(classes="acct-body")
        with Horizontal(classes="acct-buttons"):
            if self.platform.browser_stats and not self.demo:
                yield Button("Log in", id=f"login-{key}", classes="login-btn", variant="primary")
            yield Button("Open profile", id=f"profile-{key}", classes="profile-btn")
            yield Button("Refresh now", id=f"refresh-{key}", classes="refresh-btn", disabled=self.demo)
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
        source = "demo" if self.demo else p.stats_source
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
        note = "Demo data, made up on this PC." if self.demo else p.setup_note
        self.query_one(".acct-note", Static).update(Text(note, style=MUTED))
        if p.browser_stats and not self.demo:
            self.query_one(f"#login-{p.key}", Button).label = "Log in again" if source == "browser" else "Log in"
        self.query_one(f"#profile-{p.key}", Button).disabled = not p.public_handle
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
