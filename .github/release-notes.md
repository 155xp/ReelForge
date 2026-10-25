## What's new in 1.0.2

- **Install with one line, with no download warnings.** Paste the line below into PowerShell: it downloads ReelForge
  straight from GitHub, checks it and starts setup.
- **Notifications take you there.** Click one and ReelForge shows what it's about: the video on Videos, the finished
  video on Publish, the platform on Accounts.
- **A sharper anvil** in the top-left, however you open ReelForge.
- **Test copies stay out of the way.** A ReelForge folder with a `TEST-COPY.txt` in it says TEST, and never touches
  the `reelforge` command, the hourly stats job or the desktop shortcut.
- **A new README** with the demo videos, fresh screenshots and the steps after onboarding. The setup screens drop the
  line under the logo.

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
