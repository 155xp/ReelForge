"""ReelForge's first run, the Python side: the tools it needs (one list, one yes), the downloads with their progress,
a health check, onboarding, then what to do next. The screens themselves are the OpenTUI app's (ui/src/setup/); they
run this through studio/bridge.py.

setup.bat / ./setup.sh open it at the tools; `reelforge onboard` opens it at onboarding. When it closes the window
either opens ReelForge (on the tab the last screen picked) or exits.
"""

from __future__ import annotations

import json
import os
import subprocess
import traceback

from . import KIT_NAME, command, doctor, generate, logo, setup_flow, stats_schedule, tools, tui
from . import paths as P
from . import settings as S
from .bridge import Loop, Service, rpc
from .questions import BY_KEY, QUESTIONS, STEPS, Q, coerce, defaults_for

GOOD, BAD, WARN, MUTED = "#4ade80", "#ff5a4e", "#ffc83a", "#8a94a3"
BLURBS = {
    "you": "Welcome! Answer a few questions and your AI will know your channel inside out. It takes about five "
           "minutes, and you can change anything later with: reelforge onboard",
    "channel": "The basics. Your AI reads these before it picks every subject.",
    "format": "Start from a format that is already pulling views. Your AI copies what works, then does it better.",
    "platforms": "Where your videos go. ReelForge shows your stats for each one, and you post from its Publish "
                 "tab.",
    "look": "How your videos look and sound.",
    "posting": "How each post is written, and how often you post.",
    "quality": "How hard your AI should push on every video.",
    "review": "Check your answers. Nothing is written until you press Create my studio.",
}
REVIEW = ("review", "Review")


def seg_line(*parts) -> list:
    """[text, style] segments, the way the window reads styled text (see dashboard/view.py)."""
    return [[t, s] if isinstance(t, str) else t for t, s in parts]


def saved_answers() -> dict | None:
    """The answers from the last onboarding (to start from), or None."""
    if not P.ANSWERS.exists():
        return None
    try:
        return {k: v for k, v in json.loads(P.ANSWERS.read_text(encoding="utf-8")).items()
                if k in BY_KEY or k.startswith("_")}
    except ValueError:
        return None


class Setup(Service):
    def __init__(self, loop: Loop):
        super().__init__(loop)
        self.items: list[setup_flow.Item] = []
        self.failed: list[str] = []
        self.answers: dict = {}
        self.touched: set[str] = set()
        self.index = 0
        self.steps = STEPS + [REVIEW]
        self.preview = False
        self.written: list = []

    def start(self, options: dict) -> dict:
        """options: start ("tools", "onboard" or "done"), preview (tests: Create writes nothing)."""
        self.preview = bool(options.get("preview"))
        start = options.get("start") or "tools"
        return {
            "start": start, "kit": KIT_NAME, "test": P.test_copy(), "root": str(P.ROOT),
            "big": logo.cells(logo.big()), "anvil": logo.cells(logo.anvil()), "quadrants": logo.quadrants(),
            "steps": [list(s) for s in tui.STEPS], "check": tui.CHECK, "cross": tui.CROSS, "fancy": tui.FANCY,
            "onboarded": S.onboarded(),
        }

    # ---------------------------------------------------------------- step 1: the tools

    @rpc
    def plan(self) -> None:
        """Check what's already on this computer (a few seconds: it starts Blender once); "items" says."""
        self.loop.run_worker(self._plan, group="plan", exclusive=True)

    def _plan(self) -> None:
        items = setup_flow.plan()
        self.loop.call_soon(self.show_items, items)

    def show_items(self, items: list[setup_flow.Item]) -> None:
        self.items = items
        intro = seg_line(("Let's get ReelForge ready. ", "bold"),
                         ("Everything goes into this folder; nothing else on your computer changes:\n", ""),
                         (str(P.ROOT), MUTED))
        if tools.path_too_long():
            intro.append([f"\nThis folder's path is {len(str(P.ROOT))} characters long, too deep for some of "
                          "Blender's files. Move it somewhere shorter (e.g. C:\\ReelForge) first.", f"bold {WARN}"])
        self.emit("items", {
            "intro": intro,
            "items": [{"key": i.key, "name": i.name, "why": i.why, "ready": i.ready, "detail": i.detail,
                       "size_mb": i.size_mb, "can_install": i.can_install, "default": i.default} for i in items],
            "todo": [i.key for i in setup_flow.todo(items)],
            "note": "Downloads come only from the official sites (blender.org, gyan.dev, Mixkit) and every file is "
                    "checked. Mixkit's sounds are free to use in your videos, YouTube and social media included.",
        })

    @rpc
    def run_setup(self, keys: list[str]) -> None:
        """Set up the ticked items, one after the other ("job" says how each is going), then the sound library and
        the health check ("checks")."""
        chosen = [i for i in setup_flow.todo(self.items) if i.key in set(keys or [])]
        self.failed = []
        self.emit("jobs", {"jobs": [{"key": i.key, "name": i.name} for i in chosen] +
                           [{"key": "cache", "name": "Sound library", "percent": False}]})
        self.loop.run_worker(self._run_all, chosen, group="setup", exclusive=True)

    def _job(self, key: str, text: str, done: float = 0, total: float = 0, state: str = "busy") -> None:
        self.loop.call_soon(self.emit, "job", {"key": key, "text": text, "done": done, "total": total,
                                              "state": state})

    def _progress(self, key: str):
        def report(text: str, done: float, total: float) -> None:
            if total and total > 1e5:
                text += f"  {done / 1e6:.0f} of {total / 1e6:.0f} MB"
            self._job(key, text, done, total)
        return report

    def _run_all(self, items: list[setup_flow.Item]) -> None:
        for i in items:
            self._job(i.key, "starting")
            try:
                msg = setup_flow.apply(i, self._progress(i.key))
                self._job(i.key, msg, 1, 1, "ok")
            except Exception as e:  # network, disk, checksum: say it and carry on with the rest
                self.failed.append(i.name)
                self._job(i.key, "Didn't work: " + str(e).splitlines()[0][:120], 0, 1, "failed")
        try:
            if setup_flow.sounds.missing() or not tools.find_ffmpeg():
                self._job("cache", "Didn't work: needs ffmpeg and every sound first", 0, 1, "failed")
            else:
                setup_flow.prepare_sounds(self._progress("cache"))
                self._job("cache", "ready for mixing", 1, 1, "ok")
        except Exception as e:
            self._job("cache", "Didn't work: " + str(e).splitlines()[0][:120], 0, 1, "failed")
        self.loop.call_soon(self.emit, "checks", {"checking": True})
        report = doctor.checks(quiet=True)
        self.loop.call_soon(self.show_checks, report)

    def show_checks(self, report: doctor.Report) -> None:
        rows = []
        for status, what, detail in report.rows:
            if what in ("Onboarding", "CLAUDE.md", "AGENTS.md", "Dashboard"):
                continue                      # onboarding comes next; it writes those
            mark = {doctor.OK: (tui.CHECK, GOOD), doctor.WARN: ("!", WARN)}.get(status, (tui.CROSS, BAD))
            rows.append(seg_line((f"  {mark[0]} ", f"bold {mark[1]}"), (what, "bold"),
                                 (f"  {detail}" if status != doctor.OK else f"  {detail[:80]}",
                                  MUTED if status == doctor.OK else mark[1])))
        bad = bool(report.failed or self.failed)
        self.emit("checks", {"rows": rows, "bad": bad,
                             "warning": "Some things aren't ready yet (the red lines say why). You can carry on and "
                                        "fix them later with: reelforge setup" if bad else "",
                             "next": "Next: your channel" if not S.onboarded() else "Continue"})

    @rpc
    def after_tools(self) -> str:
        """Where the Next button goes: onboarding, or straight to the last screen once it's done."""
        return "done" if S.onboarded() else "onboard"

    # ---------------------------------------------------------------- step 2: onboarding

    @rpc
    def onboard_start(self) -> dict:
        start = saved_answers()
        self.answers = defaults_for(dict(start or {}))
        self.touched = set(start or {})
        return {"steps": [list(s) for s in self.steps], "blurbs": BLURBS}

    def step_questions(self, key: str) -> list[Q]:
        return [q for q in QUESTIONS if q.step == key]

    def field(self, q: Q) -> dict:
        v = self.answers.get(q.key)
        if q.kind == "long":
            v = "\n".join(v) if isinstance(v, list) else ("" if v is None else str(v))
        elif q.kind in ("text", "number"):
            v = "" if v is None else str(v)
        return {"key": q.key, "prompt": q.prompt, "required": q.required, "help": q.help, "kind": q.kind,
                "options": [list(o) for o in q.options], "value": v, "placeholder": q.placeholder_for(self.answers),
                "visible": q.visible(self.answers)}

    @rpc
    def onboard_step(self, i: int) -> dict:
        """Step i: its title and blurb, and its questions (or, on the last step, the review)."""
        self.index = i
        key, label = self.steps[i]
        out = {"index": i, "key": key, "title": f"{i + 1}/{len(self.steps)}  {label}", "blurb": BLURBS.get(key, "")}
        if key == "review":
            out["review"] = self.summary()
        else:
            self.answers = defaults_for(self.answers)
            out["fields"] = [self.field(q) for q in self.step_questions(key)]
        return out

    @staticmethod
    def _same(a, b) -> bool:
        def norm(v):
            if isinstance(v, (list, tuple)):
                return "\n".join(str(x) for x in v)
            return "" if v is None else str(v)
        return norm(a).strip() == norm(b).strip()

    @rpc
    def onboard_change(self, key: str, raw) -> dict | None:
        """You changed an answer: the step's questions as they now show (some appear or disappear; a new format brings
        its own suggestions for the questions you haven't typed in). None if nothing else changed."""
        if key not in BY_KEY or self._same(raw, self.answers.get(key)):
            return None
        self.answers[key] = raw
        self.touched.add(key)
        if key == "format":
            # follow the new format's suggestions unless you already typed your own
            for dep in ("series", "twist", "hud", "default_tags"):
                if dep not in self.touched:
                    self.answers.pop(dep, None)
            self.answers = defaults_for(self.answers)
        step = self.steps[self.index][0]
        return {"fields": [self.field(q) for q in self.step_questions(step)]}

    @rpc
    def onboard_next(self, raws: dict) -> dict:
        """Check this step's answers; {"ok": True, "step": ...} for the next one, or the problems by question."""
        key = self.steps[self.index][0]
        if key == "review":
            return {"ok": False, "status": ""}
        errors, first_bad = {}, None
        for q in self.step_questions(key):
            if not q.visible(self.answers):
                continue
            raw = raws.get(q.key, self.answers.get(q.key))
            if raw in (None, "") and not q.required and q.kind in ("number", "choice"):
                raw = q.default_for(self.answers)
            try:
                value = coerce(q, raw) if raw not in (None, "") or q.kind in ("yesno",) else raw
            except ValueError as e:
                errors[q.key] = str(e)
                first_bad = first_bad or q.key
                continue
            if q.required and value in (None, "", []):
                errors[q.key] = "Please answer this one."
                first_bad = first_bad or q.key
                continue
            if q.key == "length_custom":
                from .questions import parse_length
                try:
                    lo, hi = parse_length(value)
                    assert 5 <= lo <= hi <= 600
                except (ValueError, AssertionError):
                    errors[q.key] = "Write it as min-max seconds, e.g. 20-30"
                    first_bad = first_bad or q.key
                    continue
            self.answers[q.key] = value
        if errors:
            return {"ok": False, "errors": errors, "first": first_bad,
                    "status": "Fix the highlighted answers to continue."}
        return {"ok": True, "step": self.onboard_step(self.index + 1)}

    @rpc
    def onboard_back(self, raws: dict) -> dict | None:
        """Back a step, keeping what was typed even if it isn't valid yet."""
        if self.index == 0:
            return None
        if self.steps[self.index][0] != "review":
            for k, v in (raws or {}).items():
                if k in BY_KEY:
                    self.answers[k] = v
        return self.onboard_step(self.index - 1)

    def summary(self) -> str:
        from .questions import validate
        a, problems = validate(self.answers)
        lines = []
        for key, label in STEPS:
            lines.append(f"### {label}")
            for q in self.step_questions(key):
                if not q.visible(a):
                    continue
                v = a.get(q.key)
                if q.kind == "choice":
                    v = dict(q.options).get(v, v)
                elif q.kind == "multi":
                    v = ", ".join(dict(q.options).get(x, x) for x in (v or []))
                elif q.kind == "yesno":
                    v = "Yes" if v else "No"
                elif isinstance(v, str) and "\n" in v:
                    v = "; ".join(x.strip() for x in v.splitlines() if x.strip())
                lines.append(f"- **{q.prompt}** {v if v not in (None, '') else '_(skipped)_'}")
            lines.append("")
        if problems:
            lines += ["### Needs fixing", *[f"- {p}" for p in problems]]
        lines += ["", "Pressing **Create my studio** writes `CLAUDE.md` and `AGENTS.md` (your AI's instructions), "
                      "`my-studio/` (your settings and channel bible) and the dashboard's settings."]
        return "\n".join(lines)

    @rpc
    def onboard_create(self) -> dict:
        """Write everything: {"ok": True} and on to the last screen, or what went wrong."""
        if self.preview:
            self.written = []
            return {"ok": True}
        try:
            self.written = generate.write_all(self.answers)
        except ValueError as e:
            return {"ok": False, "status": str(e).splitlines()[0],
                    "review": self.summary() + "\n\n```\n" + str(e) + "\n```"}
        except Exception:
            return {"ok": False, "status": "Something went wrong writing your files (details below).",
                    "detail": traceback.format_exc()}
        return {"ok": True}

    # ---------------------------------------------------------------- step 3: ready

    def needs_login(self) -> list[str]:
        s = S.load()
        return [S.PLATFORM_NAMES[p] for p in ("instagram", "x")
                if p in s["platforms"]["enabled"] and s["platforms"]["handles"].get(p)]

    @rpc
    def done_info(self) -> dict:
        """The last screen: what was made, what to do next; the background stats follow as "system"."""
        self.loop.run_worker(self._apply_system, group="system", exclusive=True)
        s = S.load()
        who = s["channel"]["creator"]
        lines = [seg_line((f"You're all set{', ' + who if who else ''}!", "bold"),
                          (f"  {s['channel']['name']} is ready to make videos.", ""))]
        written = ""
        if self.written:
            written = ", ".join(sorted({P.rel(p).split(os.sep)[0] for p in self.written}))
        first = "ultracode: make my first video" if s["ai"]["ultracode"] and s["ai"]["assistant"] != "codex" else \
            "make my first video"
        steps = []
        if s["ai"]["assistant"] in ("claude", "both"):
            steps.append(seg_line(("  1. ", "bold"), ("Open this folder in Claude Code: the Claude desktop app → Code "
                                                      "→ Open folder… (or run claude in a terminal here).", "")))
        if s["ai"]["assistant"] in ("codex", "both"):
            steps.append(seg_line(("  1. " if s["ai"]["assistant"] == "codex" else "     ", "bold"),
                                  ("Codex: run codex in a terminal in this folder.", "")))
        steps.append(seg_line(("  2. ", "bold"), ("Say: ", ""), (f'"{first}"', "bold #ffffff")))
        steps.append(seg_line(("  3. ", "bold"),
                              ("When it's done, it's waiting in ReelForge → Publish (tab 4), ready for you to post.",
                               "")))
        logins = self.needs_login()
        login = ""
        if logins:
            login = (f"{' and '.join(logins)} {'needs' if len(logins) == 1 else 'need'} a one-time log-in so ReelForge "
                     "can read your stats: Open ReelForge takes you to the Accounts tab.")
        return {"head": lines, "written": written, "steps": steps, "login": login,
                "open": "Open ReelForge to log in" if logins else "Open ReelForge",
                "tab": "accounts" if logins else "overview"}

    def _apply_system(self) -> None:
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
        rows = []
        for ok, text in lines:
            mark = ("  ·", MUTED) if ok is None else (f"  {tui.CHECK}", f"bold {GOOD}") if ok else \
                (f"  {tui.CROSS}", f"bold {BAD}")
            rows.append(seg_line(mark, (f"  {text}", "")))
        self.loop.call_soon(self.emit, "system", {"rows": rows})

    @rpc
    def show_folder(self) -> None:
        try:
            if P.WINDOWS:
                os.startfile(str(P.ROOT))  # noqa: S606 (opens Explorer)
            else:
                subprocess.Popen(["open" if P.MAC else "xdg-open", str(P.ROOT)])
        except OSError:
            self.notify(str(P.ROOT))
