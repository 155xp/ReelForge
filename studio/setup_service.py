"""ReelForge's first run, the Python side: the tools it needs (one list, one yes), the downloads with their progress,
a health check, onboarding, then what to do next. The screens themselves are the OpenTUI app's (ui/src/setup/); they
run this through studio/bridge.py.

setup.bat / ./setup.sh open it at the tools; `reelforge onboard` opens it at onboarding. When it closes the window
either opens ReelForge (on the tab the last screen picked) or exits.

Onboarding also makes new profiles (one for each channel, see studio/profiles.py): `reelforge profiles new`, or New
profile in the window's profile menu, which shows these screens inside the window (embedded) and goes back to the
window when they close. Its answers start from the profile it was opened from: who you are and how your AI works, not
the channel.
"""

from __future__ import annotations

import json
import os
import subprocess
import traceback
from pathlib import Path

from . import KIT_NAME, command, doctor, generate, logo, profiles, setup_flow, signup, stats_schedule, tools, tui
from . import paths as P
from . import settings as S
from .bridge import Loop, Service, rpc
from .questions import BY_KEY, QUESTIONS, STEPS, Q, coerce, defaults_for

GOOD, BAD, WARN, MUTED = "#4ade80", "#ff5a4e", "#ffc83a", "#8a94a3"
BLURBS = {
    "you": "Welcome! Answer a few questions and your AI will know your channel inside out. It takes about five "
           "minutes, and you can change anything later with: reelforge channel",
    "channel": "The basics. Your AI reads these before it picks every subject.",
    "format": "Start from a format that is already pulling views. Your AI copies what works, then does it better.",
    "platforms": "Where your videos go. ReelForge shows your stats for each one, and you post from its Publish "
                 "tab.",
    "accounts": "Type your @handle on each, or press Sign up to make the account now. ReelForge opens each sign-up "
                "page in your own browser and never sees your passwords. No rush: you can connect any of them later "
                "on ReelForge's Accounts tab.",
    "look": "How your videos look and sound.",
    "posting": "How each post is written, and how often you post.",
    "review": "Check your answers. Nothing is written until you press Create my studio.",
}
REVIEW = ("review", "Review")
# A new profile's first step (a new channel, from the window's profile menu or reelforge profiles new).
NEW_BLURB = ("A new channel, with its own accounts, stats and settings. Answer a few questions about it (what you told "
             "ReelForge about you and your AI is filled in already); you can change anything later from its Settings "
             "in the profile menu.")
# A new profile starts from these answers of the profile it's made from: about you and your AI, not the channel.
CARRIED = ("creator", "assistant", "timezone", "background_stats")


def seg_line(*parts) -> list:
    """[text, style] segments, the way the window reads styled text (see dashboard/view.py)."""
    return [[t, s] if isinstance(t, str) else t for t, s in parts]


def saved_answers(profile=None) -> dict | None:
    """The answers from a profile's last onboarding (to start from), or None. profile: the one this process works on,
    by default."""
    path = profile.answers if profile is not None else P.ANSWERS
    if not path.exists():
        return None
    try:
        return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
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
        self.profile = profiles.current()  # the profile onboarding is for, or (new) the one it was opened from
        self.new = False                   # making a new profile: it's made when you press Create
        self.made: profiles.Profile | None = None
        self.embedded = False              # inside the ReelForge window, which it goes back to
        self.create_label = "Create my studio"

    def start(self, options: dict) -> dict:
        """options: start ("tools", "onboard" or "done"), preview (tests: Create writes nothing), new (onboarding
        makes a new profile), embedded (inside the ReelForge window: its last screen goes back there)."""
        self.preview = bool(options.get("preview"))
        self.new = bool(options.get("new"))
        self.embedded = bool(options.get("embedded"))
        start = options.get("start") or "tools"
        return {
            "start": start, "kit": KIT_NAME, "test": P.test_copy(), "root": str(P.ROOT),
            "big": logo.cells(logo.big()), "anvil": logo.cells(logo.anvil()), "quadrants": logo.quadrants(),
            "steps": [list(s) for s in tui.STEPS], "check": tui.CHECK, "cross": tui.CROSS, "fancy": tui.FANCY,
            "onboarded": False if self.new else S.onboarded(self.profile.settings),
            "new": self.new, "embedded": self.embedded, "profile": self.profile.name,
            "several": profiles.several(),
        }

    def target(self) -> profiles.Profile:
        """The profile onboarding writes: the new one once it's made, else the one it was opened for."""
        return self.made or self.profile

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
            if what in ("First-time setup", "CLAUDE.md", "AGENTS.md", "Dashboard"):
                continue                      # the channel questions come next; they write those
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
        return "done" if S.onboarded(self.target().settings) else "onboard"

    # ---------------------------------------------------------------- step 2: onboarding

    @rpc
    def onboard_start(self) -> dict:
        start = saved_answers()  # the profile it was opened for (or, for a new one, from)
        if self.new:  # a new channel: only what's about you and your AI carries over
            start = {k: v for k, v in (start or {}).items() if k in CARRIED}
        self.answers = defaults_for(dict(start or {}))
        self.touched = set(start or {})
        if self.new:
            side = "Set up a new channel"
            self.create_label = "Create the profile"
        else:
            side = f"{self.profile.name}" if profiles.several() else "Set up your channel"
            self.create_label = "Create my studio"
        return {"steps": [list(s) for s in self.steps], "blurbs": BLURBS, "side": side, "create": self.create_label}

    def step_questions(self, key: str) -> list[Q]:
        return [q for q in QUESTIONS if q.step == key]

    def field(self, q: Q) -> dict:
        v = self.answers.get(q.key)
        if q.kind == "long":
            v = "\n".join(v) if isinstance(v, list) else ("" if v is None else str(v))
        elif q.kind in ("text", "number", "handle"):
            v = "" if v is None else str(v)
        out = {"key": q.key, "prompt": q.prompt, "required": q.required, "help": q.help, "kind": q.kind,
               "options": [list(o) for o in q.options], "value": v, "placeholder": q.placeholder_for(self.answers),
               "visible": q.visible(self.answers)}
        if q.kind == "handle":
            out["platform"] = q.key.removeprefix("handle_")  # its "No account? Sign up" opens that guide
        return out

    @rpc
    def onboard_step(self, i: int) -> dict:
        """Step i: its title and blurb, and its questions (or, on the last step, the review)."""
        self.index = i
        key, label = self.steps[i]
        blurb = NEW_BLURB if self.new and key == "you" else BLURBS.get(key, "")
        if key == "review":
            blurb = blurb.replace("Create my studio", self.create_label)
        out = {"index": i, "key": key, "title": f"{i + 1}/{len(self.steps)}  {label}", "blurb": blurb}
        if key == "review":
            out["review"] = self.summary()
        else:
            self.answers = defaults_for(self.answers)
            out["fields"] = [self.field(q) for q in self.step_questions(key)]
        if key == "accounts":  # the box at the top: a Gmail just for the channel first, for someone starting from scratch
            name = str(self.answers.get("channel_name") or "").strip()
            title = f"A new channel needs its own accounts: make a Gmail for {name} first." if self.new and name else \
                "Starting from scratch? Make a Gmail for your channel first."
            out["gmail"] = {"title": title, "why": signup.GMAIL.why, "button": "Make a Gmail →"}
            if how := signup.where(self.others()):  # a second channel: its sign-ups open in a private window
                out["blurb"] = (f"Type your @handle on each, or press Sign up to make the account now. Each sign-up "
                                f"page opens {how}; ReelForge never sees your passwords. No rush: you can connect any "
                                "of them later on ReelForge's Accounts tab.")
        return out

    # ---------------------------------------------------------------- making accounts

    def others(self) -> list[str]:
        """The names of the other channels, whose accounts are probably logged in in your browser: while there are
        any, this channel's sign-ups open in a private window (see studio/signup.py)."""
        return profiles.others(None if self.new else self.profile, self.made)

    @rpc
    def signup_guide(self, key: str) -> dict:
        """How to make one account (or the channel's Gmail, "gmail"): its steps, with examples from the channel's name,
        the button that opens the official sign-up page in your own browser (a private window of it for a second
        channel), and for an account a box for the @handle you end up with."""
        view = signup.guide_view(key, str(self.answers.get("channel_name") or ""), self.others())
        if view["account"]:
            view["steps"].append("Type your @handle below." + (
                " It also needs one log-in in ReelForge, so ReelForge can read your stats: it asks for it when you "
                "open ReelForge." if signup.GUIDES[key].logs_in else ""))
        return view

    @rpc
    def open_signup(self, key: str) -> str:
        """Open a guide's page; what to say under its button."""
        return signup.open_guide(key, self.others())

    @rpc
    def signup_handle(self, typed: str) -> dict:
        """The handle typed into a sign-up guide: {"handle": "@name"} for its box on the step (maybe ""), or
        {"error": ...} to show in the guide."""
        try:
            return {"handle": signup.handle_from(typed)}
        except ValueError as e:
            return {"error": str(e)}

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
            if q.key == "channel_name" and (other := profiles.taken(str(value), None if self.new else self.profile)):
                errors[q.key] = (f"You already have a profile called {other.name}. Give this channel its own name."
                                 if self.new else f"Another profile is called {other.name}.")
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
                skipped = "_(skipped)_"
                if q.kind == "choice":
                    v = dict(q.options).get(v, v)
                elif q.kind == "multi":
                    v = ", ".join(dict(q.options).get(x, x).split("   ·")[0] for x in (v or []))
                elif q.kind == "yesno":
                    v = "Yes" if v else "No"
                elif q.kind == "handle":
                    skipped = "_(not yet: connect it any time on ReelForge's Accounts tab)_"
                elif isinstance(v, str) and "\n" in v:
                    v = "; ".join(x.strip() for x in v.splitlines() if x.strip())
                lines.append(f"- **{q.prompt}** {v if v not in (None, '') else skipped}")
            lines.append("")
        if problems:
            lines += ["### Needs fixing", *[f"- {p}" for p in problems]]
        if self.new:
            where = f"profiles{os.sep}{profiles.slug_for(str(a.get('channel_name') or ''))}"
            lines += ["", f"Pressing **Create the profile** makes this channel's own folder, `{where}`, with your AI's "
                          "notes on it (`CLAUDE.md` and `AGENTS.md`), its settings and channel bible (`my-studio/`) "
                          "and its ReelForge settings. Its stats, log-ins and notifications are its own."]
        else:
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
            if self.new and self.made is None:
                from .questions import validate

                a, problems = validate(self.answers)
                if problems:  # said below, before a folder is made
                    raise ValueError("some answers need fixing:\n  " + "\n  ".join(problems))
                self.made = profiles.create(a["channel_name"])
            self.written = generate.write_all(self.answers, self.target())
        except ValueError as e:
            return {"ok": False, "status": str(e).splitlines()[0],
                    "review": self.summary() + "\n\n```\n" + str(e) + "\n```"}
        except Exception:
            return {"ok": False, "status": "Something went wrong writing your files (details below).",
                    "detail": traceback.format_exc()}
        return {"ok": True}

    # ---------------------------------------------------------------- step 3: ready

    def needs_login(self) -> list[str]:
        s = S.load(self.target().settings)
        return [S.PLATFORM_NAMES[p] for p in ("instagram", "x")
                if p in s["platforms"]["enabled"] and s["platforms"]["handles"].get(p)]

    def to_connect(self) -> list[str]:
        """The platforms you post to without a handle yet (no account yet): you connect them on the Accounts tab."""
        s = S.load(self.target().settings)
        return [S.PLATFORM_NAMES[p] for p in s["platforms"]["enabled"] if not s["platforms"]["handles"].get(p)]

    @rpc
    def done_info(self) -> dict:
        """The last screen: what was made, what to do next; the background stats follow as "system"."""
        self.loop.run_worker(self._apply_system, group="system", exclusive=True)
        here = self.target()
        s = S.load(here.settings)
        who = s["channel"]["creator"]
        lines = [seg_line((f"You're all set{', ' + who if who else ''}!", "bold"),
                          (f"  {s['channel']['name']} is ready to make videos.", ""))]
        written = ""
        if self.written:
            written = ", ".join(sorted({_top(p, here) for p in self.written}))
        video = "my first video" if here.main else f"my first {s['channel']['name']} video"
        first = f"make {video}"
        steps = []
        folder = "this folder" if here.main else "the ReelForge folder (the same one for every channel)"
        there = "here" if here.main else "there"
        if s["ai"]["assistant"] in ("claude", "both"):
            steps.append(seg_line(("  1. ", "bold"), (f"Open {folder} in Claude Code: the Claude desktop app → Code "
                                                      f"→ Open folder… (or run claude in a terminal {there}).", "")))
        if s["ai"]["assistant"] in ("codex", "both"):
            steps.append(seg_line(("  1. " if s["ai"]["assistant"] == "codex" else "     ", "bold"),
                                  (f"Codex: run codex in a terminal in {folder}.", "")))
        # Setup only asks a few questions: the channel's brief (a file or a description, in the person's words) is
        # what the AI plans from. Its notes say where it goes and what to do with it.
        channel = s["channel"]["name"]
        say, kept = ("here's my channel", "your channel's brief") if here.main else \
            (f"here's {channel}", f"the brief for {channel}")
        steps.append(seg_line(("  2. ", "bold"), ("Say ", ""), (f'"{say}"', "bold #ffffff"),
                              (" and drag a file about it into the chat, or paste a description.", "")))
        steps.append(seg_line(("     ", ""), (f"Your notes, a doc, examples you like: it keeps it as {kept} and plans "
                                              "every video from it.", "")))
        steps.append(seg_line(("  3. ", "bold"), ("Say: ", ""), (f'"{first}"', "bold #ffffff")))
        steps.append(seg_line(("  4. ", "bold"),
                              ("When it's done, it's waiting in ReelForge → Publish (tab 4), ready for you to post.",
                               "")))
        logins, missing = self.needs_login(), self.to_connect()
        login = []
        if logins:
            login.append(f"{' and '.join(logins)} {'needs' if len(logins) == 1 else 'need'} a one-time log-in so "
                         "ReelForge can read your stats: Open ReelForge takes you to the Accounts tab.")
        if missing:
            names = missing[0] if len(missing) == 1 else ", ".join(missing[:-1]) + " and " + missing[-1]
            one = len(missing) == 1
            login.append(f"When you've made your {names} {'account' if one else 'accounts'}, connect "
                         f"{'it' if one else 'them'} on ReelForge's Accounts tab: until then ReelForge leaves "
                         f"{'it' if one else 'them'} out.")
        name = s["channel"]["name"] if self.new else "ReelForge"
        return {"head": lines, "written": written, "steps": steps, "login": "\n".join(login),
                "open": f"Open {name} to log in" if logins else f"Open {name}",
                "tab": "accounts" if logins or missing else "overview",
                "profile": here.key if self.new else "",  # the window opens the new profile next
                "back": f"Back to {self.profile.name}" if self.embedded and self.new else ""}

    def _apply_system(self) -> None:
        lines = []
        try:
            # One hourly job reads every profile that keeps its stats read in the background (most do).
            if any(S.load(p.settings)["platforms"].get("background_stats", True) for p in profiles.every()):
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
        folder = P.ROOT if self.target().main else self.target().folder
        try:
            if P.WINDOWS:
                os.startfile(str(folder))  # noqa: S606 (opens Explorer)
            else:
                subprocess.Popen(["open" if P.MAC else "xdg-open", str(folder)])
        except OSError:
            self.notify(str(folder))


def _top(path, profile) -> str:
    """What onboarding wrote, as the last screen lists it: the top folder or file, from the profile's folder."""
    root = P.ROOT if profile.main else profile.folder
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).parts[0]
    except (ValueError, IndexError):
        return P.rel(path).split(os.sep)[0]
