"""The prompt that starts your AI on a channel. First-time setup's last screen shows it with a Copy button (after
setup is run again on a channel, the update prompt: its notes are new), and Copy prompt for your AI on ReelForge's
Settings tab copies it again. It names the ReelForge folder in full, so nothing has to be dragged into the chat or
opened first, and it works in any AI that can work with files on your computer: first-time setup writes the same notes
twice, as CLAUDE.md (Claude reads it) and AGENTS.md (Codex and most other AIs read it).
"""

from __future__ import annotations

from . import paths as P
from . import profiles


def text(name: str, profile: profiles.Profile | None = None, first: bool = True) -> str:
    """The prompt for the channel called `name`. profile: the channel's (another channel's notes are in its own folder
    too); the first one's by default. first: it has no video yet, so the prompt asks for its first one, else its
    next."""
    extra = profile is not None and not profile.main
    video = f"{'first' if first else 'next'} {name + ' ' if extra else ''}video"
    own = f" {name} has its own notes too, the same two files in {profile.describe()}." if extra else ""
    return (f"I make videos for my channel, {name}, with ReelForge. My ReelForge folder is:\n{P.ROOT}\n\n"
            "Work in that folder from now on. First read the notes it has for you, and follow them: CLAUDE.md if "
            f"you're Claude, AGENTS.md if you're another AI.{own} Then make my {video}.")


def update(name: str, profile: profiles.Profile | None = None) -> str:
    """The prompt after setup is run again on a channel that was set up already: its notes are rewritten with the new
    answers, so the AI reads them again and says what changed (rather than starting on the channel from scratch)."""
    extra = profile is not None and not profile.main
    own = f" {name}'s own notes are the same two files in {profile.describe()}." if extra else ""
    return (f"I make videos for my channel, {name}, with ReelForge, and I've just changed its answers in ReelForge's "
            f"setup. My ReelForge folder is:\n{P.ROOT}\n\n"
            "Work in that folder. The notes it has for you are updated, so read them again now and follow them from "
            f"now on, in place of what you read before: CLAUDE.md if you're Claude, AGENTS.md if you're another AI.{own} "
            "Then tell me in a few lines what changed, and use it from my next video on.")


def has_videos(profile: profiles.Profile) -> bool:
    """Whether a channel has a finished video yet (one its Publish tab lists), so the prompt asks for its next video
    rather than its first. Only the channel this process works on can tell; any other is one being made, with none."""
    if profile.key != profiles.current().key:
        return False
    try:
        from dashboard import config, videos

        return bool(videos.find(config.load_config()))
    except Exception:  # no dashboard settings to go by: as for a new channel
        return False
