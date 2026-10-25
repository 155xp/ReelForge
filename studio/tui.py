"""What setup's screens and onboarding share: ReelForge's colours, the box drawn round the whole terminal, and the
logo at the top of it."""

from __future__ import annotations

import os
import sys

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.theme import Theme
from textual.widgets import Static

from . import logo

THEME = Theme(
    name="reelforge",
    primary="#e8213a",
    secondary="#8a94a3",
    accent="#ffffff",
    foreground="#e8eaed",
    background="#000000",
    surface="#0d0f12",
    panel="#15181d",
    success="#4ade80",
    warning="#ffc83a",
    error="#ff5a4e",
    dark=True,
)

# Windows Terminal (and every macOS/Linux terminal) draws ✓; the old Windows console font doesn't.
FANCY = not sys.platform.startswith("win") or bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"))
CHECK = "✓" if FANCY else "√"
CROSS = "✗" if FANCY else "x"

STEPS = [("tools", "Get the tools"), ("channel", "Your channel"), ("ready", "Ready")]

CSS = """
Screen { background: $background; }
.framed #frame {
    border: double $primary;
    border-title-align: center;
    border-title-color: $foreground;
    border-subtitle-align: right;
    border-subtitle-color: $text-muted;
    padding: 0 2;
    height: 1fr;
}
#brand { width: 100%; height: auto; content-align: center top; padding-top: 1; }
#brand.big { padding-bottom: 1; }
#body { height: 1fr; }
Button:focus { text-style: bold underline; }
.muted { color: $text-muted; }
.ok { color: $success; }
.bad { color: $error; }
.warn { color: $warning; }
"""


def wordmark(bold: bool = True) -> Text:
    """'reelforge' in the logo's colours, as plain text."""
    style = "bold " if bold else ""
    return Text.assemble(("reel", style + logo.WHITE), ("forge", style + logo.RED))


def small_brand() -> Text:
    """The anvil with the name beside it, three rows tall."""
    art = logo.rich_text(logo.anvil()).split("\n")
    lines = []
    for i, row in enumerate(art):
        line = Text()
        line.append_text(row)
        if i == 1:
            line.append("  ")
            line.append_text(wordmark())
        lines.append(line)
    return Text("\n").join(lines)


def step_title(current: str) -> Text:
    """The frame's title: the three first-run steps, the current one lit."""
    t = Text(" ")
    keys = [k for k, _ in STEPS]
    here = keys.index(current) if current in keys else -1
    for n, (key, label) in enumerate(STEPS):
        if n:
            t.append("  ·  ", style="#5b6270")
        if n < here:
            t.append(f"{CHECK} {label}", style="#4ade80")
        elif n == here:
            t.append(f"{n + 1} {label}", style="bold #ffffff")
        else:
            t.append(f"{n + 1} {label}", style="#8a94a3")
    t.append(" ")
    return t


class Brand(Static):
    """The logo: the full one when the window has room for it, otherwise the anvil and the name."""

    def __init__(self, big_min_height: int, **kw):
        super().__init__(**kw)
        self.big_min_height = big_min_height

    def redraw(self, width: int, height: int) -> None:
        px = logo.big()
        if width >= logo.width(px) + 8 and height >= self.big_min_height:
            self.update(logo.rich_text(px))
        else:
            self.update(small_brand())


class Framed(Screen):
    """A screen inside one double-line box round the whole terminal, with the logo at the top.

    Subclasses yield their content from body(). STEP lights a step in the frame's title; BIG_MIN_HEIGHT is the
    terminal height from which the full logo shows (below it, the anvil and the name)."""

    STEP = ""
    BIG_MIN_HEIGHT = 30
    HINT = "Esc to leave"

    def compose(self) -> ComposeResult:
        with Vertical(id="frame"):
            yield Brand(self.BIG_MIN_HEIGHT, id="brand")
            with Vertical(id="body"):
                yield from self.body()

    def body(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.add_class("framed")
        frame = self.query_one("#frame")
        frame.border_title = step_title(self.STEP) if self.STEP else Text.assemble(" ", wordmark(), " ")
        frame.border_subtitle = self.HINT
        self._redraw_brand(self.app.size.width, self.app.size.height)

    def on_resize(self, event: events.Resize) -> None:
        self._redraw_brand(event.size.width, event.size.height)

    def _redraw_brand(self, width: int, height: int) -> None:
        brand = self.query_one(Brand)
        brand.redraw(width, height)
        big = height >= self.BIG_MIN_HEIGHT and width >= logo.width(logo.big()) + 8
        brand.set_class(big, "big")
