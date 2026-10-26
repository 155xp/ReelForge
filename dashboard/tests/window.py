"""A ReelForge window's Python side (dashboard/service.py) for the tests, without the window itself: its loop runs on
the test's own thread whenever the test pumps it, and every view it sends is kept the way the OpenTUI window gets
it (as JSON). The window's own behaviour (keys, clicks, scrolling) is tested in ui/test/."""

from __future__ import annotations

import json
from typing import Any, Callable

from dashboard.service import Dashboard
from studio.bridge import Loop, _plain


def plain(segs: list | None) -> str:
    """The text of styled segments, [[text, style], ...]."""
    return "".join(s[0] for s in segs or [])


class Recorder(Loop):
    """A loop that keeps what it sends instead of writing it to a window."""

    def __init__(self) -> None:
        super().__init__(out=None)
        self.events: list[tuple[str, Any]] = []

    def send(self, msg: dict) -> None:
        msg = json.loads(json.dumps(msg, default=_plain))
        if "ev" in msg:
            self.events.append((msg["ev"], msg["d"]))


class Window:
    """The Python side of a ReelForge window on these platforms and settings (the stats database open already)."""

    def __init__(self, cfg: dict, platforms: dict, **options) -> None:
        self.loop = Recorder()
        self.svc = Dashboard(self.loop)
        self.init = self.svc.open(cfg, platforms, {"demo": True, **options})
        self.pump(0.3)

    def pump(self, seconds: float = 0.0, until: Callable[[], bool] | None = None) -> bool:
        return self.loop.pump(seconds, until)

    def until(self, ok: Callable[[], bool], seconds: float = 6) -> bool:
        return self.pump(seconds, ok)

    def call(self, method: str, *args) -> Any:
        """What the window does when you press something: a call, then the views it sends."""
        result = getattr(self.svc, method)(*args)
        self.pump(0.05)
        return result

    def view(self, name: str) -> Any:
        """The newest of this view the window was sent."""
        return next((d for ev, d in reversed(self.loop.events) if ev == name), None)

    def sent(self, name: str) -> list:
        return [d for ev, d in self.loop.events if ev == name]

    def toasts(self) -> list[str]:
        return [d["body"] for d in self.sent("toast")]

    def forget(self) -> None:
        """Start a fresh record of what's sent (to see what one step sends)."""
        self.loop.events.clear()

    def close(self) -> None:
        self.svc.stop()
