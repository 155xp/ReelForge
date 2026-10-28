"""ReelForge's window, the Python side: stats for TikTok, YouTube, Instagram and X, help posting by hand,
notifications and updates.

The window itself is the OpenTUI app in ui/ (ui/src/dashboard/); this is what it shows and what its buttons do. It
runs in studio/bridge.py's loop: the window calls the @rpc methods, and each update_* method sends one piece of the
window (an event named after it) for the window to draw. Reads and updates run on worker threads and hand their
results back to the loop, so the window never waits on a slow site.
"""

from __future__ import annotations

import functools
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

from studio.bridge import Loop, Service, rpc

from . import analytics, badges, besttime, config, db, desktop, notify, sync, tabs, trends, videos
from .analytics import fmt_age, fmt_ago, fmt_clock, fmt_delta, fmt_hours, fmt_num, fmt_pct
from .platforms import Platform, PlatformError, PublishItem, browser, connected
from .settings_tab import SettingsTab
from .stats_tab import StatsTab
from .platforms.base import Account, Post
from .view import (BAD, GOOD, MARK, MUTED, SHORT, TYPICAL, Text, act, change_text, chip, chips, js, legend, num,
                   parts, score_text, tag)

try:  # the ReelForge folder's own package: its version and the updater
    from studio import KIT_VERSION
    from studio import update as kit_update
except Exception:  # run on its own, outside a ReelForge folder
    KIT_VERSION, kit_update = "", None
try:  # the sign-up guides and how a typed handle is read (the ReelForge folder's too)
    from studio import signup
except Exception:
    signup = None
try:  # the channels this ReelForge folder has (each its own profile)
    from studio import profiles
except Exception:
    profiles = None

# A test copy (a second ReelForge folder for trying changes, marked by TEST-COPY.txt; see studio/paths.py) says TEST
# in the header and the window title, so it's never mistaken for the real one.
TEST_COPY = (config.APP_DIR.parent / "TEST-COPY.txt").exists()

METRICS = ("views", "followers", "likes")
TOP_COLUMNS = [("title", "Title", 20), ("age_h", "Age", 5), ("views", "Views", 8), ("views_12h", "12h", 6),
               ("score", "Score", 7)]
VIDEO_COLUMNS = [  # (key, label, width); Views 12h is wide enough for its ▼ when the table is sorted by it
    ("platform", "", 4), ("title", "Title", 40), ("age_h", "Age", 5), ("views", "Views", 8),
    ("views_12h", "Views 12h", 11), ("likes", "Likes", 7), ("comments", "Cmts", 6), ("shares", "Shares", 6),
    ("eng", "Eng", 6), ("share_rate", "Share", 6), ("vph", "Views/h", 7), ("score", "Score", 6),
    ("pscore", "On plat.", 8),
]
# Columns of numbers, which line up on the right; the rest read from the left.
RIGHT = {"views", "views_12h", "likes", "comments", "shares", "eng", "share_rate", "vph", "score", "pscore",
         "followers", "gained", "videos", "median", "share"}
# How the Compare tab's Episodes list can be sorted: by when each episode first went up, or by its views on every
# platform added up.
EPISODE_SORTS = {"newest": "Newest", "oldest": "Oldest", "views": "Most views"}
HISTORY_DAYS = 62  # account history kept in memory: the longest range (30 days) and the one before it
TABS = tabs.TAB_IDS  # every tab (the order they sit in along the top is picked on the Settings tab: dashboard/tabs.py)
UPDATE_EVERY_H = 6  # how often ReelForge asks GitHub whether there's a newer version
WATCH_EVERY = 1  # seconds between looks at what the other ReelForge windows (and the hourly job) did
# Demo mode's profiles (and the README's picture of the menu): (name, connected platforms, unread notifications).
DEMO_PROFILES = [("Night Physics", ("tiktok", "youtube", "instagram", "x"), 0),
                 ("Tiny Worlds", ("tiktok", "youtube"), 3)]
DEMO_DELETED = ("Old Experiments", 1, "212.4 MB")  # ... and a deleted one on the Settings tab: (name, days ago, size)
# Why a window can't delete a profile (Dashboard.cant_delete): the pop-up's words, and the Settings tab's note beside it.
CANT_DELETE = {
    "gone": ("That profile isn't there any more.", ""),
    "main": ("{name} is your first channel: it lives in the ReelForge folder itself, so it can't be deleted. Only the "
             "channels you've added can be.", "your first channel, in the ReelForge folder itself: it stays"),
    "here": ("This window is showing {name}. Switch to another profile first (p), then delete it from there.",
             "this window: switch to another profile to delete it"),
    "open": ("{name} is open in another ReelForge window. Close that window (or switch it to another profile), then "
             "try again.", "open in another ReelForge window"),
}
COPIES = {"tiktok": ("copy-tiktok", "Copy TikTok text"), "youtube": ("copy-youtube", "Copy YouTube hashtags"),
          "instagram": ("copy-instagram", "Copy Instagram text"), "x": ("copy-caption", "Copy caption")}
NOTHING_CONNECTED = "Connect an account on the Accounts tab to see your stats here."
# The help: (title, what it says), and for a tab its id as well: the window puts the tabs in the order you see them
# along the top, each with the number that opens it, then Publish (the green button at the right) with its key.
HELP = [
    ("Overview", "Totals for every platform, then views, followers and likes gained per hour (or per 6 hours / per day "
                 "on the longer ranges), stacked by platform. Yellow marks show when each video went up, and hours "
                 "the computer was off are filled in with an estimate, hatched. Point at a bar to see that hour's "
                 "numbers by platform; click a platform in the key to hide it. Under the cards: today's badges, like "
                 "\"Today: top 10% of your days for new TikTok followers\".", "overview"),
    ("Videos", "Every video on every platform. Views 12h is each one's views 12 hours after it went up, so new and old "
               "videos compare fairly (\"in 5h\" until it's that old, — when the computer was off then). Show picks a "
               "platform, a header sorts, and clicking a highlighted row (or Open post) opens it. Above the chart: the "
               "highlighted video's badges, like \"Top 5% of your TikTok videos for views\". The chart compares its "
               "views with your typical video at the same age. Fix episode re-files a post grouped with the wrong "
               "video; Export CSV saves every video as a spreadsheet, with when it went up (date, weekday, hour and "
               "UTC time) and its views 1, 6, 12 and 24 hours in.", "videos"),
    ("Compare", "The platform scoreboard, or pick an episode to see the same video on every platform, each against "
                "that platform's typical video. Newest, Oldest and Most views beside Episodes sort the list (Most "
                "views adds up each episode's views on every platform).", "compare"),
    ("Publish", "The green button at the top right opens it. Pick a video, check the caption, then open each upload "
                f"page: ReelForge copies the right text, shows the file in {desktop.FILES}, and checks for the new "
                "post 10 and 30 minutes later. Remove (or a right-click) hides a video or moves it to the "
                f"{desktop.BIN}; Show hidden brings hidden ones back. Under the videos, Best time to post shows each "
                "platform's part of the day whose videos got the most views in their first day, and when it next "
                "comes round; it needs 2 videos a day old in each of 2 parts of the day, with one clearly "
                "ahead.", "publish"),
    ("Accounts", "Connect the platforms you post to: ReelForge shows only the ones you've connected, everywhere else. "
                 "TikTok and YouTube need just your @handle; Instagram and X also need one log-in. No account yet? "
                 "Sign up opens the platform's own sign-up page (with more than one profile, in a private window of "
                 "your browser, so your other channel stays logged in), and Disconnect hides one again (its stats "
                 "stay saved). Each panel says where that platform's stats come from and when they were last read; "
                 "Type in stats lets you enter the numbers by hand for one ReelForge can't read yet.", "accounts"),
    ("Updates", "Your version, what's new in the next one, and Update and restart: one click downloads it, puts it in "
                "place (your channel, videos and stats stay as they are) and opens ReelForge again.", "updates"),
    ("Settings", "This channel's answers from first-time setup (Change your answers asks the questions again), an FAQ "
                 "(click a question for its answer), the order of the tabs along the top (drag a tab, or click one "
                 "and move it with the arrows; 1-7 follow it, in every profile), what ReelForge set up on this "
                 "computer (the hourly stats read, the reelforge command and the icon) and your profiles: Delete "
                 "beside one, and Restore beside one you deleted. At the bottom, Factory reset "
                 "puts every channel's settings, log-ins and stats in a backup and starts first-time setup again "
                 "(your videos stay), and Uninstall removes ReelForge, keeping your videos in a folder beside it. "
                 f"Neither deletes anything: what they clear goes to a backup or the {desktop.BIN}.", "settings"),
    ("Stats", "Your views, followers and likes added up across your platforms, over time: tick or untick a platform at "
              "the top to count it in the totals or leave it out, and pick 24H, 48H, 7D, 30D or ALL. Point at a chart "
              "to see the totals then, with each platform's part; yellow marks show when each video went up. Beside "
              "each chart: every platform's number now, what it gained over the range and its share of the total. A "
              "stretch the computer was off for is filled in with an estimate, hatched, and the totals start once "
              "every platform you count has a first reading.", "totals"),
    ("Notifications", "The bell at the top right opens the drawer: updates, milestones, badges, finished videos and "
                      "log-ins that need you. A red dot on the bell means something's unread; click one to go "
                      "to it, or the × at its right to delete it (Delete deletes the highlighted one), and Clear "
                      "all deletes them all. The hourly background job (reelforge stats on) adds them while "
                      "ReelForge is closed."),
    ("Profiles", "One profile for each channel you run, each with its own accounts, log-ins, stats, notifications, "
                 "Publish list and settings. The button with your channel's name at the top left switches between "
                 "them (a red dot on it: another profile has unread notifications), adds a new one (the same short "
                 "interview as the first, which helps you make the new channel's accounts) or changes this one's "
                 "settings. Delete beside another profile (there, or on the Settings tab) takes it out of ReelForge "
                 "once you type its name: its folder moves whole into backups, and Restore on the Settings tab brings "
                 "it back. This window's own profile and your first channel can't be deleted. The hourly job reads "
                 "every profile."),
    ("Several windows", "Open ReelForge as many times as you like (one on the Overview and one on Publish, say, or one "
                        "for each profile). Windows on the same profile take turns reading its stats, and as soon as "
                        "one of them (or the hourly job) has read them, every window shows the new numbers, "
                        "notifications and errors. r in a window while another one is reading waits for that read "
                        "instead of starting another."),
    ("Badges", "Badges only ever compare you with yourself, from the numbers ReelForge has stored. Percentages need "
               "at least 10 videos or days to compare, and ties count against you, so a badge is always true."),
]
KEYS = [("1-7", "switch tabs"), ("u", "open Publish (the green button at the top right)"),
        ("r / R", "refresh / force refresh"),
        ("p", "profiles: switch, add, change or delete one"),
        ("Tab", "move between buttons, lists and fields (Enter presses, the arrows move through a list)"),
        ("Esc", "close the drawer or a dialog, or leave a text field"), ("Ctrl+Q", "quit")]


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


def deleted_when(when: datetime | None) -> str:
    """When a profile was deleted, for the Settings tab: deleted today at 4:05 PM, yesterday at ..., on 3 October at ..."""
    if when is None:
        return "deleted"
    today = datetime.now().date()
    day = ("today" if when.date() == today else "yesterday" if when.date() == today - timedelta(days=1) else
           f"on {when.day} {when:%B}")
    return f"deleted {day} at {fmt_clock(when)}"


class Running:
    """How many of this window's reads are under way (on worker threads): each `with` block counts as one."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def __enter__(self) -> None:
        with self._lock:
            self.count += 1

    def __exit__(self, *exc) -> None:
        with self._lock:
            self.count -= 1


def table(columns: list[tuple[str, str, int]], rows: list[tuple[str | None, list]], sort: tuple | None = None,
          bold_sorted_only: bool = False) -> dict:
    """A table for the window: its columns (the sorted one with ▲ or ▼) and rows of cells, each row with the key the
    window hands back when you pick it ("<platform>|<post id>")."""
    cols = []
    for key, label, width in columns:
        arrow = (" ▼" if sort[1] else " ▲") if sort and key == sort[0] else ""
        style = "bold" if arrow or not bold_sorted_only else ""
        cols.append({"key": key, "label": Text(label + arrow, style).json(), "width": width,
                     "right": key in RIGHT})
    return {"columns": cols, "rows": [{"key": k, "cells": [c if isinstance(c, list) else
                                                             (c.json() if isinstance(c, Text) else Text(str(c)).json())
                                                             for c in cells]} for k, cells in rows]}


class Dashboard(StatsTab, SettingsTab, Service):
    def __init__(self, loop: Loop):
        super().__init__(loop)
        self.cfg: dict = {}
        # Every platform (for the Accounts tab, to connect the others), and the connected ones, which show everywhere
        # else (Platform.connected; stored: the platforms with stats, which keep them on).
        self.every: dict[str, Platform] = {}
        self.platforms: dict[str, Platform] = {}
        self.stored: set[str] = set()
        self.config_seen: float | None = None  # config.toml's time: another window connecting a platform changes it
        self.demo = False
        self.screenshots = False
        self.tab = "overview"
        self.tab_order = tabs.DEFAULT_ORDER  # the tabs along the top, left to right (the Settings tab's Tab order)
        self.note_seen = 0  # the newest notification already shown as a pop-up
        self.update_info: dict | None = None  # the last answer from the update check (studio.update.check)
        self.updating = False
        self.badge_list: list = []
        self.first_day: dict = {}  # (platform, post id) -> views at the first reading about a day after posting
        self.range = "24h"
        self.filter: str | None = None
        self.sort = ("score", True)
        self.top_sort = ("score", True)  # Top performers: (column, descending)
        self.compare_target = "board"
        self.episode_sort = "newest"  # the Compare tab's Episodes list (EPISODE_SORTS)
        self.selected_file: Path | None = None
        self.video_key: str | None = None  # the highlighted row on the Videos tab
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
        self.trend_frame: trends.Frame | None = None
        # What the other ReelForge windows did, as this one last looked (see keep_in_step): the store's change count
        # this window shows (db.bump), the shared read state (sync.shared), the notifications as the drawer last
        # showed them (notify.signature), and what another one is reading right now, for the header.
        self.changes = 0
        self.sync_seen: dict | None = None
        self.notes_sig: tuple | None = None
        self.elsewhere = ""
        self.reading = Running()  # this window's own reads: each reloads the window itself when it's done
        self.catching_up = False  # a reload for what another window read is being worked out
        self.last_seen = None
        self.profile = profiles.current() if profiles else None  # the channel this window shows
        self.elsewhere_unread = 0  # unread notifications in the other profiles (the dot on the profile button)
        self.window_lock = None  # held while this window shows its profile (see hold_profile)
        self.deleted_sizes: dict[str, str] = {}  # each deleted profile's backup: how big it is (measure_deleted)

    # --- starting ---------------------------------------------------------------------------

    def start(self, options: dict) -> dict:
        """options: tab, drawer, demo, screenshots (the README's pictures: the demo as a set-up account looks),
        only_demos (the Publish tab lists just the kit's demo videos), unconnected (demo platforms left unconnected),
        switched (the window switched to this profile: Accounts, while it has nothing connected)."""
        from .__main__ import load_platforms

        cfg, every = load_platforms(bool(options.get("demo")), options.get("only_demos", False),
                                    tuple(options.get("unconnected") or ()))
        return self.open(cfg, every, options)

    def open(self, cfg: dict, platforms: dict[str, Platform], options: dict) -> dict:
        """Show these settings and platforms (every one: only the connected ones show, see Platform.connected), with
        the stats database open already; what the window starts with. No tab asked for: the Overview, or Accounts while
        nothing is connected."""
        self.demo = bool(options.get("demo"))
        self.screenshots = bool(options.get("screenshots"))
        self.cfg, self.every = cfg, platforms
        self.stored = self._safe(db.stored_platforms, set())
        self.platforms = connected(self.every, self.stored)
        self.config_seen = _mtime(config.CONFIG_PATH)
        tab = options.get("tab")
        if options.get("switched") and not self.platforms:
            tab = "accounts"  # a profile you switched to with nothing connected yet: where you connect one
        self.tab = tab if tab in TABS else "overview" if self.platforms or tab else "accounts"
        self.load_tab_order()
        saved = db.get_meta("overview_range", "24h")
        self.range = saved if saved in trends.RANGES else "24h"
        saved = db.get_meta("episode_sort", "newest")
        self.episode_sort = saved if saved in EPISODE_SORTS else "newest"
        self.load_totals_choices()
        self.note_seen = self._safe(notify.newest_id, 0)  # what's already there shows in the drawer, not as pop-ups
        self.last_seen = db.get_meta("last_seen")  # totals when ReelForge was last open, for "since you last looked"
        self.changes = self._safe(db.changes, 0)  # before the data it goes with (see keep_in_step)
        if profiles and not self.demo:
            profiles.remember(self.profile)  # ReelForge opens on it next time
            self.hold_profile()
        self.loop.call_soon(self.started)
        return self.init_view(options)

    def init_view(self, options: dict) -> dict:
        try:
            from studio import logo

            anvil, quads = logo.cells(logo.anvil()), logo.quadrants()
        except Exception:
            anvil, quads = [], False
        tags = (f"#{videos.FIRST_TAG} " if videos.FIRST_TAG else "") + "#tag #tag"
        return {
            "platforms": self.platform_info(),
            "tab": self.tab, "drawer": bool(options.get("drawer")), "test": TEST_COPY, "demo": self.demo,
            "screenshots": self.screenshots, "title": "ReelForge TEST" if TEST_COPY else "ReelForge",
            "files": desktop.FILES, "files_window": desktop.FILES_WINDOW, "bin": desktop.BIN,
            "order": list(self.tab_order), "default_order": list(tabs.DEFAULT_ORDER),
            "anvil": anvil, "quadrants": quads, "help": HELP, "keys": KEYS, "version": KIT_VERSION,
            "max_tags": videos.MAX_TAGS, "first_tag": videos.FIRST_TAG, "default_tags": self.cfg.get("default_tags", ""),
            "caption_placeholder": "one short line that hooks the viewer", "tags_placeholder": tags,
            "copies": {k: list(v) for k, v in COPIES.items()},
            "badges_how": badges.HOW, "ranges": {k: v[0] for k, v in trends.RANGES.items()},
            "fit_steps": {k: [s.total_seconds() / 3600 for s in v] for k, v in trends.FIT_STEPS.items()},
            "videos_dir": str(config.videos_dir(self.cfg)),
            "profile": self.profile_view(),
        }

    def platform_info(self) -> list[dict]:
        return [{"key": p.key, "name": p.name, "color": p.color, "short": SHORT.get(p.key, p.key)}
                for p in self.platforms.values()]

    # --- profiles: one for each channel ------------------------------------------------------------

    def profile_view(self) -> dict:
        """The header's profile button: this window's profile, and whether another profile has unread notifications
        (a red dot). The window switches by starting its Python side again on the one you pick (see ui/src/root.tsx)."""
        if self.demo:
            return {"key": ".", "name": DEMO_PROFILES[0][0], "main": True, "several": True,
                    "elsewhere": 0 if self.screenshots else DEMO_PROFILES[1][2]}
        if profiles is None:
            return {"key": ".", "name": "ReelForge", "main": True, "several": False, "elsewhere": 0}
        p = self.profile
        return {"key": p.key, "name": p.name, "main": p.main, "several": profiles.several(),
                "elsewhere": self.elsewhere_unread}

    def update_profile(self) -> None:
        """Every half minute: the other profiles' unread notifications, for the dot on the profile button."""
        if profiles is not None and not self.demo and profiles.several():
            from . import switcher

            try:
                self.elsewhere_unread = switcher.unread_elsewhere(self.profile, profiles.every())
            except Exception:
                pass  # an extra: a profile being made or removed right now
        self.emit("profile", self.profile_view())

    @rpc
    def profiles_menu(self) -> dict:
        """The profile button's menu: every profile (this one first is marked), each with its connected platforms and
        unread notifications (and why it can't be deleted from here, if it can't), then what can be done: a new
        profile, this one's settings, deleting another one."""
        from . import switcher

        rows = []
        if self.demo:
            for i, (name, keys, unread) in enumerate(DEMO_PROFILES):
                rows.append({"key": "." if i == 0 else f"demo-{i}", "number": i + 1, "name": name, "current": i == 0,
                             "main": i == 0, "unread": 0 if i == 0 else unread, "where": "",
                             "why": CANT_DELETE["main"][0].format(name=name) if i == 0 else "",
                             "platforms": [self._tag(k) for k in keys]})
            return {"rows": rows, "current": ".", "demo": True, "onboarded": True}
        for i, p in enumerate(profiles.every() if profiles else [], 1):
            here = p == self.profile
            if here:
                keys = list(self.platforms)
                unread = sum(1 for n in self._safe(notify.recent, []) if not n["read"] and self.shows_note(n))
            else:
                info = switcher.summary(p)
                keys, unread = info["platforms"], info["unread"]
            why = self.cant_delete(p)
            rows.append({"key": p.key, "number": i, "name": p.name, "current": here, "main": p.main,
                         "unread": unread, "where": "" if p.main else p.describe(),
                         "why": CANT_DELETE[why][0].format(name=p.name) if why else "",
                         "platforms": [self._tag(k) for k in keys]})
        return {"rows": rows, "current": self.profile.key if self.profile else ".", "demo": False,
                "onboarded": bool(self.profile and self.profile.onboarded)}

    @staticmethod
    def _tag(key: str) -> dict:
        from .platforms import ORDER

        cls = next(c for c in ORDER if c.key == key)
        return {"key": key, "short": SHORT.get(key, key), "name": cls.name, "color": cls.color}

    # --- deleting a profile, and bringing it back (studio/profiles.py delete and restore) ------------------------

    def hold_profile(self) -> None:
        """This window shows its profile for as long as it's open: a lock of its own in the profile's
        dashboard/data/windows/ (the system lets go of it when the window closes, even in a crash), so no other window
        deletes the profile under it (studio/profiles.py shown). Locks left by windows that crashed are tidied away."""
        from .sync import ReadLock

        folder = profiles.windows(self.profile)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for old in folder.glob("*.lock"):
                if time.time() - old.stat().st_mtime > 60 and not profiles.held(old):
                    old.unlink()
        except OSError:
            pass  # a lock that's busy, or a folder that can't be written to: nothing to tidy
        self.window_lock = ReadLock(folder / f"{os.getpid()}.lock")
        self.window_lock.acquire()

    def let_go_of_profile(self) -> None:
        if self.window_lock is None:
            return
        self.window_lock.release()
        try:
            self.window_lock.path.unlink()
        except OSError:
            pass  # another window of this process's number has it: it's theirs now
        self.window_lock = None

    def cant_delete(self, p) -> str:
        """Why this window can't delete a profile (a key of CANT_DELETE), or "" when it can: never the first one (the
        ReelForge folder itself), this window's own, or one another window is showing."""
        if p is None:
            return "gone"
        if p.main:
            return "main"
        if p == self.profile:
            return "here"
        return "open" if profiles.shown(p) else ""

    def _deleted(self, backup: str):
        return next((d for d in profiles.deleted() if d.backup.name == backup), None) if profiles else None

    @rpc
    def delete_profile_info(self, key: str) -> dict | None:
        """The dialog before deleting a profile: which, everything that goes with it, where it's kept, and the name to
        type. None when it can't be deleted from here, with a pop-up saying why."""
        if self.demo:
            self.notify("Demo mode: nothing is deleted.", timeout=4)
            return None
        p = profiles.get(key) if profiles else None
        why = self.cant_delete(p)
        if why:
            self.notify(CANT_DELETE[why][0].format(name=p.name if p else ""), title="Can't delete it",
                        severity="warning", timeout=10)
            return None
        from studio import reset

        try:
            episodes = sum(1 for d in p.episodes.iterdir() if d.is_dir())
        except OSError:
            episodes = 0
        outside = [f for f in reset.video_folders(p) if f.is_dir() and not reset._inside(f, p.folder)]
        note = Text()
        note.append(p.name, "bold")
        note.append(f"\n{p.describe()}\n\n", MUTED)
        note.append("Deleting it takes it out of ReelForge", "bold")
        videos = f"{episodes} episode{'s' * (episodes != 1)}" if episodes else "none yet"
        note.append(f": its accounts and log-ins, its stats and notifications, its settings, your AI's notes on it and "
                    f"its videos ({videos}).\n\n", MUTED)
        note.append("Nothing is deleted for good.", "bold")
        note.append(" Its folder moves, whole, into backups in the ReelForge folder, and Restore on the Settings tab "
                    "brings it back.", MUTED)
        for f in outside:
            note.append(f"\n\nVideos kept outside its folder stay where they are: {f}", MUTED)
        return {"key": p.key, "name": p.name, "note": note.json(), "word": p.name}

    @rpc
    def delete_profile(self, key: str, typed: str) -> bool:
        """Delete another profile, asked for with its name typed: a worker moves its folder into a backup (waiting
        for a stats read of it under way to finish first), then says how it went. False when it can't be deleted."""
        p = profiles.get(key) if profiles and not self.demo else None
        if self.cant_delete(p) or " ".join(str(typed or "").split()).casefold() != " ".join(p.name.split()).casefold():
            return False
        self.loop.run_worker(self._delete_profile, p, group="profiles")
        return True

    def _delete_profile(self, p) -> None:
        name = p.name
        say = lambda line: self.loop.call_soon(lambda: self.notify(line, timeout=8))  # noqa: E731
        problem = ""
        if not profiles.wait_for_read(p, 90, say):
            problem = f"{name}'s stats are still being read. Try again in a minute."
        else:
            try:
                gone = profiles.delete(p)
            except (ValueError, OSError) as e:
                problem = f"{e} Close any ReelForge window showing it, then try again."
        if problem:
            self.loop.call_soon(lambda: self.notify(problem, title="Not deleted", severity="error", timeout=12))
            return
        self.write_guides()  # your AI's notes no longer list it

        def done() -> None:
            self.notify(f"{name} is kept whole in {gone.where}. Restore on the Settings tab brings it back.",
                        title="Profile deleted", timeout=12)
            self.update_profile()
            if self.tab == "settings":
                self.update_settings()

        self.loop.call_soon(done)

    @staticmethod
    def write_guides() -> None:
        """The first channel's notes for your AI list every channel: write them again once one goes or comes back."""
        try:
            from studio import generate

            generate.write_guides(profiles.main())
        except Exception:
            pass  # notes for your AI, which `reelforge channel --regenerate` writes again too

    @rpc
    def restore_profile(self, backup: str) -> bool:
        """Restore on the Settings tab: a deleted profile back in profiles/, with everything it had."""
        if self.demo:
            self.notify("Demo mode: nothing is changed.", timeout=4)
            return False
        d = self._deleted(backup)
        try:
            if d is None:
                raise ValueError("That deleted profile isn't in backups any more.")
            p = profiles.restore(d, wait=2)
        except (ValueError, OSError) as e:
            self.notify(str(e), title="Not restored", severity="error", timeout=12)
            self.update_settings()
            return False
        self.write_guides()
        self.notify(f"{p.name} is back, as it was. Switch to it with the button at the top left (p).",
                    title="Profile restored", timeout=10)
        self.update_profile()
        self.update_settings()
        return True

    @rpc
    def discard_profile(self, backup: str) -> bool:
        """Move to Recycle Bin on the Settings tab: a deleted profile's backup goes to the Recycle Bin (or the Trash),
        to free its space. A worker does it: a big one takes a moment."""
        if self.demo:
            self.notify("Demo mode: nothing is changed.", timeout=4)
            return False
        d = self._deleted(backup)
        if d is None:
            self.update_settings()
            return False

        def work() -> None:
            name = d.name
            ok = desktop.recycle(d.backup) and not d.backup.exists()
            msg = (f"{name}'s backup is in the {desktop.BIN}." if ok else
                   f"Couldn't move {name}'s backup ({d.backup}) to the {desktop.BIN}: delete that folder yourself.")
            self.loop.call_soon(lambda: (self.notify(msg, severity="information" if ok else "error", timeout=10),
                                         self.update_settings()))

        self.loop.run_worker(work, group="profiles")
        return True

    def profiles_settings(self) -> dict:
        """The Settings tab's Profiles panel: every profile, each with whether this window can delete it (and if not,
        why not), then the deleted ones kept in backups/, the newest first, each with when and how big."""
        if self.demo:
            rows = [{"key": "." if i == 0 else f"demo-{i}", "number": i + 1, "name": name, "current": i == 0,
                     "main": i == 0, "deletable": i > 0,
                     "note": CANT_DELETE["main"][1] if i == 0 else f"profiles{os.sep}{profiles.slug_for(name)}"}
                    for i, (name, _, _) in enumerate(DEMO_PROFILES)] if profiles else []
            name, days, size = DEMO_DELETED
            when = datetime.now().replace(hour=21, minute=12, second=0) - timedelta(days=days)
            slug = profiles.slug_for(name) if profiles else "old-experiments"
            gone = [{"id": "demo", "name": name, "when": deleted_when(when), "size": size,
                     "where": os.path.join("backups", f"deleted-profile-{slug}-{when:%Y-%m-%d-%H%M%S}")}]
            return {"rows": rows, "deleted": gone}
        if profiles is None:
            return {"rows": [], "deleted": []}
        rows = []
        for i, p in enumerate(profiles.every(), 1):
            why = self.cant_delete(p)
            rows.append({"key": p.key, "number": i, "name": p.name, "current": p == self.profile, "main": p.main,
                         "deletable": not why, "note": CANT_DELETE[why][1] if why else p.describe()})
        gone = [{"id": d.backup.name, "name": d.name, "when": deleted_when(d.when), "where": d.where,
                 "size": self.deleted_sizes.get(d.backup.name, "")} for d in profiles.deleted()]
        return {"rows": rows, "deleted": gone}

    def measure_deleted(self) -> None:
        """How big each deleted profile's backup is, for the Settings tab (on a worker: a big one takes a moment)."""
        if profiles is None or self.demo:
            return
        from studio.reset import fmt_size

        self.deleted_sizes = {d.backup.name: fmt_size(profiles.size(d.backup)) for d in profiles.deleted()}

    def started(self) -> None:
        self.update_profile()
        self.show_platforms()
        self.reload()
        self.scan_files()
        self.update_notes()
        if self.tab == "settings":
            self.update_settings()
        self.start_updates()
        self.run_refresh(manual=False)
        self.loop.run_worker(self.compact_db, group="maintenance")
        self.loop.set_interval(60, self.update_best_time)  # "next: today 8 PM" moves on with the clock
        minutes = minutes_setting(self.cfg, "refresh_minutes", 30)
        if minutes:
            self.loop.set_interval(min(300, max(minutes * 60, 60)), lambda: self.run_refresh(manual=False))
        self.loop.set_interval(30, self.tick)
        self.loop.set_interval(WATCH_EVERY, self.keep_in_step)
        # Say what changed while ReelForge was closed once the first refresh is in (or after a while without one).
        self.loop.set_timer(45, self.welcome_back)

    def stop(self) -> None:
        for w in self.loop.workers.values():
            w.is_cancelled = True
        self.let_go_of_profile()

    def show_platforms(self) -> None:
        """Only the connected platforms show anywhere: the window's own parts (the Publish buttons) follow this view,
        and the rest is sent from self.platforms. What's switched off or filtered to stays only while it's connected."""
        self.hidden_lines &= set(self.platforms)
        if self.filter not in self.platforms:
            self.filter = None
        self.emit("platforms", {"platforms": self.platform_info()})

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
                name = p["episode"] or videos.strip_hashtags(p["title"] or "") or "A video"
                notify.add("hot", f"Taking off on {self.platforms[p['platform']].name}",
                           f"{name[:60]} is doing {p['score']:.1f}× your typical video.",
                           key=f"hot:{p['platform']}|{p['post_id']}")
        badges.notify_new(self.posts, self.first_day, self.account_rows, self.platforms)

    def shows_note(self, note: dict) -> bool:
        """Whether a notification is in the drawer: not one about a platform that isn't connected (it's back once you
        connect that platform again)."""
        key = notify.platform_of(note, {k: p.name for k, p in self.every.items()})
        return key is None or key in self.platforms

    def show_new_notes(self) -> None:
        """Pop up what's been added since the last look (a few at most), then refresh the bell and the drawer."""
        new = self._safe(lambda: notify.since(self.note_seen), [])
        for n in [n for n in new if self.shows_note(n)][-4:]:
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

    def tell_others(self) -> None:
        """Something every window shows changed in this one (typed-in stats, an episode, an upload page opened, a
        hidden video): the other ReelForge windows load it (see keep_in_step). This one shows it already, unless
        another window changed something too meanwhile: then this one loads that."""
        changes = self._safe(db.bump, None)
        if changes == self.changes + 1:
            self.changes = changes

    def tick(self) -> None:
        """Every half minute: the "updated" time, the other profiles' news, and the charts once a new hour (or day)
        starts."""
        self.update_header()
        self.update_profile()
        if self.trend_frame is not None and analytics.now() >= self.trend_frame.ends[-1]:
            self.update_trends()
            self.update_cards()
        if self.tab == "totals" and self.totals_frame is not None and analytics.now() >= self.totals_frame.ends[-1]:
            self.update_totals()

    # --- data -----------------------------------------------------------------------------

    def run_refresh(self, manual: bool, force: bool = False, only: str | None = None) -> None:
        self.loop.run_worker(self._refresh, manual, force, only, group="refresh", exclusive=True)

    def _refresh(self, manual: bool, force: bool, only: str | None) -> None:
        """Read the stats (or wait for another window's read; see sync.refresh), then show them here. The other
        windows show them too (keep_in_step)."""
        platforms = {only: self.platforms[only]} if only in self.platforms else self.platforms
        worker = self.loop.current_worker()
        with self.reading:
            try:
                result = sync.refresh(platforms, self.cfg, manual, force,
                                      on_status=lambda s: self.loop.call_soon(self.set_status, s),
                                      stop=lambda: worker.is_cancelled)
                # Crunch the numbers here, off the loop's thread, so the window never stalls.
                data = self.load_data() if result.done else None
            except Exception as e:  # the database was busy, say: report it, keep running
                result, data = sync.Result(errors=[f"{type(e).__name__}: {e}"]), None
            if result.busy and worker.is_cancelled:
                return  # it stopped waiting: a newer refresh took over, or ReelForge is closing
            self.loop.call_soon(self.after_refresh, result, manual, data)

    def after_refresh(self, result: sync.Result, manual: bool, data: dict | None) -> None:
        self.set_status("")
        for e in result.errors:
            self.notify(e, title="Refresh failed", severity="error", timeout=10)
        if result.done:
            self.show_new_data(result.changes, data)
        else:
            self.update_accounts()
            if manual and not result.errors:
                if result.busy:
                    who = result.waited or "ReelForge"  # None: this window's own automatic read
                    self.notify(f"{who[0].upper()}{who[1:]} has been reading your stats for {sync.WAIT // 60} "
                                "minutes, so this one stopped waiting. Try again in a moment.", severity="warning",
                                timeout=10)
                elif result.waited:
                    self.notify(f"Up to date: {result.waited} just read your stats.", timeout=6)
                elif not any(p.has_stats for p in self.platforms.values()):
                    self.notify("Nothing to read yet: connect an account on the Accounts tab.")
                else:
                    self.notify("Up to date. Platforms read through the browser wait a bit between reads; "
                                "R reads them anyway.")
        self.keep_in_step(read_here=True)  # what another window read meanwhile, or while this one waited for it

    def show_new_data(self, changes: int | None, data: dict | None) -> None:
        """New numbers on screen, whichever window read them (changes: the store's change count they go with), with
        the notifications they bring and, the first time, how much changed since you last looked."""
        self.changes = max(self.changes, changes or 0)
        self.reload(data)
        self.celebrate()
        self.show_new_notes()
        if self.last_seen is not None:
            self.welcome_back()
        else:
            self.save_seen()

    def keep_in_step(self, read_here: bool = False) -> None:
        """Every second, and after each of this window's own reads (read_here): what the other ReelForge windows, and
        the hourly job, are up to. A read one of them has under way shows in the header, one it finished shows here
        too, and so do its notifications and errors."""
        self.follow_config()  # a platform another window connected or disconnected
        self.follow_tab_order()  # a tab another window moved
        try:
            with db.connect() as c:  # one quick look at the store
                state, changes, notes = sync.shared(c), db.changes(c), notify.signature(c)
        except sqlite3.Error:
            return  # busy: the next look
        run = sync.reading_elsewhere(state)
        elsewhere = f"refreshing {run['what']}…" if run else ""
        header = elsewhere != self.elsewhere
        self.elsewhere = elsewhere
        if state != self.sync_seen and sync.adopt(state):  # their errors, and when each platform is read next
            self.sync_seen = state
            self.update_accounts()
            header = True
        if header:
            self.update_header()
        # What another ReelForge saved since this window last loaded, worked out off the loop's thread (a read under
        # way here reloads this window itself when it's done).
        if changes > self.changes and not self.catching_up and (read_here or not self.reading.count):
            self.catching_up = True
            self.loop.run_worker(self._load_shared, changes, group="shared")
        if notes != self.notes_sig:
            self.show_new_notes()
            # Another window's update check (a new version comes with a notification): the Updates tab says so too.
            info = self._safe(lambda: db.get_meta("update_check"), None)
            if info and info != self.update_info and not self.demo and not self.updating:
                self.update_info = info
                self.show_update()

    def _load_shared(self, changes: int) -> None:
        try:
            data = self.load_data()
        except Exception:
            data = None  # the database was busy: the next look tries again
        self.loop.call_soon(self.shared_loaded, changes, data)

    def shared_loaded(self, changes: int, data: dict | None) -> None:
        self.catching_up = False
        if data is not None and changes > self.changes:  # not older than what this window shows
            self.show_new_data(changes, data)
            if self.tab == "publish":
                self.scan_files()  # a video another window hid, or posted

    def compact_db(self) -> None:
        try:
            db.compact()
        except Exception:
            pass  # thinning old snapshots can wait for the next start

    def load_data(self) -> dict:
        """Everything the window shows, from the database. Safe to run on a worker thread."""
        parsed = analytics.parse_series(db.post_series(analytics.history_since()))
        since = (analytics.now() - timedelta(days=HISTORY_DAYS)).isoformat(timespec="seconds")
        posts = [p for p in db.posts_latest() if p["platform"] in self.platforms and p["published_at"]]
        analytics.add_early_views(analytics.enrich(posts, parsed), analytics.parse_series(db.early_series()))
        history = {key: db.account_series(key, "") for key in self.platforms}  # all of it, for the Stats tab's ALL
        return {
            "parsed": parsed,
            "posts": posts,
            "latest": db.latest_accounts(),
            "episodes": db.episodes(),
            "account_rows": {key: [r for r in rows if r["ts"] >= since] for key, rows in history.items()},
            "account_history": history,
            "first_day": badges.first_day_views(),
        }

    def reload(self, data: dict | None = None) -> None:
        data = data or self.load_data()
        self.parsed, self.posts, self.latest = data["parsed"], data["posts"], data["latest"]
        self.episodes, self.account_rows = data["episodes"], data["account_rows"]
        self.account_history = data["account_history"]
        self.first_day = data["first_day"]
        self.update_header()
        self.update_overview()
        self.update_badges()
        self.update_uploads()
        self.update_accounts()
        self.update_posted()
        self.update_best_time()
        # Tabs you're not looking at are rebuilt when you open them.
        self.stale = {"videos", "compare", "totals"}
        self.update_active_tab()

    def update_active_tab(self) -> None:
        if self.tab in self.stale:
            self.stale.discard(self.tab)
            if self.tab == "videos":
                self.update_videos()
            elif self.tab == "totals":
                self.update_totals()
            else:
                self.update_episode_list()
                self.update_compare()

    @rpc
    def tab_opened(self, tab: str) -> None:
        """The window switched tabs (a key, a click, or a notification)."""
        if tab not in TABS:
            return
        self.tab = tab
        self.update_active_tab()
        if tab == "publish":
            self.scan_files()
        elif tab == "settings":
            self.update_settings()

    def set_status(self, text: str) -> None:
        self.status = text
        self.update_header()

    def update_header(self) -> None:
        """When the stats were read, under the Refresh button at the top ("refreshed": how long ago, and the read
        under way, here or in another window, if there is one), and the line at the foot of the window ("header": see
        header_line). The platforms aren't listed at the foot any more (DJ, 2026-10-28): only one whose last read
        failed is."""
        stamps = [r["ts"] for r in self.latest.values()]
        self.emit("refreshed", {"ago": fmt_ago(max(stamps) if stamps else None),
                                "reading": self.status or self.elsewhere})  # this window's read, or another one's
        self.emit("header", {"line": self.header_line(False).json(), "short": self.header_line(True).json()})

    def header_line(self, short: bool) -> Text:
        """The foot of the window, at the left: the TEST or DEMO badge, a nudge to connect an account while none is,
        and any platform whose last read failed (a click shows why, on Accounts). short: the same with TT / YT / IG /
        X, for a narrow window."""
        t = Text()
        gap, after_badge = ("  ", "  ") if short else ("    ", "   ")
        if TEST_COPY:
            t.append(" TEST ", "bold #ffffff on #e8213a")
            t.append(after_badge)
        if self.demo and not self.screenshots:
            t.append(" DEMO ", "bold #0a0c0f on #ffcc33")
            t.append(after_badge)
        if not self.platforms:
            t.append("No accounts connected yet  ", MUTED)
            t.append_text(chip("Connect one", act("tab", "accounts")))
            t.append(gap)
        failed = [SHORT.get(p.key, p.key) if short else p.name for p in self.platforms.values()
                  if p.key in sync.last_errors]
        if failed:
            t.append(f"● {', '.join(failed)}: last refresh failed", f"bold {BAD}", act("tab", "accounts"))
            if not short:
                t.append("  see Accounts", MUTED, act("tab", "accounts"))
        return t

    # --- overview -------------------------------------------------------------------------

    def update_overview(self) -> None:
        self.update_cards()
        self.update_trends()
        self.update_top()
        self.update_latest()

    def update_cards(self) -> None:
        """The All platforms card and one per platform: totals, 24-hour change, and views per hour."""
        fr = trends.frame("24h", analytics.now())
        captions = ["views per hour · last 24h", "views per hour", "views/h"]  # the first that fits
        sums: list[float | None] = [None] * fr.n
        totals: dict[str, list] = {f: [] for f in METRICS}
        changes: dict[str, list] = {f: [] for f in METRICS}
        cards = []
        for p in self.platforms.values():
            rows = self.account_rows.get(p.key, [])
            latest = self.latest.get(p.key)
            change = {f: trends.change(rows, f, 24) for f in METRICS}
            gains = trends.bucket(trends.points(rows, "views"), fr).gains
            for i, g in enumerate(gains):
                if g is not None:
                    sums[i] = (sums[i] or 0) + g
            card = {"id": p.key, "color": p.color, "titles": [p.name, SHORT.get(p.key, p.name)],
                    "gains": _from_first(gains), "captions": captions}
            if latest is not None:
                card.update(values={f: latest[f] for f in METRICS}, changes=change)
            elif not p.has_stats:
                how = "log in once" if p.browser_stats and p.public_handle else "add your handle"
                card["message"] = Text.assemble(("not tracking yet\n", MUTED), ("Accounts tab: ", MUTED),
                                                (how, "bold")).json()
            else:
                card["message"] = Text("waiting for the first refresh", MUTED).json()
            cards.append(card)
            for f in METRICS:
                if latest is not None and latest[f] is not None:
                    totals[f].append(latest[f])
                if change[f] is not None:
                    changes[f].append(change[f])
        total = {"id": "total", "color": GOOD, "titles": ["All platforms", "All"], "gains": _from_first(sums),
                 "captions": captions}
        if sum(1 for k in self.platforms if k in self.latest):
            total.update(values={f: sum(v) if v else None for f, v in totals.items()},
                         changes={f: sum(v) if v else None for f, v in changes.items()})
        elif not self.platforms:
            total["message"] = Text.assemble(("no accounts connected yet\n", MUTED), ("Accounts tab: ", MUTED),
                                             ("connect one", "bold")).json()
        else:
            total["message"] = Text("no stats yet", MUTED).json()
        # The All platforms card adds up two or more (or says how to connect the first one).
        self.emit("cards", {"cards": cards if len(self.platforms) == 1 else [total, *cards]})

    def update_trends(self) -> None:
        """The Overview's three charts: what each platform gained per bucket, stacked. Each comes in every bucket
        size the window may need (trends.frame_fit: a chart too narrow for a bar per bucket combines buckets so every
        bar keeps its columns and a gap), and the window draws the one that fits."""
        fr = trends.frame(self.range, analytics.now())
        self.trend_frame = fr
        ranges = Text()
        for key, (label, _, _) in trends.RANGES.items():
            ranges.append_text(chip(label, act("set_range", key), key == self.range))
            ranges.append(" ")
        ranges.append("   ")
        visible = [p for p in self.platforms.values() if p.key not in self.hidden_lines]
        span = trends.RANGES[self.range][0].lower()
        metrics = {}
        fits = [trends.frame_span(trends.RANGES[self.range][1] + step, step, fr.now) for step in
                trends.FIT_STEPS[self.range]]
        for metric in METRICS:
            pts = {p.key: trends.points(self.account_rows.get(p.key, []), metric) for p in visible}
            pts = {k: v for k, v in pts.items() if v}
            if not pts:
                metrics[metric] = {"empty": NOTHING_CONNECTED if not self.platforms else
                                   "Every platform is hidden: click a name above to show it again." if not visible
                                   else None}
                continue
            s = trends.summarise(pts, fr)
            variants = []
            for fit in fits:
                keep = next(i for i in range(fit.n) if fit.ends[i] > fr.starts[0])
                view = trends.Frame(fit.starts[keep:], fit.ends[keep:], fit.now, fit.step)
                variants.append(self.trend_variant(view, pts, visible))
            metrics[metric] = {"variants": variants, "span": span, "hourly": fr.hourly,
                               "summary": {"latest": s.latest, "gained": s.gained, "pace": s.pace,
                                           "change": s.change}}
        self.emit("trends", {
            "range": self.range, "ranges": ranges.json(),
            "legend": legend(self.platforms.values(), self.hidden_lines).json(),
            "legend_short": legend(self.platforms.values(), self.hidden_lines, short=True).json(),
            "metrics": metrics,
        })

    def trend_variant(self, fr: trends.Frame, pts: dict, visible: list[Platform]) -> dict:
        """One bucket size of a chart: its buckets (labels for the axis and the hover read-out), each platform's gains
        per bucket (the last one still filling up, so drawn dimmer; guess: how much of each is an estimate, filling a
        gap in the readings, drawn hatched) and the marks where videos went up."""
        series = []
        for p in visible:
            if p.key in pts:
                b = trends.bucket(pts[p.key], fr, estimate=True)
                series.append({"key": p.key, "name": p.name, "color": p.color, "values": b.gains,
                               "faint": [i == fr.n - 1 for i in range(fr.n)], "guess": b.est})
        unit = {"h": "per hour", "day": "per day"}.get(fr.unit(), f"per {fr.unit()}")
        return {"step_h": fr.step.total_seconds() / 3600, "n": fr.n, "unit": unit, "slots": slot_info(fr),
                "series": series, "marks": [{"x": m[0], "label": m[1]} for m in self.post_marks(fr)]}

    def post_marks(self, fr: trends.Frame) -> list[tuple[float, str]]:
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
                marks.append((i + frac, trends.short_title(e["title"], titles)))
        return marks

    @rpc
    @db_safe
    def set_range(self, key: str) -> None:
        if key in trends.RANGES and key != self.range:
            self.range = key
            db.set_meta("overview_range", key)
            self.update_trends()

    def update_top(self) -> None:
        title = [(Text("TOP PERFORMERS  ", "bold"), 0), (chip("Open post", act("open_post")), 0),
                 (Text("   score = × your typical video", MUTED), 1)]
        ranked = sorted((p for p in self.posts if p["score"] is not None and (p["views"] or 0) >= 50),
                        key=lambda p: p["score"], reverse=True)[:15]
        # The episode's title where ReelForge knows it (captions carry hashtags and links), without the opening every
        # title shares, so the narrow column shows what tells the videos apart.
        titles = {e["id"]: e["title"] for e in self.episodes}
        rows = [(trends.distinct_title(titles.get(p["episode_id"]) or videos.strip_hashtags(p["title"] or ""),
                                       list(titles.values())) or "(untitled)", p) for p in ranked]
        key, reverse = self.top_sort
        rows.sort(key=lambda r: r[0].lower() if key == "title" else _value(r[1], key) or 0, reverse=reverse)
        cells = [(f"{p['platform']}|{p['post_id']}",
                  [tag(self.platforms[p["platform"]]), Text(name), Text(fmt_age(p["age_h"])), num(p["views"]),
                   _after(p, 12), score_text(p["score"])]) for name, p in rows]
        self.emit("top", {"title": parts(title), **table([("platform", "", 4), *TOP_COLUMNS], cells, self.top_sort)})

    def update_latest(self) -> None:
        """The newest video on every platform: how it's doing so far."""
        heading = Text("LATEST VIDEO  ", "bold")
        body = Text()
        newest = None
        for e in self.episodes:
            ps = [q for q in self.posts if q["episode_id"] == e["id"]]
            if ps and (newest is None or min(q["published_at"] for q in ps) > newest[2]):
                newest = (e, ps, min(q["published_at"] for q in ps))
        if newest is None:
            body.append("Your newest video shows up here once it's posted.", MUTED)
        else:
            e, ps, first = newest
            heading.append(f"posted {fmt_ago(first)}   ", MUTED)
            heading.append_text(chip("Compare", act("show_episode", e["id"])))
            body.append(e["title"] + "\n", "bold")
            by = {q["platform"]: q for q in ps}
            for p in self.platforms.values():
                q = by.get(p.key)
                body.append_text(tag(p))
                if not q:
                    body.append("   not posted yet\n", MUTED)
                    continue
                body.append(f" {fmt_num(q['views']):>8} views", "bold")
                body.append(f" {fmt_num(q['likes']):>7} likes", MUTED)
                body.append(f" {fmt_num(q['vph']):>7}/h ", MUTED)
                body.append_text(score_text(q["score"]))
                body.append("\n")
            total = sum(q["views"] or 0 for q in ps)
            body.append(f"{fmt_num(total)} views on {len(by)}/{len(self.platforms)} platforms", MUTED)
        self.emit("latest", {"heading": heading.json(), "body": body.json()})

    @rpc
    def show_episode(self, episode_id: int) -> None:
        self.compare_target = f"ep-{episode_id}"
        self.switch_tab("compare")
        self.update_episode_list()
        self.update_compare()

    def switch_tab(self, tab: str) -> None:
        """Show a tab from here (a notification, Compare on the latest video): the window opens it, rebuilt first if
        it was waiting to be."""
        self.tab = tab
        self.emit("tab", {"tab": tab})
        self.update_active_tab()

    # --- videos ---------------------------------------------------------------------------

    def update_videos(self, select: str | None = None) -> None:
        """The Videos table, with the highlighted video still highlighted, or `select` ("<platform>|<post id>")."""
        key, reverse = self.sort
        rows = [p for p in self.posts if not self.filter or p["platform"] == self.filter]

        def sort_value(p):
            v = _value(p, key)
            if key in ("title", "platform"):
                return (v or "").lower()
            return v if v is not None else float("-inf")

        rows.sort(key=sort_value, reverse=reverse)
        cells = [(f"{p['platform']}|{p['post_id']}", [
            tag(self.platforms[p["platform"]]), Text(p["title"] or "(untitled)"), Text(fmt_age(p["age_h"])),
            num(p["views"], "bold"), _after(p, 12), num(p["likes"]), num(p["comments"]), num(p["shares"]),
            Text(fmt_pct(p["eng"])), Text(fmt_pct(p["share_rate"])), num(p["vph"]), score_text(p["score"]),
            score_text(p.get("pscore"))]) for p in rows]
        filters = Text("SHOW ", f"bold {MUTED}")
        filters.append_text(chip("All", act("set_filter", ""), not self.filter))
        for pl in self.platforms.values():
            filters.append(" ")
            filters.append_text(chip(pl.name, act("set_filter", pl.key), self.filter == pl.key))
        filters.append("    ")
        hint = [(filters, 0),
                (chips(("Open post", act("open_post")), ("Fix episode", act("fix_episode")),
                       ("Export CSV", act("export_csv"))), 0),
                (Text(f"    {len(rows)} videos · click a header to sort · click a row again to open it", MUTED), 1)]
        keys = [k for k, _ in cells]
        if select in keys:
            self.video_key = select
        elif self.video_key not in keys:
            self.video_key = keys[0] if keys else None
        self.emit("videos", {"hint": parts(hint), **table(VIDEO_COLUMNS, cells, self.sort, bold_sorted_only=True),
                             "select": self.video_key, "focus": select is not None})
        self.update_video_detail()

    @rpc
    def export_csv(self) -> None:
        """Every video's numbers as a spreadsheet file (data/exports/), shown in Explorer or Finder: when it went up
        (this computer's date, weekday and hour, and the platform's own time in UTC) and its views 1, 6, 12 and 24
        hours in (empty where ReelForge wasn't reading then, or the video isn't that old yet)."""
        import csv

        folder = config.DATA_DIR / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"videos-{datetime.now():%Y%m%d-%H%M}.csv"
        fields = ["platform", "title", "episode", "posted", "posted_weekday", "posted_hour", "posted_utc",
                  "age_hours", "views", *(f"views_after_{h}h" for h in analytics.AFTER_HOURS), "likes", "comments",
                  "shares", "engagement", "share_rate", "views_per_hour", "score", "score_on_platform", "url"]
        try:
            with path.open("w", newline="", encoding="utf-8-sig") as f:  # the BOM makes Excel read it as UTF-8
                out = csv.writer(f)
                out.writerow(fields)
                for p in sorted(self.posts, key=lambda q: q["published_at"], reverse=True):
                    local = p["published"].astimezone()
                    after = p.get("after", {})
                    out.writerow([self.platforms[p["platform"]].name, _cell(p["title"]), _cell(p["episode"]),
                                  local.strftime("%Y-%m-%d %H:%M"), local.strftime("%A"), local.hour,
                                  p["published"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  round(p["age_h"], 1), p["views"],
                                  *(None if after.get(h) is None else round(after[h]) for h in analytics.AFTER_HOURS),
                                  p["likes"], p["comments"], p["shares"],
                                  None if p["eng"] is None else round(p["eng"], 4),
                                  None if p["share_rate"] is None else round(p["share_rate"], 4),
                                  round(p["vph"], 1), None if p["score"] is None else round(p["score"], 2),
                                  None if p.get("pscore") is None else round(p["pscore"], 2), p["url"] or ""])
        except OSError as e:
            self.notify(f"Couldn't write {path.name}: {e}", severity="error")
            return
        desktop.reveal(path)
        self.notify(f"{len(self.posts)} videos saved to {path.name} ({desktop.FILES} is showing it).", timeout=8)

    @rpc
    def set_filter(self, key: str) -> None:
        self.filter = key or None
        self.update_videos()

    @rpc
    def open_row(self, key: str) -> None:
        """Clicking an already-highlighted row (or Enter) opens that post."""
        post = self._post_for(key)
        if post and post["url"]:
            desktop.open_url(post["url"])

    @rpc
    def sort_top(self, key: str) -> None:
        """Click a header to sort the top 15 by it; click it again to flip the order."""
        if key == "platform":
            return
        self.top_sort = (key, not self.top_sort[1] if self.top_sort[0] == key else key != "title")
        self.update_top()

    @rpc
    def sort_videos(self, key: str) -> None:
        self.sort = (key, not self.sort[1] if self.sort[0] == key else key not in ("title", "platform"))
        self.update_videos()

    @rpc
    def video_highlighted(self, key: str | None) -> None:
        """The window moved the Videos table's highlight."""
        if key != self.video_key:
            self.video_key = key
            self.update_video_detail()

    def update_video_detail(self) -> None:
        post = self._post_for(self.video_key)
        self.update_video_badges(post)
        if not post:
            self.emit("detail", {"key": None, "title": Text("VIEWS SINCE POSTING", "bold").json(),
                                 "empty": "Pick a video above to see its views against your typical video's."})
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
            series.append({"key": "typical", "name": typical, "color": TYPICAL, "xs": txs, "ys": tys, "style": "line"})
        if "this" not in self.hidden_curves:
            series.append({"key": "this", "name": "this video", "color": p.color, "xs": xs, "ys": ys,
                           "style": "area"})
        title = Text("VIEWS SINCE POSTING  ", "bold")
        for which, label, color in (("this", "this video", p.color), ("typical", typical, TYPICAL)):
            off = which in self.hidden_curves
            title.append(f"━ {label}", "strike #4a515c" if off else (f"bold {color}" if which == "this" else color),
                         act("toggle_curve", which))
            title.append("  ")
        title.append(f" {(post['title'] or '')[:50]} · {fmt_num(post['views'])} views", MUTED)
        empty = None
        if not any(s["xs"] for s in series):
            empty = ("Both lines are hidden: click one above to show it." if len(self.hidden_curves) == 2
                     else "No snapshots for this video yet; it fills in after a couple of refreshes.")
        self.emit("detail", {"key": self.video_key, "title": title.json(), "series": series, "span": span,
                             "empty": empty})

    @rpc
    def toggle_curve(self, which: str) -> None:
        self.hidden_curves ^= {which}
        self.update_video_detail()

    @rpc
    def toggle_line(self, key: str) -> None:
        """Hide or show one platform on every chart (the keys show which are off)."""
        self.hidden_lines ^= {key}
        self.update_trends()
        if self.tab == "compare":
            self.update_compare()
        else:
            self.stale.add("compare")  # redrawn when you open it

    # --- compare --------------------------------------------------------------------------

    def update_episode_list(self) -> None:
        # How many platforms each episode is on (a second post on the same platform doesn't count twice), and its views
        # on all of them.
        on: dict[int, set[str]] = {}
        views: dict[int, int] = {}
        for p in self.posts:
            if p["episode_id"]:
                on.setdefault(p["episode_id"], set()).add(p["platform"])
                views[p["episode_id"]] = views.get(p["episode_id"], 0) + (p["views"] or 0)
        episodes = list(self.episodes)  # newest first (db.episodes)
        if self.episode_sort == "oldest":
            episodes.reverse()
        elif self.episode_sort == "views":
            episodes.sort(key=lambda e: views.get(e["id"], 0), reverse=True)  # ties stay newest first
        items = [{"id": "board", "lines": [Text("◆ Platform scoreboard", "bold #ffcc33").json()]}]
        titles = [e["title"] for e in self.episodes]
        for e in episodes:
            count = len(on.get(e["id"], ()))
            if self.episode_sort == "views":  # each one's views beside it, so the order explains itself
                label = Text(trends.distinct_title(e["title"], titles)[:27].ljust(27))
                label.append(f" {fmt_num(views.get(e['id'], 0)):>6}", "bold")
            else:
                label = Text(trends.distinct_title(e["title"], titles)[:30].ljust(30))
            label.append(f" {count}/{len(self.platforms)}", GOOD if count == len(self.platforms) else MUTED)
            items.append({"id": f"ep-{e['id']}", "lines": [label.json()]})
        ids = [i["id"] for i in items]
        sort = chips(*((name, act("sort_episodes", key), key == self.episode_sort)
                       for key, name in EPISODE_SORTS.items()))
        self.emit("episodes", {"items": items, "selected": self.compare_target if self.compare_target in ids
                               else "board", "sort": sort.json()})

    @rpc
    @db_safe
    def sort_episodes(self, key: str) -> None:
        """Newest, Oldest or Most views beside the Episodes list: sort it that way, here and in the next window."""
        if key in EPISODE_SORTS and key != self.episode_sort:
            self.episode_sort = key
            self.update_episode_list()
            db.set_meta("episode_sort", key)

    @rpc
    def pick_episode(self, option_id: str) -> None:
        if option_id and option_id != self.compare_target:
            self.compare_target = option_id
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
        measured = [p for p in ps if stats[p.key]["posts"]]
        at_day = bool(measured) and all(stats[p.key]["at_day"] for p in measured)
        bars = [
            ("MEDIAN VIEWS PER VIDEO" + (" · AT 24 HOURS" if at_day else " · SO FAR"),
             [(p.name, stats[p.key]["median"] or 0, p.color, fmt_num(stats[p.key]["median"])) for p in ps]),
            ("LIKE RATE  likes / views",
             [(p.name, stats[p.key]["likes"] or 0, p.color, fmt_pct(stats[p.key]["likes"])) for p in ps]),
            ("FOLLOWERS GAINED · " + ("7 DAYS" if tracked_days >= 8 else "SINCE TRACKING STARTED"),
             [(p.name, stats[p.key]["followers"] or 0, p.color, fmt_delta(stats[p.key]["followers"]) or "—")
              for p in ps]),
        ]
        curves = {p.key: analytics.typical_curve(self.posts, self.parsed, p.key, 72.0) for p in ps}
        # Show as much of the first 3 days as there's history for, so short histories fill the chart.
        horizon = max((xs[-1] for xs, _ in curves.values() if xs), default=72.0)
        charts = []
        for p in ps:
            xs, ys = curves[p.key]
            series = [{"key": p.key, "name": p.name, "color": p.color, "xs": xs, "ys": ys, "style": "area"}]
            heading = Text.assemble((p.name + "  ", f"bold {p.color}"),
                                    (f"typical video, first {fmt_age(horizon)}", MUTED))
            if ys:
                heading.append(f" · {fmt_num(ys[-1])} views by {fmt_age(xs[-1])}", MUTED)
            charts.append(self.compare_chart(p, heading, series, horizon, "Needs a few videos with some history."))
        rows = []
        for p in ps:
            s = stats[p.key]
            latest = self.latest.get(p.key)
            best = s["best"]
            rows.append((f"{best['platform']}|{best['post_id']}" if best else None, [
                tag(p), num(latest["followers"] if latest else None), Text(fmt_delta(s["followers"])),
                num(len(s["posts"])), num(s["median"]), Text(fmt_pct(s["likes"])), Text(fmt_pct(s["share"])),
                Text(f"{fmt_num(best['views'])} · {best['title'] or '(untitled)'}" if best else "—")]))
        columns = [("platform", "", 4), ("followers", "Followers", 9), ("gained", "Gained", 7), ("videos", "Videos", 6),
                   ("median", "Median", 8), ("likes", "Likes", 6), ("share", "Share", 6), ("title", "Best video", 34)]
        self.emit("compare", {"heading": Text.assemble(("PLATFORM SCOREBOARD  ", "bold"),
                                                       ("which platform is working", MUTED)).json(),
                              "bars": bars, "charts": charts, "table": table(columns, rows)})

    def compare_episode(self, episode_id: int) -> None:
        posts: dict[str, dict] = {}
        for q in sorted((q for q in self.posts if q["episode_id"] == episode_id), key=lambda q: q["published_at"]):
            posts.setdefault(q["platform"], q)  # the first post on each platform
        title = next((e["title"] for e in self.episodes if e["id"] == episode_id), "")
        ps = list(self.platforms.values())
        bars = [
            ("VIEWS", [(p.name, posts[p.key]["views"] or 0 if p.key in posts else 0, p.color,
                        fmt_num(posts[p.key]["views"]) if p.key in posts else "not posted") for p in ps]),
            ("ENGAGEMENT", [(p.name, (posts[p.key]["eng"] or 0) if p.key in posts else 0, p.color,
                             fmt_pct(posts[p.key]["eng"]) if p.key in posts else "—") for p in ps]),
        ]
        charts = []
        for p in ps:
            q = posts.get(p.key)
            if not q:
                charts.append(self.compare_chart(p, Text(p.name, f"bold {p.color}"), [], 1,
                                                  f"Not posted on {p.name} yet."))
                continue
            xs, ys = analytics.post_curve(q, self.parsed)
            span = max(xs[-1] if xs else 0, q["age_h"], 1)
            txs, tys = analytics.typical_curve(self.posts, self.parsed, p.key, span, exclude=q)
            series = [{"key": p.key, "name": "this", "color": p.color, "xs": xs, "ys": ys, "style": "area"},
                      {"key": "typical", "name": "typical", "color": TYPICAL, "xs": txs, "ys": tys, "style": "line"}]
            heading = Text.assemble((p.name + "  ", f"bold {p.color}"), (f"{fmt_num(q['views'])} views", "bold"),
                                    (f" · {fmt_num(q['likes'])} likes · ", MUTED))
            heading.append_text(score_text(q["score"]))
            heading.append(" typical", MUTED)
            charts.append(self.compare_chart(p, heading, series, span, "No snapshots for this post yet."))
        rows = []
        for p in ps:
            q = posts.get(p.key)
            if not q:
                rows.append((None, [tag(p), Text("not yet", MUTED)]))
                continue
            rows.append((f"{q['platform']}|{q['post_id']}", [
                tag(p), num(q["views"], "bold"), num(q["likes"]), num(q["comments"]), num(q["shares"]),
                Text(fmt_pct(q["eng"])), Text(fmt_pct(q["share_rate"])), score_text(q["score"]),
                Text(fmt_age(q["age_h"])), Text(q["url"] or "")]))
        columns = [("platform", "", 4), ("views", "Views", 8), ("likes", "Likes", 7), ("comments", "Cmts", 6),
                   ("shares", "Shares", 6), ("eng", "Eng", 6), ("share", "Share", 6), ("score", "Score", 6),
                   ("age", "Age", 5), ("title", "Link", 40)]
        self.emit("compare", {"heading": Text.assemble(("EPISODE  ", "bold"), title).json(), "bars": bars,
                              "charts": charts, "table": table(columns, rows)})

    def compare_chart(self, p: Platform, heading: Text, series: list[dict], span: float, empty: str) -> dict:
        hidden = p.key in self.hidden_lines
        if hidden or not any(s["xs"] for s in series):
            return {"key": p.key, "heading": heading.json(), "empty": f"{p.name} is hidden: click its name on the "
                    "Overview key to show it." if hidden else empty}
        return {"key": p.key, "heading": heading.json(), "series": series, "span": span, "empty": None}

    # --- publish --------------------------------------------------------------------------

    def scan_files(self) -> None:
        if not self.demo:
            self._safe(lambda: notify.check_videos(self.cfg), 0)
            self.show_new_notes()
        hidden = db.get_meta("hidden_videos", [])
        hidden_names = {db.video_file(h).name.lower() for h in hidden}
        every = videos.find(self.cfg)
        files = [f for f in every if db.video_file(f.name).name.lower() not in hidden_names]
        posted = self.posted_platforms()
        items = []
        for f in files:
            try:
                st = f.stat()
            except OSError:
                continue  # moved or deleted since the folder was listed
            on = posted.get(db.video_file(f.name).name.lower(), set())
            label = Text("✓ " if on else "  ", GOOD)
            label.append(f.name)
            source = "pipeline" if videos.from_pipeline(f) else _short(f.parent.name, 22)
            ago = fmt_ago(datetime.fromtimestamp(st.st_mtime).astimezone().isoformat())
            info = Text(f"   {source} · {st.st_size / 1024 / 1024:.1f} MB · {ago}  ", MUTED)
            for p in self.platforms.values():
                info.append(SHORT[p.key] + " ", f"bold {p.color}" if p.key in on else "#3a4049")
            items.append({"id": str(f), "lines": [label.json(), info.json()]})
        empty = None
        if not items:
            empty = [Text("No videos yet.", MUTED).json(), Text("Put finished .mp4 files in", MUTED).json(),
                     Text(str(config.videos_dir(self.cfg)), MUTED).json()]
        heading = Text.assemble(("VIDEOS  ", "bold"), (f"{len(files)}  ", MUTED))
        if items:
            heading.append_text(chip("Remove", act("remove_picked")))
            heading.append(" ")
        if len(every) > len(files):
            heading.append_text(chip(f"Show {len(every) - len(files)} hidden", act("unhide_videos")))
        ids = [i["id"] for i in items]
        if self.selected_file is not None and str(self.selected_file) not in ids:
            self.selected_file = None
            self.update_posted()
        if self.selected_file is None and ids:
            self.pick(Path(ids[0]))  # start with the newest video picked
        self.emit("files", {"heading": heading.json(), "items": items, "empty": empty,
                            "selected": str(self.selected_file) if self.selected_file else None})

    def posted_platforms(self) -> dict[str, set[str]]:
        """Video file name (lower case) -> the platforms its episode is posted on."""
        by_episode: dict[int, set[str]] = {}
        for p in self.posts:
            if p["episode_id"]:
                by_episode.setdefault(p["episode_id"], set()).add(p["platform"])
        out: dict[str, set[str]] = {}
        for e in self.episodes:
            if e["video"]:
                out.setdefault(db.video_file(e["video"]).name.lower(), set()).update(by_episode.get(e["id"], set()))
        return out

    @rpc
    def remove_menu(self, path: str | None = None) -> dict | None:
        """What the Remove dialog says about a video (the picked one, or a right-clicked one); None if there's none."""
        target = Path(path) if path else self.selected_file
        if not target or not target.exists():
            self.notify("Pick a video on the left first.", severity="warning")
            return None
        note = Text()
        note.append(target.name, "bold")
        note.append(f"\n{target.parent}\n\n", MUTED)
        note.append(f"Move to {desktop.BIN}", "bold")
        note.append(f" deletes the video file (you can restore it from the {desktop.BIN}).", MUTED)
        if videos.from_pipeline(target):
            note.append(" The episode's spec and build files stay, so the pipeline can render it again.", MUTED)
        note.append("\nHide from list", "bold")
        note.append(" keeps the file but takes it off this list (Show hidden brings it back).", MUTED)
        return {"path": str(target), "note": note.json(), "bin": desktop.BIN}

    @rpc
    @db_safe
    def remove_video(self, path: str, choice: str | None) -> None:
        path = Path(path)
        if choice == "hide":
            hidden = db.get_meta("hidden_videos", [])
            db.set_meta("hidden_videos", sorted({*hidden, str(path)}))
            self.notify(f"{path.name} hidden. Show hidden (top of the list) brings it back.")
        elif choice == "recycle":
            sidecar = path.with_suffix(".json")
            if not desktop.recycle(path):
                self.notify(f"Couldn't move {path.name} to the {desktop.BIN} (is it open somewhere?).", severity="error")
                return
            if sidecar.exists() and not videos.from_pipeline(path):
                desktop.recycle(sidecar)
            other = next((f for f in videos.find(self.cfg) if f.name.lower() == path.name.lower()), None)
            self.notify(f"{path.name} moved to the {desktop.BIN}." + (
                f" Another copy is still in {other.parent}; it's on the list now (Hide takes it off)."
                if other else ""))
        else:
            return
        self.tell_others()
        if self.selected_file == path:
            self.selected_file = None
            self.update_posted()
        self.scan_files()

    @rpc
    @db_safe
    def unhide_videos(self) -> None:
        if db.get_meta("hidden_videos", []):
            db.set_meta("hidden_videos", [])
            self.tell_others()
            self.notify("Hidden videos are back on the list.")
            self.scan_files()

    @rpc
    def pick_file(self, path: str) -> None:
        if path and Path(path) != self.selected_file:
            self.pick(Path(path))

    def pick(self, path: Path) -> None:
        """Pick a video to post: its caption and hashtags go into the form."""
        self.selected_file = path
        meta, warnings = videos.meta(path, self.cfg)
        for w in warnings:
            self.notify(w, severity="warning")
        self.emit("form", {"file": str(path), "caption": meta["caption"], "tags": meta["tags"]})
        self.form_changed(meta["caption"], meta["tags"])
        self.update_posted()

    @rpc
    def form_changed(self, caption: str, tags: str) -> None:
        """Show exactly what each platform will get, and the caption/hashtag limits."""
        item = self.form_item(caption, tags)
        caption_len = len(item.text_for("x"))
        n = len(videos.tag_list(item.tags))
        label = Text("Hashtags  ")
        label.append(f"{n}/{videos.MAX_TAGS}", BAD if n > videos.MAX_TAGS else MUTED)
        hint = f"  (only the first {videos.MAX_TAGS} are used)" if n > videos.MAX_TAGS else \
            (f"  (TikTok always gets #{videos.FIRST_TAG} first)" if videos.MAX_TAGS > 0 and videos.FIRST_TAG else "")
        label.append(hint, MUTED)
        cap = Text("Caption  ")
        cap.append(f"{caption_len}/100", BAD if caption_len > 100 else MUTED)
        cap.append("  (one line: the X post, the YouTube title, and the start of TikTok / Instagram)", MUTED)
        preview = []
        rows = {"tiktok": item.text_for("tiktok"), "instagram": item.text_for("instagram"),
                "youtube": f"{item.title}   description: {item.text_for('youtube')}", "x": item.text_for("x")}
        for key, text in rows.items():
            if key in self.platforms:
                p = self.platforms[key]
                preview.append({"name": p.name, "color": p.color, "text": text or "—"})
        self.emit("preview", {"caption": cap.json(), "tags": label.json(), "rows": preview})

    def update_posted(self) -> None:
        """Where the picked video is already up, so you know which upload pages are left."""
        out = Text()
        video = self.selected_file
        episode = db.episode_for_video(video.name) if video else None
        by = {}
        if video:
            out.append("POSTED  ", f"bold {MUTED}")
            if episode:
                for q in sorted((q for q in self.posts if q["episode_id"] == episode["id"]),
                                key=lambda q: q["published_at"]):
                    by.setdefault(q["platform"], q)
            for p in self.platforms.values():
                q = by.get(p.key)
                if q:
                    out.append(f"✓ {p.name}", f"bold {p.color}")
                    out.append(f" {fmt_num(q['views'])} views, {fmt_ago(q['published_at'])}    ", MUTED)
                else:
                    out.append(f"○ {p.name}    ", "#5c6370")
            if not by:
                out.append("(ReelForge spots each post at its next refresh)", MUTED)
        done = {p.key: p.key in by for p in self.platforms.values()}
        self.emit("posted", {"line": out.json(), "done": done})

    def update_best_time(self) -> None:
        """Under the videos: each platform's best part of the day so far, and when it next comes round (besttime)."""
        found = besttime.best_times(self.posts, self.platforms)
        self.emit("best", {
            "title": parts([(Text("BEST TIME TO POST  ", "bold"), 0),
                            (Text("by views in each video's first day", MUTED), 1)]),
            "lines": [parts(besttime.parts(found[p.key], tag(p))) for p in self.platforms.values()],
        })

    def form_item(self, caption: str, tags: str) -> PublishItem:
        return PublishItem(video=self.selected_file or Path(), caption=(caption or "").strip(),
                           tags=(tags or "").strip())

    def copy_text(self, text: str) -> None:
        if not desktop.copy(text):
            self.emit("clipboard", {"text": text})  # the terminal's clipboard (OSC 52), as a fallback

    def _picked(self) -> bool:
        if self.selected_file and self.selected_file.exists():
            return True
        self.notify("Pick a video on the left first.", severity="warning")
        return False

    @rpc
    def open_upload(self, key: str, caption: str, tags: str) -> None:
        """Copy the right text, show the file in Explorer or Finder, open the platform's upload page."""
        if not self._picked() or key not in self.platforms:
            return
        p = self.platforms[key]
        item = self.form_item(caption, tags)
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
        self.notify(f"{p.name}: {what} copied. Drag {item.video.name} in from {desktop.FILES_WINDOW}, then paste.{tip}",
                    title="Upload page opened", timeout=12)
        self.record_manual([p], item)

    @rpc
    def open_all(self, caption: str, tags: str) -> None:
        """Open every upload page at once, with the TikTok text (or the caption) on the clipboard."""
        if not self._picked():
            return
        item = self.form_item(caption, tags)
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
        self.tell_others()
        self.episodes = db.episodes()
        self.update_uploads()
        self.update_episode_list()
        self.scan_files()
        self.update_posted()
        # Look for the new post once it's had time to go up (10 and 30 minutes later), whatever the
        # usual refresh timing says.
        for timer in self.post_check_timers:
            timer.stop()
        self.post_check_timers = [self.loop.set_timer(minutes * 60, lambda: self.run_refresh(manual=True, force=True))
                                  for minutes in (10, 30)]

    @rpc
    def copy_field(self, which: str, caption: str, tags: str) -> None:
        item = self.form_item(caption, tags)
        text, what = {
            "copy-caption": (item.title, "Caption"),
            "copy-caption-alone": (item.title, "Caption"),
            "copy-tiktok": (item.text_for("tiktok"), "TikTok text"),
            "copy-instagram": (item.text_for("instagram"), "Instagram text"),
            "copy-youtube": (item.text_for("youtube"), "YouTube hashtags"),
        }[which]
        if not text:
            self.notify(f"{what} is empty: write a caption first.", severity="warning")
            return
        self.copy_text(text)
        self.notify(f"{what} copied.", timeout=3)

    @rpc
    def reveal_file(self) -> None:
        if self._picked():
            desktop.reveal(self.selected_file)

    def update_uploads(self) -> None:
        """Upload pages you opened, and whether the post has turned up since."""
        episodes = {db.video_file(e["video"]).name.lower(): e["id"] for e in self.episodes if e["video"]}
        found = {}
        for q in self.posts:
            if q["episode_id"]:
                found.setdefault((q["episode_id"], q["platform"]), q)
        rows = []
        for u in db.uploads():
            when = db.parse(u["ts"]).astimezone()
            p = self.platforms.get(u["platform"])
            q = found.get((episodes.get((u["video"] or "").lower()), u["platform"]))
            if q:
                mark, note = Text("✓", GOOD), Text(f"live · {fmt_num(q['views'])} views · {q['url'] or ''}")
            elif u["status"] == "manual":
                mark, note = Text("→", MUTED), Text("opened the upload page · not spotted yet", MUTED)
            else:
                mark, note = Text("✓" if u["status"] == "ok" else "×", GOOD if u["status"] == "ok" else BAD), \
                    Text(u["url"] or u["message"] or "")
            rows.append((None, [Text(fmt_clock(when) if when.date() == datetime.now().date()
                                     else when.strftime("%m/%d")), tag(p) if p else Text(u["platform"]),
                                Text(u["video"] or ""), mark, note]))
        columns = [("when", "When", 8), ("platform", "", 4), ("title", "Video", 26), ("mark", "", 2),
                   ("note", "Post", 64)]
        self.emit("uploads", {"heading": Text("RECENT UPLOADS", "bold").json(), **table(columns, rows)})

    # --- accounts -------------------------------------------------------------------------

    def account_state(self, p: Platform) -> str:
        """on: connected; login: its handle is in, waiting for the one log-in (Instagram and X); off: not connected."""
        if p.connected(self.stored):
            return "on"
        return "login" if p.public_handle else "off"

    def update_accounts(self) -> None:
        """A panel per platform, in one of three states (account_state): connected, with where its stats come from,
        how fresh they are, its buttons and its followers over time, and Disconnect at the right of its first line;
        waiting for its log-in; or not connected, with a box for its @handle, Connect and Sign up."""
        fresh_since = (analytics.now() - timedelta(days=2)).isoformat(timespec="seconds")
        pretend = self.demo and self.screenshots  # the README's pictures show the demo as a set-up account looks
        others = self.other_channels()
        private = None  # the browser a second channel's sign-ups open a private window of, worked out once it's needed
        panels = []
        for p in self.every.values():
            state = self.account_state(p)
            panel = {"key": p.key, "name": p.name, "color": p.color, "state": state,
                     "disconnect": chip("Disconnect", act("disconnect", p.key)).json() if state != "off" else None}
            if state == "off":
                then = "" if p.public_stats else ", then log in once in ReelForge's own browser window"
                if private is None:
                    private = signup.private_name(others) if signup is not None and others else ""
                panel.update(
                    status=Text("○ not connected", f"bold {MUTED}").json(), status_short=None,
                    body=Text(f"Type your @handle and press Connect to see {p.name} in ReelForge{then}. No account "
                              "yet? Sign up makes one" + (f", in a private {private} window." if private else "."),
                              MUTED).json(),
                    note=Text(p.setup_note, MUTED).json(), signup=signup is not None)
                panels.append(panel)
                continue
            rows = self.account_rows.get(p.key, [])
            latest = self.latest.get(p.key)
            fresh = any(q["platform"] == p.key and q["published_at"] >= fresh_since for q in self.posts)
            nxt = sync.next_read(p, self.cfg, latest["ts"] if latest else None, fresh)
            due = None
            if nxt is not None:
                minutes = (nxt - analytics.now()).total_seconds() / 60
                due = "any moment" if minutes < 1 else f"in about {fmt_age(minutes / 60)}"
            error = sync.last_errors.get(p.key)
            logs_in = p.browser_stats and not self.demo or pretend and p.key in ("instagram", "x")
            source = "demo" if self.demo and not pretend else p.stats_source
            if pretend and logs_in:
                source = "browser"  # what Instagram and X say once you've logged in
            if state == "login":
                source = None
            short = None
            if source == "demo":
                status = Text("● demo data", f"bold {GOOD}")
            elif source == "browser":
                status = Text(f"● reading {p.handle} through ReelForge's browser", f"bold {GOOD}")
                short = Text(f"● reading {p.handle}", f"bold {GOOD}")
            elif source == "public":
                status = Text(f"● public stats for {p.handle}", f"bold {GOOD}")
            elif state == "login":
                status = Text(f"○ {p.handle}: log in once to finish connecting", f"bold {p.color}")
                short = Text("○ log in once to finish", f"bold {p.color}")
            else:
                status = Text(f"○ {p.handle}: log in again to keep tracking", f"bold {p.color}")
                short = Text("○ log in again", f"bold {p.color}")
            body = Text()
            if state == "login":
                body.append(f"{p.name} shows up everywhere in ReelForge once you've logged in, or once you've typed "
                            "its numbers in by hand.", MUTED)
            else:
                body.append(f"last refresh {fmt_ago(latest['ts'] if latest else None)}", MUTED)
                if due:
                    body.append(f" · next {due}", MUTED)
                posts = sum(1 for q in self.posts if q["platform"] == p.key)
                if posts:
                    body.append(f"\n{posts} videos tracked", MUTED)
                    if rows:
                        since = db.parse(rows[0]["ts"]).astimezone().strftime("%b %d").replace(" 0", " ")
                        body.append(f" · history since {since}", MUTED)
            if error:
                body.append(f"\n\nlast read failed: {error[1]}" if state == "login" else
                            f"\nlast read failed: {error[1]}", BAD)
            note = "Demo data, made up on this PC." if self.demo and not pretend else p.setup_note
            panel.update(
                status=status.json(), status_short=short.json() if short else None, body=body.json(),
                note=Text(note, MUTED).json(), logs_in=logs_in,
                login_label="Log in again" if source == "browser" else "Log in",
                profile_disabled=not p.public_handle and not pretend, refresh_disabled=self.demo and not pretend,
                show_log=not p.has_stats, chart=self.followers_chart(p, rows) if state == "on" else None)
            panels.append(panel)
        missing = [p for k, p in self.every.items() if k not in self.platforms]
        hint = None
        if not self.platforms:
            hint = parts([
                (Text("Connect the platforms you post to: ReelForge only shows the ones you've connected.  ", MUTED), 1),
                (Text("New channel? " if others else "Starting from scratch? ", "bold"), 0),
                (chip("Make a Gmail first", act("gmail")), 0),
                (Text("  it's your YouTube login, and the others can sign up with the same email.", MUTED), 2)])
        elif missing:
            hint = parts([(Text(f"Only connected platforms show up in ReelForge. Connect {_either(missing)} here any "
                                "time.", MUTED), 0)])
        self.emit("accounts", {"panels": panels, "hint": hint})

    def followers_chart(self, p: Platform, rows: list) -> dict | None:
        """An account's followers over the time ReelForge has been reading them: the heading, the points, and each
        bucket's label and number for the hover read-out. A bucket whose middle fell in a gap between readings (the
        computer was off) is an estimate, the straight line between the readings either side: hatched (est), and
        guessed for the read-out."""
        pts = trends.points(rows, "followers", hold=False)
        if len(pts) < 2:
            return None
        days = (analytics.now() - pts[0][0]).total_seconds() / 86400
        fr = trends.frame_since(pts[0][0]) if days < 30 else trends.frame("30d")
        b = trends.bucket(pts, fr, estimate=True)
        xs = [i + 1 for i, v in enumerate(b.totals) if v is not None]
        ys = [v for v in b.totals if v is not None]
        if not ys:
            return None
        longest = max(trends.GAP, fr.step)
        holes = [(t0, t1) for (t0, _), (t1, _) in zip(pts, pts[1:]) if t1 - t0 > longest]
        guessed = [any(t0 < a + (z - a) / 2 < t1 for t0, t1 in holes) for a, z in zip(fr.starts, fr.ends)]
        est: list[list[int]] = []
        for i, guess in enumerate(guessed):
            if guess and est and est[-1][1] == i:
                est[-1][1] = i + 1
            elif guess:
                est.append([i, i + 1])
        first = pts[0][0].astimezone()  # the first reading, not the start of its hour, so the date matches the panel
        heading = Text.assemble(("FOLLOWERS  ", "bold"),
                                (f"since {first:%b} {first.day}  " if days < 30 else "last 30 days  ", MUTED),
                                (fmt_num(pts[-1][1]), "bold"))
        heading.append("  ")
        heading.append_text(change_text(pts[-1][1] - (ys[0] if len(ys) > 1 else pts[0][1])))
        return {"heading": heading.json(), "n": fr.n, "step_h": fr.step.total_seconds() / 3600,
                "slots": slot_info(fr), "values": b.totals, "guessed": guessed,
                "series": [{"key": p.key, "name": p.name, "color": p.color, "xs": xs, "ys": ys, "style": "area",
                            "est": est}]}

    @rpc
    def login(self, key: str) -> None:
        p = self.every[key]
        if not p.public_handle:
            self.notify(f"Connect {p.name} with your @handle first.", severity="warning")
            return
        self.loop.run_worker(self._browser_login, p, group="login")

    @rpc
    def open_profile(self, key: str) -> None:
        """Open profile: your page on the platform, in your browser. (Not called profile: self.profile is the channel
        this window shows, and it would hide the call.)"""
        p = self.every[key]
        if p.public_handle:
            desktop.open_url(desktop.profile_url(p.key, p.public_handle))

    @rpc
    def refresh_platform(self, key: str) -> None:
        p = self.every[key]
        if not p.has_stats:
            self.notify(f"{p.name} isn't set up yet (see the panel).", severity="warning")
            return
        self.run_refresh(True, True, p.key)

    def _browser_login(self, p: Platform) -> None:
        window = f"{'An' if browser.NAME == 'Edge' else 'A'} {browser.NAME} window"
        self.loop.call_soon(self.notify, f"{window} is opening (if ReelForge is reading stats right now, as soon as "
                                         f"that's done). Log in to {p.name} there; ReelForge carries on by itself "
                                         "once you're in.", f"Log in to {p.name}", "information", 15)
        try:
            browser.login(p.key)
        except Exception as e:
            msg = str(e) if isinstance(e, PlatformError) else f"{type(e).__name__}: {e}"
            self.loop.call_soon(self.notify, msg, f"{p.name} not logged in", "error", 15)
            return
        self.loop.call_soon(self.notify, f"Logged in to {p.name}. Reading your stats now…")
        self.loop.call_soon(self.follow_connections)  # connected now, if it was waiting for this
        self.loop.call_soon(self.run_refresh, True, True, p.key)

    # --- connecting and disconnecting -------------------------------------------------------

    @rpc
    def connect(self, key: str, typed: str) -> str | None:
        """Connect: the handle typed into a panel that isn't connected yet. What's wrong with it, or None."""
        p = self.every[key]
        try:
            handle = signup.handle_from(typed) if signup else ("@" + typed.strip().lstrip("@") if typed.strip() else "")
        except ValueError as e:
            return str(e)
        if not handle:
            return f"Type your {p.name} @handle first, or press Sign up to make the account."
        if self.demo:
            self.notify("Demo mode: nothing is saved.", timeout=4)
            return None
        self.loop.run_worker(self._save_account, p, handle, group="accounts")
        return None

    @rpc
    def signup_guide(self, key: str) -> dict | None:
        """No account yet: the platform's sign-up guide (or the channel's Gmail, "gmail"), as its dialog shows it: a
        few steps, with examples from the channel's name, the button that opens the platform's own sign-up page (in a
        private window for a second channel), and for an account a box for the @handle you end up with, which Connect
        takes from there."""
        if signup is None:
            return None
        channel = self.profile.channel_name if self.profile is not None and not self.demo else ""
        view = signup.guide_view(key, channel, self.other_channels())
        if view["account"]:
            view["steps"].append("Type your @handle below and press Connect." + (
                " ReelForge then opens its own browser window for the one log-in." if signup.GUIDES[key].logs_in
                else ""))
        return {**view, "title": view["title"].upper()}

    @rpc
    def open_signup(self, key: str) -> str | None:
        """Open a guide's page; what to say under its button."""
        return signup.open_guide(key, self.other_channels()) if signup is not None else None

    def other_channels(self) -> list[str]:
        """The names of this ReelForge's other channels, whose accounts are probably logged in in your browser: while
        there are any, this one's sign-ups open in a private window (studio/signup.py). The demo has none."""
        if profiles is None or self.profile is None or self.demo:
            return []
        return profiles.others(self.profile)

    @rpc
    def disconnect_info(self, key: str) -> dict | None:
        """Are you sure? What the Disconnect dialog says: it hides the platform everywhere and stops its reads, and
        its stats stay."""
        p = self.every.get(key)
        if p is None or not p.public_handle:
            return None
        if self.demo:
            self.notify("Demo mode: nothing is saved.", timeout=4)
            return None
        note = Text()
        note.append(f"{p.name}  ", f"bold {p.color}")
        note.append(p.handle, "bold")
        note.append(f"\n\nReelForge stops reading {p.name}, and its cards, charts, columns, filters, upload buttons and "
                    "notifications leave every tab. Everything it has read so far stays saved, so connecting it again "
                    "(on this tab, with the same @handle) brings it all back.", MUTED)
        if p.browser_stats:
            note.append(f"\nYou stay logged in to {p.name} in ReelForge's browser.", MUTED)
        return {"key": key, "title": f"DISCONNECT {p.name.upper()}?", "note": note.json()}

    @rpc
    def disconnect(self, key: str) -> None:
        p = self.every.get(key)
        if p is not None and p.public_handle and not self.demo:
            self.loop.run_worker(self._save_account, p, "", group="accounts")

    def _save_account(self, p: Platform, handle: str) -> None:
        """Connect a platform with its handle, or disconnect it (""): your settings change (config.save_handle), then
        it shows up everywhere, or leaves, straight away."""
        try:
            config.save_handle(p.key, handle)
        except Exception as e:
            self.loop.call_soon(self.notify, f"Couldn't save {p.name}'s handle: {e}", "", "error", 12)
            return
        self.loop.call_soon(self.account_saved, p, handle)

    def account_saved(self, p: Platform, handle: str) -> None:
        p.cfg["handle"] = handle
        self.config_seen = _mtime(config.CONFIG_PATH)
        self.follow_connections()
        self.tell_others()
        if not handle:
            self.notify(f"ReelForge stops reading {p.name} and hides it everywhere. Its stats so far stay saved: "
                        "connect it again to see them.", title=f"{p.name} disconnected", timeout=12)
        elif p.key in self.platforms:
            self.notify(f"Reading {handle}'s stats now…", title=f"{p.name} connected", timeout=8)
            self.run_refresh(True, True, p.key)
        else:  # Instagram and X: the one log-in comes next (its own message says where)
            self.loop.run_worker(self._browser_login, p, group="login")

    def follow_connections(self) -> None:
        """Show what's connected now, everywhere: after a connect or a disconnect (here or in another window), a
        log-in, or a platform's first stats."""
        self.stored = self._safe(db.stored_platforms, self.stored)
        now = connected(self.every, self.stored)
        if list(now) != list(self.platforms):
            self.platforms = now
            self.show_platforms()
            self.reload()
            self.update_notes()
            if self.tab == "publish":
                self.scan_files()
        else:
            self.update_accounts()
        self.update_header()

    def follow_config(self) -> None:
        """Another ReelForge window connected or disconnected a platform: its handle changed in config.toml."""
        if self.demo:
            return
        seen = _mtime(config.CONFIG_PATH)
        if seen == self.config_seen:
            return
        self.config_seen = seen
        try:
            fresh = config.load_config()
        except config.ConfigError:
            return
        changed = False
        for key, p in self.every.items():
            handle = str((fresh.get(key) or {}).get("handle", ""))
            if handle != str(p.cfg.get("handle", "")):
                p.cfg["handle"] = handle
                changed = True
        if changed:
            self.loop.call_soon(self.follow_connections)

    # --- typed-in stats --------------------------------------------------------------------

    @rpc
    def log_stats(self, start: str | None = None) -> dict | None:
        """Type in numbers for platforms ReelForge can't read itself (Instagram and X before logging in): what the
        dialog shows."""
        manual = [p for p in self.every.values() if p.public_handle and not p.has_stats]
        if not manual:
            self.notify("Every platform already gets its stats automatically.")
            return None
        if start not in {p.key for p in manual}:
            start = manual[0].key
        last = {}
        for p in manual:
            latest = self.latest.get(p.key)
            last[p.key] = {
                "followers": latest["followers"] if latest else None,
                "views": {str(q["episode_id"]): q["views"] for q in self.posts
                          if q["platform"] == p.key and q["post_id"].startswith("manual-") and q["views"] is not None},
            }
        episodes = [{"id": e["id"], "title": e["title"]} for e in db.episodes()[:12]]
        return {"platforms": [{"key": p.key, "name": p.name} for p in manual], "start": start, "episodes": episodes,
                "last": last}

    @rpc
    def save_logged_stats(self, key: str, followers_text: str, views_text: dict) -> str | None:
        """The dialog's Save: None once saved, or what to fix."""
        from .platforms.public import parse_count

        def number(text: str) -> int | None:
            text = (text or "").strip()
            if not text:
                return None
            n = parse_count(text)
            if not 0 <= n < 10 ** 12:  # nothing has a trillion views; anything bigger is a typo (or too big to store)
                raise ValueError(text)
            return n

        try:
            followers = number(followers_text)
            views = {int(e): v for e, t in (views_text or {}).items() if (v := number(t)) is not None}
        except (ValueError, OverflowError):
            return "Whole numbers only, please (like 1234, 3,400 or 1.2K)."
        if followers is None and not views:
            return "Nothing to save yet."
        try:
            self._save_logged(key, followers, views)
        except sqlite3.OperationalError as e:
            return f"The stats database is busy ({e}). Try again in a moment."
        return None

    def _save_logged(self, key: str, followers: int | None, views: dict[int, int]) -> None:
        p = self.every[key]
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
        self.tell_others()
        self.notify(f"{p.name} stats saved.", timeout=3)
        self.reload()
        if key not in self.platforms:  # its first numbers connect it
            self.follow_connections()

    # --- fixing an episode link --------------------------------------------------------------

    @rpc
    def fix_episode(self, key: str | None) -> dict | None:
        """What the "Which video is this?" dialog shows for a highlighted post."""
        post = self._post_for(key)
        if not post:
            self.notify("Highlight a video first.", severity="warning")
            return None
        p = self.platforms[post["platform"]]
        note = Text()
        note.append(f"{p.name}  ", f"bold {p.color}")
        note.append(post["title"] or "(no caption)", "bold")
        note.append("\nReelForge matches posts to videos by their caption. If it got this one wrong, pick the right "
                    "video; ReelForge keeps your choice from now on.", MUTED)
        options = [{"id": "none", "lines": [Text("Not one of my videos", MUTED).json()]}]
        for e in db.episodes():
            label = Text(("✓ " if e["id"] == post["episode_id"] else "  "), GOOD)
            label.append(e["title"])
            options.append({"id": f"ep-{e['id']}", "lines": [label.json()]})
        return {"key": key, "note": note.json(), "options": options,
                "current": f"ep-{post['episode_id']}" if post["episode_id"] else None}

    @rpc
    @db_safe
    def set_episode(self, key: str, choice: str | None) -> None:
        post = self._post_for(key)
        if choice is None or post is None:
            return
        episode = None if choice == "none" else int(choice[3:])
        db.set_post_episode(post["platform"], post["post_id"], episode)
        self.tell_others()
        title = next((e["title"] for e in self.episodes if e["id"] == episode), None)
        self.notify(f"Filed under: {title}" if title else "Marked as not one of your videos.", timeout=5)
        self.reload()

    # --- notifications ----------------------------------------------------------------------

    @rpc
    def drawer_opened(self) -> None:
        self.update_notes()

    def update_notes(self) -> None:
        """The bell's red dot, and the drawer's list (newest first)."""
        self.notes_sig = self._safe(notify.signature, None)  # first: a change after it shows next (keep_in_step)
        notes = [n for n in self._safe(notify.recent, []) if self.shows_note(n)]
        items = []
        for n in notes:
            icon, color, _ = notify.KINDS.get(n["kind"], notify.KINDS["info"])
            mark = Text("● " if not n["read"] else "  ", f"bold {BAD}")
            mark.append(f"{icon} ", f"bold {color}")
            items.append({"id": n["id"], "mark": mark.json(), "title": Text(n["title"], "bold" if not n["read"]
                                                                            else "").json(),
                          "body": " ".join((n["body"] or "").split()), "ago": fmt_ago(n["ts"]), "read": bool(n["read"])})
        unread = sum(1 for n in notes if not n["read"])
        head = Text("NOTIFICATIONS  ", "bold")
        head.append(f"{unread} new" if unread else "all read", BAD if unread else MUTED)
        buttons = [("Mark all read", act("mark_all_read"))] if unread else []
        if notes:
            buttons.append(("Clear all", act("clear_notes")))
        self.emit("notes", {"unread": unread, "head": head.json(), "close": chip("Close", act("close_drawer")).json(),
                            "tools": chips(*buttons, gap="  ").json(), "items": items,
                            "empty": "Nothing yet. Updates, milestones, badges and finished videos show up here."})

    @rpc
    @db_safe
    def open_note(self, note_id: int) -> None:
        """Clicking a notification marks it read and shows what it's about."""
        note = next((n for n in notify.recent() if n["id"] == note_id), None)
        notify.mark_read(note_id)
        if note:
            self.go_to(note)
        self.update_notes()

    def go_to(self, note: dict) -> None:
        """Open the tab a notification is about and pick out what it's about there, whether or not that tab is open
        already: the video on Videos (with its platform's videos showing), the finished video on Publish, or the
        platform's card on the Overview or panel on Accounts (framed for a few seconds)."""
        to = notify.target(note, {k: p.name for k, p in self.platforms.items()})
        if to.tab not in TABS:
            return
        self.switch_tab(to.tab)
        if to.post:
            self.show_post(to.post)
        elif to.file:
            self.show_file(to.file)
        elif to.card in (*self.platforms, "total"):
            self.emit("pick", {"id": f"card-{to.card}"})
        elif to.account in self.platforms:
            self.emit("pick", {"id": f"acct-{to.account}"})
            if note["kind"] == "login":
                self.emit("focus", {"id": f"login-{to.account}"})  # Enter logs in again

    def show_post(self, key: str) -> None:
        """The Videos tab showing one video ("<platform>|<post id>"): its platform's videos, with it highlighted and
        scrolled into view."""
        post = self._post_for(key)
        if post is None:
            self.notify("That video isn't on the Videos tab any more.", severity="warning")
            return
        self.filter = post["platform"]
        self.stale.discard("videos")
        self.update_videos(select=key)

    def show_file(self, name: str) -> None:
        """The Publish tab with one finished video picked (by file name), its caption and hashtags filled in."""
        path = next((f for f in videos.find(self.cfg) if f.name.lower() == name.lower()), None)
        if path is None:
            self.notify(f"{name} isn't in your video folders any more.", severity="warning")
            return
        if db.video_file(path.name).name.lower() in {db.video_file(h).name.lower()
                                                    for h in db.get_meta("hidden_videos", [])}:
            self.notify(f"{path.name} is hidden. Show hidden (top of the list) brings it back.", severity="warning")
            return
        self.pick(path)
        self.scan_files()  # lists it, highlighted
        self.emit("focus", {"id": "file-list"})

    @rpc
    @db_safe
    def mark_all_read(self) -> None:
        notify.mark_all_read()
        self.update_notes()

    @rpc
    @db_safe
    def clear_notes(self) -> None:
        """Clear all: every notification leaves the drawer for good, as with each one's × (see notify.delete_all)."""
        notify.delete_all()
        self.update_notes()

    @rpc
    @db_safe
    def delete_note(self, note_id: int) -> None:
        """A notification's ×, or Delete on the highlighted one: it leaves the drawer for good (see notify.delete)."""
        notify.delete(note_id)
        self.update_notes()

    # --- badges -------------------------------------------------------------------------------

    def update_badges(self) -> None:
        """The account's badges under the cards on the Overview (none: the line is hidden)."""
        self.badge_list = badges.account_badges(self.account_rows, self.platforms)
        self.emit("badges", {"line": parts([(badges.badge_text(b), i) for i, b in enumerate(self.badge_list[:4])])})

    def update_video_badges(self, post: dict | None) -> None:
        found = badges.video_badges(post, self.posts, self.first_day, self.platforms) if post else []
        self.emit("video_badges", {"line": parts([(badges.badge_text(b), i) for i, b in enumerate(found)])})

    # --- updates ------------------------------------------------------------------------------

    def start_updates(self) -> None:
        """The Updates tab from the last check, a new check when that's old, and "Updated to ..." after a restart."""
        if self.demo:
            from .demo import SAMPLE_UPDATE, SCREENSHOT_NOTES

            self.update_info = {"current": KIT_VERSION or "1.0.0", "latest": SAMPLE_UPDATE[0], "newer": True,
                                "notes": SCREENSHOT_NOTES if self.screenshots else SAMPLE_UPDATE[1], "url": "",
                                "error": "", "checked": db.now_iso()}
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
            self.loop.run_worker(self._update_check, False, group="update-check", exclusive=True)

    def _update_check(self, manual: bool) -> None:
        info = kit_update.check()
        info["checked"] = db.now_iso()
        try:
            db.set_meta("update_check", info)
            if info["newer"]:
                notify.update_available(info["latest"])
        except sqlite3.Error:
            pass
        self.loop.call_soon(self.after_update_check, info, manual)

    def after_update_check(self, info: dict, manual: bool) -> None:
        self.update_info = info
        self.show_update()
        self.show_new_notes()
        if manual and not info["error"] and not info["newer"]:
            self.notify(f"ReelForge {info['current']} is the newest version.", timeout=5)
        elif manual and info["error"]:
            self.notify(info["error"], severity="warning", timeout=8)

    def show_update(self, step: Text | None = None, progress: tuple | None = None) -> None:
        info = self.update_info or {}
        newer = bool(info.get("newer"))
        out = Text()
        view = {"newer": newer, "apply": {"show": False, "disabled": True, "label": "Update and restart"},
                "check_disabled": True, "notes": "", "how": [], "updating": self.updating}
        if kit_update is None and not self.demo:
            out.append("Updates work from a ReelForge folder (this copy of the dashboard is running on its own).",
                       MUTED)
            self.emit("update", {**view, "status": out.json()})
            return
        out.append(f"ReelForge {info.get('current') or KIT_VERSION}", "bold")
        if newer:
            out.append("   ")
            out.append(f"{info['latest']} is out", f"bold {GOOD}")
            out.append("  ·  one click downloads it, puts it in place and restarts ReelForge", MUTED)
        elif info.get("error"):
            out.append(f"   {info['error']}", MUTED)
        elif info.get("latest"):
            out.append("   the newest version", GOOD)
        else:
            out.append("   checking for updates…", MUTED)
        if info.get("checked"):
            out.append(f"\nchecked {fmt_ago(info['checked'])}", MUTED)
        live = not self.demo or self.screenshots  # the README's pictures show the tab as it looks for real
        view["apply"] = {"show": newer, "disabled": self.updating or not live,
                         "label": "Update and restart" + ("" if live else " (demo)")}
        view["check_disabled"] = self.updating or not live
        if newer:
            view["notes"] = whats_new(info.get("notes", "")) or f"Release notes: {info.get('url')}"
        elif info.get("latest"):
            # The notes are the version you have when it's the newest (what "Updated to ..." points you to).
            own = info["latest"] == (info.get("current") or KIT_VERSION) and whats_new(info.get("notes", ""))
            view["notes"] = (f"You have the newest version, {info['latest']}. When a new one comes out, a notification "
                             "tells you, and this tab updates ReelForge in one click." + (f"\n\n{own}" if own else ""))
        else:
            view["notes"] = "ReelForge checks for a new version every few hours while it's open."
        kind = "zip" if self.demo and self.screenshots else kit_update.install_kind() if kit_update else ""
        how = {
            "zip": "An update downloads the new version and copies its files over this folder.",
            "git": "A git copy: an update runs git pull.",
        }.get(kind, "")
        if how:
            view["how"] = Text(how + "  Your channel, videos, stats and settings are never touched.", MUTED).json()
        self.emit("update", {**view, "status": out.json()})

    @rpc
    def check_updates(self) -> None:
        if kit_update and not self.demo:
            self.emit("update_step", {"status": Text("Checking…", MUTED).json()})
            self.loop.run_worker(self._update_check, True, group="update-check", exclusive=True)

    @rpc
    def release_page(self) -> None:
        url = (self.update_info or {}).get("url") or (kit_update.RELEASES if kit_update else "")
        if url:
            desktop.open_url(url)

    @rpc
    def start_update(self) -> None:
        if self.demo:
            self.notify("Demo mode: nothing is downloaded.", timeout=4)
            return
        if not kit_update or not (self.update_info or {}).get("newer") or self.updating:
            return
        self.updating = True
        self.show_update()
        self.update_progress("Starting", 0, 0)
        self.loop.run_worker(self._update_apply, group="update-apply", exclusive=True)

    def _update_apply(self) -> None:
        def progress(what: str, done: int, total: int) -> None:
            self.loop.call_soon(self.update_progress, what, done, total)

        def log(text: str) -> None:
            self.loop.call_soon(self.notify, text, "", "warning", 12)

        try:
            message = kit_update.apply(kit_update.release_from(self.update_info), progress, log)
        except kit_update.UpdateError as e:
            self.loop.call_soon(self.update_failed, str(e))
            return
        except Exception as e:
            self.loop.call_soon(self.update_failed, f"{type(e).__name__}: {e}")
            return
        self.loop.call_soon(self.update_done, message)

    def update_progress(self, what: str, done: int, total: int) -> None:
        size = f"  {done / 1e6:.1f} of {total / 1e6:.0f} MB" if total > 100_000 else ""
        self.emit("update_step", {"step": Text(f"{what}…{size}", MUTED).json(),
                                  "progress": {"done": done, "total": total or None}})

    def update_done(self, message: str) -> None:
        self.emit("update_step", {"step": Text(f"{message} Restarting…", f"bold {GOOD}").json(),
                                  "progress": {"done": 1, "total": 1}, "done": True})
        self.loop.set_timer(1.5, lambda: self.exit(kit_update.RESTART))

    def update_failed(self, message: str) -> None:
        self.updating = False
        self.show_update()
        self.emit("update_step", {"step": Text(f"The update didn't finish: {message}\nThe version you have keeps "
                                               "working.", BAD).json(), "progress": None, "failed": True})

    # --- shared actions -------------------------------------------------------------------

    @rpc
    def refresh(self, force: bool = False) -> None:
        self.run_refresh(manual=True, force=force)

    @rpc
    def open_post(self, key: str | None) -> None:
        post = self._post_for(key)
        if post and post["url"]:
            desktop.open_url(post["url"])
        else:
            self.notify("Highlight a video with a link first.", severity="warning")

    def _post_for(self, key: str | None) -> dict | None:
        if not key or "|" not in key:
            return None
        platform, post_id = key.split("|", 1)
        return next((p for p in self.posts if p["platform"] == platform and p["post_id"] == post_id), None)


def slot_info(fr: trends.Frame) -> list[dict]:
    """Each bucket of a frame as the window needs it: the hover label (Fri 7 PM, Fri 6–8 PM, Fri Oct 24, Oct
    20–22), where it sits after a number (at 8 PM, on Oct 20), and what the time axis may write under it (the clock
    hour, or the weekday at midnight, or the date)."""
    out = []
    for i, (a, b) in enumerate(zip(fr.starts, fr.ends)):
        out.append({"label": _slot_label(fr, i), "when": _when(fr, i), "hour": a.hour, "day": a.day,
                    "weekday": f"{a:%a}", "clock": fmt_clock(a).replace(":00", ""), "date": f"{a:%b} {a.day}"})
    return out


def whats_new(notes: str) -> str:
    """A release's notes as the Updates tab shows them: what's new, without the download guide under the "---" (for
    someone who hasn't got ReelForge) or the "Already have ReelForge?" line (you're on the tab it points to)."""
    kept = []
    for line in (notes or "").splitlines():
        if line.strip() in ("---", "***", "___"):
            break
        if not line.startswith("Already have ReelForge?"):
            kept.append(line)
    return "\n".join(kept).strip()


def _either(ps: list[Platform]) -> str:
    """'Instagram', 'Instagram or X', 'TikTok, Instagram or X'."""
    names = [p.name for p in ps]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


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


def _value(p: dict, key: str):
    """A post's number in a table's column, for sorting: Views 12h (views_12h) is its views 12 hours in."""
    return p["after"][12] if key == "views_12h" else p.get(key)


def _after(p: dict, hours: int) -> Text:
    """A video's views `hours` after it went up, for a table: "in 5h" until it's that old, "soon" until the next reading
    measures it, and — when ReelForge wasn't reading round then (the computer was off)."""
    if p["after"][hours] is not None:
        return num(p["after"][hours])
    left = hours - p["age_h"]
    text = (f"in {fmt_age(max(left, 1 / 60))}" if left > 0 else "soon") if hours in p["due"] else "—"
    return Text(text, MUTED)


def _from_first(values: list[float | None]) -> list[float]:
    """Drop the empty hours before the first reading and after the last one (they'd draw as a run of zeros)."""
    known = [i for i, v in enumerate(values) if v is not None]
    return [v or 0.0 for v in values[known[0]:known[-1] + 1]] if known else []


def _days(a: datetime, b: datetime) -> str:
    """A bucket's days: Oct 20, or Oct 20–22 when it's several days combined."""
    last = (b - timedelta(hours=12)).date()  # the bucket's last day (b is the midnight after it)
    if last <= a.date():
        return f"{a:%b} {a.day}"
    return f"{a:%b} {a.day}–" + (f"{last.day}" if last.month == a.month else f"{last:%b} {last.day}")


def _slot_label(fr: trends.Frame, i: int) -> str:
    """The hovered bar: Fri 7 PM, Fri 6–8 PM, Fri Oct 24, Oct 20–22."""
    a, b = fr.starts[i], fr.ends[i]
    if fr.daily:
        days = _days(a, b)
        return days if "–" in days else f"{a:%a} {days}"
    if fr.hourly:
        return f"{a:%a} {fmt_clock(a).replace(':00', '')}"
    return f"{a:%a} {fmt_hours(a, b)}"


def _when(fr: trends.Frame, i: int) -> str:
    """When bucket i was, after a number: at 8 PM (Fri), 6–8 PM (Fri), on Oct 20, Oct 20–22."""
    a, b = fr.starts[i], fr.ends[i]
    if fr.daily:
        days = _days(a, b)
        return days if "–" in days else f"on {days}"
    day = "" if a.date() == fr.now.date() else f" {a:%a}"
    return (f"at {fmt_clock(a).replace(':00', '')}" if fr.hourly else fmt_hours(a, b)) + day
