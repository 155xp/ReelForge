"""The profile button in the header and its menu: every profile (every channel, see studio/profiles.py), the platforms
each one has connected, and its unread notifications.

A window shows one profile. What it knows about the others it reads straight from their own files: the handles in
their config.toml, their log-ins and the platforms their stats.db has numbers for (so "connected" means what it means
in their own window, Platform.connected), and their unread notifications, leaving out those about platforms they
haven't connected, as their drawer does. Nothing is written to another profile's files.
"""

from __future__ import annotations

import json
import sqlite3
import tomllib
from contextlib import closing
from pathlib import Path

from . import notify
from .platforms import ORDER

NAMES = {cls.key: cls.name for cls in ORDER}
BROWSER_ONLY = {cls.key for cls in ORDER if cls.browser_stats}  # read only after the one log-in (Instagram, X)


def _config(p) -> Path:
    """A profile's dashboard settings: dashboard/config.toml beside the window's code for the first one."""
    return p.config


def handles(p) -> dict[str, str]:
    """The platforms a profile has a handle for: key -> handle."""
    try:
        with _config(p).open("rb") as f:
            cfg = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out = {}
    for key in NAMES:
        table = cfg.get(key)
        handle = str(table.get("handle", "")).strip() if isinstance(table, dict) else ""
        if handle:
            out[key] = handle
    return out


def _logged_in(p) -> set[str]:
    try:
        tokens = json.loads((p.data / "tokens.json").read_text("utf-8"))
    except (OSError, ValueError):
        return set()
    return {k for k in BROWSER_ONLY if isinstance(tokens, dict) and tokens.get(f"browser:{k}") is not None}


def _store(p):
    """Its stats.db, opened read-only (None when it has none yet, or it's busy)."""
    path = p.db
    if not path.is_file():
        return None
    try:
        return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
    except sqlite3.Error:
        return None


def summary(p) -> dict:
    """What the menu shows about a profile it isn't showing: its connected platforms (in ReelForge's order) and how many
    of its notifications are unread."""
    have = handles(p)
    stored: set[str] = set()
    rows: list = []
    conn = _store(p)
    if conn is not None:
        with closing(conn):
            try:
                stored = {r[0] for r in conn.execute("SELECT DISTINCT platform FROM account_stats")}
                rows = conn.execute("SELECT kind, key, title FROM notifications WHERE read = 0 AND deleted = 0"
                                    ).fetchall()
            except sqlite3.Error:
                pass  # an old or half-made store: nothing to count
    logged = _logged_in(p)
    on = [k for k in NAMES if k in have and (k not in BROWSER_ONLY or k in logged or k in stored)]
    unread = 0
    for kind, key, title in rows:
        about = notify.platform_of({"kind": kind, "key": key, "title": title}, NAMES)
        if about is None or about in on:
            unread += 1
    return {"platforms": on, "unread": unread}


def unread_elsewhere(here, every) -> int:
    """Unread notifications in every profile but this one (the red dot on the profile button)."""
    return sum(summary(p)["unread"] for p in every if p != here)
