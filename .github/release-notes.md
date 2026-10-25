## What's new in 1.0.5

- **Macs and Linux PCs get the full ReelForge.** They're no longer experimental: everything ReelForge does on
  Windows, it now does on a Mac (Apple Silicon or Intel) and on Linux, and every change is tested on all three before
  it ships.
  - **One-line install:** paste `curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh | bash`
    into Terminal. It downloads straight from GitHub, so macOS doesn't stop it.
  - **Nothing to install first.** Setup now downloads ffmpeg on a Mac and on Linux too, and a private Python inside
    the ReelForge folder when yours is older than 3.11, so you don't need Homebrew or a package manager.
  - **ReelForge's icon:** in your Applications folder on a Mac (Launchpad, Spotlight and the Dock), in your app menu
    on Linux.
  - **Stats with the browser you have:** Chrome or Edge, or a Chromium setup downloads if you have neither (it used
    to need Microsoft Edge).
  - **Publish works all the way:** the copy buttons fill the clipboard, the video shows in Finder or your file
    manager, and Remove moves it to the Trash.
  - **The hourly stats job** is a launchd agent on a Mac and a systemd timer on Linux (or a cron job without systemd).
  - **Fixed:** an update on a Mac could leave ReelForge's launchers unable to run, and setup's colours were wrong in
    macOS's Terminal before macOS 26.
- **Only the platforms you use.** Onboarding asks where you post, with TikTok, YouTube Shorts and Instagram Reels
  ticked to start, and helps you make any account you don't have yet, starting with a new Gmail for your channel.
  ReelForge then shows only the platforms you've connected, with no empty cards, charts or buttons for the others,
  and the Accounts tab connects or disconnects one any time.
- **Views 12h.** The Videos tab and Top performers show each video's views 12 hours after it went up, so a video from
  this morning and one from last week compare fairly (until then it says when the number comes in). Export CSV has
  them too, between the 6 and 24 hour columns.
- **Delete notifications.** Each notification has a big × on its right that deletes it, and **Clear all** deletes
  every one.
- **A bigger bell** in the window's top-right corner, well away from Quit.
- **Every open ReelForge window shows the same stats.** Windows (and the hourly job) take turns reading, and each
  shows what any of them read, with its notifications.
- **Fixed:** hashtags typed together (`#fyp#whatif`) no longer stay in the caption, a custom video length can be
  written as a range like 20-30 seconds, and a review that says "not approved" no longer counts as an approval.

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
the ReelForge folder once you say yes, then starts the onboarding interview. You'll need Claude Code (a paid Claude
plan or an API account) or Codex, a Mac with Apple Silicon or a PC with a recent NVIDIA or AMD graphics card (an Intel
Mac works too, more slowly), and about 15 GB of free disk space. `SHA256SUMS.txt` lists every download's checksum.

## Then

1. Open the ReelForge folder in Claude Code (the Claude desktop app's **Code** tab, then **Open folder…**), or run
   `codex` in it.
2. Say **"make my first video"** (with Claude's ultracode: "ultracode: make my first video").
3. Type `reelforge 4` in a terminal (or open ReelForge's icon and go to **Publish**, tab 4) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge 6`) installs this version in one click.

See the README for the full guide.
