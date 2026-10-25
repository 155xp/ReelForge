"""What every platform implements, plus the shared stats and post-text types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PlatformError(Exception):
    """A failure with a message fit to show in the UI. needs_login: the site logged ReelForge's browser out, so
    reading it again takes a new log-in on the Accounts tab."""

    def __init__(self, message: str = "", needs_login: bool = False):
        super().__init__(message)
        self.needs_login = needs_login


@dataclass
class Account:
    handle: str
    followers: int | None
    views: int | None = None  # None: ReelForge sums the views of the posts it can see
    likes: int | None = None
    posts: int | None = None


@dataclass
class Post:
    post_id: str
    title: str
    url: str | None
    published_at: str | int
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int | None = 0
    saves: int | None = None


@dataclass
class PublishItem:
    video: Path
    caption: str  # one line, e.g. "What if your coffee doubled every 2 seconds?"
    tags: str     # "#whatif #pov ...": up to 5 are used

    def text_for(self, platform: str) -> str:
        """The platform's post text (see videos.post_text); for YouTube, the description."""
        from ..videos import post_text

        return post_text(platform, self.caption, self.tags)

    @property
    def title(self) -> str:
        """The caption without hashtags: YouTube's title and the episode's name in ReelForge."""
        return self.text_for("x")[:100]


class Platform:
    key = ""
    name = ""
    color = "#ffffff"
    setup_note = ""  # where the stats come from, shown on the Accounts tab
    public_stats = False  # True: a handle in config.toml is enough for stats (no login)
    browser_stats = False  # True: logging in once in ReelForge's browser gives stats

    def __init__(self, cfg: dict):
        self.cfg = cfg

    @property
    def public_handle(self) -> str:
        """The handle from config.toml, without the @."""
        return str(self.cfg.get("handle", "")).strip().lstrip("@")

    @property
    def logged_in(self) -> bool:
        """Logged in once in ReelForge's browser (only platforms that read their stats that way)."""
        from . import browser

        return self.browser_stats and browser.logged_in(self.key)

    @property
    def stats_source(self) -> str | None:
        """Where stats come from: "browser" (logged in once in ReelForge's browser), "public" (just the handle), or
        None."""
        if not self.public_handle:
            return None
        if self.logged_in:
            return "browser"
        return "public" if self.public_stats else None

    @property
    def has_stats(self) -> bool:
        return self.stats_source is not None

    def connected(self, stored=frozenset()) -> bool:
        """Whether this platform is on in ReelForge: its card, charts and their keys, Videos filter, Compare chart,
        Publish buttons, best time and notifications. It is once you've added your handle on the Accounts tab and
        ReelForge can read it: straight away for TikTok and YouTube, after the one log-in for Instagram and X. Stats
        already stored for it (`stored`: the platforms with any) keep it on too, so a log-in that runs out, or stats
        typed in by hand, never hide its history."""
        return bool(self.public_handle) and (not self.browser_stats or self.logged_in or self.key in stored)

    @property
    def uses_browser(self) -> bool:
        """Whether a refresh opens ReelForge's background browser (slower, so it refreshes less often)."""
        from . import browser

        return self.stats_source == "browser" or (self.stats_source == "public" and self.key == "tiktok"
                                                  and browser.available())

    @property
    def handle(self) -> str:
        return "@" + self.public_handle if self.public_handle else ""

    def fetch(self) -> tuple[Account, list[Post]]:
        raise NotImplementedError


def first_line(text: str | None, limit: int = 200) -> str:
    return (text or "").strip().split("\n")[0][:limit]
