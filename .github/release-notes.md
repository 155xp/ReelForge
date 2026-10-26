## What's new in 1.0.6

- **Run more than one channel.** Each channel is a profile with its own accounts, stats, notifications and videos.
  - Switch with the channel button at the top left, or press **p**. A red dot means another one has news.
  - **New profile** asks a few questions about the channel, then opens its Accounts tab.
  - Your first channel stays exactly where it is.
- **Sign up without logging out.** New profile helps you make the channel's accounts, starting with a Gmail.
  Sign-up pages open in a private browser window, so your other channel stays logged in.
- **Your AI knows every channel.** Each one gets its own folder with its own notes, and videos follow their
  channel's rules. "Make today's videos" makes every channel's, except one set to post **Only when I ask**.
- **Tell your AI about your channel.** Drag a file about it into the chat (or paste a description) and say
  "here's my channel". Your AI keeps it as the channel's brief and plans every video from it.
- **Tidier What's new.** This panel now shows release notes as clean, short lists at any window size.
- **A shorter first-time setup.** It no longer asks how hard your AI should work: High is the standard. For more
  or less, the profile menu has **Advanced settings**: Max, High and Fast. `reelforge channel` changes your
  channel's answers.
- **A Settings tab (7).** Your channel's answers, your AI's reasoning and what ReelForge set up, in one place.
  - **Factory reset** puts your settings, logins and stats in a backup, then first-time setup again. Videos stay.
  - **Uninstall** removes ReelForge and keeps your videos in a folder beside it. `reelforge uninstall` does it too.
  - Both ask you to type your channel's name, never delete anything for good, and never stop half-way.
- **The setup box fits any window.** It stays whole in a small window or one you resize, and the hints on its bottom
  edge are gone.
- **Meet the anvil, ReelForge's mascot.** He winks hello in first-time setup, hammers while it downloads and hops
  when it's all ready. On the Updates tab he hammers while an update installs, and he naps where there's nothing yet.
- **No more Setup.exe.** ReelForge installs only with its one-line command, so Windows never calls it unverified.

Already have ReelForge? Open **Updates** (`reelforge 6`) and click **Update and restart**.

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
3. Type `reelforge 4` in a terminal (or open ReelForge's icon and go to **Publish**, tab 4) to post it.

Already have ReelForge? Its **Updates** tab (`reelforge 6`) installs this version in one click.

See the README for the full guide.
