"""Pull stats from every platform ReelForge can read into the local store."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Callable

from . import analytics, db, notify
from .platforms import Platform, PlatformError

# When each platform was last tried, successful or not, so a failing one waits like any other
# instead of being retried on every tick.
_attempted: dict[str, str] = {}
# The last failed read per platform: (when, message). Cleared by the next good read.
last_errors: dict[str, tuple[str, str]] = {}
# One refresh at a time: a second one (you pressing r during an automatic one) waits for the first.
_running = threading.Lock()


def gap_minutes(p: Platform, cfg: dict, manual: bool, fresh: bool = False) -> float:
    """How long a platform waits between reads (0: only when you press Refresh).

    Auto refresh follows refresh_minutes. A manual refresh runs anything older than 2 minutes.
    Reads through ReelForge's browser wait an hour, or 30 minutes while the platform has a video under two
    days old (10 minutes when you press r).
    """
    gap = 2 if manual else cfg.get("refresh_minutes", 30)
    if p.uses_browser:  # each read opens Edge for a few seconds, so go easy
        gap = max(gap or 0, 10 if manual else (30 if fresh else 60))
    return gap or 0


def _last(p: Platform, last_ts: str | None) -> str | None:
    return max(filter(None, (last_ts, _attempted.get(p.key))), default=None)


def due(p: Platform, cfg: dict, last_ts: str | None, manual: bool, fresh: bool = False) -> bool:
    """Whether a platform should refresh now."""
    last_ts = _last(p, last_ts)
    if not last_ts:
        return True
    gap = gap_minutes(p, cfg, manual, fresh)
    if not gap:
        return manual
    age_minutes = (analytics.now() - db.parse(last_ts)).total_seconds() / 60
    return age_minutes >= gap * 0.9


def next_read(p: Platform, cfg: dict, last_ts: str | None, fresh: bool = False) -> datetime | None:
    """Roughly when the automatic refresh reads this platform next (None: it doesn't)."""
    gap = gap_minutes(p, cfg, False, fresh)
    last_ts = _last(p, last_ts)
    if not p.has_stats or not gap or not last_ts:
        return None
    return max(db.parse(last_ts) + timedelta(minutes=gap * 0.9), analytics.now())


def refresh(platforms: dict[str, Platform], cfg: dict, manual: bool = False, force: bool = False,
            on_status: Callable[[str], None] | None = None) -> tuple[list[str], list[str]]:
    """Fetch every due platform in parallel and store a snapshot. Returns (refreshed names, errors)."""
    with _running:
        return _refresh(platforms, cfg, manual, force, on_status)


def _refresh(platforms: dict[str, Platform], cfg: dict, manual: bool, force: bool,
             on_status: Callable[[str], None] | None) -> tuple[list[str], list[str]]:
    latest = db.latest_accounts()
    fresh = db.platforms_with_posts_since((analytics.now() - timedelta(days=2)).isoformat(timespec="seconds"))
    todo = [
        p for p in platforms.values()
        if p.has_stats and (force or due(p, cfg, latest[p.key]["ts"] if p.key in latest else None, manual,
                                         p.key in fresh))
    ]
    if not todo:
        return [], []
    if on_status:
        on_status("refreshing " + ", ".join(p.name for p in todo) + "…")
    for p in todo:
        _attempted[p.key] = db.now_iso()

    def fetch(p: Platform):
        try:
            return p, p.fetch(), None
        except Exception as e:  # one platform failing shouldn't stop the others
            return p, None, e

    done, errors, read = [], [], {}
    with ThreadPoolExecutor(len(todo)) as pool:
        for p, result, error in pool.map(fetch, todo):
            if error is None:
                try:
                    account, posts = result
                    db.record_snapshot(p.key, account, posts)
                except Exception as e:  # e.g. the database is busy: report it, keep the app running
                    error = e
            if error is not None:
                msg = str(error) if isinstance(error, PlatformError) else f"{type(error).__name__}: {error}"
                msg = msg.strip().splitlines()[0] if msg.strip() else type(error).__name__  # browser errors run long
                last_errors[p.key] = (db.now_iso(), msg)
                errors.append(f"{p.name}: {msg}")
                if getattr(error, "needs_login", False):
                    _tell(lambda: notify.add("login", f"Log in to {p.name} again", msg, key=f"login:{p.key}"))
                continue
            last_errors.pop(p.key, None)
            _tell(lambda: notify.release(f"login:{p.key}"))
            done.append(p.name)
            read[p.key] = p.name
    if done:
        try:
            analytics.auto_link()
        except Exception as e:
            errors.append(f"Matching posts to videos failed ({type(e).__name__}: {e}); it tries again next refresh.")
        # Round numbers passed since the last read. A platform read for the first time only sets the starting point.
        _tell(lambda: notify.check_milestones(read, {k for k in read if k not in latest}))
    return done, errors


def _tell(fn) -> None:
    """Notifications are extras: a hiccup writing one never fails the refresh."""
    try:
        fn()
    except Exception:
        pass
