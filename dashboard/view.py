"""Styled text for ReelForge's window, as the Python side sends it to the OpenTUI frontend in ui/.

A Text is a run of segments, each [text, style] or [text, style, action]: style is a few words such as
"bold #3dff9a on #1f5c45" (bold, dim, italic, underline, strike, a text colour, "on" and a background colour), and
an action makes that piece clickable (a chip, a key on a chart): ["set_range", "7d"] runs the action set_range with
the argument "7d" (ui/src/dashboard/actions.ts). Parts are (Text, importance) pairs that the frontend fits to the
room it has, leaving out the least important (highest number) first (ui/src/lib/fit.ts).

The colours every view shares are here too, and short_num, the shortest way to write a number.
"""

from __future__ import annotations

import unicodedata

BACKGROUND = "#0a0c0f"
MUTED = "#8b93a1"
GOOD = "#3dff9a"
BAD = "#ff4d5e"
TYPICAL = "#ffb020"  # the "typical video" line: amber, unlike any platform colour
MARK = "#ffcc33"     # chart marks and hovered values
SHORT = {"tiktok": "TT", "youtube": "YT", "instagram": "IG", "x": "X"}


def cell_len(text: str) -> int:
    """Terminal columns the text takes: wide characters (CJK, most emoji) take two."""
    return sum(0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in "WF" else 1
               for ch in text)


def _under(base: str, style: str) -> str:
    """style on top of base: the later words win (a second colour replaces the first)."""
    return f"{base} {style}" if base and style else base or style


class Text:
    """A line (or lines) of styled segments; the few parts of rich.text.Text's API ReelForge uses.

    As with rich, the style a Text is made with is its base style: it's under everything appended to it later too, so
    Text("✓ ", GOOD).append(name) draws the name green as well."""

    def __init__(self, text: str = "", style: str = "", act: list | None = None):
        self.style = style
        self.segs: list[list] = []  # each piece with its own style, the base style not yet under it
        if text:
            self.append(text, "", act)

    def append(self, text: str, style: str = "", act: list | None = None) -> "Text":
        if text:
            self.segs.append([text, style, act] if act else [text, style])
        return self

    def append_text(self, other: "Text") -> "Text":
        self.segs.extend(list(s) for s in other.json())
        return self

    @classmethod
    def assemble(cls, *parts) -> "Text":
        """Text.assemble(("bold part", "bold"), "plain part", other_text)"""
        out = cls()
        for part in parts:
            if isinstance(part, Text):
                out.append_text(part)
            elif isinstance(part, str):
                out.append(part)
            else:
                out.append(*part)
        return out

    def copy(self) -> "Text":
        out = Text(style=self.style)
        out.segs = [list(s) for s in self.segs]
        return out

    def __add__(self, other: "Text") -> "Text":
        return self.copy().append_text(other)

    @property
    def plain(self) -> str:
        return "".join(s[0] for s in self.segs)

    @property
    def cell_len(self) -> int:
        return cell_len(self.plain)

    def __len__(self) -> int:
        return len(self.plain)

    def __str__(self) -> str:
        return self.plain

    def __repr__(self) -> str:
        return f"Text({self.plain!r})"

    def json(self) -> list:
        if not self.style:
            return self.segs
        return [[s[0], _under(self.style, s[1]), *s[2:]] for s in self.segs]


def js(value):
    """Texts (and parts made of them) as the plain lists the frontend reads."""
    if isinstance(value, Text):
        return value.json()
    if isinstance(value, (list, tuple)):
        return [js(v) for v in value]
    if isinstance(value, dict):
        return {k: js(v) for k, v in value.items()}
    return value


def parts(items: list[tuple[Text, int]]) -> list:
    """(Text, importance) parts as [[segments], importance]."""
    return [[t.json(), i] for t, i in items]


def act(name: str, *args) -> list:
    return [name, *args]


def chip(label: str, action: list | None, active: bool = False) -> Text:
    """A small button inside text: runs its action when clicked. An active chip shows a selected state."""
    if active or action is None:
        return Text(f" {label} ", "bold #ffffff on #1f5c45")
    return Text(f" {label} ", "#c9d1d9 on #1c222b", action)


def chips(*items, gap: str = " ") -> Text:
    """Several chips in a row: each item is (label, action) or (label, action, active)."""
    out = Text()
    for i, item in enumerate(items):
        if i:
            out.append(gap)
        out.append_text(chip(*item))
    return out


def tag(p) -> Text:
    return Text(f"● {SHORT.get(p.key, p.key)}", f"bold {p.color}")


def num(n, style: str = "") -> Text:
    from .analytics import fmt_num

    return Text(fmt_num(n), style)


def score_text(score: float | None) -> Text:
    if score is None:
        return Text("—", MUTED)
    style = f"bold {GOOD}" if score >= 2 else GOOD if score >= 1.2 else BAD if score < 0.6 else ""
    return Text(f"{score:.1f}×", style)


def change_text(n: float | None, suffix: str = "") -> Text:
    """+1.2K in green, −40 in red, nothing for no change."""
    from .analytics import fmt_delta

    if not n:
        return Text("")
    return Text(f"{fmt_delta(n)}{suffix}", GOOD if n > 0 else BAD)


def legend(platforms, hidden: set[str] = frozenset(), toggle: str = "toggle_line", short: bool = False) -> Text:
    """Platform key for a chart; click a name to hide or show it (hidden ones are struck through)."""
    out = Text()
    for p in platforms:
        off = p.key in hidden
        style = "strike #4a515c" if off else f"bold {p.color}"
        name = SHORT.get(p.key, p.key) if short else p.name
        out.append(f"■ {name}", style, [toggle, p.key])
        out.append("  ")
    return out


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
