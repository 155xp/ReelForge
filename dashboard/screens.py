"""Pop-up dialogs: type in stats, remove a video, fix which episode a post belongs to, and help."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Select, Static
from textual.widgets.option_list import Option

from .platforms import Platform
from .platforms.public import parse_count
from .widgets import GOOD, MUTED


class LogStats(ModalScreen[tuple | None]):
    """Type in numbers for platforms ReelForge can't read (Instagram and X before logging in).

    Dismisses with (platform key, followers or None, {episode id: views}).
    """

    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, platforms: list[Platform], start: str, episodes: list, last: dict[str, dict]):
        super().__init__()
        self.platforms = {p.key: p for p in platforms}
        self.start = start
        self.episodes = episodes  # newest first
        self.last = last  # platform -> {"followers": n, "views": {episode id: n}}

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("LOG STATS", classes="dialog-title")
            yield Select([(p.name, p.key) for p in self.platforms.values()], value=self.start, allow_blank=False,
                         id="ls-platform")
            yield Static(Text("Copy the numbers from the app. Blank fields are skipped; 1.2K and 3,400 both work. "
                              "Enter saves.", style=MUTED), id="ls-hint")
            with Horizontal(classes="ls-row"):
                yield Static(Text("Followers", style="bold"), classes="ls-label")
                yield Input(id="ls-followers", placeholder="followers")
            if self.episodes:
                yield Static(Text("VIEWS PER VIDEO", style=f"bold {MUTED}"), classes="ls-section")
            else:
                yield Static(Text("Videos show up here once you've uploaded them from the Publish tab.", style=MUTED))
            with VerticalScroll(id="ls-videos"):
                for e in self.episodes:
                    with Horizontal(classes="ls-row"):
                        yield Static(e["title"], classes="ls-label")
                        yield Input(id=f"ls-ep-{e['id']}", placeholder="views")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="save", variant="primary")

    def on_mount(self) -> None:
        self.fill(self.start)
        self.query_one("#ls-followers", Input).focus()

    def fill(self, key: str) -> None:
        last = self.last.get(key, {})
        followers = last.get("followers")
        self.query_one("#ls-followers", Input).value = "" if followers is None else str(followers)
        for e in self.episodes:
            views = last.get("views", {}).get(e["id"])
            self.query_one(f"#ls-ep-{e['id']}", Input).value = "" if views is None else str(views)

    @on(Select.Changed, "#ls-platform")
    def switch(self, event: Select.Changed) -> None:
        self.fill(event.value)

    @on(Input.Submitted)
    @on(Button.Pressed, "#save")
    def save(self) -> None:
        def number(input_id: str) -> int | None:
            text = self.query_one(input_id, Input).value.strip()
            if not text:
                return None
            n = parse_count(text)
            if not 0 <= n < 10 ** 12:  # nothing has a trillion views; anything bigger is a typo (or too big to store)
                raise ValueError(text)
            return n

        try:
            followers = number("#ls-followers")
            views = {e["id"]: v for e in self.episodes if (v := number(f"#ls-ep-{e['id']}")) is not None}
        except (ValueError, OverflowError):
            self.notify("Whole numbers only, please (like 1234, 3,400 or 1.2K).", severity="warning")
            return
        if followers is None and not views:
            self.notify("Nothing to save yet.", severity="warning")
            return
        self.dismiss((self.query_one("#ls-platform", Select).value, followers, views))

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


class VideoMenu(ModalScreen[str | None]):
    """What to do with a video in the Publish list: dismisses with "recycle", "hide" or None."""

    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, video: Path, from_pipeline: bool):
        super().__init__()
        self.video, self.from_pipeline = video, from_pipeline

    def compose(self) -> ComposeResult:
        note = Text()
        note.append(self.video.name, style="bold")
        note.append(f"\n{self.video.parent}\n\n", style=MUTED)
        note.append("Move to Recycle Bin", style="bold")
        note.append(" deletes the video file (you can restore it from the Recycle Bin).", style=MUTED)
        if self.from_pipeline:
            note.append(" The episode's spec and build files stay, so the pipeline can render it again.", style=MUTED)
        note.append("\nHide from list", style="bold")
        note.append(" keeps the file but takes it off this list (Show hidden brings it back).", style=MUTED)
        with Vertical(id="dialog"):
            yield Static("REMOVE VIDEO", classes="dialog-title")
            yield Static(note)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Hide from list", id="hide")
                yield Button("Move to Recycle Bin", id="recycle", variant="error")

    def on_mount(self) -> None:
        self.query_one("#cancel", Button).focus()

    @on(Button.Pressed)
    def choose(self, event: Button.Pressed) -> None:
        self.dismiss(None if event.button.id == "cancel" else event.button.id)


class EpisodePicker(ModalScreen[str | None]):
    """Which video a post is: dismisses with "ep-<id>", "none" (not an episode) or None (cancel)."""

    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    def __init__(self, post: dict, episodes: list, platform: Platform):
        super().__init__()
        self.post, self.episodes, self.platform = post, episodes, platform

    def compose(self) -> ComposeResult:
        note = Text()
        note.append(f"{self.platform.name}  ", style=f"bold {self.platform.color}")
        note.append(self.post["title"] or "(no caption)", style="bold")
        note.append("\nReelForge matches posts to videos by their caption. If it got this one wrong, pick the right "
                    "video; ReelForge keeps your choice from now on.", style=MUTED)
        options = [Option(Text("Not one of my videos", style=MUTED), id="none")]
        for e in self.episodes:
            label = Text(("✓ " if e["id"] == self.post["episode_id"] else "  "), style=GOOD)
            label.append(e["title"])
            options.append(Option(label, id=f"ep-{e['id']}"))
        with Vertical(id="dialog"):
            yield Static("WHICH VIDEO IS THIS?", classes="dialog-title")
            yield Static(note)
            yield OptionList(*options, id="episode-choices")
            with Horizontal(classes="dialog-buttons"):
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        choices = self.query_one("#episode-choices", OptionList)
        choices.focus()
        current = f"ep-{self.post['episode_id']}" if self.post["episode_id"] else None
        for i in range(choices.option_count):
            if choices.get_option_at_index(i).id == current:
                choices.highlighted = i

    @on(OptionList.OptionSelected, "#episode-choices")
    def chosen(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_id)

    @on(Button.Pressed, "#cancel")
    def cancel(self) -> None:
        self.dismiss(None)


HELP = [
    ("Overview (1)", "Totals for every platform, then views, followers and likes gained per hour (or per 6 hours / "
                     "per day on the longer ranges), stacked by platform. Yellow marks show when each video went up. "
                     "Point at a bar to see that hour's numbers by platform; click a platform in the key to hide it. "
                     "Under the cards: today's badges, like \"Today: top 10% of your days for new TikTok "
                     "followers\"."),
    ("Videos (2)", "Every video on every platform. Show picks a platform, a header sorts, and clicking a highlighted "
                   "row (or Open post) opens it. Above the chart: the highlighted video's badges, like \"Top 5% of "
                   "your TikTok videos for views\". The chart compares its views with your typical video at the same "
                   "age. Fix episode re-files a post grouped with the wrong video; Export CSV saves every video as a "
                   "spreadsheet, with when it went up (date, weekday, hour and UTC time) and its views 1, 6 and 24 "
                   "hours in."),
    ("Compare (3)", "The platform scoreboard, or pick an episode to see the same video on every platform, each "
                    "against that platform's typical video."),
    ("Publish (4)", "Pick a video, check the caption, then open each upload page: ReelForge copies the right text, "
                    "shows the file in Explorer, and checks for the new post 10 and 30 minutes later. Remove (or a "
                    "right-click) hides a video or moves it to the Recycle Bin; Show hidden brings hidden ones back. "
                    "Under the videos, Best time to post shows each platform's part of the day whose videos got the "
                    "most views in their first day, and when it next comes round; it needs 2 videos a day old in "
                    "each of 2 parts of the day, with one clearly ahead."),
    ("Accounts (5)", "Where each platform's stats come from, when they were last read, and the Instagram / X log-in. "
                     "Type in stats lets you enter the numbers by hand for a platform ReelForge can't read yet."),
    ("Updates (6)", "Your version, what's new in the next one, and Update and restart: one click downloads it, puts "
                    "it in place (your channel, videos and stats stay as they are) and opens ReelForge again."),
    ("Notifications", "The bell at the top right opens the drawer: updates, milestones, badges, finished videos and "
                      "log-ins that need you. A red dot on the bell means something's unread; click one to go "
                      "to it, or the × at its right to delete it (Delete deletes the highlighted one), and Clear "
                      "all deletes them all. The hourly background job (reelforge stats on) adds them while "
                      "ReelForge is closed."),
    ("Badges", "Badges only ever compare you with yourself, from the numbers ReelForge has stored. Percentages need "
               "at least 10 videos or days to compare, and ties count against you, so a badge is always true."),
]
KEYS = [("1-6", "switch tabs"), ("r / R", "refresh / force refresh")]


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss(None)", "Close")]

    def compose(self) -> ComposeResult:
        body = Text()
        for tab, text in HELP:
            body.append(f"{tab}\n", style=f"bold {GOOD}")
            body.append(text + "\n\n")
        body.append("Keys\n", style=f"bold {GOOD}")
        for key, what in KEYS:
            body.append(f"  {key:<8}", style="bold")
            body.append(what + "\n", style=MUTED)
        body.append("Everything else is a button on the page it applies to.", style=MUTED)
        with Vertical(id="dialog"):
            yield Static("HOW REELFORGE WORKS", classes="dialog-title")
            with VerticalScroll(id="help-body"):
                yield Static(body)
            with Horizontal(classes="dialog-buttons"):
                yield Button("Close", id="close", variant="primary")

    def on_mount(self) -> None:
        self.query_one("#close", Button).focus()

    @on(Button.Pressed, "#close")
    def close(self) -> None:
        self.dismiss(None)
