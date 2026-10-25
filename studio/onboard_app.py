"""The onboarding interview, inside ReelForge's first-run box (Textual). `reelforge onboard` (or onboard.bat /
./onboard.sh) runs it; setup runs it straight after the tools. Mouse and keyboard both work: Tab moves between
fields, Enter presses a button."""

from __future__ import annotations

import json
import traceback

from rich.table import Table
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (Button, Input, Label, Markdown, RadioButton, RadioSet, SelectionList, Static, Switch,
                             TextArea)
from textual.markup import escape
from textual.widgets.selection_list import Selection

from . import generate, signup, tui
from . import paths as P
from .questions import BY_KEY, QUESTIONS, STEPS, Q, coerce, defaults_for

BLURBS = {
    "you": "Welcome! Answer a few questions and your AI will know your channel inside out. It takes about five "
           "minutes, and you can change anything later with: reelforge onboard",
    "channel": "The basics. Your AI reads these before it picks every subject.",
    "format": "Start from a format that is already pulling views. Your AI copies what works, then does it better.",
    "platforms": "Where your videos go. ReelForge shows your stats for each one, and you post from its Publish "
                 "tab.",
    "accounts": "Type your @handle on each, or press Sign up to make the account now. ReelForge opens each sign-up "
                "page in your own browser and never sees your passwords. No rush: you can connect any of them later "
                "on ReelForge's Accounts tab.",
    "look": "How your videos look and sound.",
    "posting": "How each post is written, and how often you post.",
    "quality": "How hard your AI should push on every video.",
    "review": "Check your answers. Nothing is written until you press Create my studio.",
}
REVIEW = ("review", "Review")


class Field(Vertical):
    """One question: its prompt, help line, input widget and an error line."""

    def __init__(self, q: Q, value, answers: dict):
        super().__init__(classes="field", id=f"f-{q.key}")
        self.q = q
        self.value = value
        self.answers = answers

    def compose(self) -> ComposeResult:
        q, v = self.q, self.value
        yield Label(escape(q.prompt) + (" *" if q.required else ""), classes="prompt")
        if q.help:
            yield Static(escape(q.help), classes="help")
        ph = q.placeholder_for(self.answers)
        wid = f"w-{q.key}"
        if q.kind == "text" or q.kind == "number":
            yield Input(value="" if v is None else str(v), placeholder=ph, id=wid,
                        type="integer" if q.kind == "number" else "text")
        elif q.kind == "long":
            text = "\n".join(v) if isinstance(v, list) else ("" if v is None else str(v))
            yield TextArea(text, id=wid, placeholder=ph, soft_wrap=True, classes="long")
        elif q.kind == "choice":
            with RadioSet(id=wid):
                for value, label in q.options:
                    yield RadioButton(escape(label), value=(value == v), name=value)
        elif q.kind == "multi":
            chosen = set(v or [])
            yield SelectionList[str](*[Selection(escape(label), value, value in chosen) for value, label in q.options],
                                     id=wid)
        elif q.kind == "yesno":
            with Horizontal(classes="switchrow"):
                yield Switch(value=bool(v), id=wid)
                yield Label("Yes" if v else "No", id=f"yn-{q.key}", classes="yn")
        elif q.kind == "handle":
            with Horizontal(classes="handlerow"):
                yield Input(value="" if v is None else str(v), placeholder=ph, id=wid)
                yield Button("No account? Sign up →", id=f"signup-{q.key.removeprefix('handle_')}",
                             classes="signup")
        yield Static("", classes="error", id=f"e-{q.key}")

    def raw(self):
        w = self.query_one(f"#w-{self.q.key}")
        if isinstance(w, Input):
            return w.value
        if isinstance(w, TextArea):
            return w.text
        if isinstance(w, RadioSet):
            b = w.pressed_button
            return b.name if b is not None else None
        if isinstance(w, SelectionList):
            return list(w.selected)
        if isinstance(w, Switch):
            return w.value
        return None

    def set_raw(self, value):
        """Change the shown value without it counting as something you typed."""
        w = self.query_one(f"#w-{self.q.key}")
        if isinstance(w, Input):
            with w.prevent(Input.Changed):
                w.value = "" if value is None else str(value)
        elif isinstance(w, TextArea):
            with w.prevent(TextArea.Changed):
                w.text = "\n".join(value) if isinstance(value, list) else ("" if value is None else str(value))

    def error(self, text: str):
        self.query_one(f"#e-{self.q.key}", Static).update(text)
        self.set_class(bool(text), "bad")


class Quit(ModalScreen[bool]):
    DEFAULT_CSS = """
    Quit { align: center middle; background: $background 70%; }
    Quit #dialog { width: 60; height: auto; padding: 1 2; background: $panel; border: double $primary; }
    Quit #dialog .buttons { height: auto; padding-top: 1; }
    Quit #dialog Button { margin-right: 2; }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Leave onboarding? Your answers so far won't be saved.")
            with Horizontal(classes="buttons"):
                yield Button("Keep going", variant="primary", id="stay")
                yield Button("Leave", variant="error", id="leave")

    @on(Button.Pressed)
    def done(self, event: Button.Pressed):
        self.dismiss(event.button.id == "leave")


def guide_steps(guide: signup.Guide) -> Table:
    """A sign-up guide's steps, numbered: open the page, what to do there, then (for an account) type the handle."""
    steps = [f"Press {guide.button}: the page opens in your browser.", *guide.steps]
    if guide.key != "gmail":
        steps.append("Type your @handle below." + (" It also needs one log-in in ReelForge, so ReelForge can read "
                                                   "your stats: it asks for it when you open ReelForge."
                                                   if guide.logs_in else ""))
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=3, justify="right", style="bold")
    grid.add_column(ratio=1)
    for n, step in enumerate(steps, 1):
        grid.add_row(f"{n}.", step)
    return grid


class SignupGuide(ModalScreen[str | None]):
    """How to make one account (or the channel's Gmail): the steps, a button that opens the official sign-up page in
    your own browser, and (for an account) a box for the @handle you end up with. Dismisses with that handle (maybe
    ""), or None for Back."""

    DEFAULT_CSS = """
    SignupGuide { align: center middle; background: $background 70%; }
    SignupGuide #guide { width: 84; max-width: 95%; height: auto; max-height: 95%; padding: 1 2; background: $panel;
                         border: double $primary; }
    SignupGuide #guide-title { text-style: bold; color: $accent; }
    SignupGuide #guide-why { color: $text-muted; padding-bottom: 1; }
    SignupGuide #guide-open { margin: 1 0 0 4; }
    SignupGuide #guide-opened { color: $success; height: auto; padding: 0 0 0 4; }
    SignupGuide #guide-handle-label { text-style: bold; padding-top: 1; }
    SignupGuide #guide-error { color: $error; height: auto; }
    SignupGuide .buttons { height: auto; padding-top: 1; }
    SignupGuide .buttons Button { margin-right: 2; min-width: 14; }
    """
    BINDINGS = [Binding("escape", "back", "Back", show=False)]

    def __init__(self, guide: signup.Guide, handle: str = ""):
        super().__init__()
        self.guide, self.handle = guide, handle

    def compose(self) -> ComposeResult:
        g = self.guide
        with Vertical(id="guide"):
            yield Static(g.title, id="guide-title")
            yield Static(g.why, id="guide-why")
            yield Static(guide_steps(g), id="guide-steps")
            yield Button(f"{g.button} →", variant="primary", id="guide-open")
            yield Static("", id="guide-opened")
            if g.key != "gmail":
                yield Label("Your @handle", id="guide-handle-label")
                yield Input(value=self.handle, placeholder="@yourname", id="guide-handle")
                yield Static("", id="guide-error")
            with Horizontal(classes="buttons"):
                yield Button("Done", id="guide-done")
                yield Button("Back", id="guide-back")

    def on_mount(self) -> None:
        self.query_one("#guide-open", Button).focus()

    @on(Button.Pressed, "#guide-open")
    def open_page(self) -> None:
        signup.open_page(self.guide.url)
        self.query_one("#guide-opened", Static).update(
            f"{tui.CHECK} Opened in your browser. Come back here when you're done.")
        handle = self.query(Input)
        (handle.first() if handle else self.query_one("#guide-done", Button)).focus()

    @on(Input.Submitted, "#guide-handle")
    @on(Button.Pressed, "#guide-done")
    def done(self) -> None:
        if self.guide.key == "gmail":
            self.dismiss(None)
            return
        try:
            handle = signup.handle_from(self.query_one("#guide-handle", Input).value)
        except ValueError as e:
            self.query_one("#guide-error", Static).update(str(e))
            return
        self.dismiss(handle)

    @on(Button.Pressed, "#guide-back")
    def action_back(self) -> None:
        self.dismiss(None)


class GmailOffer(Vertical):
    """The box at the top of Your accounts: a Gmail just for the channel first, for someone starting from scratch."""

    DEFAULT_CSS = """
    GmailOffer { height: auto; border: round $panel-lighten-2; padding: 0 1; margin-bottom: 1; }
    GmailOffer .offer-title { text-style: bold; }
    GmailOffer .offer-why { color: $text-muted; }
    GmailOffer Button { margin-top: 1; }
    """

    def compose(self) -> ComposeResult:
        yield Static("Starting from scratch? Make a Gmail for your channel first.", classes="offer-title")
        yield Static(signup.GMAIL.why, classes="offer-why")
        yield Button("Make a Gmail →", id="gmail")


class OnboardScreen(tui.Framed):
    """The interview, step by step, then a review. Create writes everything and calls on_done(answers, written)."""

    STEP = "channel"
    BIG_MIN_HEIGHT = 48                   # the questions need the room; smaller windows get the anvil and the name
    HINT = " Tab moves  ·  Enter presses  ·  Esc to leave "
    DEFAULT_CSS = """
    OnboardScreen #side { width: 30; padding: 1 2 0 0; border-right: solid $panel-lighten-2; }
    OnboardScreen #tag { color: $text-muted; padding-bottom: 1; }
    OnboardScreen .step { padding: 0 1; color: $text-muted; }
    OnboardScreen .step.current { color: $text; text-style: bold; background: $primary 25%; }
    OnboardScreen .step.done { color: $success; }
    OnboardScreen #main { padding: 1 0 0 3; }
    OnboardScreen #title { text-style: bold; color: $accent; }
    OnboardScreen #blurb { color: $text-muted; padding-bottom: 1; }
    OnboardScreen #fields { height: 1fr; scrollbar-gutter: stable; }
    OnboardScreen .field { height: auto; padding: 0 0 1 0; }
    OnboardScreen .field.hidden { display: none; }
    OnboardScreen .prompt { text-style: bold; }
    OnboardScreen .help { color: $text-muted; }
    OnboardScreen .error { color: $error; height: auto; }
    OnboardScreen .field.bad Input, OnboardScreen .field.bad TextArea, OnboardScreen .field.bad RadioSet,
    OnboardScreen .field.bad SelectionList { border: tall $error; }
    OnboardScreen TextArea.long { height: 5; }
    OnboardScreen RadioSet { width: 100%; }
    OnboardScreen SelectionList { height: auto; max-height: 12; }
    OnboardScreen .switchrow { height: auto; }
    OnboardScreen .yn { padding: 1 1; }
    OnboardScreen .handlerow { height: auto; }
    OnboardScreen .handlerow Input { width: 1fr; max-width: 44; }
    OnboardScreen .handlerow .signup { margin-left: 2; min-width: 26; }
    OnboardScreen #nav { height: auto; dock: bottom; padding: 1 0 0 0; }
    OnboardScreen #nav Button { margin-right: 2; min-width: 22; }
    OnboardScreen #status { color: $text-muted; padding: 1 0 0 2; }
    OnboardScreen #review { height: 1fr; }
    """
    BINDINGS = [Binding("ctrl+q", "leave", "Quit"), Binding("escape", "leave", "Quit", show=False)]

    def __init__(self, answers: dict | None = None, preview: bool = False, on_done=None):
        super().__init__()
        self.answers = defaults_for(dict(answers or {}))
        self.touched: set[str] = set(answers or {})
        self.index = 0
        self.preview = preview            # tests: don't write files on Create
        self.on_done = on_done
        self.steps = STEPS + [REVIEW]

    def body(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="side"):
                yield Static("Set up your channel", id="tag")
                for key, label in self.steps:
                    yield Static(f"  {label}", classes="step", id=f"s-{key}")
            with Vertical(id="main"):
                yield Static("", id="title")
                yield Static("", id="blurb")
                yield VerticalScroll(id="fields")
                with Horizontal(id="nav"):
                    yield Button("Back", id="back")
                    yield Button("Next", variant="primary", id="next")
                    yield Static("", id="status")

    def on_mount(self) -> None:
        super().on_mount()
        self.call_after_refresh(self.show_step, 0)

    # ---------------------------------------------------------------- steps

    def step_questions(self, key: str) -> list[Q]:
        return [q for q in QUESTIONS if q.step == key]

    async def show_step(self, i: int) -> None:
        self.index = i
        key, label = self.steps[i]
        for n, (k, _) in enumerate(self.steps):
            s = self.query_one(f"#s-{k}", Static)
            s.set_class(n == i, "current")
            s.set_class(n < i, "done")
            s.update(("✓ " if n < i else "› " if n == i else "  ") + dict(self.steps)[k])
        self.query_one("#title", Static).update(f"{i + 1}/{len(self.steps)}  {label}")
        self.query_one("#blurb", Static).update(BLURBS.get(key, ""))
        box = self.query_one("#fields", VerticalScroll)
        await box.remove_children()
        if key == "review":
            await box.mount(Markdown(self.summary(), id="review"))
            self.query_one("#next", Button).label = "Create my studio"
        else:
            self.answers = defaults_for(self.answers)
            fields = [Field(q, self.answers.get(q.key), self.answers) for q in self.step_questions(key)]
            await box.mount_all([GmailOffer()] + fields if key == "accounts" else fields)
            self.refresh_visibility()
            self.query_one("#next", Button).label = "Next"
        self.query_one("#back", Button).disabled = i == 0
        self.query_one("#status", Static).update("")
        box.scroll_home(animate=False)
        first = next((w for w in box.query("Input, TextArea, RadioSet, SelectionList, Switch")
                      if not any(a.has_class("hidden") for a in w.ancestors)), None)  # not a platform you left out
        if first is not None:
            first.focus()

    def fields(self) -> list[Field]:
        return list(self.query(Field))

    def refresh_visibility(self) -> None:
        for f in self.fields():
            f.set_class(not f.q.visible(self.answers), "hidden")

    # ---------------------------------------------------------------- live updates

    @staticmethod
    def _same(a, b) -> bool:
        def norm(v):
            if isinstance(v, (list, tuple)):
                return "\n".join(str(x) for x in v)
            return "" if v is None else str(v)
        return norm(a).strip() == norm(b).strip()

    def _changed(self, widget) -> None:
        field = next((a for a in widget.ancestors_with_self if isinstance(a, Field)), None)
        if field is None:
            return
        key = field.q.key
        raw = field.raw()
        if self._same(raw, self.answers.get(key)):
            return                      # not a real change (mounting, or a value set by the app)
        self.answers[key] = raw
        self.touched.add(key)
        if isinstance(widget, Switch):
            self.query_one(f"#yn-{key}", Label).update("Yes" if widget.value else "No")
        if key == "format":
            # follow the new format's suggestions unless you already typed your own
            for dep in ("series", "twist", "hud", "default_tags"):
                if dep not in self.touched:
                    self.answers.pop(dep, None)
            self.answers = defaults_for(self.answers)
            for f in self.fields():
                if f.q.key in ("series", "twist") and f.q.key not in self.touched:
                    f.set_raw(self.answers.get(f.q.key))
                    self.touched.discard(f.q.key)
        field.error("")
        self.refresh_visibility()

    @on(Input.Changed)
    @on(TextArea.Changed)
    @on(RadioSet.Changed)
    @on(SelectionList.SelectedChanged)
    @on(Switch.Changed)
    def changed(self, event) -> None:
        if event.control is not None:
            self._changed(event.control)

    # ---------------------------------------------------------------- making accounts

    @on(Button.Pressed, "#gmail")
    def make_gmail(self) -> None:
        self.app.push_screen(SignupGuide(signup.GMAIL))

    @on(Button.Pressed, ".signup")
    def sign_up(self, event: Button.Pressed) -> None:
        """A platform's sign-up guide; the handle you type there goes into its box here."""
        key = event.button.id.removeprefix("signup-")
        field = self.query_one(f"#f-handle_{key}", Field)

        def got(handle: str | None) -> None:
            if handle is not None:
                self.query_one(f"#w-handle_{key}", Input).value = handle   # counts as typed: it's your answer
                field.error("")

        self.app.push_screen(SignupGuide(signup.GUIDES[key], field.raw() or ""), got)

    # ---------------------------------------------------------------- navigation

    def validate_step(self) -> bool:
        ok = True
        first_bad = None
        for f in self.fields():
            q = f.q
            if not q.visible(self.answers):
                continue
            raw = f.raw()
            if raw in (None, "") and not q.required and q.kind in ("number", "choice"):
                raw = q.default_for(self.answers)
            try:
                value = coerce(q, raw) if raw not in (None, "") or q.kind in ("yesno",) else raw
            except ValueError as e:
                f.error(str(e))
                ok, first_bad = False, first_bad or f
                continue
            if q.required and value in (None, "", []):
                f.error("Please answer this one.")
                ok, first_bad = False, first_bad or f
                continue
            if q.key == "length_custom":
                from .questions import parse_length
                try:
                    lo, hi = parse_length(value)
                    assert 5 <= lo <= hi <= 600
                except (ValueError, AssertionError):
                    f.error("Write it as min-max seconds, e.g. 20-30")
                    ok, first_bad = False, first_bad or f
                    continue
            self.answers[q.key] = value
            f.error("")
        if first_bad is not None:
            self.query_one("#fields", VerticalScroll).scroll_to_widget(first_bad, animate=False)
            self.query_one("#status", Static).update("Fix the highlighted answers to continue.")
        return ok

    @on(Button.Pressed, "#next")
    async def next_step(self) -> None:
        key = self.steps[self.index][0]
        if key == "review":
            await self.create()
            return
        if self.validate_step():
            await self.show_step(self.index + 1)

    @on(Button.Pressed, "#back")
    async def prev_step(self) -> None:
        if self.index > 0:
            if self.steps[self.index][0] != "review":
                for f in self.fields():       # keep what was typed, even if not valid yet
                    self.answers[f.q.key] = f.raw()
            await self.show_step(self.index - 1)

    def action_leave(self) -> None:
        def maybe(leave: bool | None):
            if leave:
                self.app.exit(None)
        self.app.push_screen(Quit(), maybe)

    # ---------------------------------------------------------------- review and create

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
        lines += ["", "Pressing **Create my studio** writes `CLAUDE.md` and `AGENTS.md` (your AI's instructions), "
                      "`my-studio/` (your settings and channel bible) and the dashboard's settings."]
        return "\n".join(lines)

    async def create(self) -> None:
        status = self.query_one("#status", Static)
        if self.preview:
            self._finish([])
            return
        try:
            written = generate.write_all(self.answers)
        except ValueError as e:
            status.update(str(e).splitlines()[0])
            box = self.query_one("#fields", VerticalScroll)
            await box.remove_children()
            await box.mount(Markdown(self.summary() + "\n\n```\n" + str(e) + "\n```", id="review"))
            return
        except Exception:
            status.update("Something went wrong writing your files (details below).")
            box = self.query_one("#fields", VerticalScroll)
            await box.mount(Static(traceback.format_exc(), classes="error"))
            return
        self._finish(written)

    def _finish(self, written: list) -> None:
        if self.on_done:
            self.on_done(self.answers, written)
        else:
            self.app.exit(written)


def saved_answers() -> dict | None:
    """The answers from the last onboarding (to start from), or None."""
    if not P.ANSWERS.exists():
        return None
    try:
        return {k: v for k, v in json.loads(P.ANSWERS.read_text(encoding="utf-8")).items()
                if k in BY_KEY or k.startswith("_")}
    except ValueError:
        return None


class Onboard(App):
    """The interview on its own (tests use it with preview=True): exits with the answers, or None if you left."""

    CSS = tui.CSS

    def __init__(self, answers: dict | None = None, preview: bool = False):
        super().__init__()
        self.start_answers, self.preview = answers, preview
        self.result: list | None = None

    def on_mount(self) -> None:
        self.register_theme(tui.THEME)
        self.theme = tui.THEME.name
        self.push_screen(OnboardScreen(self.start_answers, self.preview, on_done=self._done))

    def _done(self, answers: dict, written: list) -> None:
        self.result = written
        self.exit(answers)
