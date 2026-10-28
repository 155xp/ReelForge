"""Every call ReelForge's window makes reaches its Python side. The window (ui/src/, TypeScript) names each call in a
string, and the bridge (studio/bridge.py) answers only a method marked @rpc, so nothing checks a name until someone
presses the button: in 1.0.6 the Accounts tab's Open profile called "profile", which the dashboard's self.profile (the
channel a window shows) hid, and every press said only "no call named 'profile'". These read every call in the
window's code and every action its chips and chart keys carry, and ask the started services the way the bridge does."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from dashboard import db, demo, sync
from dashboard.config import PLATFORM_KEYS
from dashboard.service import TABS, Dashboard
from dashboard.tests.window import Recorder, Window
from studio.bridge import RPC
from studio.setup_service import Setup

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui" / "src"
CALL = re.compile(r"""\.(?:send|call)(?:<[^>()]*>)?\(\s*["'`](\w+)["'`]""")  # bridge.send("name"), .call<T>("name")
OWN = re.compile(r"""\bcase\s+["'](\w+)["']\s*:""")  # the actions the window runs itself (DashState.run)


def calls(screen: str) -> dict[str, list[str]]:
    """The calls in the window's code for a screen (ui/src/dashboard or ui/src/setup): name -> the files making it."""
    found: dict[str, list[str]] = {}
    for path in sorted((UI / screen).rglob("*.ts*")):
        for name in CALL.findall(path.read_text(encoding="utf-8")):
            found.setdefault(name, []).append(path.name)
    return found


def actions(value, found: set[str]) -> set[str]:
    """The actions in a view: a clickable segment is [text, style, [action, *args]]."""
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        if (len(value) == 3 and isinstance(value[0], str) and isinstance(value[1], str) and isinstance(value[2], list)
                and value[2] and isinstance(value[2][0], str)):
            found.add(value[2][0])
        for v in value:
            actions(v, found)
    return found


def answered(service, name: str) -> bool:
    """Whether the bridge answers this call: the service has a method of that name marked @rpc."""
    return bool(getattr(getattr(service, name, None), RPC, False))


def rpc_names(cls: type) -> set[str]:
    """The methods a service's class marks @rpc."""
    return {name for klass in cls.__mro__ for name, fn in vars(klass).items() if getattr(fn, RPC, False)}


class DashboardCalls(unittest.TestCase):
    """The stats window's Python side (dashboard/service.py) on the demo, X not connected, YouTube's last read failed
    (so the foot of the window names it, with a click that opens Accounts), every tab opened."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.addCleanup(setattr, db, "_path", db._path)
        root = Path(tmp.name)
        cfg = {"refresh_minutes": 0, "videos_dir": str(root / "none"), "episodes_dir": str(root / "none"),
               "completed_dir": str(root / "none"), **{key: {} for key in PLATFORM_KEYS}}
        db.init(root / "demo.db")
        demo.seed()
        for state in (sync._attempted, sync.last_errors):
            state.clear()
            self.addCleanup(state.clear)
        sync.last_errors["youtube"] = (db.now_iso(), "Couldn't read YouTube")
        sync._share(None)  # as every ReelForge window sees it
        self.w = Window(cfg, demo.platforms(unconnected=("x",)), drawer=True)
        self.addCleanup(self.w.close)
        for tab in TABS:
            self.w.call("tab_opened", tab)

    def test_every_call_the_window_makes_is_answered(self):
        made = calls("dashboard")
        self.assertTrue({"connect", "login", "check_updates"} <= set(made))
        for name, where in made.items():
            with self.subTest(name):
                self.assertTrue(answered(self.w.svc, name), f"{name} (called in {', '.join(where)}) isn't answered")

    def test_every_chip_and_chart_key_is_answered(self):
        own = set(OWN.findall((UI / "dashboard" / "state.tsx").read_text(encoding="utf-8")))
        found: set[str] = set()
        for _, data in self.w.loop.events:
            actions(data, found)
        self.assertTrue({"set_range", "toggle_line", "tab"} <= found)
        for name in sorted(found - own):
            with self.subTest(name):
                self.assertTrue(answered(self.w.svc, name), f"a chip or key's action {name} isn't answered")

    def test_no_attribute_hides_a_call(self):
        names = rpc_names(Dashboard)
        self.assertTrue({"connect", "login", "check_updates"} <= names)
        for name in sorted(names):
            with self.subTest(name):
                self.assertTrue(answered(self.w.svc, name), f"self.{name} hides the call {name}")


class SetupCalls(unittest.TestCase):
    """First-time setup's Python side (studio/setup_service.py), started as its screens start it."""

    def test_every_call_the_screens_make_is_answered(self):
        for options in ({"preview": True}, {"start": "onboard", "preview": True},
                        {"start": "onboard", "preview": True, "new": True, "embedded": True}):
            svc = Setup(Recorder())
            svc.start(options)
            for name, where in calls("setup").items():
                with self.subTest(name, options=options):
                    self.assertTrue(answered(svc, name), f"{name} (called in {', '.join(where)}) isn't answered")
            for name in sorted(rpc_names(Setup)):
                with self.subTest(name, options=options):
                    self.assertTrue(answered(svc, name), f"self.{name} hides the call {name}")


if __name__ == "__main__":
    unittest.main()
