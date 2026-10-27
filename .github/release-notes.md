## What's new in 1.0.7

- **A Stats tab.** Your followers and likes added up across your platforms, over time.
  - Tick a platform to count it in the totals, or untick it to leave it out. Pick 24H, 48H, 7D, 30D or ALL.
  - Point at a chart for the totals at that moment and each platform's part. Yellow marks show when videos went up.
- **Delete a channel you added.** Click **Delete** beside it in the profile menu or on the Settings tab's **Profiles** panel.
  - You type its name first. Its folder moves into a backup in the ReelForge folder, so nothing is lost.
  - **Restore** puts it back as it was, and **Move to the Recycle Bin** (the Trash on a Mac) frees its space.
  - `reelforge profiles delete NAME` and `reelforge profiles restore` do the same from a terminal.
- **Put the tabs in your order.** On the Settings tab, drag a tab where you want it, or move it with the arrows.
  - The number keys and `reelforge 1` to `reelforge 8` follow your order, in every profile.
  - Updates and Settings now start at the far left. **Reset to default** puts them back there.
- **An FAQ on the Settings tab.** Click a question for its answer.
  - The first says which model your AI uses and how hard it thinks: your AI app decides that, and the answer says how to change it.
- **Sort the Compare tab's episodes.** Newest first, oldest first, or by most views on every platform added up.
- **Fixes.** **Open profile** works again, and X's **Connect** answers while pop-ups are up.

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
3. Type `reelforge publish` in a terminal (or open ReelForge's icon and go to **Publish**) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge updates`) installs this version in one click.

See the README for the full guide.
