"""ReelForge's window: stats for TikTok, YouTube, Instagram and X, help posting by hand, notifications and updates."""

from __future__ import annotations

import functools
import math
import textwrap
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median

from rich.style import Style
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.css.scalar import ScalarOffset
from textual.theme import Theme
from textual.widgets import (Button, DataTable, Input, Label, Markdown, OptionList, ProgressBar, Static, TabbedContent,
                             TabPane)
from textual.widgets.data_table import ColumnKey
from textual.widgets.option_list import Option

from . import analytics, badges, charts, config, db, desktop, notify, sync, trends, videos
from .analytics import fmt_age, fmt_ago, fmt_clock, fmt_delta, fmt_num, fmt_pct
from .platforms import Platform, PlatformError, PublishItem, browser
from .platforms.base import Account, Post
from .screens import EpisodePicker, HelpScreen, LogStats, VideoMenu
from .widgets import (BAD, GOOD, MUTED, SHORT, TYPICAL, AccountPanel, ActionText, Bars, Bell, ChartPanel, Logo,
                      PlatformCard, TotalCard, VideoList, change_text, chip, chips, clickable, legend, num,
                      score_text, tag)

try:  # the ReelForge folder's own package: its version and the updater
    from studio import KIT_VERSION
    from studio import update as kit_update
except Exception:  # run on its own, outside a ReelForge folder
    KIT_VERSION, kit_update = "", None

THEME = Theme(
    name="reelforge-dashboard",
    primary="#3dff9a",
    secondary="#7aa2f7",
    accent="#ffcc33",
    foreground="#d7dde6",
    background="#0a0c0f",
    surface="#101318",
    panel="#161a21",
    success="#3dff9a",
    warning="#ffcc33",
    error="#ff4d5e",
    dark=True,
)

METRICS = ("views", "followers", "likes")
TOP_COLUMNS = [("title", "Title", 20), ("age_h", "Age", 5), ("views", "Views", 8), ("score", "Score", 7)]
VIDEO_COLUMNS = [  # (key, label, width)
    ("platform", "", 4), ("title", "Title", 40), ("age_h", "Age", 5), ("views", "Views", 8), ("likes", "Likes", 7),
    ("comments", "Cmts", 6), ("shares", "Shares", 6), ("eng", "Eng", 6), ("share_rate", "Share", 6),
    ("vph", "Views/h", 7), ("score", "Score", 6), ("pscore", "On plat.", 8),
]
HISTORY_DAYS = 62  # account history kept in memory: the longest range (30 days) and the one before it
TABS = ("overview", "videos", "compare", "publish", "accounts", "updates")
UPDATE_EVERY_H = 6  # how often ReelForge asks GitHub whether there's a newer version


def db_safe(method):
    """For things you do on screen that write to the database: if it's busy (ReelForge tidying it, a scheduled refresh),
    say so instead of crashing."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except sqlite3.OperationalError as e:
            self.notify(f"The stats database is busy ({e}). Try again in a moment.", severity="warning", timeout=8)

    return wrapper


def minutes_setting(cfg: dict, key: str, default: float) -> float:
    try:
        return max(float(cfg.get(key, default)), 0.0)
    except (TypeError, ValueError):
        return default


class ReelForge(App):
    CSS_PATH = "app.tcss"
    TITLE = "ReelForge"
    # Only tabs and refresh have keys; everything else is a button on the page it applies to.
    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("R", "refresh(True)", "Force refresh", show=False),
        Binding("1", "tab('overview')", "Overview", show=False),
        Binding("2", "tab('videos')", "Videos", show=False),
        Binding("3", "tab('compare')", "Compare", show=False),
        Binding("4", "tab('publish')", "Publish", show=False),
        Binding("5", "tab('accounts')", "Accounts", show=False),
        Binding("6", "tab('updates')", "Updates", show=False),
        Binding("escape", "leave_field", "Leave field", show=False),
    ]

    def __init__(self, cfg: dict, platforms: dict[str, Platform], demo: bool = False, tab: str = "overview",
                 drawer: bool = False):
        super().__init__()
        # No animations: the tab underline (and scrolling) jump straight to where they're going.
        self.animation_level = "none"
        self.cfg, self.platforms, self.demo = cfg, platforms, demo
        self.start_tab = tab if tab in TABS else "overview"
        self.start_drawer = drawer
        name = config.channel_name(cfg)
        self.title = f"ReelForge · {name}" if name else "ReelForge"
        self.note_seen = 0  # the newest notification already shown as a pop-up
        self.update_info: dict | None = None  # the last answer from the update check (studio.update.check)
        self.updating = False
        self.badge_list: list = []  # the account's badges on the Overview
        self.first_day: dict = {}  # (platform, post id) -> views at the first reading about a day after posting
        saved = db.get_meta("overview_range", "24h")
        self.range = saved if saved in trends.RANGES else "24h"
        self.filter: str | None = None
        self.sort = ("score", True)
        self.top_sort = ("score", True)  # Top performers: (column, descending)
        self.compare_target = "board"
        self.selected_file: Path | None = None
        self.status = ""
        self.posts: list[dict] = []
        self.parsed: analytics.Series = {}
        self.latest: dict = {}
        self.episodes: list = []
        self.account_rows: dict[str, list] = {}
        self.stale: set[str] = set()  # tabs to rebuild when next opened
        self.post_check_timers: list = []
        self.hidden_lines: set[str] = set()  # platforms switched off in the chart keys
        self.hidden_curves: set[str] = set()  # "this" / "typical" switched off in the video chart
        self.trend_state: dict[str, tuple] = {}  # metric -> (frame, series, summary)
        self.detail_state: tuple | None = None  # (post, span, series) for the Videos chart
        self.compare_state: dict[str, tuple] = {}  # platform -> (title, series) for the Compare charts

    # --- layout ---------------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        ps = list(self.platforms.values())
        with Horizontal(id="header"):
            yield Logo(config.channel_name(self.cfg), id="logo")
            yield ActionText(id="status")
            yield ActionText(chips(("Refresh", "refresh"), ("Help", "help"), ("Quit", "quit")), id="actions")
            yield Bell(id="bell")
        with Horizontal(id="main"):
            yield from self.compose_tabs(ps)
            with Vertical(id="drawer"):
                yield ActionText(id="drawer-head")
                yield OptionList(id="notes")

    def compose_tabs(self, ps: list[Platform]) -> ComposeResult:
        with TabbedContent(initial=self.start_tab):
            with TabPane("Overview", id="overview"):
                with Horizontal(id="cards"):
                    yield TotalCard()
                    for p in ps:
                        yield PlatformCard(p)
                yield ActionText(id="badges")
                with Horizontal(id="overview-main"):
                    with Vertical(id="trends"):
                        yield ActionText(id="trends-bar")
                        yield ChartPanel(id="views-chart")
                        with Horizontal(id="trends-row"):
                            yield ChartPanel(id="followers-chart")
                            yield ChartPanel(id="likes-chart")
                    with Vertical(id="side"):
                        with Vertical(id="top-box", classes="box"):
                            yield ActionText(id="top-title", classes="box-title")
                            yield DataTable(id="top-table", cursor_type="row")
                        with Vertical(id="latest-box", classes="box"):
                            yield ActionText(id="latest-title", classes="box-title")
                            yield Static(id="latest-body")
            with TabPane("Videos", id="videos"):
                yield ActionText(id="videos-hint", classes="hint")
                yield DataTable(id="videos-table", cursor_type="row", zebra_stripes=True)
                yield ActionText(id="video-badges")
                yield ChartPanel(id="video-detail")
            with TabPane("Compare", id="compare"):
                with Horizontal():
                    yield OptionList(id="episode-list")
                    with VerticalScroll(id="compare-main"):
                        with Vertical(id="compare-bars-box", classes="box"):
                            yield ActionText(id="compare-heading", classes="box-title")
                            yield Bars(id="compare-bars")
                        with Grid(id="compare-grid"):
                            for p in ps:
                                yield ChartPanel(id=f"compare-{p.key}")
                        yield DataTable(id="compare-table", cursor_type="row")
            with TabPane("Publish", id="publish"):
                with Horizontal():
                    with Vertical(id="file-box", classes="box"):
                        yield ActionText(id="file-heading", classes="box-title")
                        yield VideoList(id="file-list")
                    with VerticalScroll(id="publish-form", classes="box"):
                        yield Label("Caption", id="caption-label")
                        yield Input(id="f-caption", max_length=200, placeholder="one short line that hooks the viewer")
                        yield Label("Hashtags", id="tags-label")
                        yield Input(id="f-tags", value=self.cfg.get("default_tags", ""), placeholder=(f"#{videos.FIRST_TAG} " if videos.FIRST_TAG else "") + "#tag #tag")
                        yield Static(id="preview")
                        yield Static(id="posted")
                        yield Static(Text.assemble(
                            ("UPLOAD  ", "bold"),
                            ("each button opens the upload page, copies that platform's text and shows the file",
                             MUTED),
                        ), classes="box-title", id="manual-heading")
                        # Each copy button sits under its platform's button, both as wide as the wider label.
                        copies = {"tiktok": ("copy-tiktok", "Copy TikTok text"),
                                  "youtube": ("copy-youtube", "Copy YouTube hashtags"),
                                  "instagram": ("copy-instagram", "Copy Instagram text"),
                                  "x": ("copy-caption", "Copy caption")}  # the caption is the X text
                        widths = {p.key: max(len(f"{p.name} →"), len(copies.get(p.key, ("", ""))[1])) + 4 for p in ps}
                        open_all = f"Open all {len(ps)} →"
                        with Horizontal(classes="manual-row"):
                            btn = Button(open_all, id="open-all", variant="primary")
                            btn.styles.width = len(open_all) + 4
                            yield btn
                            for p in ps:
                                btn = Button(f"{p.name} →", id=f"open-{p.key}", classes="open-btn")
                                btn.styles.width = widths[p.key]
                                yield btn
                            yield Button("Show file", id="reveal")
                        with Horizontal(classes="manual-row"):
                            spacer = Static(classes="copy-spacer")
                            spacer.styles.width = len(open_all) + 4  # under "Open all"
                            yield spacer
                            for p in ps:
                                if p.key in copies:
                                    btn_id, label = copies[p.key]
                                    btn = Button(label, id=btn_id, classes="copy-btn")
                                    btn.styles.width = widths[p.key]
                                    yield btn
                            if "x" not in self.platforms:
                                yield Button("Copy caption", id="copy-caption", classes="copy-btn")
                        yield ActionText(id="uploads-heading", classes="box-title")
                        yield DataTable(id="uploads-table", cursor_type="row")
            with TabPane("Accounts", id="accounts"):
                with Grid(id="accounts-grid"):
                    for p in ps:
                        yield AccountPanel(p, self.demo)
            with TabPane("Updates", id="updates"):
                with Vertical(id="update-box", classes="box"):
                    yield Static(id="update-status")
                    with Horizontal(id="update-buttons"):
                        yield Button("Update and restart", id="update-apply", variant="primary")
                        yield Button("Check now", id="update-check")
                        yield Button("Release page", id="update-page")
                    yield ProgressBar(id="update-progress", show_eta=False)
                    yield Static(id="update-step")
                with VerticalScroll(id="update-notes-box", classes="box"):
                    yield Static(Text("WHAT'S NEW", style="bold"), classes="box-title")
                    yield Markdown(id="update-notes")
                yield Static(id="update-how", classes="hint")

    def on_mount(self) -> None:
        self.register_theme(THEME)
        self.theme = THEME.name
        self.note_seen = self._safe(notify.newest_id, 0)  # what's already there shows in the drawer, not as pop-ups
        self.query_one("#drawer").display = self.start_drawer
        top = self.query_one("#top-table", DataTable)
        top.add_column("", width=4, key="platform")
        for key, label, width in TOP_COLUMNS:
            top.add_column(label, width=width, key=key)
        table = self.query_one("#videos-table", DataTable)
        for key, label, width in VIDEO_COLUMNS:
            table.add_column(label, key=key, width=width)
        uploads = self.query_one("#uploads-table", DataTable)
        for label, width in (("When", 8), ("", 4), ("Video", 26), ("", 2), ("Post", 64)):
            uploads.add_column(label, width=width)
        self.query_one("#episode-list", OptionList).border_title = "EPISODES"
        self.query_one("#uploads-heading", ActionText).update(Text("RECENT UPLOADS", style="bold"))

        self.last_seen = db.get_meta("last_seen")  # totals when ReelForge was last open, for "since you last looked"
        self.reload()
        self.scan_files()
        self.update_notes()
        self.start_updates()
        self.run_refresh(manual=False)
        self.compact_db()
        minutes = minutes_setting(self.cfg, "refresh_minutes", 30)
        if minutes:
            self.set_interval(min(300, max(minutes * 60, 60)), lambda: self.run_refresh(manual=False))
        self.set_interval(30, self.tick)
        # Say what changed while ReelForge was closed once the first refresh is in (or after a while without one).
        self.set_timer(45, self.welcome_back)

    def totals(self) -> dict[str, float | None]:
        out = {}
        for f in METRICS:
            values = [r[f] for k, r in self.latest.items() if k in self.platforms and r[f] is not None]
            out[f] = sum(values) if values else None
        return out

    def welcome_back(self) -> None:
        """Once per start: how much changed since ReelForge was last open."""
        seen, self.last_seen = self.last_seen, None
        now = self.totals()
        if seen is not None and seen.get("ts"):
            hours = (analytics.now() - db.parse(seen["ts"])).total_seconds() / 3600
            gains = [(f, now[f] - seen[f]) for f in ("views", "followers", "likes")
                     if now.get(f) is not None and seen.get(f) is not None and now[f] != seen[f]]
            if hours >= 1 and gains:
                self.notify(" · ".join(f"{fmt_delta(g)} {f}" for f, g in gains),
                            title=f"Since you last looked ({fmt_age(hours)} ago)", timeout=20)
        self.save_seen()

    @db_safe
    def save_seen(self) -> None:
        if self.last_seen is None and not self.demo and any(v is not None for v in self.totals().values()):
            db.set_meta("last_seen", {"ts": db.now_iso(), **self.totals()})

    @db_safe
    def celebrate(self) -> None:
        """A notification for a new video doing 3x your typical one in its first 12 hours (once per video), and for
        each badge a video or the account moves up to. Milestones come from the refresh itself."""
        for p in self.posts:
            if p["score"] and p["score"] >= 3 and p["age_h"] <= 12 and (p["views"] or 0) >= 100:
                notify.add("hot", f"Taking off on {self.platforms[p['platform']].name}",
                           f"{(p['title'] or 'A video')[:60]} is doing {p['score']:.1f}× your typical video.",
                           key=f"hot:{p['platform']}|{p['post_id']}")
        badges.notify_new(self.posts, self.first_day, self.account_rows, self.platforms)

    def show_new_notes(self) -> None:
        """Pop up what's been added since the last look (a few at most), then refresh the bell and the drawer."""
        new = self._safe(lambda: notify.since(self.note_seen), [])
        for n in new[-4:]:
            kind = notify.KINDS.get(n["kind"], notify.KINDS["info"])
            self.notify(n["body"] or "", title=f"{kind[0]} {n['title']}", timeout=12,
                        severity="error" if n["kind"] == "login" else "information")
        if new:
            self.note_seen = new[-1]["id"]
        self.update_notes()

    def _safe(self, fn, default):
        """For reads that are extras (notifications, update info): a busy database shouldn't stop anything."""
        try:
            return fn()
        except sqlite3.Error:
            return default

    def tick(self) -> None:
        """Every half minute: the "updated" time, and the charts once a new hour (or day) starts."""
        self.update_header()
        fr = self.trend_state.get("views", (None,))[0]
        if fr is not None and analytics.now() >= fr.ends[-1]:
            self.update_trends()
            self.update_cards()

    # --- data -----------------------------------------------------------------------------

    @work(thread=True, exclusive=True, group="refresh", exit_on_error=False)
    def run_refresh(self, manual: bool, force: bool = False, only: str | None = None) -> None:
        platforms = {only: self.platforms[only]} if only in self.platforms else self.platforms
        try:
            done, errors = sync.refresh(platforms, self.cfg, manual, force,
                                        on_status=lambda s: self.call_from_thread(self.set_status, s))
            # Crunch the numbers here, off the UI thread, so the screen never stalls.
            data = self.load_data() if done else None
        except Exception as e:  # the database was busy, say: report it, keep running
            done, errors, data = [], [f"{type(e).__name__}: {e}"], None
        self.call_from_thread(self.after_refresh, done, errors, manual, data)

    def after_refresh(self, done: list[str], errors: list[str], manual: bool, data: dict | None) -> None:
        self.set_status("")
        for e in errors:
            self.notify(e, title="Refresh failed", severity="error", timeout=10)
        if done:
            self.reload(data)
            self.celebrate()
            self.show_new_notes()
            if self.last_seen is not None:
                self.welcome_back()
            else:
                self.save_seen()
        else:
            self.update_accounts()
            if manual and not errors:
                if not any(p.has_stats for p in self.platforms.values()):
                    self.notify("Nothing to read yet: add your handles in config.toml, or log in on the Accounts tab.")
                else:
                    self.notify("Up to date. Platforms read through the browser wait a bit between reads; "
                                "R reads them anyway.")

    @work(thread=True, group="maintenance", exit_on_error=False)
    def compact_db(self) -> None:
        try:
            db.compact()
        except Exception:
            pass  # thinning old snapshots can wait for the next start

    def load_data(self) -> dict:
        """Everything the screens show, from the database. Safe to run on a worker thread."""
        parsed = analytics.parse_series(db.post_series(analytics.history_since()))
        since = (analytics.now() - timedelta(days=HISTORY_DAYS)).isoformat(timespec="seconds")
        posts = [p for p in db.posts_latest() if p["platform"] in self.platforms and p["published_at"]]
        return {
            "parsed": parsed,
            "posts": analytics.enrich(posts, parsed),
            "latest": db.latest_accounts(),
            "episodes": db.episodes(),
            "account_rows": {key: db.account_series(key, since) for key in self.platforms},
            "first_day": badges.first_day_views(),
        }

    def reload(self, data: dict | None = None) -> None:
        data = data or self.load_data()
        self.parsed, self.posts, self.latest = data["parsed"], data["posts"], data["latest"]
        self.episodes, self.account_rows = data["episodes"], data["account_rows"]
        self.first_day = data["first_day"]
        self.update_header()
        self.update_overview()
        self.update_badges()
        self.update_uploads()
        self.update_accounts()
        self.update_posted()
        # Tabs you're not looking at are rebuilt when you open them.
        self.stale = {"videos", "compare"}
        self.update_active_tab()

    def update_active_tab(self) -> None:
        tab = self.query_one(TabbedContent).active
        if tab in self.stale:
            self.stale.discard(tab)
            if tab == "videos":
                self.update_videos()
            else:
                self.update_episode_list()
                self.update_compare()

    @on(TabbedContent.TabActivated)
    def tab_opened(self) -> None:
        self.update_active_tab()
        if self.query_one(TabbedContent).active == "publish":
            self.scan_files()

    def set_status(self, text: str) -> None:
        self.status = text
        self.update_header()

    def update_header(self) -> None:
        t = Text()
        if self.demo:
            t.append(" DEMO ", style="bold #0a0c0f on #ffcc33")
            t.append("   ")
        for p in self.platforms.values():
            live = p.has_stats or p.key in self.latest  # typed-in stats count too
            failed = p.key in sync.last_errors
            color = BAD if failed else p.color if live else "#4a515c"
            t.append("● " if live else "○ ", style=Style(color=color) + clickable("tab('accounts')"))
            t.append(p.name, style=Style(color=color, bold=live) + clickable("tab('accounts')"))
            t.append("    ")
        stamps = [r["ts"] for r in self.latest.values()]
        t.append(f"updated {fmt_ago(max(stamps) if stamps else None)}", style=MUTED)
        if self.status:
            t.append(f"    {self.status}", style="#ffcc33")
        self.query_one("#status", ActionText).update(t)

    # --- overview -------------------------------------------------------------------------

    def update_overview(self) -> None:
        self.update_cards()
        self.update_trends()
        self.update_top()
        self.update_latest()

    def update_cards(self) -> None:
        """The All platforms card and one per platform: totals, 24-hour change, and views per hour."""
        fr = trends.frame("24h", analytics.now())
        caption = "views per hour · last 24h"
        sums: list[float | None] = [None] * fr.n
        totals: dict[str, list] = {f: [] for f in METRICS}
        changes: dict[str, list] = {f: [] for f in METRICS}
        for p in self.platforms.values():
            rows = self.account_rows.get(p.key, [])
            latest = self.latest.get(p.key)
            change = {f: trends.change(rows, f, 24) for f in METRICS}
            gains = trends.bucket(trends.points(rows, "views"), fr).gains
            for i, g in enumerate(gains):
                if g is not None:
                    sums[i] = (sums[i] or 0) + g
            self.query_one(f"#card-{p.key}", PlatformCard).show(latest, change, _from_first(gains), caption)
            for f in METRICS:
                if latest is not None and latest[f] is not None:
                    totals[f].append(latest[f])
                if change[f] is not None:
                    changes[f].append(change[f])
        self.query_one("#card-total", TotalCard).show(
            {f: sum(v) if v else None for f, v in totals.items()},
            {f: sum(v) if v else None for f, v in changes.items()},
            _from_first(sums), sum(1 for k in self.platforms if k in self.latest), caption)

    def update_trends(self) -> None:
        fr = trends.frame(self.range, analytics.now())
        ranges = Text()
        for key, (label, _, _) in trends.RANGES.items():
            ranges.append_text(chip(label, f"set_range('{key}')", key == self.range))
            ranges.append(" ")
        ranges.append("   ")
        def parts(width: int) -> list:
            full = legend(self.platforms.values(), self.hidden_lines)
            short = ranges.cell_len + full.cell_len + 8 > width  # TT YT IG X when the full names don't fit
            return [(ranges, 0), (legend(self.platforms.values(), self.hidden_lines, short=short), 0),
                    (Text("   ▼ video posted", style=charts.MARK), 1)]

        self.query_one("#trends-bar", ActionText).set_parts(parts)
        visible = [p for p in self.platforms.values() if p.key not in self.hidden_lines]
        marks = self.post_marks(fr)
        for metric in METRICS:
            self.draw_metric(metric, fr, visible, marks)

    def draw_metric(self, metric: str, fr: trends.Frame, visible: list[Platform], marks: list[charts.Mark]) -> None:
        """Bars of what each platform gained per bucket, stacked; the title carries the total."""
        panel = self.query_one(f"#{metric}-chart", ChartPanel)
        pts = {p.key: trends.points(self.account_rows.get(p.key, []), metric) for p in visible}
        pts = {k: v for k, v in pts.items() if v}
        if not pts:
            self.trend_state.pop(metric, None)
            panel.set_title(Text(metric.upper(), style="bold"))
            panel.show_empty("Every platform is hidden: click a name above to show it again." if not visible
                             else None)
            return
        per = {k: trends.bucket(v, fr) for k, v in pts.items()}
        series = []
        for p in visible:
            if p.key in per:
                b = per[p.key]
                faint = [i == fr.n - 1 for i in range(fr.n)]          # the hour still filling up
                series.append(charts.Series(p.key, p.name, p.color, values=b.gains, faint=faint))
        self.trend_state[metric] = (fr, series, trends.summarise(pts, fr))
        panel.set_title(self.metric_title(metric, panel.plot.hover))

        def draw(w: int, h: int, hover: int | None):
            return charts.bars(series, fr.n, w, h, _clock(fr), marks, hover)

        panel.draw(draw, fr.n)

    def metric_title(self, metric: str, slot: int | None = None) -> list[tuple[Text, int]]:
        """The chart's title as (text, importance) parts: the numbers that matter, or the hovered bar's."""
        fr, series, s = self.trend_state[metric]
        span = trends.RANGES[self.range][0].lower()
        parts = [(Text(f"{metric.upper()}  ", style="bold"), 0)]
        if slot is not None and 0 <= slot < fr.n:
            parts.append((Text(_slot_label(fr, slot) + "  ", style=f"bold {charts.MARK}"), 0))
            vals = [(x, x.values[slot]) for x in series if slot < len(x.values) and x.values[slot] is not None]
            if not vals:
                parts.append((Text("no readings yet", style=MUTED), 0))
                return parts
            parts.append((Text(f"+{fmt_num(sum(v for _, v in vals))}  ", style="bold"), 0))
            for x, v in vals:
                parts.append((Text(f"{SHORT.get(x.key, x.key)} {fmt_num(v)}  ", style=x.color), 1))
            if slot == fr.n - 1:
                parts.append((Text("so far", style=MUTED), 2))
            return parts
        unit = {"h": "per hour", "day": "per day"}.get(fr.unit(), f"per {fr.unit()}")
        parts.append((Text(unit + "   ", style=MUTED), 5))
        if s.latest is not None:
            parts.append((Text.assemble((fmt_num(s.latest), "bold"), (" total   ", MUTED)), 0))
        if s.gained:
            parts.append((Text.assemble(change_text(s.gained), (f" in {span}   ", MUTED)), 1))
        if s.pace is not None and fr.hourly:
            parts.append((Text(f"now {fmt_num(s.pace)}/h   ", style=MUTED), 2))
        if s.change is not None:
            up = s.change >= 0
            parts.append((Text(f"{'▲' if up else '▼'} {abs(s.change) * 100:.0f}% vs the {span} before   ",
                               style=GOOD if up else BAD), 3))
        if s.best:
            parts.append((Text(f"best {fmt_num(s.best)} {_when(fr, s.best_at)}", style=MUTED), 4))
        return parts

    def post_marks(self, fr: trends.Frame) -> list[charts.Mark]:
        """A mark at the moment each video first went up (videos with at least one post)."""
        posted = {p["episode_id"] for p in self.posts if p["episode_id"]}
        titles = [e["title"] for e in self.episodes]
        marks = []
        for e in self.episodes:
            if e["id"] not in posted or not e["first_post"]:
                continue
            t = db.parse(e["first_post"]).astimezone()
            i = fr.index(t)
            if i is not None:
                frac = (t - fr.starts[i]) / (fr.ends[i] - fr.starts[i])
                marks.append(charts.Mark(i + frac, trends.short_title(e["title"], titles)))
        return marks

    @db_safe
    def action_set_range(self, key: str) -> None:
        if key in trends.RANGES and key != self.range:
            self.range = key
            db.set_meta("overview_range", key)
            self.update_trends()

    def update_top(self) -> None:
        self.query_one("#top-title", ActionText).set_parts([
            (Text("TOP PERFORMERS  ", style="bold"), 0), (chip("Open post", "open_post"), 0),
            (Text("   score = × your typical video", style=MUTED), 1)])
        top = self.query_one("#top-table", DataTable)
        keep = self._cursor_key(top)
        top.clear()
        ranked = sorted((p for p in self.posts if p["score"] is not None and (p["views"] or 0) >= 50),
                        key=lambda p: p["score"], reverse=True)[:15]
        # The episode's title where ReelForge knows it (captions carry hashtags and links), without the opening every
        # title shares, so the narrow column shows what tells the videos apart.
        titles = {e["id"]: e["title"] for e in self.episodes}
        rows = [(trends.distinct_title(titles.get(p["episode_id"]) or videos.strip_hashtags(p["title"] or ""),
                                       list(titles.values())) or "(untitled)", p) for p in ranked]
        key, reverse = self.top_sort
        rows.sort(key=lambda r: r[0].lower() if key == "title" else r[1][key] or 0, reverse=reverse)
        for k, label, _ in TOP_COLUMNS:
            arrow = (" ▼" if reverse else " ▲") if k == key else ""
            top.columns[ColumnKey(k)].label = Text(label + arrow, style="bold")
        for name, p in rows:
            top.add_row(tag(self.platforms[p["platform"]]), name, fmt_age(p["age_h"]),
                        num(p["views"]), score_text(p["score"]), key=f"{p['platform']}|{p['post_id']}")
        self._restore_cursor(top, keep)

    def update_latest(self) -> None:
        """The newest video on every platform: how it's doing so far."""
        heading = Text("LATEST VIDEO  ", style="bold")
        body = Text()
        newest = None
        for e in self.episodes:
            ps = [q for q in self.posts if q["episode_id"] == e["id"]]
            if ps and (newest is None or min(q["published_at"] for q in ps) > newest[2]):
                newest = (e, ps, min(q["published_at"] for q in ps))
        if newest is None:
            body.append("Your newest video shows up here once it's posted.", style=MUTED)
        else:
            e, ps, first = newest
            heading.append(f"posted {fmt_ago(first)}   ", style=MUTED)
            heading.append_text(chip("Compare", f"show_episode({e['id']})"))
            body.append(e["title"] + "\n", style="bold")
            by = {q["platform"]: q for q in ps}
            for p in self.platforms.values():
                q = by.get(p.key)
                body.append_text(tag(p))
                if not q:
                    body.append("   not posted yet\n", style=MUTED)
                    continue
                body.append(f" {fmt_num(q['views']):>8} views", style="bold")
                body.append(f" {fmt_num(q['likes']):>7} likes", style=MUTED)
                body.append(f" {fmt_num(q['vph']):>7}/h ", style=MUTED)
                body.append_text(score_text(q["score"]))
                body.append("\n")
            total = sum(q["views"] or 0 for q in ps)
            body.append(f"{fmt_num(total)} views on {len(by)}/{len(self.platforms)} platforms", style=MUTED)
        self.query_one("#latest-title", ActionText).update(heading)
        self.query_one("#latest-body", Static).update(body)

    def action_show_episode(self, episode_id: int) -> None:
        self.compare_target = f"ep-{episode_id}"
        self.query_one(TabbedContent).active = "compare"
        self.update_episode_list()
        self.update_compare()

    # --- videos ---------------------------------------------------------------------------

    def update_videos(self) -> None:
        table = self.query_one("#videos-table", DataTable)
        keep = self._cursor_key(table)
        table.clear()
        key, reverse = self.sort
        rows = [p for p in self.posts if not self.filter or p["platform"] == self.filter]

        def sort_value(p):
            v = p.get(key)
            if key in ("title", "platform"):
                return (v or "").lower()
            return v if v is not None else float("-inf")

        rows.sort(key=sort_value, reverse=reverse)
        for p in rows:
            table.add_row(
                tag(self.platforms[p["platform"]]), p["title"] or "(untitled)", fmt_age(p["age_h"]),
                num(p["views"], "bold"), num(p["likes"]), num(p["comments"]), num(p["shares"]),
                Text(fmt_pct(p["eng"]), justify="right"), Text(fmt_pct(p["share_rate"]), justify="right"),
                num(p["vph"]), score_text(p["score"]), score_text(p.get("pscore")),
                key=f"{p['platform']}|{p['post_id']}",
            )
        self._restore_cursor(table, keep)
        filters = Text("SHOW ", style=f"bold {MUTED}")
        filters.append_text(chip("All", "set_filter('')", not self.filter))
        for pl in self.platforms.values():
            filters.append(" ")
            filters.append_text(chip(pl.name, f"set_filter('{pl.key}')", self.filter == pl.key))
        filters.append("    ")
        self.query_one("#videos-hint", ActionText).set_parts([
            (filters, 0),
            (chips(("Open post", "open_post"), ("Fix episode", "fix_episode"), ("Export CSV", "export_csv")), 0),
            (Text(f"    {len(rows)} videos · click a header to sort · click a row again to open it",
                  style=MUTED), 1)])
        for k, label, _ in VIDEO_COLUMNS:
            if k != "platform":
                arrow = (" ▼" if reverse else " ▲") if k == key else ""
                table.columns[ColumnKey(k)].label = Text(label + arrow, style="bold" if arrow else "")
        self.update_video_detail()

    def action_export_csv(self) -> None:
        """Every video's numbers as a spreadsheet file (data/exports/), shown in Explorer."""
        import csv

        folder = config.DATA_DIR / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"videos-{datetime.now():%Y%m%d-%H%M}.csv"
        fields = ["platform", "title", "episode", "posted", "age_hours", "views", "likes", "comments", "shares",
                  "engagement", "share_rate", "views_per_hour", "score", "score_on_platform", "url"]
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as f:  # the BOM makes Excel read it as UTF-8
                out = csv.writer(f)
                out.writerow(fields)
                for p in sorted(self.posts, key=lambda q: q["published_at"], reverse=True):
                    out.writerow([self.platforms[p["platform"]].name, _cell(p["title"]), _cell(p["episode"]),
                                  p["published"].astimezone().strftime("%Y-%m-%d %H:%M"), round(p["age_h"], 1),
                                  p["views"], p["likes"], p["comments"], p["shares"],
                                  None if p["eng"] is None else round(p["eng"], 4),
                                  None if p["share_rate"] is None else round(p["share_rate"], 4),
                                  round(p["vph"], 1), None if p["score"] is None else round(p["score"], 2),
                                  None if p.get("pscore") is None else round(p["pscore"], 2), p["url"] or ""])
        except OSError as e:
            self.notify(f"Couldn't write {path.name}: {e}", severity="error")
            return
        desktop.reveal(path)
        self.notify(f"{len(self.posts)} videos saved to {path.name} (Explorer is showing it).", timeout=8)

    def action_set_filter(self, key: str) -> None:
        self.filter = key or None
        self.update_videos()

    @on(DataTable.RowSelected, "#videos-table, #top-table, #compare-table")
    def open_selected(self, event: DataTable.RowSelected) -> None:
        """Clicking an already-highlighted row (or Enter) opens that post."""
        post = self._post_for(event.row_key.value)
        if post and post["url"]:
            desktop.open_url(post["url"])

    @on(DataTable.HeaderSelected, "#top-table")
    def sort_top(self, event: DataTable.HeaderSelected) -> None:
        """Click a header to sort the top 15 by it; click it again to flip the order."""
        key = event.column_key.value
        if key == "platform":
            return
        self.top_sort = (key, not self.top_sort[1] if self.top_sort[0] == key else key != "title")
        self.update_top()

    @on(DataTable.HeaderSelected, "#videos-table")
    def sort_videos(self, event: DataTable.HeaderSelected) -> None:
        key = event.column_key.value
        self.sort = (key, not self.sort[1] if self.sort[0] == key else key not in ("title", "platform"))
        self.update_videos()

    @on(DataTable.RowHighlighted, "#videos-table")
    def update_video_detail(self) -> None:
        chart = self.query_one("#video-detail", ChartPanel)
        post = self._post_for(self._cursor_key(self.query_one("#videos-table", DataTable)))
        self.update_video_badges(post)
        if not post:
            self.detail_state = None
            chart.set_title(Text("VIEWS SINCE POSTING", style="bold"))
            chart.show_empty("Pick a video above to see its views against your typical video's.")
            return
        p = self.platforms[post["platform"]]
        xs, ys = analytics.post_curve(post, self.parsed)
        span = max(xs[-1] if xs else 0, post["age_h"], 1)
        # Measured against your typical video on the same platform, or on all of them while that's too few.
        txs, tys = analytics.typical_curve(self.posts, self.parsed, post["platform"], span, exclude=post)
        typical = f"typical {p.name} video"
        if not txs:
            txs, tys = analytics.typical_curve(self.posts, self.parsed, None, span, exclude=post)
            typical = "typical video"
        series = []
        if "typical" not in self.hidden_curves:
            series.append(charts.Series("typical", typical, TYPICAL, xs=txs, ys=tys))
        if "this" not in self.hidden_curves:
            series.append(charts.Series("this", "this video", p.color, xs=xs, ys=ys, style="area"))
        self.detail_state = (post, span, series)
        chart.set_title(self.detail_title(chart.plot.hover))
        if not any(s.xs for s in series):
            chart.show_empty("Both lines are hidden: click one above to show it." if len(self.hidden_curves) == 2
                             else "No snapshots for this video yet; it fills in after a couple of refreshes.")
            return
        chart.draw(lambda w, h, hover: charts.lines(series, span, w, h, lambda pw: charts.age_labels(span, pw), (),
                                                    hover, zero=True), span)

    def detail_title(self, slot: int | None = None) -> Text:
        post, span, series = self.detail_state
        p = self.platforms[post["platform"]]
        title = Text("VIEWS SINCE POSTING  ", style="bold")
        if slot is not None:
            title.append(f"at {fmt_age(slot + 1)}  ", style=f"bold {charts.MARK}")
            values = {}
            for s in series:
                if s.xs and s.xs[0] <= slot + 1 <= s.xs[-1]:
                    values[s.key] = analytics.interp(s.xs, s.ys, slot + 1)
                    title.append(f"{s.name} {fmt_num(values[s.key])}  ", style=s.color)
            if values.get("typical") and "this" in values:
                title.append(f"{values['this'] / values['typical']:.1f}× typical", style="bold")
            return title
        typical = next((s.name for s in series if s.key == "typical"), "typical video")
        for which, label, color in (("this", "this video", p.color), ("typical", typical, TYPICAL)):
            off = which in self.hidden_curves
            style = Style(color="#4a515c", strike=True) if off else Style(color=color, bold=which == "this")
            title.append(f"━ {label}", style=style + clickable(f"toggle_curve('{which}')"))
            title.append("  ")
        title.append(f" {(post['title'] or '')[:50]} · {fmt_num(post['views'])} views", style=MUTED)
        return title

    def action_toggle_curve(self, which: str) -> None:
        self.hidden_curves ^= {which}
        self.update_video_detail()

    def action_toggle_line(self, key: str) -> None:
        """Hide or show one platform on every chart (the keys show which are off)."""
        self.hidden_lines ^= {key}
        self.update_trends()
        if self.query_one(TabbedContent).active == "compare":
            self.update_compare()
        else:
            self.stale.add("compare")  # redrawn when you open it

    @on(charts.Plot.Hovered)
    def plot_hovered(self, event: charts.Plot.Hovered) -> None:
        panel = event.plot.parent
        pid = panel.id or "" if panel else ""
        if pid.endswith("-chart") and pid[:-6] in self.trend_state:
            panel.set_title(self.metric_title(pid[:-6], event.slot))
        elif pid == "video-detail" and self.detail_state:
            panel.set_title(self.detail_title(event.slot))
        elif pid.startswith("compare-") and pid[8:] in self.compare_state:
            panel.set_title(self.compare_title(pid[8:], event.slot))

    # --- compare --------------------------------------------------------------------------

    def update_episode_list(self) -> None:
        options = self.query_one("#episode-list", OptionList)
        # How many platforms each episode is on; a second post on the same platform doesn't count twice.
        on: dict[int, set[str]] = {}
        for p in self.posts:
            if p["episode_id"]:
                on.setdefault(p["episode_id"], set()).add(p["platform"])
        items = [Option(Text("◆ Platform scoreboard", style="bold #ffcc33"), id="board")]
        titles = [e["title"] for e in self.episodes]
        for e in self.episodes:
            count = len(on.get(e["id"], ()))
            label = Text(trends.distinct_title(e["title"], titles)[:30].ljust(30))
            label.append(f" {count}/{len(self.platforms)}", style=GOOD if count == len(self.platforms) else MUTED)
            items.append(Option(label, id=f"ep-{e['id']}"))
        options.clear_options()
        options.add_options(items)
        ids = [o.id for o in items]
        options.highlighted = ids.index(self.compare_target) if self.compare_target in ids else 0

    @on(OptionList.OptionHighlighted, "#episode-list")
    def pick_episode(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id and event.option_id != self.compare_target:
            self.compare_target = event.option_id
            self.update_compare()

    def update_compare(self) -> None:
        if self.compare_target.startswith("ep-") and any(f"ep-{e['id']}" == self.compare_target
                                                         for e in self.episodes):
            self.compare_episode(int(self.compare_target[3:]))
        else:
            self.compare_target = "board"
            self.compare_board()

    def compare_board(self) -> None:
        stats = {}
        for key, p in self.platforms.items():
            posts = [q for q in self.posts if q["platform"] == key and q["views"] is not None]
            # Views at 24 hours compare videos fairly; a 30-minute-old post would drag "current views" down.
            at_day = [v for q in posts if q["age_h"] >= 24
                      and (v := analytics.views_at(self.parsed.get((key, q["post_id"]), analytics.NO_CURVE),
                                                   q["published"], 24)) is not None]
            likes = [q["likes"] / q["views"] for q in posts if q["views"] and q["likes"] is not None]
            followers = trends.change(self.account_rows.get(key, []), "followers", 24 * 7)
            if followers is None:
                followers = trends.since_first(self.account_rows.get(key, []), "followers")
            stats[key] = {
                "posts": posts,
                "median": median(at_day) if len(at_day) >= 2 else (median(q["views"] for q in posts) if posts else None),
                "at_day": len(at_day) >= 2,
                "likes": mean(likes) if likes else None,
                "share": mean(s) if (s := [q["share_rate"] for q in posts if q["views"]
                                           and q["share_rate"] is not None]) else None,
                "followers": followers,
                "best": max(posts, key=lambda q: q["views"] or 0, default=None),
            }
        ps = list(self.platforms.values())
        tracked_days = max((len({r["ts"][:10] for r in self.account_rows.get(p.key, [])}) for p in ps), default=0)
        self.query_one("#compare-heading", ActionText).update(Text.assemble(
            ("PLATFORM SCOREBOARD  ", "bold"), ("which platform is working", MUTED)))
        measured = [p for p in ps if stats[p.key]["posts"]]
        at_day = bool(measured) and all(stats[p.key]["at_day"] for p in measured)
        self.query_one("#compare-bars", Bars).show([
            ("MEDIAN VIEWS PER VIDEO" + (" · AT 24 HOURS" if at_day else " · SO FAR"),
             [(p.name, stats[p.key]["median"] or 0, p.color, fmt_num(stats[p.key]["median"])) for p in ps]),
            ("LIKE RATE  likes / views",
             [(p.name, stats[p.key]["likes"] or 0, p.color, fmt_pct(stats[p.key]["likes"])) for p in ps]),
            ("FOLLOWERS GAINED · " + ("7 DAYS" if tracked_days >= 8 else "SINCE TRACKING STARTED"),
             [(p.name, stats[p.key]["followers"] or 0, p.color, fmt_delta(stats[p.key]["followers"]) or "—")
              for p in ps]),
        ])
        curves = {p.key: analytics.typical_curve(self.posts, self.parsed, p.key, 72.0) for p in ps}
        # Show as much of the first 3 days as there's history for, so short histories fill the chart.
        horizon = max((xs[-1] for xs, _ in curves.values() if xs), default=72.0)
        self.compare_state = {}
        for p in ps:
            xs, ys = curves[p.key]
            series = [charts.Series(p.key, p.name, p.color, xs=xs, ys=ys, style="area")]
            heading = Text.assemble((p.name + "  ", f"bold {p.color}"),
                                    (f"typical video, first {fmt_age(horizon)}", MUTED))
            if ys:
                heading.append(f" · {fmt_num(ys[-1])} views by {fmt_age(xs[-1])}", style=MUTED)
            self.draw_compare(p, heading, series, horizon, "Needs a few videos with some history.")

        table = self.query_one("#compare-table", DataTable)
        table.clear(columns=True)
        for label, width in (("", 4), ("Followers", 9), ("Gained", 7), ("Videos", 6), ("Median", 8),
                             ("Likes", 6), ("Share", 6), ("Best video", 34)):
            table.add_column(label, width=width)
        for p in ps:
            s = stats[p.key]
            latest = self.latest.get(p.key)
            best = s["best"]
            table.add_row(tag(p), num(latest["followers"] if latest else None),
                          Text(fmt_delta(s["followers"]), justify="right"), num(len(s["posts"])), num(s["median"]),
                          Text(fmt_pct(s["likes"]), justify="right"), Text(fmt_pct(s["share"]), justify="right"),
                          f"{fmt_num(best['views'])} · {best['title'] or '(untitled)'}" if best else "—",
                          key=f"{best['platform']}|{best['post_id']}" if best else None)

    def compare_episode(self, episode_id: int) -> None:
        posts: dict[str, dict] = {}
        for q in sorted((q for q in self.posts if q["episode_id"] == episode_id), key=lambda q: q["published_at"]):
            posts.setdefault(q["platform"], q)  # the first post on each platform
        title = next((e["title"] for e in self.episodes if e["id"] == episode_id), "")
        ps = list(self.platforms.values())
        self.query_one("#compare-heading", ActionText).update(Text.assemble(("EPISODE  ", "bold"), title))
        self.query_one("#compare-bars", Bars).show([
            ("VIEWS", [(p.name, posts[p.key]["views"] or 0 if p.key in posts else 0, p.color,
                        fmt_num(posts[p.key]["views"]) if p.key in posts else "not posted") for p in ps]),
            ("ENGAGEMENT", [(p.name, (posts[p.key]["eng"] or 0) if p.key in posts else 0, p.color,
                             fmt_pct(posts[p.key]["eng"]) if p.key in posts else "—") for p in ps]),
        ])
        self.compare_state = {}
        for p in ps:
            q = posts.get(p.key)
            if not q:
                self.draw_compare(p, Text(p.name, style=f"bold {p.color}"), [], 1, f"Not posted on {p.name} yet.")
                continue
            xs, ys = analytics.post_curve(q, self.parsed)
            span = max(xs[-1] if xs else 0, q["age_h"], 1)
            txs, tys = analytics.typical_curve(self.posts, self.parsed, p.key, span, exclude=q)
            series = [charts.Series(p.key, "this", p.color, xs=xs, ys=ys, style="area"),
                      charts.Series("typical", "typical", TYPICAL, xs=txs, ys=tys)]
            heading = Text.assemble((p.name + "  ", f"bold {p.color}"), (f"{fmt_num(q['views'])} views", "bold"),
                                    (f" · {fmt_num(q['likes'])} likes · ", MUTED))
            heading.append_text(score_text(q["score"]))
            heading.append(" typical", style=MUTED)
            self.draw_compare(p, heading, series, span, "No snapshots for this post yet.")

        table = self.query_one("#compare-table", DataTable)
        table.clear(columns=True)
        for label, width in (("", 4), ("Views", 8), ("Likes", 7), ("Cmts", 6), ("Shares", 6), ("Eng", 6),
                             ("Share", 6), ("Score", 6), ("Age", 5), ("Link", 40)):
            table.add_column(label, width=width)
        for p in ps:
            q = posts.get(p.key)
            if not q:
                table.add_row(tag(p), Text("not yet", style=MUTED))
                continue
            table.add_row(tag(p), num(q["views"], "bold"), num(q["likes"]), num(q["comments"]), num(q["shares"]),
                          Text(fmt_pct(q["eng"]), justify="right"), Text(fmt_pct(q["share_rate"]), justify="right"),
                          score_text(q["score"]), fmt_age(q["age_h"]), q["url"] or "",
                          key=f"{q['platform']}|{q['post_id']}")

    def draw_compare(self, p: Platform, heading: Text, series: list[charts.Series], span: float,
                     empty: str) -> None:
        panel = self.query_one(f"#compare-{p.key}", ChartPanel)
        panel.set_title(heading)
        if p.key in self.hidden_lines or not any(s.xs for s in series):
            self.compare_state.pop(p.key, None)
            panel.show_empty(f"{p.name} is hidden: click its name on the Overview key to show it."
                             if p.key in self.hidden_lines else empty)
            return
        self.compare_state[p.key] = (heading, series)
        panel.set_title(self.compare_title(p.key, panel.plot.hover))
        panel.draw(lambda w, h, hover: charts.lines(series, span, w, h, lambda pw: charts.age_labels(span, pw), (),
                                                    hover, zero=True), span)

    def compare_title(self, key: str, slot: int | None) -> Text:
        heading, series = self.compare_state[key]
        if slot is None:
            return heading
        out = Text(f"at {fmt_age(slot + 1)}  ", style=f"bold {charts.MARK}")
        for s in series:
            if s.xs and s.xs[0] <= slot + 1 <= s.xs[-1]:
                out.append(f"{s.name} {fmt_num(analytics.interp(s.xs, s.ys, slot + 1))}  ", style=s.color)
        return out

    # --- publish --------------------------------------------------------------------------

    def scan_files(self) -> None:
        if not self.demo:
            self._safe(lambda: notify.check_videos(self.cfg), 0)
            self.show_new_notes()
        hidden = db.get_meta("hidden_videos", [])
        hidden_names = {Path(h).name.lower() for h in hidden}
        every = videos.find(self.cfg)
        files = [f for f in every if f.name.lower() not in hidden_names]
        posted = self.posted_platforms()
        options = self.query_one("#file-list", OptionList)
        highlighted = self.selected_file
        options.clear_options()
        ids = []
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue  # moved or deleted since the folder was listed
            on = posted.get(f.name.lower(), set())
            label = Text("✓ " if on else "  ", style=GOOD)
            label.append(f.name)
            source = "pipeline" if videos.from_pipeline(f) else _short(f.parent.name, 22)
            ago = fmt_ago(datetime.fromtimestamp(st.st_mtime).astimezone().isoformat())
            label.append(f"\n   {source} · {st.st_size / 1024 / 1024:.1f} MB · {ago}  ", style=MUTED)
            for p in self.platforms.values():
                label.append(SHORT[p.key] + " ", style=f"bold {p.color}" if p.key in on else "#3a4049")
            options.add_option(Option(label, id=str(f)))
            ids.append(str(f))
        if not ids:
            options.add_option(Option(Text(
                f"No videos yet.\nPut finished .mp4 files in\n{config.videos_dir(self.cfg)}", style=MUTED),
                disabled=True))
        heading = Text.assemble(("VIDEOS  ", "bold"), (f"{len(files)}  ", MUTED))
        if ids:
            heading.append_text(chip("Remove", "remove_picked"))
            heading.append(" ")
        if len(every) > len(files):
            heading.append_text(chip(f"Show {len(every) - len(files)} hidden", "unhide_videos"))
        self.query_one("#file-heading", ActionText).update(heading)
        if highlighted and str(highlighted) in ids:
            options.highlighted = ids.index(str(highlighted))
        elif ids and highlighted is None:
            options.highlighted = 0  # start with the newest video picked

    def posted_platforms(self) -> dict[str, set[str]]:
        """Video file name (lower case) -> the platforms its episode is posted on."""
        by_episode: dict[int, set[str]] = {}
        for p in self.posts:
            if p["episode_id"]:
                by_episode.setdefault(p["episode_id"], set()).add(p["platform"])
        out: dict[str, set[str]] = {}
        for e in self.episodes:
            if e["video"]:
                out.setdefault(Path(e["video"]).name.lower(), set()).update(by_episode.get(e["id"], set()))
        return out

    @on(VideoList.Menu)
    def video_menu(self, event: VideoList.Menu) -> None:
        self.ask_remove(Path(event.option_id))

    def action_remove_picked(self) -> None:
        """The Remove button above the list: hide or recycle the picked video."""
        if self._picked():
            self.ask_remove(self.selected_file)

    def ask_remove(self, path: Path) -> None:
        self.push_screen(VideoMenu(path, videos.from_pipeline(path)), lambda choice: self.remove_video(path, choice))

    @db_safe
    def remove_video(self, path: Path, choice: str | None) -> None:
        if choice == "hide":
            hidden = db.get_meta("hidden_videos", [])
            db.set_meta("hidden_videos", sorted({*hidden, str(path)}))
            self.notify(f"{path.name} hidden. Show hidden (top of the list) brings it back.")
        elif choice == "recycle":
            sidecar = path.with_suffix(".json")
            if not desktop.recycle(path):
                self.notify(f"Couldn't move {path.name} to the Recycle Bin (is it open somewhere?).", severity="error")
                return
            if sidecar.exists() and not videos.from_pipeline(path):
                desktop.recycle(sidecar)
            other = next((f for f in videos.find(self.cfg) if f.name.lower() == path.name.lower()), None)
            self.notify(f"{path.name} moved to the Recycle Bin." + (
                f" Another copy is still in {other.parent}; it's on the list now (Hide takes it off)."
                if other else ""))
        else:
            return
        if self.selected_file == path:
            self.selected_file = None
            self.update_posted()
        self.scan_files()

    @db_safe
    def action_unhide_videos(self) -> None:
        if db.get_meta("hidden_videos", []):
            db.set_meta("hidden_videos", [])
            self.notify("Hidden videos are back on the list.")
            self.scan_files()

    @on(OptionList.OptionHighlighted, "#file-list")
    def pick_file(self, event: OptionList.OptionHighlighted) -> None:
        if not event.option_id or Path(event.option_id) == self.selected_file:
            return
        path = Path(event.option_id)
        self.selected_file = path
        meta, warnings = videos.meta(path, self.cfg)
        for w in warnings:
            self.notify(w, severity="warning")
        self.query_one("#f-caption", Input).value = meta["caption"]
        self.query_one("#f-tags", Input).value = meta["tags"]
        self.update_posted()

    @on(Input.Changed, "#f-caption")
    @on(Input.Changed, "#f-tags")
    def update_preview(self) -> None:
        """Show exactly what each platform will get, and the caption/hashtag limits."""
        item = self.form_item()
        caption_len = len(item.text_for("x"))
        n = len(videos.tag_list(item.tags))
        label = Text("Hashtags  ")
        label.append(f"{n}/{videos.MAX_TAGS}", style=BAD if n > videos.MAX_TAGS else MUTED)
        hint = f"  (only the first {videos.MAX_TAGS} are used)" if n > videos.MAX_TAGS else \
            (f"  (TikTok always gets #{videos.FIRST_TAG} first)" if videos.FIRST_TAG else "")
        label.append(hint, style=MUTED)
        self.query_one("#tags-label", Label).update(label)
        caption = Text("Caption  ")
        caption.append(f"{caption_len}/100", style=BAD if caption_len > 100 else MUTED)
        caption.append("  (one line: the X post, the YouTube title, and the start of TikTok / Instagram)", style=MUTED)
        self.query_one("#caption-label", Label).update(caption)

        preview = Text("PREVIEW\n", style=f"bold {MUTED}")
        rows = {"tiktok": item.text_for("tiktok"), "instagram": item.text_for("instagram"),
                "youtube": f"{item.title}   description: {item.text_for('youtube')}", "x": item.text_for("x")}
        for key, text in rows.items():
            if key in self.platforms:
                p = self.platforms[key]
                preview.append(f"{p.name:<10}", style=f"bold {p.color}")
                preview.append((text or "—") + "\n")
        self.query_one("#preview", Static).update(preview)

    def update_posted(self) -> None:
        """Where the picked video is already up, so you know which upload pages are left."""
        out = Text()
        video = self.selected_file
        episode = db.episode_for_video(video.name) if video else None
        if video:
            out.append("POSTED  ", style=f"bold {MUTED}")
            by = {}
            if episode:
                for q in sorted((q for q in self.posts if q["episode_id"] == episode["id"]),
                                key=lambda q: q["published_at"]):
                    by.setdefault(q["platform"], q)
            for p in self.platforms.values():
                q = by.get(p.key)
                if q:
                    out.append(f"✓ {p.name}", style=f"bold {p.color}")
                    out.append(f" {fmt_num(q['views'])} views, {fmt_ago(q['published_at'])}    ", style=MUTED)
                else:
                    out.append(f"○ {p.name}    ", style="#5c6370")
            if not by:
                out.append("(ReelForge spots each post at its next refresh)", style=MUTED)
        self.query_one("#posted", Static).update(out)
        for p in self.platforms.values():
            done = bool(video and episode and any(q["episode_id"] == episode["id"] and q["platform"] == p.key
                                                  for q in self.posts))
            self.query_one(f"#open-{p.key}", Button).label = f"{p.name} {'✓' if done else '→'}"

    def form_item(self) -> PublishItem:
        return PublishItem(
            video=self.selected_file or Path(),
            caption=self.query_one("#f-caption", Input).value.strip(),
            tags=self.query_one("#f-tags", Input).value.strip(),
        )

    def copy_text(self, text: str) -> None:
        if not desktop.copy(text):
            self.copy_to_clipboard(text)  # terminal clipboard (OSC 52) as a fallback

    def _picked(self) -> bool:
        if self.selected_file and self.selected_file.exists():
            return True
        self.notify("Pick a video on the left first.", severity="warning")
        return False

    @on(Button.Pressed, ".open-btn")
    def open_upload(self, event: Button.Pressed) -> None:
        """Copy the right text, show the file in Explorer, open the platform's upload page."""
        if not self._picked():
            return
        p = self.platforms[event.button.id.split("-", 1)[1]]
        item = self.form_item()
        text, what = {"youtube": (item.title, "caption (title)"), "x": (item.text_for("x"), "caption")}.get(
            p.key, (item.text_for(p.key), "caption + hashtags"))
        if text:
            self.copy_text(text)
        else:
            self.notify(f"The caption is empty, so nothing was copied for {p.name}.", severity="warning")
        desktop.reveal(item.video)
        desktop.open_upload_page(p.key)
        tip = {
            "youtube": " For the description, use Copy YouTube hashtags.",
            "instagram": " Click + Create, then Post/Reel.",
        }.get(p.key, "")
        self.notify(f"{p.name}: {what} copied. Drag {item.video.name} in from the Explorer window, then paste.{tip}",
                    title="Upload page opened", timeout=12)
        self.record_manual([p], item)

    @on(Button.Pressed, "#open-all")
    def open_all(self) -> None:
        """Open every upload page at once, with the TikTok text (or the caption) on the clipboard."""
        if not self._picked():
            return
        item = self.form_item()
        first = "tiktok" if "tiktok" in self.platforms else None
        self.copy_text(item.text_for(first) if first else item.title)
        desktop.reveal(item.video)
        for p in self.platforms.values():
            desktop.open_upload_page(p.key)
        self.record_manual(list(self.platforms.values()), item)
        self.notify(f"{'TikTok text' if first else 'Caption'} copied. For the others use the Copy buttons. "
                    "On Instagram click + Create.", title=f"{len(self.platforms)} upload pages opened", timeout=15)

    @db_safe
    def record_manual(self, platforms: list[Platform], item: PublishItem) -> None:
        """Note a manual upload, so the video gets its ✓ and its posts can be matched to the episode."""
        if not db.episode_for_video(item.video.name):
            db.create_episode(item.title or item.video.stem, str(item.video))
        for p in platforms:
            db.log_upload(p.key, item.video.name, "manual", message="opened the upload page")
        self.episodes = db.episodes()
        self.update_uploads()
        self.update_episode_list()
        self.scan_files()
        self.update_posted()
        # Look for the new post once it's had time to go up (10 and 30 minutes later), whatever the
        # usual refresh timing says.
        for timer in self.post_check_timers:
            timer.stop()
        self.post_check_timers = [self.set_timer(minutes * 60, lambda: self.run_refresh(manual=True, force=True))
                                  for minutes in (10, 30)]

    @on(Button.Pressed, ".copy-btn")
    def copy_field(self, event: Button.Pressed) -> None:
        item = self.form_item()
        text, what = {
            "copy-caption": (item.title, "Caption"),
            "copy-tiktok": (item.text_for("tiktok"), "TikTok text"),
            "copy-instagram": (item.text_for("instagram"), "Instagram text"),
            "copy-youtube": (item.text_for("youtube"), "YouTube hashtags"),
        }[event.button.id]
        if not text:
            self.notify(f"{what} is empty: write a caption first.", severity="warning")
            return
        self.copy_text(text)
        self.notify(f"{what} copied.", timeout=3)

    @on(Button.Pressed, "#reveal")
    def reveal_file(self) -> None:
        if self._picked():
            desktop.reveal(self.selected_file)

    def update_uploads(self) -> None:
        """Upload pages you opened, and whether the post has turned up since."""
        table = self.query_one("#uploads-table", DataTable)
        table.clear()
        episodes = {Path(e["video"]).name.lower(): e["id"] for e in self.episodes if e["video"]}
        found = {}
        for q in self.posts:
            if q["episode_id"]:
                found.setdefault((q["episode_id"], q["platform"]), q)
        for u in db.uploads():
            when = db.parse(u["ts"]).astimezone()
            p = self.platforms.get(u["platform"])
            q = found.get((episodes.get((u["video"] or "").lower()), u["platform"]))
            if q:
                mark, note = Text("✓", style=GOOD), Text(f"live · {fmt_num(q['views'])} views · {q['url'] or ''}")
            elif u["status"] == "manual":
                mark, note = Text("→", style=MUTED), Text("opened the upload page · not spotted yet", style=MUTED)
            else:
                mark, note = Text("✓" if u["status"] == "ok" else "×", style=GOOD if u["status"] == "ok" else BAD), \
                    Text(u["url"] or u["message"] or "")
            table.add_row(fmt_clock(when) if when.date() == datetime.now().date() else when.strftime("%m/%d"),
                          tag(p) if p else u["platform"], u["video"] or "", mark, note)

    # --- accounts -------------------------------------------------------------------------

    def update_accounts(self) -> None:
        fresh_since = (analytics.now() - timedelta(days=2)).isoformat(timespec="seconds")
        for panel in self.query(AccountPanel):
            p = panel.platform
            rows = self.account_rows.get(p.key, [])
            latest = self.latest.get(p.key)
            fresh = any(q["platform"] == p.key and q["published_at"] >= fresh_since for q in self.posts)
            nxt = sync.next_read(p, self.cfg, latest["ts"] if latest else None, fresh)
            due = None
            if nxt is not None:
                minutes = (nxt - analytics.now()).total_seconds() / 60
                due = "any moment" if minutes < 1 else f"in about {fmt_age(minutes / 60)}"
            error = sync.last_errors.get(p.key)
            panel.show(latest, {
                "posts": sum(1 for q in self.posts if q["platform"] == p.key),
                "since": db.parse(rows[0]["ts"]).astimezone().strftime("%b %d").replace(" 0", " ") if rows else None,
                "error": error[1] if error else None,
                "due": due,
                "chart": self.followers_chart(p, rows),
            })

    def followers_chart(self, p: Platform, rows: list) -> tuple | None:
        """(heading, draw function, slots, describe(slot)) for an account's followers over the time ReelForge has been
        reading them."""
        pts = trends.points(rows, "followers", hold=False)
        if len(pts) < 2:
            return None
        days = (analytics.now() - pts[0][0]).total_seconds() / 86400
        fr = trends.frame_since(pts[0][0]) if days < 30 else trends.frame("30d")
        b = trends.bucket(pts, fr)
        xs = [i + 1 for i, v in enumerate(b.totals) if v is not None]
        ys = [v for v in b.totals if v is not None]
        if not ys:
            return None
        first = pts[0][0].astimezone()  # the first reading, not the start of its hour, so the date matches the panel
        heading = Text.assemble(("FOLLOWERS  ", "bold"),
                                (f"since {first:%b} {first.day}  " if days < 30 else "last 30 days  ", MUTED),
                                (fmt_num(pts[-1][1]), "bold"))
        heading.append("  ")
        heading.append_text(change_text(pts[-1][1] - (ys[0] if len(ys) > 1 else pts[0][1])))
        series = [charts.Series(p.key, p.name, p.color, xs=xs, ys=ys, style="area")]

        def describe(slot: int) -> Text:
            value = b.totals[slot] if 0 <= slot < fr.n else None
            out = Text.assemble(("FOLLOWERS  ", "bold"), (_slot_label(fr, slot) + "  ", f"bold {charts.MARK}"))
            out.append(fmt_num(value) if value is not None else "no reading yet", style="bold" if value else MUTED)
            return out

        def draw(w: int, h: int, hover: int | None):
            return charts.lines(series, fr.n, w, h, _clock(fr), (), hover)

        return heading, draw, fr.n, describe

    @on(Button.Pressed, ".login-btn")
    def login_button(self, event: Button.Pressed) -> None:
        p = self.platforms[event.button.id.split("-", 1)[1]]
        if not p.public_handle:
            self.notify(f'Add handle = "@you" under [{p.key}] in config.toml first.', severity="warning")
            return
        self.run_browser_login(p)

    @on(Button.Pressed, ".profile-btn")
    def profile_button(self, event: Button.Pressed) -> None:
        p = self.platforms[event.button.id.split("-", 1)[1]]
        if p.public_handle:
            desktop.open_url(desktop.profile_url(p.key, p.public_handle))

    @on(Button.Pressed, ".log-btn")
    def log_button(self, event: Button.Pressed) -> None:
        self.action_log_stats(event.button.id.split("-", 1)[1])

    @on(Button.Pressed, ".refresh-btn")
    def refresh_button(self, event: Button.Pressed) -> None:
        p = self.platforms[event.button.id.split("-", 1)[1]]
        if not p.has_stats:
            self.notify(f"{p.name} isn't set up yet (see the panel).", severity="warning")
            return
        self.run_refresh(True, True, p.key)

    @work(thread=True, group="login", exit_on_error=False)
    def run_browser_login(self, p: Platform) -> None:
        self.call_from_thread(self.notify, f"An Edge window is opening (if ReelForge is reading stats right now, as "
                              f"soon as that's done). Log in to {p.name} there; ReelForge carries on by itself once "
                              f"you're in.",
                              title=f"Log in to {p.name}", timeout=15)
        try:
            browser.login(p.key)
        except Exception as e:
            msg = str(e) if isinstance(e, PlatformError) else f"{type(e).__name__}: {e}"
            self.call_from_thread(self.notify, msg, title=f"{p.name} not logged in", severity="error", timeout=15)
            return
        self.call_from_thread(self.notify, f"Logged in to {p.name}. Reading your stats now…")
        self.call_from_thread(self.update_accounts)
        self.call_from_thread(self.update_header)
        self.call_from_thread(self.run_refresh, True, True, p.key)

    # --- typed-in stats --------------------------------------------------------------------

    def action_log_stats(self, start: str | None = None) -> None:
        """Type in numbers for platforms ReelForge can't read itself (Instagram and X before logging in)."""
        manual = [p for p in self.platforms.values() if not p.has_stats]
        if not manual:
            self.notify("Every platform already gets its stats automatically.")
            return
        if start not in {p.key for p in manual}:
            start = manual[0].key
        last = {}
        for p in manual:
            latest = self.latest.get(p.key)
            last[p.key] = {
                "followers": latest["followers"] if latest else None,
                "views": {q["episode_id"]: q["views"] for q in self.posts
                          if q["platform"] == p.key and q["post_id"].startswith("manual-") and q["views"] is not None},
            }
        episodes = db.episodes()[:12]
        self.push_screen(LogStats(manual, start, episodes, last), self.save_logged_stats)

    @db_safe
    def save_logged_stats(self, result: tuple | None) -> None:
        if not result:
            return
        key, followers, views = result
        p = self.platforms[key]
        episodes = {e["id"]: e for e in db.episodes()}
        posts = []
        for episode_id, n in views.items():
            e = episodes[episode_id]
            post_id = f"manual-{episode_id}"
            db.add_post(key, post_id, episode_id, e["title"], None, e["first_post"])
            posts.append(Post(post_id, e["title"], None, e["first_post"], views=n, likes=None, comments=None,
                              shares=None))
        # Videos left blank keep their last numbers, so the account total stays whole.
        for q in self.posts:
            if q["platform"] == key and q["post_id"].startswith("manual-") and q["episode_id"] not in views \
                    and q["views"] is not None:
                posts.append(Post(q["post_id"], q["title"], None, q["published_at"], views=q["views"],
                                  likes=None, comments=None, shares=None))
        if followers is None and self.latest.get(key):
            followers = self.latest[key]["followers"]
        db.record_snapshot(key, Account(handle=p.handle, followers=followers), posts)
        self.notify(f"{p.name} stats saved.", timeout=3)
        self.reload()

    # --- fixing an episode link --------------------------------------------------------------

    def action_fix_episode(self) -> None:
        post = self._highlighted_post()
        if not post:
            self.notify("Highlight a video first.", severity="warning")
            return
        self.push_screen(EpisodePicker(post, db.episodes(), self.platforms[post["platform"]]),
                         lambda choice: self.set_episode(post, choice))

    @db_safe
    def set_episode(self, post: dict, choice: str | None) -> None:
        if choice is None:
            return
        episode = None if choice == "none" else int(choice[3:])
        db.set_post_episode(post["platform"], post["post_id"], episode)
        title = next((e["title"] for e in self.episodes if e["id"] == episode), None)
        self.notify(f"Filed under: {title}" if title else "Marked as not one of your videos.", timeout=5)
        self.reload()

    # --- shared actions -------------------------------------------------------------------

    def action_tab(self, tab: str) -> None:
        self.query_one(TabbedContent).active = tab

    # --- notifications ----------------------------------------------------------------------

    def action_toggle_drawer(self) -> None:
        drawer = self.query_one("#drawer")
        drawer.display = not drawer.display
        if drawer.display:
            drawer.styles.offset = (drawer.styles.width.value, 0)  # slides in from the right
            drawer.styles.animate("offset", ScalarOffset.from_offset((0, 0)), duration=0.2, easing="out_cubic")
            self.update_notes()
            self.query_one("#notes", OptionList).focus()

    def action_close_drawer(self) -> None:
        self.query_one("#drawer").display = False

    def update_notes(self) -> None:
        """The bell's red dot, and the drawer's list (newest first)."""
        notes = self._safe(notify.recent, [])
        unread = sum(1 for n in notes if not n["read"])
        self.query_one("#bell", Bell).show(unread)
        head = Text("NOTIFICATIONS  ", style="bold")
        head.append(f"{unread} new  " if unread else "all read  ", style=BAD if unread else MUTED)
        parts = [(head, 0)]
        if unread:
            parts.append((chip("Mark all read", "mark_all_read"), 0))
            parts.append((Text(" "), 0))
        parts.append((chip("Close", "close_drawer"), 0))
        self.query_one("#drawer-head", ActionText).set_parts(parts)
        box = self.query_one("#notes", OptionList)
        keep = box.highlighted
        box.clear_options()
        if not notes:
            box.add_option(Option(Text("Nothing yet. Updates, milestones, badges and finished videos show up "
                                       "here.", style=MUTED), disabled=True))
            return
        for n in notes:
            icon, color, _ = notify.KINDS.get(n["kind"], notify.KINDS["info"])
            line = Text()
            line.append("● " if not n["read"] else "  ", style=f"bold {BAD}")
            line.append(f"{icon} ", style=f"bold {color}")
            line.append(n["title"], style="bold" if not n["read"] else "")
            for part in textwrap.wrap(n["body"] or "", 36)[:3]:
                line.append(f"\n    {part}", style=MUTED)
            line.append(f"\n    {fmt_ago(n['ts'])}", style="#5c6370")
            box.add_option(Option(line, id=f"note-{n['id']}"))
        if keep is not None and keep < box.option_count:
            box.highlighted = keep

    @on(OptionList.OptionSelected, "#notes")
    @db_safe
    def open_note(self, event: OptionList.OptionSelected) -> None:
        """Clicking a notification marks it read and opens the tab it's about."""
        if not (event.option_id or "").startswith("note-"):
            return
        note_id = int(event.option_id[5:])
        note = next((n for n in notify.recent() if n["id"] == note_id), None)
        notify.mark_read(note_id)
        if note and note["tab"] in TABS:
            self.action_tab(note["tab"])
        self.update_notes()

    @db_safe
    def action_mark_all_read(self) -> None:
        notify.mark_all_read()
        self.update_notes()

    # --- badges -------------------------------------------------------------------------------

    def update_badges(self) -> None:
        """The account's badges under the cards on the Overview (hidden when there are none)."""
        self.badge_list = badges.account_badges(self.account_rows, self.platforms)
        line = self.query_one("#badges", ActionText)
        line.display = bool(self.badge_list)
        if self.badge_list:
            line.set_parts([(badges.badge_text(b), i) for i, b in enumerate(self.badge_list[:4])])
            line.tooltip = badges.HOW

    def update_video_badges(self, post: dict | None) -> None:
        line = self.query_one("#video-badges", ActionText)
        found = badges.video_badges(post, self.posts, self.first_day, self.platforms) if post else []
        line.display = bool(found)
        if found:
            line.set_parts([(badges.badge_text(b), i) for i, b in enumerate(found)])
            line.tooltip = badges.HOW

    # --- updates ------------------------------------------------------------------------------

    def start_updates(self) -> None:
        """The Updates tab from the last check, a new check when that's old, and "Updated to ..." after a restart."""
        if self.demo:
            from .demo import SAMPLE_UPDATE

            self.update_info = {"current": KIT_VERSION or "1.0.0", "latest": SAMPLE_UPDATE[0], "newer": True,
                                "notes": SAMPLE_UPDATE[1], "url": "", "error": "", "checked": db.now_iso()}
            self.show_update()
            return
        if kit_update is None:
            self.show_update()
            return
        done = kit_update.take_marker()
        if done:
            self.notify(f"You're on ReelForge {done.get('to')} now (from {done.get('from')}).", title="Updated",
                        timeout=15)
            self._safe(lambda: notify.add("update", f"Updated to ReelForge {done.get('to')}",
                                          f"From {done.get('from')}. See what's new on the Updates tab.",
                                          key=f"updated:{done.get('to')}", read=True), False)
        self.update_info = self._safe(lambda: db.get_meta("update_check"), None)
        self.show_update()
        info = self.update_info
        stale = not info or info.get("current") != KIT_VERSION or _hours_since(info.get("checked")) >= UPDATE_EVERY_H
        if stale:
            self.run_update_check(manual=False)

    @work(thread=True, exclusive=True, group="update-check", exit_on_error=False)
    def run_update_check(self, manual: bool) -> None:
        info = kit_update.check()
        info["checked"] = db.now_iso()
        try:
            db.set_meta("update_check", info)
            if info["newer"]:
                notify.update_available(info["latest"])
        except sqlite3.Error:
            pass
        self.call_from_thread(self.after_update_check, info, manual)

    def after_update_check(self, info: dict, manual: bool) -> None:
        self.update_info = info
        self.show_update()
        self.show_new_notes()
        if manual and not info["error"] and not info["newer"]:
            self.notify(f"ReelForge {info['current']} is the newest version.", timeout=5)
        elif manual and info["error"]:
            self.notify(info["error"], severity="warning", timeout=8)

    def show_update(self) -> None:
        info = self.update_info or {}
        status, how = self.query_one("#update-status", Static), self.query_one("#update-how", Static)
        apply, check = self.query_one("#update-apply", Button), self.query_one("#update-check", Button)
        notes = self.query_one("#update-notes", Markdown)
        tab = self.query_one(TabbedContent).get_tab("updates")
        newer = bool(info.get("newer"))
        tab.label = Text.assemble("Updates", (" ●", f"bold {BAD}")) if newer else Text("Updates")
        out = Text()
        if kit_update is None and not self.demo:
            out.append("Updates work from a ReelForge folder (this copy of the dashboard is running on its own).",
                       style=MUTED)
            apply.disabled = check.disabled = True
            status.update(out)
            return
        out.append(f"ReelForge {info.get('current') or KIT_VERSION}", style="bold")
        if newer:
            out.append("   ")
            out.append(f"{info['latest']} is out", style=f"bold {GOOD}")
            out.append("  ·  one click downloads it, puts it in place and restarts ReelForge", style=MUTED)
        elif info.get("error"):
            out.append(f"   {info['error']}", style=MUTED)
        elif info.get("latest"):
            out.append("   the newest version", style=GOOD)
        else:
            out.append("   checking for updates…", style=MUTED)
        if info.get("checked"):
            out.append(f"\nchecked {fmt_ago(info['checked'])}", style=MUTED)
        status.update(out)
        apply.display = newer
        apply.disabled = self.updating or self.demo
        apply.label = "Update and restart" + (" (demo)" if self.demo else "")
        check.disabled = self.updating or self.demo
        self.query_one("#update-progress").display = self.updating
        if newer:
            notes.update(info.get("notes") or f"Release notes: {info.get('url')}")
        elif info.get("latest"):
            notes.update(f"You have the newest version, {info['latest']}. When a new one comes out, a notification "
                         "tells you, and this tab updates ReelForge in one click.")
        else:
            notes.update("ReelForge checks for a new version every few hours while it's open.")
        kind = kit_update.install_kind() if kit_update else ""
        how.update(Text({
            "installer": "Installed with the Windows installer: an update runs the new installer quietly into this "
                         "folder.",
            "zip": "Installed from a download: an update copies the new version's files over this folder.",
            "git": "A git copy: an update runs git pull.",
        }.get(kind, ""), style=MUTED) + Text("  Your channel, videos, stats and settings are never touched.",
                                             style=MUTED) if kind else Text(""))

    @on(Button.Pressed, "#update-check")
    def check_updates(self) -> None:
        if kit_update and not self.demo:
            self.query_one("#update-status", Static).update(Text("Checking…", style=MUTED))
            self.run_update_check(manual=True)

    @on(Button.Pressed, "#update-page")
    def open_release_page(self) -> None:
        url = (self.update_info or {}).get("url") or (kit_update.RELEASES if kit_update else "")
        if url:
            desktop.open_url(url)

    @on(Button.Pressed, "#update-apply")
    def start_update(self) -> None:
        if self.demo:
            self.notify("Demo mode: nothing is downloaded.", timeout=4)
            return
        if not kit_update or not (self.update_info or {}).get("newer") or self.updating:
            return
        self.updating = True
        self.show_update()
        self.update_progress("Starting", 0, 0)
        self.run_update_apply()

    @work(thread=True, exclusive=True, group="update-apply", exit_on_error=False)
    def run_update_apply(self) -> None:
        def progress(what: str, done: int, total: int) -> None:
            self.call_from_thread(self.update_progress, what, done, total)

        def log(text: str) -> None:
            self.call_from_thread(self.notify, text, severity="warning", timeout=12)

        try:
            message = kit_update.apply(kit_update.release_from(self.update_info), progress, log)
        except kit_update.UpdateError as e:
            self.call_from_thread(self.update_failed, str(e))
            return
        except Exception as e:
            self.call_from_thread(self.update_failed, f"{type(e).__name__}: {e}")
            return
        self.call_from_thread(self.update_done, message)

    def update_progress(self, what: str, done: int, total: int) -> None:
        bar = self.query_one("#update-progress", ProgressBar)
        bar.display = True
        bar.update(total=total or None, progress=done)
        size = f"  {done / 1e6:.1f} of {total / 1e6:.0f} MB" if total > 100_000 else ""
        self.query_one("#update-step", Static).update(Text(f"{what}…{size}", style=MUTED))

    def update_done(self, message: str) -> None:
        self.query_one("#update-step", Static).update(Text(f"{message} Restarting…", style=f"bold {GOOD}"))
        self.set_timer(1.5, lambda: self.exit(return_code=kit_update.RESTART))

    def update_failed(self, message: str) -> None:
        self.updating = False
        self.show_update()
        self.query_one("#update-step", Static).update(Text(
            f"The update didn't finish: {message}\nThe version you have keeps working.", style=BAD))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_leave_field(self) -> None:
        """Esc closes the drawer, or leaves a text field so single-key shortcuts work again."""
        drawer = self.query_one("#drawer")
        if drawer.display:
            drawer.display = False
        elif isinstance(self.focused, Input):
            self.set_focus(None)

    def action_refresh(self, force: bool = False) -> None:
        self.run_refresh(manual=True, force=force)

    def _highlighted_post(self) -> dict | None:
        tab = self.query_one(TabbedContent).active
        table_id = {"overview": "#top-table", "videos": "#videos-table", "compare": "#compare-table"}.get(tab)
        return self._post_for(self._cursor_key(self.query_one(table_id, DataTable))) if table_id else None

    def action_open_post(self) -> None:
        post = self._highlighted_post()
        if post and post["url"]:
            desktop.open_url(post["url"])
        else:
            self.notify("Highlight a video with a link first.", severity="warning")

    def _post_for(self, key: str | None) -> dict | None:
        if not key or "|" not in key:
            return None
        platform, post_id = key.split("|", 1)
        return next((p for p in self.posts if p["platform"] == platform and p["post_id"] == post_id), None)

    @staticmethod
    def _cursor_key(table: DataTable) -> str | None:
        if not table.row_count:
            return None
        try:
            return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None

    @staticmethod
    def _restore_cursor(table: DataTable, key: str | None) -> None:
        if key is None:
            return
        try:
            table.move_cursor(row=table.get_row_index(key))
        except Exception:
            pass


def _hours_since(ts: str | None) -> float:
    if not ts:
        return float("inf")
    try:
        return (analytics.now() - db.parse(ts)).total_seconds() / 3600
    except (TypeError, ValueError):
        return float("inf")


def _short(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width - 1].rstrip(" -_") + "…"


def _cell(text: str | None) -> str:
    """Spreadsheet-safe text: a leading = + - or @ would make Excel run it as a formula."""
    text = text or ""
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _from_first(values: list[float | None]) -> list[float]:
    """Drop the empty hours before the first reading and after the last one (they'd draw as a run of zeros)."""
    known = [i for i, v in enumerate(values) if v is not None]
    return [v or 0.0 for v in values[known[0]:known[-1] + 1]] if known else []


def _clock(fr: trends.Frame):
    """The x axis labels for a frame, as a function of the plot's width."""
    return lambda pw: charts.clock_labels(fr.starts, pw, fr.step.total_seconds() / 3600)


def _slot_label(fr: trends.Frame, i: int) -> str:
    a, b = fr.starts[i], fr.ends[i]
    if fr.daily:
        return f"{a:%a} {a:%b} {a.day}"
    if fr.hourly:
        return f"{a:%a} {fmt_clock(a).replace(':00', '')}"
    return f"{a:%a} {fmt_clock(a).replace(':00', '')}–{fmt_clock(b).replace(':00', '')}"


def _when(fr: trends.Frame, t: datetime | None) -> str:
    if t is None:
        return ""
    if fr.daily:
        return f"on {t:%b} {t.day}"
    same_day = t.date() == fr.now.date()
    return f"at {fmt_clock(t).replace(':00', '')}" + ("" if same_day else f" {t:%a}")
