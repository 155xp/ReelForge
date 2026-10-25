"""Instagram: stats read from your profile in ReelForge's own browser, once you've logged in there."""

from __future__ import annotations

from . import browser
from .base import Account, Platform, PlatformError, Post


class Instagram(Platform):
    key = "instagram"
    name = "Instagram"
    color = "#b46cff"
    browser_stats = True
    setup_note = (f"Log in opens ReelForge's own {browser.NAME} window; log in there once and ReelForge reads your profile "
                  "in the background about once an hour: followers, plus each Reel's views, likes, comments and shares. "
                  "Your normal browser isn't touched.")

    def fetch(self) -> tuple[Account, list[Post]]:
        if not self.logged_in:
            raise PlatformError("Log in to Instagram once on the Accounts tab (5) so ReelForge can read your stats.",
                                needs_login=True)
        return browser.instagram(self.public_handle)
