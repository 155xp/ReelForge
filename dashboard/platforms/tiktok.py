"""TikTok: stats from the public profile, no login; reading it in ReelForge's background browser adds per-video numbers."""

from __future__ import annotations

from . import browser, public
from .base import Account, Platform, Post


class TikTok(Platform):
    key = "tiktok"
    name = "TikTok"
    color = "#25f4ee"
    public_stats = True
    setup_note = ("Stats come from your public profile, read in the background about once an hour: followers and "
                  "total likes, plus each video's views, likes, comments, shares and saves. No login needed.")

    def fetch(self) -> tuple[Account, list[Post]]:
        if browser.available():
            try:
                return browser.tiktok(self.public_handle)  # per-video numbers too
            except Exception:
                pass  # a captcha, a timeout, a page that changed: the plain page still gives the totals
        return public.tiktok(self.public_handle)
