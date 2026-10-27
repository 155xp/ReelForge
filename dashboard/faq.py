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


def model_answer(assistant: str) -> str:
    """Which model your AI uses and how hard it thinks: up to your AI app, never ReelForge. assistant: claude, codex,
    both, or "" while the channel isn't set up (then both)."""
    claude, codex = assistant in ("claude", "both", ""), assistant in ("codex", "both", "")
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


def items(*, assistant: str, root: Path, episodes: Path, completed: Path, channel: str, main: bool,
          several: bool, refresh_minutes: float, demo: bool = False) -> list[dict]:
    """The questions and their answers ({"q": ..., "a": Markdown}), for the channel the window is on. root: the
    ReelForge folder. channel: its name; main: it's the first channel (the ReelForge folder's own); several: there
    are others. In the demo, nothing on this computer is named."""
    claude, codex = assistant in ("claude", "both", ""), assistant in ("codex", "both", "")
    if demo:
        here = "`C:\\Users\\you\\ReelForge`" if desktop.WINDOWS else "`~/ReelForge`"
        episodes_at, completed_at = "`episodes`", "`completed videos`"
    else:
        here, episodes_at, completed_at = f"`{root}`", folder(episodes, root), folder(completed, root)
    name = md(channel)
    first = "make my first video" if main else f"make my first {name} video"
    brief = "here's my channel" if main else f"here's {name}"
    open_it = []
    if claude:
        open_it.append(f"In the Claude desktop app, go to **Code**, click **Open folder…** and pick {here} (or run "
                       "`claude` in a terminal there).")
    if codex:
        open_it.append(f"For Codex, run `codex` in a terminal in {here}." if claude else
                       f"Run `codex` in a terminal in {here}.")
    notes = "`CLAUDE.md`" if not codex else "`AGENTS.md`" if not claude else "`CLAUDE.md` (or `AGENTS.md` for Codex)"
    plan = ("your own Claude Code plan" if not codex else "your own Codex plan" if not claude else
            "your own Claude Code or Codex plan")
    minutes = round(refresh_minutes)
    open_now = (f"While ReelForge is open, it reads them every {minutes} minutes, and **r** reads them now."
                if minutes else "While ReelForge is open, **r** reads them.")
    return [
        {"q": "Which model does my AI use, and how hard does it think?", "a": model_answer(assistant)},
        {"q": "How do I make a video?",
         "a": "Open the ReelForge folder in your AI. " + " ".join(open_it) + "\n\n"
              f"Then say **{first}**. After that, **make today's videos** makes the next ones"
              + (" for every channel that posts regularly" if several else "")
              + ". Each finished video waits on **Publish** (tab 4)."},
        {"q": "My AI doesn't know about my channel.",
         "a": f"Make sure you opened the ReelForge folder itself ({here}), not the folder it's in: your AI reads its "
              f"notes, {notes}, from there. First-time setup only asks a few questions, so give it the full picture "
              f"too: drag a file about your channel into the chat (or paste a description) and say **{brief}**. It "
              "keeps your words as the channel's brief and plans every video from it."},
        {"q": "Does ReelForge post for me?",
         "a": "No. ReelForge never posts, uploads or sends anything. Finished videos wait on **Publish** (tab 4): each "
              "platform's button opens its upload page, copies exactly the text it needs and shows the video in "
              f"{desktop.FILES}, so you drag it in and press Post."},
        {"q": "Where are my videos?",
         "a": f"On **Publish** (tab 4), and as files: every video has its own folder in {episodes_at}, and a copy of "
              f"each finished one goes to {completed_at}."},
        {"q": "Do my stats update while ReelForge is closed?",
         "a": "Yes, while the **Hourly stats read** on this tab is on: once an hour, while your computer is on, it "
              f"reads your stats for about a minute, then stops. {open_now}"},
        {"q": "A platform is red in the bar along the bottom.",
         "a": "Its last read failed. Click it to open **Accounts**, where that platform says what went wrong. "
              "Instagram and X sometimes need **Log in** again, and **Refresh now** tries once more."},
        {"q": "Can I run more than one channel?",
         "a": "Yes. Press **p** (or click your channel's name at the top left), then **New profile**. It asks a few "
              "questions about the new channel and helps you make its accounts, in a private window of your browser "
              "so this channel stays logged in. Each channel has its own accounts, stats, notifications and videos, "
              "and your AI makes them all from the ReelForge folder."},
        {"q": "How do I update ReelForge?",
         "a": "**Updates** (tab 6) checks for a new version every few hours while ReelForge is open, and the bell tells "
              "you when one is out. **Update and restart** installs it, and your channel, videos, stats and settings "
              "stay as they are."},
        {"q": "Something isn't working.",
         "a": "Run `reelforge doctor` in a terminal: it checks everything ReelForge needs and says how to fix anything "
              "that fails. `reelforge setup` repairs the setup."},
        {"q": "Does ReelForge cost anything?",
         "a": f"No: ReelForge is free and open source. Making videos uses {plan}, and more effort uses more of it."},
    ]
