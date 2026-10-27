"""X: stats read from your profile in ReelForge's own browser, once you've logged in there."""

from __future__ import annotations

from . import browser
from .base import Account, Platform, PlatformError, Post


class X(Platform):
    key = "x"
    name = "X"
    color = "#e7e9ea"
    browser_stats = True
    setup_note = (f"Log in opens ReelForge's own {browser.NAME} window; log in there once and ReelForge reads your profile "
                  "in the background about once an hour: followers, plus each video post's views, likes, replies, "
                  "reposts and bookmarks. Your normal browser isn't touched.")

    def fetch(self) -> tuple[Account, list[Post]]:
        if not self.logged_in:
            raise PlatformError("Log in to X once on the Accounts tab so ReelForge can read your stats.",
                                needs_login=True)
        return browser.x(self.public_handle)
