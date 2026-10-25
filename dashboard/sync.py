"""Pull stats from every platform ReelForge can read into the local store.

Every ReelForge window you have open, and the hourly background job, read into the same store, so they take turns
(ReadLock): one reads, a read you asked for in another window waits for it, and an automatic one leaves it to that
one. Each window then shows what was read, whoever read it (app.ReelForge.keep_in_step). What they share about the
reads is kept in the store too (see shared): when each platform was last tried, its last error and the read under way.
"""

from __future__ import annotations

import errno
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import analytics, db, notify
from .platforms import Platform, PlatformError

# When each platform was last tried, successful or not, so a failing one waits like any other
# instead of being retried on every tick. Shared by every ReelForge, like last_errors (see shared).
_attempted: dict[str, str] = {}
# The last failed read per platform: (when, message). Cleared by the next good read.
last_errors: dict[str, tuple[str, str]] = {}
# One refresh at a time in this ReelForge: a second one (you pressing r during an automatic one) waits for the first.
# Between ReelForges, ReadLock does the same.
_running = threading.Lock()
STATE = "sync"  # the meta key of the state every ReelForge shares (see shared)
WAIT = 600      # seconds a read you asked for waits while another ReelForge reads
ME = f"{os.getpid()}-{time.time_ns()}"  # this ReelForge, in the shared state
WHO = {"window": "another ReelForge window", "job": "the hourly stats job"}  # who's reading, for messages
_stale: str | None = None  # a read under way whose ReelForge closed before it finished (see reading_elsewhere)


@dataclass
class Result:
    """How a refresh went: the platforms it read (by name) and the errors."""
    done: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    busy: bool = False         # another ReelForge was reading: this one left it to that one, or stopped waiting
    waited: str | None = None  # who this one waited for (WHO), when it had to
    changes: int | None = None  # the store's change count (db.bump) once this read was saved


if sys.platform == "win32":
    import msvcrt

    _BUSY = {errno.EACCES, errno.EDEADLOCK}

    def _lock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    _BUSY = {errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES}

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class ReadLock:
    """Whose turn it is to read: a lock on a file next to the store, held by one ReelForge at a time. The system lets
    go of it when that ReelForge closes, even mid-read or in a crash, so it's never left stuck."""

    def __init__(self, path: Path):
        self.path = path
        self.fd: int | None = None
        self.locked = False

    def acquire(self, wait: float = 0, stop: Callable[[], bool] | None = None) -> bool:
        """Take it, waiting up to `wait` seconds while another ReelForge has it (or until stop() says to give up).
        False: it's still taken."""
        deadline = time.monotonic() + wait
        try:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        except OSError:
            return True  # nowhere to put it: read anyway, as ReelForge did before windows took turns
        while True:
            try:
                _lock(fd)
            except OSError as e:
                if e.errno not in _BUSY:
                    break  # this drive can't lock files: read anyway
                if time.monotonic() >= deadline or (stop and stop()):
                    os.close(fd)
                    return False
                time.sleep(0.25)
                continue
            self.locked = True
            break
        self.fd = fd
        return True

    def release(self) -> None:
        if self.fd is None:
            return
        try:
            if self.locked:
                _unlock(self.fd)
        except OSError:
            pass  # closing it lets go too
        finally:
            os.close(self.fd)
            self.fd, self.locked = None, False

    def held(self) -> bool:
        """Whether another ReelForge has it right now: a quick try, let go of at once."""
        if not self.acquire():
            return True
        self.release()
        return False


def lock_path() -> Path:
    """The file every ReelForge reading into this store takes turns on: stats.refresh.lock next to stats.db."""
    return db._path.with_name(f"{db._path.stem}.refresh.lock")


def shared(conn=None) -> dict:
    """What every ReelForge knows about the reads: attempted ({platform: when}), errors ({platform: [when, message]})
    and running ({"by", "who", "what", "since"}) while one of them is reading, else None."""
    state = db.get_meta(STATE, None, conn)
    return state if isinstance(state, dict) else {}


def adopt(state: dict) -> bool:
    """Take the shared attempts and errors as this ReelForge's own, whoever made them. Not while this one is reading
    (False): it shares its own when it's done."""
    if not _running.acquire(blocking=False):
        return False
    try:
        _take(state)
    finally:
        _running.release()
    return True


def _take(state: dict) -> None:
    _attempted.clear()
    _attempted.update({k: v for k, v in (state.get("attempted") or {}).items() if isinstance(v, str)})
    last_errors.clear()
    last_errors.update({k: (v[0], v[1]) for k, v in (state.get("errors") or {}).items()
                        if isinstance(v, list) and len(v) == 2})


def _share(running: dict | None) -> None:
    """Save this ReelForge's attempts and errors for the others, and the read it has under way (None: it's over)."""
    try:
        db.set_meta(STATE, {"attempted": _attempted, "errors": last_errors, "running": running})
    except Exception:
        pass  # the store is busy: the others see it after the next read


def reading_elsewhere(state: dict) -> dict | None:
    """The read another ReelForge has under way right now (shared's running), or None."""
    global _stale
    run = state.get("running")
    if not isinstance(run, dict) or run.get("by") == ME:
        return None
    mark = f"{run.get('by')}@{run.get('since')}"
    if mark == _stale:
        return None
    if not ReadLock(lock_path()).held():
        _stale = mark  # its ReelForge closed mid-read
        return None
    return run


def gap_minutes(p: Platform, cfg: dict, manual: bool, fresh: bool = False) -> float:
    """How long a platform waits between reads (0: only when you press Refresh).

    Auto refresh follows refresh_minutes. A manual refresh runs anything older than 2 minutes.
    Reads through ReelForge's browser wait an hour, or 30 minutes while the platform has a video under two
    days old (10 minutes when you press r).
    """
    gap = 2 if manual else cfg.get("refresh_minutes", 30)
    if p.uses_browser:  # each read opens a browser for a few seconds, so go easy
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
            on_status: Callable[[str], None] | None = None, who: str = "window",
            stop: Callable[[], bool] | None = None) -> Result:
    """Fetch every due platform in parallel and store a snapshot.

    One ReelForge reads at a time. While another one is reading, a refresh you asked for (manual) waits for it, up to
    WAIT seconds, then leaves out what it read (or tried) after you asked; an automatic one leaves the read to it
    (busy). who: "window" or "job" (see WHO), for the others' messages. stop: says when to stop waiting (the window
    is closing, say).
    """
    asked = db.now_iso()
    wait = WAIT if manual else 0
    deadline = time.monotonic() + wait
    got = _running.acquire(blocking=False)
    while not got and time.monotonic() < deadline and not (stop and stop()):
        got = _running.acquire(timeout=0.25)
    if not got:
        return Result(busy=True)
    try:
        lock, waited = ReadLock(lock_path()), None
        if not lock.acquire():
            if not wait:
                return Result(busy=True)
            waited = WHO.get((shared().get("running") or {}).get("who"), WHO["window"])
            if not lock.acquire(max(deadline - time.monotonic(), 0), stop):
                return Result(busy=True, waited=waited)
        try:
            result = _refresh(platforms, cfg, manual, force, on_status, asked, who)
        finally:
            lock.release()
        result.waited = waited
        return result
    finally:
        _running.release()


def _refresh(platforms: dict[str, Platform], cfg: dict, manual: bool, force: bool,
             on_status: Callable[[str], None] | None, asked: str, who: str) -> Result:
    _take(shared())  # what the other ReelForges tried since this one last read
    latest = db.latest_accounts()
    last = {k: r["ts"] for k, r in latest.items()}
    fresh = db.platforms_with_posts_since((analytics.now() - timedelta(days=2)).isoformat(timespec="seconds"))
    # A platform another ReelForge read (or tried) after this refresh was asked for is as fresh as it would make it.
    # (Times are to the second: one from the second it was asked in may be from just before, so it doesn't count.)
    todo = [
        p for p in platforms.values()
        if p.has_stats and (_last(p, last.get(p.key)) or "") <= asked
        and (force or due(p, cfg, last.get(p.key), manual, p.key in fresh))
    ]
    if not todo:
        return Result()
    names = ", ".join(p.name for p in todo)
    if on_status:
        on_status(f"refreshing {names}…")
    now = db.now_iso()
    for p in todo:
        _attempted[p.key] = now
    _share({"by": ME, "who": who, "what": names, "since": now})

    def fetch(p: Platform):
        try:
            return p, p.fetch(), None
        except Exception as e:  # one platform failing shouldn't stop the others
            return p, None, e

    done, errors, read, changes = [], [], {}, None
    try:
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
                    # The first line only: browser errors run long.
                    msg = msg.strip().splitlines()[0] if msg.strip() else type(error).__name__
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
                errors.append(f"Matching posts to videos failed ({type(e).__name__}: {e}); it tries again next "
                              "refresh.")
            # Round numbers passed since the last read. A platform read for the first time only sets the starting
            # point. Views across every platform add up the connected ones (those this refresh was given).
            _tell(lambda: notify.check_milestones(read, {k for k in read if k not in latest}, on=set(platforms)))
    finally:
        if read:  # every other window reloads (app.ReelForge.keep_in_step)
            try:
                changes = db.bump()
            except Exception:
                pass
        _share(None)
    return Result(done, errors, changes=changes)


def _tell(fn) -> None:
    """Notifications are extras: a hiccup writing one never fails the refresh."""
    try:
        fn()
    except Exception:
        pass
