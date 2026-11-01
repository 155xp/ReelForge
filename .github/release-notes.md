## What's new in 2.2.0

- **Which AI makes your videos is a tick list: Claude Code, Codex or both.** An earlier answer carries over (an old Both is both again).
  - With both, setup's last screen and the Settings tab name both, and the FAQ answers for both.
- **Copy the prompt is always on screen.** On setup's last screen it's the first button in the bottom row, even in a small window.
  - Run setup again and the prompt tells your AI what changed in your answers, so it uses them from the next video.
- **Open in Explorer** beside ReelForge's folder on the Settings tab (Finder on a Mac, the file manager on Linux).
- **The Publish tab's YouTube Copy caption** sits under YouTube's button and copies the title with #shorts.

## What's new in 2.1.1

- **Copy the prompt for your AI: nothing to drag in.** Setup's last screen shows it, with a **Copy the prompt** button.
  - It has your ReelForge folder's path in it. Paste it into Claude Code, Codex or any AI that works with your files.
  - Your AI gets to know your channel, then makes your first video.
  - **Copy prompt for your AI** on the Settings tab copies it again any time.
- **Claude Code or Codex: you pick which AI makes your videos.** Setup recommends neither, and Both is gone.
  - An earlier Both answer now counts as Claude Code. **Change your answers** on the Settings tab switches it.

## What's new in 2.1.0

- **ReelForge can move into a folder of its own.** The Settings tab says where it is, under On this computer.
  - Kept somewhere else, like the Desktop? **Move…** puts it where the install line does: your user folder's ReelForge.
  - Everything in it goes along in one step. The reelforge command, the icon and Background refresh follow it.
  - In a terminal it's `reelforge move`, or `reelforge move FOLDER` for another folder on the same drive.
- **The install line finds a ReelForge you already have** somewhere else, and points you to Move, not a second copy.
- **Uninstall puts Windows Terminal's ReelForge profile in the Recycle Bin** too, as it says it does.

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

1. Setup's last screen has the prompt for your AI: click **Copy the prompt** and paste it into Claude Code (the Claude
   desktop app's **Code** tab), Codex or any AI that can work with files on your computer. It has the ReelForge
   folder's path in it, so there's nothing to drag in or open first.
2. Your AI gets to know your channel, then makes your first video.
3. Type `reelforge publish` in a terminal (or open ReelForge's icon and click the green **Publish** button) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge updates`) installs this version in one click.

See the README for the full guide.
