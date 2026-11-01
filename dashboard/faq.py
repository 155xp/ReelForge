"""The Settings tab's FAQ: the questions people ask about ReelForge, each with its answer in a little Markdown (**bold**,
`code` and "- " lists, drawn by ui/src/ui/Panels.tsx's Markdown). The answers fit the channel the window is on: the
AI it was set up with, where its videos are, what your computer calls its file browser.

The first answer is the honest one about your AI's model and how hard it thinks: your AI app decides both. First-time
setup only asks Claude Code for a start (studio/generate.py write_claude_settings), which ReelForge never changes,
so the window has no setting for it.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import desktop


def md(text: str) -> str:
    """Text from elsewhere (a channel's name) as Markdown that shows it as it is."""
    return "".join("\\" + ch if ch in "\\`*_[]" else ch for ch in text)


def folder(path: Path, root: Path) -> str:
    """A folder as an answer names it: from the ReelForge folder when it's in there (`episodes`), else in full."""
    try:
        rel = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return f"`{path}`"
    return f"`{os.sep.join(rel.parts) or path.name}`"


def model_answer(assistant: list[str]) -> str:
    """Which model your AI uses and how hard it thinks: up to your AI app, never ReelForge. assistant: the AIs the
    channel was set up with (claude, codex or both), or none while it isn't set up (then both)."""
    claude, codex = not assistant or "claude" in assistant, not assistant or "codex" in assistant
    lead = "Your AI app decides that, not ReelForge."
    blocks = []
    if claude:
        blocks += [
            f"{lead} First-time setup asks Claude Code for **Opus at high effort** in the ReelForge folder (in "
            "`.claude/settings.local.json`) and never changes it after that. Claude Code started in a terminal in that "
            "folder begins that way, but ReelForge can't control it everywhere:",
            "- The Claude desktop app uses the model and effort you pick under its prompt box.\n"
            "- A session that's already open keeps the ones it started with.\n"
            "- Your plan and its usage limits decide which models you can use.",
            "Type `/model` or `/effort` in Claude Code to see or change them.",
        ]
    if codex:
        said = ("ReelForge's `.codex/config.toml` asks Codex for high reasoning in the ReelForge folder once you trust "
                "it as a project. `/model` in Codex picks the model and how hard it reasons, and your plan decides "
                "which models you can use.")
        blocks.append(f"With Codex: {said}" if claude else f"{lead} {said}")
    blocks.append("More effort means your AI thinks longer before it acts: often a better video, but slower, and it "
                  "uses more of your plan.")
    return "\n\n".join(blocks)


def items(*, assistant: list[str], root: Path, episodes: Path, completed: Path, channel: str, main: bool,
          several: bool, refresh_minutes: float, demo: bool = False) -> list[dict]:
    """The questions and their answers ({"q": ..., "a": Markdown}), for the channel the window is on. assistant: the
    AIs it was set up with (claude, codex or both; none while it isn't set up). root: the ReelForge folder. channel: its name;
    main: it's the first channel (the ReelForge folder's own); several: there are others. In the demo, nothing on
    this computer is named."""
    claude, codex = not assistant or "claude" in assistant, not assistant or "codex" in assistant
    if demo:
        here = "`C:\\Users\\you\\ReelForge`" if desktop.WINDOWS else "`~/ReelForge`"
        episodes_at, completed_at, own = "`episodes`", "`completed videos`", here
    else:
        here, episodes_at, completed_at = f"`{root}`", folder(episodes, root), folder(completed, root)
        try:
            from studio import move

            own = f"`{move.home()}`"
        except ImportError:   # the dashboard run on its own, outside a ReelForge folder
            own = "`C:\\Users\\<you>\\ReelForge`" if desktop.WINDOWS else "`~/ReelForge`"
    name = md(channel)
    # Your AI starts on a channel from the prompt that Copy prompt for your AI copies (studio/ai_prompt.py): it names
    # the ReelForge folder, so nothing is dragged in or opened first. A channel not set up yet has no prompt yet.
    app = ", ".join(label for label, on in (
        ("Claude Code (the **Code** tab in the Claude desktop app, or `claude` in a terminal)", claude),
        ("Codex (`codex` in a terminal)", codex)) if on)
    video = "your next video" if main else f"the next {name} video"
    start = (f"Press **Copy prompt for your AI** on this tab, under the channel's answers, and paste it into {app} or "
             "any other AI that can work with files on this computer. It names the ReelForge folder "
             f"({here}), so there's nothing to drag in or open first, and asks your AI for {video} (the first one, on "
             "a new channel)." if assistant else
             "Set this channel up first (**Set it up** on this tab). First-time setup's last screen gives you the "
             "prompt for your AI, with a button that copies it, and **Copy prompt for your AI** on this tab copies it "
             "again any time.")
    notes = ("Start it with the prompt from **Copy prompt for your AI** on this tab: it tells your AI where the "
             f"ReelForge folder is ({here}) and to read its notes there (`CLAUDE.md` for Claude, `AGENTS.md` for any "
             "other AI)." if assistant else
             "Set this channel up first (**Set it up** on this tab): first-time setup writes your AI's notes about it "
             "(`CLAUDE.md` for Claude, `AGENTS.md` for any other AI).")
    plan = ("your own Claude Code plan" if not codex else "your own Codex plan" if not claude else
            "your own Claude Code or Codex plan")
    minutes = round(refresh_minutes)
    open_now = (f"While ReelForge is open, it reads them every {minutes} minutes, and **r** reads them now."
                if minutes else "While ReelForge is open, **r** reads them.")
    return [
        {"q": "Which model does my AI use, and how hard does it think?", "a": model_answer(assistant)},
        {"q": "How do I make a video?",
         "a": start + "\n\nAfter that, **make today's videos** makes the next ones"
              + (" for every channel that posts regularly" if several else "")
              + ". Each finished video waits on **Publish**."},
        {"q": "My AI doesn't know about my channel.",
         "a": notes + " First-time setup only asks a few questions, so give it the full picture too: describe "
              f"{'your channel' if main else name} in the chat, or give it the path of a file about it (your notes, "
              "a doc, examples you like). It keeps your words as the channel's brief and plans every video from it."},
        {"q": "Does ReelForge post for me?",
         "a": "No. ReelForge never posts, uploads or sends anything. Finished videos wait on **Publish**: each "
              "platform's button opens its upload page, copies exactly the text it needs and shows the video in "
              f"{desktop.FILES}, so you drag it in and press Post."},
        {"q": "Where are my videos?",
         "a": f"On **Publish**, and as files: every video has its own folder in {episodes_at}, and a copy of "
              f"each finished one goes to {completed_at}."},
        {"q": "Do my stats update while ReelForge is closed?",
         "a": "Yes, while **Background refresh** on this tab is on: once an hour, while your computer is on, it "
              f"reads your stats for about a minute, then stops. {open_now}"},
        {"q": "The bottom left says a platform's last refresh failed.",
         "a": "Its last read failed. Click it to open **Accounts**, where that platform says what went wrong. "
              "Instagram and X sometimes need **Log in** again, and **Refresh now** tries once more."},
        {"q": "Can I run more than one channel?",
         "a": "Yes. Press **p** (or click your channel's name at the top left), then **New profile**. It asks a few "
              "questions about the new channel and helps you make its accounts, in a private window of your browser "
              "so this channel stays logged in. Each channel has its own accounts, stats, notifications and videos, "
              "and your AI makes them all from the ReelForge folder. To stop running one you added, **Delete** it "
              "there (or under **Profiles** on this tab): it moves whole into a backup, and **Restore** brings it "
              "back."},
        {"q": "How do I update ReelForge?",
         "a": "**Updates** checks for a new version every few hours while ReelForge is open, and the bell tells "
              "you when one is out. **Update and restart** installs it, and your channel, videos, stats and settings "
              "stay as they are."},
        {"q": "Can I move the ReelForge folder?",
         "a": f"Yes. ReelForge belongs in a folder of its own, {own}: when it's somewhere else, **Move…** beside "
              "**ReelForge's folder** on this tab puts it there (or `reelforge move FOLDER` in a terminal, for another "
              "folder on the same drive). Everything in it goes along, and the reelforge command, the icon and "
              "Background refresh follow it. Moved it by hand? Run `reelforge setup` in its new place."},
        {"q": "Something isn't working.",
         "a": "Try **Restart** on this tab first: ReelForge closes and opens again. If that doesn't fix it, run "
              "`reelforge doctor` in a terminal: it checks everything ReelForge needs and says how to fix anything "
              "that fails. `reelforge setup` repairs the setup."},
        {"q": "Does ReelForge cost anything?",
         "a": f"No: ReelForge is free and open source. Making videos uses {plan}, and more effort uses more of it."},
    ]
