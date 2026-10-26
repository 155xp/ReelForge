"""The Python side of ReelForge's window. The window itself is the OpenTUI app in ui/ (TypeScript, run by Bun); it
starts this as a child process and talks to it in lines of JSON over stdin and stdout:

  in    {"id": 7, "m": "set_range", "a": ["7d"]}      call a method of the service (the reply has the same id)
  out   {"id": 7, "r": <result>}  or  {"id": 7, "e": "what went wrong"}
  out   {"ev": "trends", "d": {...}}                   something to show: the window keeps the newest of each

The first line names the service: {"id": 0, "m": "start", "a": ["dashboard", {...options}]} starts the stats
window's (dashboard/service.py), {"id": 0, "m": "start", "a": ["setup", {...}]} the first-run screens'
(studio/setup_service.py). Every call and every timer runs on one thread, in order, like the old Textual app's
event loop; slow work runs on worker threads, which hand their results back with call_soon.

stdout carries nothing but these lines: print() and anything a library writes go to stderr, which goes to the window's
log (REELFORGE_LOG). REELFORGE_BRIDGE_PRELOAD names a Python file to run first (tests and the screenshots use it for
sample data). Standard library only, so it starts fast.

  python -m studio.bridge
"""

from __future__ import annotations

import heapq
import itertools
import json
import os
import queue
import sys
import threading
import time
import traceback
from typing import Any, Callable

RPC = "_rpc"  # the attribute that marks a method the window may call


def rpc(fn: Callable) -> Callable:
    """Mark a service method the window may call."""
    setattr(fn, RPC, True)
    return fn


class Cancelled(Exception):
    pass


class Worker:
    """Work on a thread: is_cancelled says a newer worker in the same exclusive group took over (or the window is
    closing), so it should stop at the next good moment."""

    def __init__(self, group: str | None):
        self.group = group
        self.is_cancelled = False
        self.thread: threading.Thread | None = None


class Timer:
    def __init__(self, loop: "Loop", when: float, fn: Callable, every: float | None):
        self.loop, self.when, self.fn, self.every = loop, when, fn, every
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class Loop:
    """One thread runs everything in order: calls from the window, timers and callbacks from workers."""

    def __init__(self, out):
        self.out = out
        self.write_lock = threading.Lock()
        self.tasks: queue.Queue = queue.Queue()
        self.timers: list = []
        self.counter = itertools.count()
        self.running = True
        self.workers: dict[str, Worker] = {}
        self.local = threading.local()

    # ---- talking to the window

    def send(self, msg: dict) -> None:
        line = json.dumps(msg, ensure_ascii=False, separators=(",", ":"), default=_plain)
        with self.write_lock:
            try:
                self.out.write(line + "\n")
                self.out.flush()
            except (OSError, ValueError):
                self.running = False  # the window has gone

    def emit(self, event: str, data: Any = None) -> None:
        self.send({"ev": event, "d": data})

    # ---- scheduling

    def call_soon(self, fn: Callable, *args) -> None:
        """Run fn on the loop's thread (safe from any thread)."""
        self.tasks.put(lambda: fn(*args))

    call_from_thread = call_soon

    def set_timer(self, delay: float, fn: Callable) -> Timer:
        t = Timer(self, time.monotonic() + delay, fn, None)
        self.tasks.put(lambda: heapq.heappush(self.timers, (t.when, next(self.counter), t)))
        return t

    def set_interval(self, every: float, fn: Callable) -> Timer:
        t = Timer(self, time.monotonic() + every, fn, every)
        self.tasks.put(lambda: heapq.heappush(self.timers, (t.when, next(self.counter), t)))
        return t

    def run_worker(self, fn: Callable, *args, group: str | None = None, exclusive: bool = False) -> Worker:
        """Run fn(*args) on a thread. exclusive: a worker already running in the same group is cancelled."""
        w = Worker(group)
        if group and exclusive and group in self.workers:
            self.workers[group].is_cancelled = True
        if group:
            self.workers[group] = w

        def run() -> None:
            self.local.worker = w
            try:
                fn(*args)
            except Cancelled:
                pass
            except Exception:
                traceback.print_exc()

        w.thread = threading.Thread(target=run, daemon=True, name=f"worker-{group or 'any'}")
        w.thread.start()
        return w

    def current_worker(self) -> Worker:
        return getattr(self.local, "worker", None) or Worker(None)

    # ---- the loop

    def run(self, handle: Callable[[dict], None]) -> None:
        while self.running:
            self.step(handle)
        for w in self.workers.values():
            w.is_cancelled = True  # a read waiting on another window's stops waiting; one under way finishes

    def step(self, handle: Callable[[dict], None] | None = None, longest: float = 0.5) -> None:
        """Run the timers that are due, then wait (up to `longest` seconds) for the next task and run it."""
        now = time.monotonic()
        while self.timers and self.timers[0][0] <= now:
            _, _, t = heapq.heappop(self.timers)
            if t.stopped:
                continue
            if t.every:
                t.when = now + t.every
                heapq.heappush(self.timers, (t.when, next(self.counter), t))
            self._guard(t.fn)
        wait = max(0.0, min(self.timers[0][0] - time.monotonic(), longest)) if self.timers else longest
        try:
            task = self.tasks.get(timeout=wait)
        except queue.Empty:
            return
        if isinstance(task, dict):
            if handle:
                handle(task)
        else:
            self._guard(task)

    def pump(self, seconds: float = 0.0, until: Callable[[], bool] | None = None) -> bool:
        """Run the loop on this thread for a while (tests): `seconds`, or until `until()` holds (then True)."""
        end = time.monotonic() + seconds
        while True:
            if until and until():
                return True
            if time.monotonic() >= end:
                return bool(until and until())
            self.step(longest=min(0.05, max(end - time.monotonic(), 0)))

    def _guard(self, fn: Callable) -> None:
        try:
            fn()
        except Exception as e:
            traceback.print_exc()
            self.emit("toast", {"title": "Something went wrong", "body": f"{type(e).__name__}: {e}",
                                "severity": "error", "timeout": 10})


def _plain(value):
    """What json can't write by itself: paths, sets, dataclasses, rows."""
    from pathlib import PurePath

    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    if hasattr(value, "json"):
        return value.json()
    if hasattr(value, "keys"):
        return {k: value[k] for k in value.keys()}
    return str(value)


class Service:
    """What a window's backend is: it gets the loop, and the window calls its @rpc methods."""

    def __init__(self, loop: Loop):
        self.loop = loop

    def emit(self, event: str, data: Any = None) -> None:
        self.loop.emit(event, data)

    def notify(self, body: str, title: str = "", severity: str = "information", timeout: float = 5) -> None:
        """A pop-up in the window's corner, like Textual's notify."""
        self.emit("toast", {"title": title, "body": body, "severity": severity, "timeout": timeout})

    def exit(self, code: int = 0, result: Any = None) -> None:
        """Close the window: it exits with this code (75 asks the launcher to start ReelForge again)."""
        self.emit("exit", {"code": code, "result": result})

    def start(self, options: dict) -> Any:
        return None

    def stop(self) -> None:
        pass


def make_service(name: str, loop: Loop) -> Service:
    if name == "dashboard":
        from dashboard.service import Dashboard

        return Dashboard(loop)
    if name == "setup":
        from .setup_service import Setup

        return Setup(loop)
    raise ValueError(f"no service called {name!r}")


def private_streams():
    """stdin and stdout for the window's lines only: fd 0 and 1 now point elsewhere, so nothing else (print, a
    library, a program ReelForge starts) can read the window's calls or write into its replies."""
    proto_in = os.fdopen(os.dup(0), "r", encoding="utf-8", newline="\n")
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    os.dup2(2, 1)
    sys.stdin = open(os.devnull, encoding="utf-8")
    sys.stdout = sys.stderr
    return proto_in, proto_out


FINISH = ("refresh", "login", "update-apply")  # work that finishes before the Python side exits (a read closes its
                                              # browser first; an update leaves the folder whole)


def log_to(path: str) -> None:
    """stderr into the window's log file (REELFORGE_LOG): the window owns the terminal, so nothing may write there."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    except OSError:
        return
    os.dup2(fd, 2)
    os.close(fd)
    sys.stderr = open(2, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)


def main() -> int:
    if os.environ.get("REELFORGE_LOG"):
        log_to(os.environ["REELFORGE_LOG"])
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    proto_in, proto_out = private_streams()
    if os.environ.get("REELFORGE_BRIDGE_PRELOAD"):
        # Tests and the screenshots (scripts/shots_preload.py): sample data in place of this computer's, set up
        # before anything starts.
        import runpy

        runpy.run_path(os.environ["REELFORGE_BRIDGE_PRELOAD"], run_name="preload")
    loop = Loop(proto_out)
    service: list[Service] = []

    def handle(msg: dict) -> None:
        mid, method, args = msg.get("id"), msg.get("m", ""), msg.get("a") or []
        try:
            if method == "start":
                name, options = args[0], (args[1] if len(args) > 1 else {})
                svc = make_service(name, loop)
                service[:] = [svc]
                result = svc.start(options or {})
            elif method == "stop":
                for svc in service:
                    svc.stop()
                loop.running = False
                # True: a stats read (or an update) is still running; this process finishes it before it exits.
                result = any(w.thread and w.thread.is_alive() for g, w in loop.workers.items() if g in FINISH)
            else:
                if not service:
                    raise RuntimeError("nothing started yet")
                fn = getattr(service[0], method, None)
                if fn is None or not getattr(fn, RPC, False):
                    raise AttributeError(f"no call named {method!r}")
                result = fn(*args)
            if mid is not None:
                loop.send({"id": mid, "r": result})
        except Exception as e:
            traceback.print_exc()
            if mid is not None:
                loop.send({"id": mid, "e": f"{type(e).__name__}: {e}"})

    def read() -> None:
        for line in proto_in:
            line = line.strip()
            if not line:
                continue
            try:
                loop.tasks.put(json.loads(line))
            except ValueError:
                print(f"bridge: not JSON: {line[:200]}", file=sys.stderr)
        loop.call_soon(lambda: setattr(loop, "running", False))  # the window closed its end

    threading.Thread(target=read, daemon=True, name="bridge-reader").start()
    loop.run(handle)
    for svc in service:
        try:
            svc.stop()
        except Exception:
            traceback.print_exc()
    for group, w in list(loop.workers.items()):
        if group in FINISH and w.thread:
            w.thread.join(timeout=600)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.exit(main())
