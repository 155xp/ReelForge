"""Making the accounts a channel needs, for creators starting from scratch, and reading the @handle they end up with.

Onboarding's "Your accounts" step and the ReelForge window's Accounts tab show these guides: a few steps, and a button
that opens the platform's own sign-up page in your usual browser. ReelForge never makes an account itself, fills in a
sign-up form or sees a password: you sign up on the site, then type your new @handle into ReelForge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Guide:
    key: str
    title: str          # the guide's heading
    why: str            # a line on what it's for
    url: str            # the official sign-up page
    button: str         # the button that opens it
    steps: tuple[str, ...]  # what to do there (the screens add "press the button" before and "type it here" after)

    @property
    def logs_in(self) -> bool:
        """Instagram and X also need one log-in in ReelForge's own browser before it can read your stats."""
        return self.key in ("instagram", "x")


GMAIL = Guide(
    "gmail", "Make a Gmail for your channel",
    "One Gmail just for your channel is your YouTube login, and TikTok, Instagram and X can sign up with the same "
    "email, so the whole channel lives on one address, apart from your personal accounts.",
    "https://accounts.google.com/signup", "Open Google sign-up",
    ("Name it after your channel, and pick an address to match, like nightphysics@gmail.com.",
     "Google may text your phone a code to check it's you. Keep the password somewhere safe.",
     "Then make your accounts with it: YouTube first, then the others."),
)

GUIDES = {
    "tiktok": Guide(
        "tiktok", "Make your TikTok account", "Sign up on TikTok with your channel's Gmail.",
        "https://www.tiktok.com/signup", "Open TikTok sign-up",
        ("Sign up with your channel's Gmail (Use phone or email), or Continue with Google.",
         "Pick a username that matches your channel: that's your @handle. You can change it later in Edit profile.")),
    "youtube": Guide(
        "youtube", "Make your YouTube channel", "Your channel's Gmail is all YouTube needs.",
        "https://www.youtube.com/create_channel", "Open YouTube",
        ("Sign in with your channel's Gmail.",
         "YouTube asks for a name and a handle for your channel: use your channel's name for both.")),
    "instagram": Guide(
        "instagram", "Make your Instagram account", "Sign up on Instagram with your channel's Gmail.",
        "https://www.instagram.com/accounts/emailsignup/", "Open Instagram sign-up",
        ("Sign up with your channel's Gmail.",
         "Pick a username that matches your channel: that's your @handle.")),
    "x": Guide(
        "x", "Make your X account", "Sign up on X with your channel's Gmail.",
        "https://x.com/i/flow/signup", "Open X sign-up",
        ("Sign up with your channel's Gmail, or Sign up with Google.",
         "Pick a username that matches your channel: that's your @handle.")),
}

# A profile's address, for a handle pasted as a link: tiktok.com/@name, youtube.com/@name, instagram.com/name,
# x.com/name (or twitter.com/name).
_LINK = re.compile(r"^(?:https?://)?(?:[\w-]+\.)*(?:tiktok|youtube|instagram|x|twitter)\.com/@?([^/?#\s]+)", re.I)
_HANDLE = re.compile(r"^[A-Za-z0-9._-]{1,30}$")
_NOT_PROFILES = {"channel", "c", "user", "watch", "shorts", "p", "reel", "reels", "video", "i", "home", "explore"}


def handle_from(text: str) -> str:
    """What you typed (@name, name, or your profile's link) -> "@name", or "" for nothing. Raises ValueError, with a
    message to show, for anything else (a link to a video, or to a YouTube channel by its ID, isn't a handle)."""
    text = (text or "").strip()
    if not text:
        return ""
    link = _LINK.match(text)
    if link:
        if link.group(1).lower() in _NOT_PROFILES:
            raise ValueError("That link isn't your profile: type your @handle instead, like @yourchannel.")
        text = link.group(1)
    name = text.lstrip("@").strip()
    if not _HANDLE.match(name):
        raise ValueError("That isn't a handle: use letters, numbers, dots, dashes and underscores, like "
                         "@yourchannel.")
    return "@" + name


def open_page(url: str) -> None:
    """A sign-up page in your usual browser (the tests put a stand-in here)."""
    import webbrowser

    webbrowser.open(url)
