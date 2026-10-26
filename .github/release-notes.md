## What's new in 1.0.6

- **Run more than one channel.** Each channel is a profile with its own accounts, stats, notifications and videos.
  - Switch with the channel button at the top left, or press **p**. A red dot means another one has news.
  - **New profile** asks a few questions about the channel, then opens its Accounts tab.
  - Your first channel stays exactly where it is.
- **Your AI knows every channel.** Each one gets its own folder with its own notes, and videos follow their
  channel's rules. "Make today's videos" makes every channel's, except one set to post **Only when I ask**.
- **Tell your AI about your channel.** Drag a file about it into the chat (or paste a description) and say
  "here's my channel". Your AI keeps it as the channel's brief and plans every video from it.
- **Tidier What's new.** This panel now shows release notes as clean, short lists at any window size.
- **A shorter first-time setup.** It no longer asks how hard your AI should work: High is the standard. For more
  or less, the profile menu has **Advanced settings**: Max, High and Fast. `reelforge channel` changes your
  channel's answers.
- **The setup box fits any window.** It stays whole in a small window or one you resize, and the hints on its bottom
  edge are gone.

Already have ReelForge? Open **Updates** (`reelforge 6`) and click **Update and restart**.

---

ReelForge lets Claude Code or Codex make faceless short videos for TikTok, YouTube Shorts, Instagram Reels and X,
then shows you how each one does once you've posted it. Nothing is ever posted for you.

## Download

| Your computer | Download | Then |
|---|---|---|
| **Windows 10 / 11** | `install.ps1` | Open PowerShell, paste `irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 \| iex` and press Enter. It downloads ReelForge straight from GitHub into your user folder, checks it and starts setup, so neither the browser nor Windows warns about it. |
| **Mac or Linux** | `install.sh` | Open Terminal, paste `curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh \| bash` and press Enter. It downloads ReelForge straight from GitHub into `~/ReelForge`, checks it and starts setup, so neither the browser nor macOS warns about it. |
| Windows, installer | `ReelForge-…-Windows-Setup.exe` | Run it (if Windows says "Windows protected your PC", click **More info**, then **Run anyway**: the installer isn't code-signed). It installs into your user folder, adds the `reelforge` command and a desktop icon, and starts setup. |
| Windows, no installer | `ReelForge-…-Windows.zip` | Unzip it to a short path (e.g. `C:\Users\you\ReelForge`) and double-click `setup.bat`. |
| Mac, no install line | `ReelForge-…-macOS.zip` | Unzip it and double-click `Set up ReelForge.command`. If macOS says it can't check the file, open **System Settings › Privacy & Security** and click **Open Anyway** (on macOS 14 and older, right-click the file and choose **Open**). |
| Linux, no install line | `ReelForge-…-Linux.tar.gz` | Extract it and run `./setup.sh`. |
| Developers | Source code (zip / tar.gz) | Same files; run `setup.bat` or `./setup.sh`. |

Setup shows what ReelForge still needs (Blender 4.5 LTS, ffmpeg, the sound effects, the `reelforge` command,
ReelForge's icon, and on a Mac or Linux PC a private Python or a Chromium if it hasn't got one), sets it all up inside
the ReelForge folder once you say yes, then asks a few questions about your channel. You'll need Claude Code (a
paid Claude plan or an API account) or Codex, a Mac with Apple Silicon or a PC with a recent NVIDIA or AMD graphics card (an Intel
Mac works too, more slowly), and about 15 GB of free disk space. `SHA256SUMS.txt` lists every download's checksum.

## Then

1. Open the ReelForge folder in Claude Code (the Claude desktop app's **Code** tab, then **Open folder…**), or run
   `codex` in it.
2. Say **"make my first video"**.
3. Type `reelforge 4` in a terminal (or open ReelForge's icon and go to **Publish**, tab 4) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge 6`) installs this version in one click.

See the README for the full guide.
