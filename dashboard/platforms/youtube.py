"""YouTube: stats from the public channel page and its video feed, no login."""

from __future__ import annotations

from . import public
from .base import Account, Platform, Post


class YouTube(Platform):
    key = "youtube"
    name = "YouTube"
    color = "#ff4040"
    public_stats = True
    setup_note = ("Stats come from your public channel page and feed, read in the background about once an hour (every "
                  "30 minutes while ReelForge is open): subscribers (once YouTube shows the count), plus views and "
                  "likes of your latest 15 videos. No login needed.")

    def fetch(self) -> tuple[Account, list[Post]]:
        return public.youtube(self.public_handle)
