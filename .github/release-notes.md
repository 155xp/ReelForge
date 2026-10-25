## What's new in 1.0.3

- **A setup that stops part way repairs itself.** If setup's window was closed (or Ctrl+C was pressed) while it was
  making ReelForge's Python environment, every later open crashed with "No module named 'rich'", and running setup
  again didn't help. Now ReelForge notices, makes that environment again and carries on with setup.
- **The one-line install works with a short user folder name** (such as `C:\Users\JOHNSM~1`), which used to stop it
  before setup.

Already have ReelForge? Open **Updates** (`reelforge 6`) and click **Update and restart**.

---

ReelForge lets Claude Code or Codex make faceless short videos for TikTok, YouTube Shorts, Instagram Reels and X,
then shows you how each one does once you've posted it. Nothing is ever posted for you.

## Download

| Your computer | Download | Then |
|---|---|---|
| **Windows 10 / 11** | `install.ps1` | Open PowerShell, paste `irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 \| iex` and press Enter. It downloads ReelForge straight from GitHub into your user folder, checks it and starts setup, so neither the browser nor Windows warns about it. |
| Windows, installer | `ReelForge-…-Windows-Setup.exe` | Run it (if Windows says "Windows protected your PC", click **More info**, then **Run anyway**: the installer isn't code-signed). It installs into your user folder, adds the `reelforge` command and a desktop icon, and starts setup. |
| Windows, no installer | `ReelForge-…-Windows.zip` | Unzip it to a short path (e.g. `C:\Users\you\ReelForge`) and double-click `setup.bat`. |
| macOS (experimental) | `ReelForge-…-macOS.zip` | Unzip it, right-click `Set up ReelForge.command`, choose **Open**. Needs Python 3.11+ and ffmpeg (`brew install python@3.13 ffmpeg`). |
| Linux (experimental) | `ReelForge-…-Linux.tar.gz` | Extract it and run `./setup.sh`. Needs Python 3.11+ and ffmpeg. |
| Developers | Source code (zip / tar.gz) | Same files; run `setup.bat` or `./setup.sh`. |

Setup shows what ReelForge still needs (Blender 4.5 LTS, ffmpeg on Windows, the sound effects, the `reelforge`
command), sets it all up inside the ReelForge folder once you say yes, then starts the onboarding interview.
You'll need Claude Code (a paid Claude plan or an API account) or Codex, a recent NVIDIA or AMD graphics card, and
about 15 GB of free disk space. `SHA256SUMS.txt` lists every download's checksum.

## Then

1. Open the ReelForge folder in Claude Code (the Claude desktop app's **Code** tab, then **Open folder…**), or run
   `codex` in it.
2. Say **"make my first video"** (with Claude's ultracode: "ultracode: make my first video").
3. Type `reelforge 4` in a terminal (or double-click the ReelForge icon and go to **Publish**, tab 4) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge 6`) installs this version in one click.

See the README for the full guide.
