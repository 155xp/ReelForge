"""ReelForge's first run, all inside one box round the terminal with the logo on top: the tools it needs (one list,
one yes), the downloads with their progress, a health check, onboarding, then what to do next.

setup.bat / ./setup.sh open it at the tools; `reelforge onboard` opens it at onboarding. run() returns what to do
after it closes: ("dashboard", tab) to open ReelForge on that tab, or None.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, ProgressBar, Static

from . import KIT_NAME, command, doctor, setup_flow, stats_schedule, tools, tui
from . import paths as P
from . import settings as S
from .onboard_app import OnboardScreen, saved_answers

GOOD, BAD, WARN, MUTED = "#4ade80", "#ff5a4e", "#ffc83a", "#8a94a3"

CSS = """
#intro { height: auto; }
#items { height: auto; padding: 1 0 0 0; }
.item { height: 1; }
.item .mark { width: 6; }
.item Tick { width: 3; height: 1; border: none; padding: 0; margin-right: 3; background: transparent; }
.item Tick > .toggle--button { background: transparent; color: $text-muted; }
.item Tick.-on > .toggle--button { color: $success; text-style: bold; }
.item Tick:focus { background: $primary 30%; }
.item .name { width: 26; text-style: bold; }
.item .what { width: 1fr; color: $text-muted; }
#note { height: auto; color: $text-muted; padding: 1 0 0 0; }
#buttons { height: auto; dock: bottom; padding: 1 0 0 0; }
#buttons Button { margin-right: 2; min-width: 20; }
#go { min-width: 28; }
.job { height: 2; }
.job .mark { width: 4; padding-left: 1; }
.job .name { width: 24; text-style: bold; }
.job ProgressBar { width: 44; }
.job .status { width: 1fr; color: $text-muted; }
#checks { height: auto; padding: 1 0 0 0; }
#done-text { height: auto; }
"""


class Tick(Checkbox):
    """A tick that can be turned off: the same green tick as the ready rows while on, a grey circle while off.
    Textual's own checkbox draws a box round it with half blocks, which sat oddly next to the plain ticks."""

    BUTTON_LEFT = BUTTON_RIGHT = " "

    @property
    def BUTTON_INNER(self) -> str:  # noqa: N802 (the name Textual reads)
        return tui.CHECK if self.value else "○"


def _mark(ok: bool | None) -> Text:
    if ok is None:
        return Text("  …", style=MUTED)
    return Text(f"  {tui.CHECK}", style=f"bold {GOOD}") if ok else Text(f"  {tui.CROSS}", style=f"bold {BAD}")


class ToolsScreen(tui.Framed):
    """Step 1: what ReelForge needs, ticked, and one button to set it all up."""

    STEP = "tools"
    BIG_MIN_HEIGHT = 30
    HINT = " Space ticks  ·  Enter presses  ·  Esc to leave "
    BINDINGS = [Binding("escape", "leave", "Leave", show=False)]

    def body(self) -> ComposeResult:
        yield Static(id="intro")
        yield VerticalScroll(id="items")
        yield Static(id="note")
        with Horizontal(id="buttons"):
            yield Button("Checking…", variant="primary", id="go", disabled=True)
            yield Button("Skip for now", id="skip", disabled=True)

    def on_mount(self) -> None:
        super().on_mount()
        self.items: list[setup_flow.Item] = []
        self.query_one("#intro", Static).update(Text.assemble(
            ("Let's get ReelForge ready. ", "bold"),
            "Checking what's already on this computer…"))
        self.check()

    @work(thread=True, exclusive=True)
    def check(self) -> None:
        items = setup_flow.plan()
        self.app.call_from_thread(self.show_items, items)

    async def show_items(self, items: list[setup_flow.Item]) -> None:
        self.items = items
        box = self.query_one("#items", VerticalScroll)
        await box.remove_children()
        rows = []
        for i in items:
            first = (Tick("", i.default, id=f"cb-{i.key}") if not i.ready and i.can_install else
                     Static(Text(f" {tui.CHECK}", style=f"bold {GOOD}") if i.ready else
                            Text(" !", style=f"bold {WARN}"), classes="mark"))
            what = Text(i.why + "  ·  ", style=MUTED)
            what.append(i.detail, style=GOOD if i.ready else (WARN if not i.can_install else MUTED))
            rows.append(Horizontal(first, Static(i.name, classes="name"), Static(what, classes="what"),
                                   classes="item"))
        await box.mount_all(rows)
        intro = Text.assemble(("Let's get ReelForge ready. ", "bold"),
                              "Everything goes into this folder; nothing else on your computer changes:\n")
        intro.append(str(P.ROOT), style=MUTED)
        if tools.path_too_long():
            intro.append(f"\nThis folder's path is {len(str(P.ROOT))} characters long, too deep for some of Blender's "
                         "files. Move it somewhere shorter (e.g. C:\\ReelForge) first.", style=f"bold {WARN}")
        self.query_one("#intro", Static).update(intro)
        self.query_one("#note", Static).update(
            "Downloads come only from the official sites (blender.org, gyan.dev, Mixkit) and every file is checked. "
            "Mixkit's sounds are free to use in your videos, YouTube and social media included.")
        go, skip = self.query_one("#go", Button), self.query_one("#skip", Button)
        go.disabled = skip.disabled = False
        self.update_go()
        go.focus()

    def chosen(self) -> list[setup_flow.Item]:
        out = []
        for i in setup_flow.todo(self.items):
            cb = self.query(f"#cb-{i.key}")
            if cb and cb.first(Checkbox).value:
                out.append(i)
        return out

    def update_go(self) -> None:
        go = self.query_one("#go", Button)
        picked = self.chosen()
        if not setup_flow.todo(self.items):
            go.label = "Continue"
            self.query_one("#skip", Button).display = False
        elif picked:
            mb = sum(i.size_mb for i in picked)
            go.label = f"Set up (about {mb} MB)" if mb else "Set up"
        else:
            go.label = "Continue without these"
        go.refresh(layout=True)

    @on(Checkbox.Changed)
    def ticked(self) -> None:
        self.update_go()

    @on(Button.Pressed, "#go")
    def go(self) -> None:
        self.app.switch_screen(WorkScreen(self.chosen()))

    @on(Button.Pressed, "#skip")
    def skip(self) -> None:
        self.app.switch_screen(WorkScreen([]))

    def action_leave(self) -> None:
        self.app.exit(None)


class WorkScreen(tui.Framed):
    """Step 1, continued: each download with its progress, then the health check."""

    STEP = "tools"
    BIG_MIN_HEIGHT = 30
    HINT = " This can take a few minutes "

    def __init__(self, items: list[setup_flow.Item]):
        super().__init__()
        self.items = items
        self.failed: list[str] = []

    def body(self) -> ComposeResult:
        with VerticalScroll(id="jobs"):
            for i in self.items:
                with Horizontal(classes="job", id=f"job-{i.key}"):
                    yield Static(Text("·", style=MUTED), classes="mark", id=f"mk-{i.key}")
                    yield Static(i.name, classes="name")
                    yield ProgressBar(total=None, show_eta=False, id=f"bar-{i.key}")
                    yield Static("waiting", classes="status", id=f"st-{i.key}")
            with Horizontal(classes="job", id="job-sounds-cache"):
                yield Static(Text("·", style=MUTED), classes="mark", id="mk-cache")
                yield Static("Sound library", classes="name")
                yield ProgressBar(total=None, show_eta=False, show_percentage=False, id="bar-cache")
                yield Static("waiting", classes="status", id="st-cache")
            yield Static(id="checks")
        with Horizontal(id="buttons"):
            yield Button("Working…", variant="primary", id="next", disabled=True)
            yield Button("Check again", id="again")

    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" if tui.FANCY else "-\\|/"

    def on_mount(self) -> None:
        super().on_mount()
        self.query_one("#again", Button).display = False
        self.working: set[str] = set()
        self.tick = 0
        self.set_interval(0.12, self._spin)
        self.run_all()

    def _spin(self) -> None:
        """Turn the spinner next to whatever is downloading or installing right now."""
        self.tick += 1
        for key in self.working:
            self.query_one(f"#mk-{key}", Static).update(Text(self.SPIN[self.tick % len(self.SPIN)], style="bold"))

    def _progress(self, key: str):
        def report(text: str, done: float, total: float) -> None:
            self.app.call_from_thread(self._show, key, text, done, total)
        return report

    def _show(self, key: str, text: str, done: float, total: float) -> None:
        self.working.add(key)
        bar = self.query_one(f"#bar-{key}", ProgressBar)
        if total:
            bar.update(total=total, progress=done)
            if total > 1e5:
                text += f"  {done / 1e6:.0f} of {total / 1e6:.0f} MB"
        else:
            bar.update(total=None)
        self.query_one(f"#st-{key}", Static).update(text)

    def _finished(self, key: str, ok: bool, text: str) -> None:
        self.working.discard(key)
        self.query_one(f"#mk-{key}", Static).update(
            Text(tui.CHECK, style=f"bold {GOOD}") if ok else Text(tui.CROSS, style=f"bold {BAD}"))
        bar = self.query_one(f"#bar-{key}", ProgressBar)
        bar.update(total=1, progress=1 if ok else 0)
        self.query_one(f"#st-{key}", Static).update(Text(text if ok else "Didn't work: " + text,
                                                         style=GOOD if ok else BAD))

    @work(thread=True, exclusive=True)
    def run_all(self) -> None:
        for i in self.items:
            self.app.call_from_thread(self._show, i.key, "starting", 0, 0)
            try:
                msg = setup_flow.apply(i, self._progress(i.key))
                self.app.call_from_thread(self._finished, i.key, True, msg)
            except Exception as e:  # network, disk, checksum: say it and carry on with the rest
                self.failed.append(i.name)
                self.app.call_from_thread(self._finished, i.key, False, str(e).splitlines()[0][:120])
        try:
            if setup_flow.sounds.missing() or not tools.find_ffmpeg():
                self.app.call_from_thread(self._finished, "cache", False, "needs ffmpeg and every sound first")
            else:
                setup_flow.prepare_sounds(self._progress("cache"))
                self.app.call_from_thread(self._finished, "cache", True, "ready for mixing")
        except Exception as e:
            self.app.call_from_thread(self._finished, "cache", False, str(e).splitlines()[0][:120])
        self.app.call_from_thread(self._checking)
        report = doctor.checks(quiet=True)
        self.app.call_from_thread(self.show_checks, report)

    def _checking(self) -> None:
        self.query_one("#checks", Static).update(Text("Checking everything…", style=MUTED))

    def show_checks(self, report: doctor.Report) -> None:
        t = Text("Health check\n", style="bold")
        for status, what, detail in report.rows:
            if what in ("Onboarding", "CLAUDE.md", "AGENTS.md", "Dashboard"):
                continue                      # onboarding comes next; it writes those
            mark = {doctor.OK: (tui.CHECK, GOOD), doctor.WARN: ("!", WARN)}.get(status, (tui.CROSS, BAD))
            t.append(f"  {mark[0]} ", style=f"bold {mark[1]}")
            t.append(what, style="bold")
            t.append(f"  {detail}\n" if status != doctor.OK else f"  {detail[:80]}\n",
                     style=MUTED if status == doctor.OK else mark[1])
        bad = report.failed or self.failed
        if bad:
            t.append("\nSome things aren't ready yet (the red lines say why). You can carry on and fix them later "
                     "with: reelforge setup", style=WARN)
        self.query_one("#checks", Static).update(t)
        nxt = self.query_one("#next", Button)
        nxt.label = "Next: your channel" if not S.onboarded() else "Continue"
        nxt.disabled = False
        nxt.focus()
        self.query_one("#again", Button).display = bool(bad)

    @on(Button.Pressed, "#next")
    def next(self) -> None:
        self.app.after_tools()

    @on(Button.Pressed, "#again")
    def again(self) -> None:
        self.app.switch_screen(ToolsScreen())


class DoneScreen(tui.Framed):
    """Step 3: what was made, what runs in the background, and what to do next."""

    STEP = "ready"
    BIG_MIN_HEIGHT = 32
    HINT = " Enter presses  ·  Esc closes "
    BINDINGS = [Binding("escape", "close", "Close", show=False)]

    def __init__(self, written: list | None = None):
        super().__init__()
        self.written = written or []

    def body(self) -> ComposeResult:
        yield VerticalScroll(Static(id="done-text"))
        with Horizontal(id="buttons"):
            yield Button("Open ReelForge", variant="primary", id="open")
            yield Button("Show this folder", id="folder")
            yield Button("Close", id="close")

    def on_mount(self) -> None:
        super().on_mount()
        self.system_lines: list[Text] = [Text("  Setting up your background stats…", style=MUTED)]
        self.draw()
        self.query_one("#open", Button).focus()
        self.apply_system()

    def needs_login(self) -> list[str]:
        s = S.load()
        return [S.PLATFORM_NAMES[p] for p in ("instagram", "x")
                if p in s["platforms"]["enabled"] and s["platforms"]["handles"].get(p)]

    @work(thread=True, exclusive=True)
    def apply_system(self) -> None:
        s = S.load()
        lines = []
        try:
            if s["platforms"].get("background_stats", True):
                msg = stats_schedule.enable()
                if msg.startswith(stats_schedule.TEST_COPY):       # a test copy leaves the job alone
                    lines.append((None, msg))
                elif msg.startswith(stats_schedule.ELSEWHERE):     # another copy's job, left alone
                    lines.append((None, "Background stats: " + msg))
                else:
                    ok = not msg.startswith(("Couldn't", "Background stats need"))
                    lines.append((ok, "Background stats: " + msg if ok else msg))
            elif stats_schedule.status() == "on":
                lines.append((True, stats_schedule.disable()))
            else:
                lines.append((True, "Background stats: off. Turn them on any time with: reelforge stats on"))
        except Exception as e:
            lines.append((False, f"Background stats couldn't be set up ({e}). Try: reelforge stats on"))
        if command.status() == "on":
            lines.append((True, "Type reelforge in any new terminal window to open ReelForge."))
        elif P.test_copy():
            lines.append((None, "This is a test copy: typing reelforge in a terminal still opens your main "
                                "ReelForge."))
        else:
            lines.append((None, "To open ReelForge by typing reelforge in a terminal, run setup again and tick "
                                "the reelforge command."))
        self.app.call_from_thread(self._set_system, lines)

    def _set_system(self, lines) -> None:
        self.system_lines = []
        for ok, text in lines:
            row = _mark(ok) if ok is not None else Text("  ·", style=MUTED)
            row.append(f"  {text}")
            self.system_lines.append(row)
        self.draw()

    def draw(self) -> None:
        s = S.load()
        who = s["channel"]["creator"]
        t = Text(f"You're all set{', ' + who if who else ''}!", style="bold")
        t.append(f"  {s['channel']['name']} is ready to make videos.\n\n")
        if self.written:
            t.append("Written:  ", style=MUTED)
            t.append(", ".join(sorted({P.rel(p).split(os.sep)[0] for p in self.written})) + "\n\n", style=MUTED)
        for row in self.system_lines:
            t.append_text(row)
            t.append("\n")
        t.append("\nWhat's next\n", style="bold")
        first = "ultracode: make my first video" if s["ai"]["ultracode"] and s["ai"]["assistant"] != "codex" else \
            "make my first video"
        if s["ai"]["assistant"] in ("claude", "both"):
            t.append("  1. ", style="bold")
            t.append("Open this folder in Claude Code: the Claude desktop app → Code → Open folder… (or run claude "
                     "in a terminal here).\n")
        if s["ai"]["assistant"] in ("codex", "both"):
            t.append("  1. " if s["ai"]["assistant"] == "codex" else "     ", style="bold")
            t.append("Codex: run codex in a terminal in this folder.\n")
        t.append("  2. ", style="bold")
        t.append("Say: ")
        t.append(f'"{first}"', style="bold #ffffff")
        t.append("\n  3. ", style="bold")
        t.append("When it's done, it's waiting in ReelForge → Publish (tab 4), ready for you to post.\n")
        logins = self.needs_login()
        if logins:
            t.append(f"\n{' and '.join(logins)} {'needs' if len(logins) == 1 else 'need'} a one-time log-in so "
                     "ReelForge can read your stats: Open ReelForge takes you to the Accounts tab.", style=WARN)
            self.query_one("#open", Button).label = "Open ReelForge to log in"
        self.query_one("#done-text", Static).update(t)

    @on(Button.Pressed, "#open")
    def open_app(self) -> None:
        self.app.exit(("dashboard", "accounts" if self.needs_login() else "overview"))

    @on(Button.Pressed, "#folder")
    def show_folder(self) -> None:
        try:
            if P.WINDOWS:
                os.startfile(str(P.ROOT))  # noqa: S606 (opens Explorer)
            else:
                subprocess.Popen(["open" if P.MAC else "xdg-open", str(P.ROOT)])
        except OSError:
            self.notify(str(P.ROOT))

    @on(Button.Pressed, "#close")
    def action_close(self) -> None:
        self.app.exit(None)


class FirstRun(App):
    TITLE = KIT_NAME
    CSS = tui.CSS + CSS

    def __init__(self, start: str = "tools"):
        super().__init__()
        self.start = start

    def on_mount(self) -> None:
        self.register_theme(tui.THEME)
        self.theme = tui.THEME.name
        if self.start == "onboard":
            self.push_screen(self.onboarding())
        elif self.start == "done":
            self.push_screen(DoneScreen())
        else:
            self.push_screen(ToolsScreen())

    def onboarding(self) -> OnboardScreen:
        return OnboardScreen(saved_answers(), on_done=self.onboarded)

    def after_tools(self) -> None:
        self.switch_screen(DoneScreen() if S.onboarded() else self.onboarding())

    def onboarded(self, answers: dict, written: list) -> None:
        self.switch_screen(DoneScreen(written))


def run(start: str = "tools"):
    """Show the first-run screens. Returns ("dashboard", tab) to open ReelForge next, or None."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(f"{KIT_NAME} TEST setup" if P.test_copy() else f"{KIT_NAME} setup")
    return FirstRun(start).run()

