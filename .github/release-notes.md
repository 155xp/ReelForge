## What's new in 1.0.9

- **Publish is a green button at the top right.** It's no longer a tab: click it from any tab, or press **u**.
  - It turns solid green while you're on Publish, and `reelforge publish` still opens it.
  - The other seven tabs keep your order: **1**-**7** and `reelforge 1` to `reelforge 7` open them.
- **When your stats were last read is under ↻ Refresh** at the top, in amber while they're being read.
  - The bar along the bottom no longer lists your platforms: it names one only when its last refresh failed.
  - Click it for the Accounts tab, which says why.
- **Gaps in the charts are filled in.** The hours your computer was off are estimated and drawn hatched.
  - That's on the Overview, the Stats tab and the Accounts tab's charts. Pointing at one says it's estimated.
  - An estimate is never your best day, hour or bar, and badges still count only what was read.
- **A views chart on the Stats tab** above followers and likes: your views added up across your platforms, with its own breakdown.

## What's new in 1.0.8

- **Your stats come first** in the tabs' default order, and **Reset to default** on the Settings tab puts them back in it.
- **The badges' pop-up shows whole.** Pointing at the badges on the Overview or Videos tab no longer leaves a stray box under them.

Already have ReelForge? Open the **Updates** tab and click **Update and restart**.

---

ReelForge lets Claude Code or Codex make faceless short videos for TikTok, YouTube Shorts, Instagram Reels and X,
then shows you how each one does once you've posted it. Nothing is ever posted for you.

## Install

- **Windows 10 / 11:** open PowerShell, paste `irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 | iex` and press Enter.
- **Mac or Linux:** open Terminal, paste `curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh | bash` and press Enter.

It downloads ReelForge straight from GitHub into a ReelForge folder in your user folder, checks it against `SHA256SUMS.txt` and starts setup, so neither your browser nor your computer warns about it. The other files below are what it downloads.

Installed ReelForge with the old Setup.exe? Its Updates tab can't install this version, so paste the Windows line into PowerShell instead: it finds that ReelForge and updates it in place, keeping your channel, videos, stats, logins and settings.

Setup shows what ReelForge still needs (Blender 4.5 LTS, ffmpeg, the sound effects, the `reelforge` command,
ReelForge's icon, and on a Mac or Linux PC a private Python or a Chromium if it hasn't got one), sets it all up inside
the ReelForge folder once you say yes, then asks a few questions about your channel. You'll need Claude Code (a
paid Claude plan or an API account) or Codex, a Mac with Apple Silicon or a PC with a recent NVIDIA or AMD graphics card (an Intel
Mac works too, more slowly), and about 15 GB of free disk space.

## Then

1. Open the ReelForge folder in Claude Code (the Claude desktop app's **Code** tab, then **Open folder…**), or run
   `codex` in it.
2. Say **"make my first video"**.
3. Type `reelforge publish` in a terminal (or open ReelForge's icon and click the green **Publish** button) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge updates`) installs this version in one click.

See the README for the full guide.
