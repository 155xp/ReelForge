<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="docs/logo-light.png">
    <img src="docs/logo-light.png" alt="ReelForge" width="480">
  </picture>
</p>

<p align="center">
  ReelForge lets Claude Code or Codex make faceless short videos for TikTok, YouTube Shorts, Instagram Reels and X,
  then shows you how each one does once you've posted it. It runs on Windows, macOS and Linux.
</p>

<p align="center">
  <a href="#quick-start"><img alt="Get ReelForge" src="https://img.shields.io/github/v/release/dan2756/ReelForge?style=for-the-badge&label=Get%20ReelForge&labelColor=1b1f24&color=e8213a"></a>
</p>

![ReelForge's Overview tab: followers, views and likes on every platform, hour by hour](docs/screenshots/app-overview.png)

## What it makes

An AI made these three videos with ReelForge, start to finish: it wrote the script, checked every number against a
real source, built and rendered the 3D scenes, and added the text and the sound. They're ReelForge's three demos.

<p align="center">
  <img src="docs/demos/rubber-duck.webp" width="250" alt="What if a rubber duck doubled in size every 2 seconds?">&nbsp;
  <img src="docs/demos/meteor.webp" width="250" alt="What if a meteor exploded 15 miles away?">&nbsp;
  <img src="docs/demos/everyone-jumps.webp" width="250" alt="What if everyone on Earth jumped at the same time?">
</p>

You start from a format that's already pulling views, like "What if X doubled every 2 seconds?" or "What if everyone
on Earth did X at once?", or you describe your own.

## Quick start

You need about 15 GB of free space, Claude Code or Codex, and one of these:

- a **Windows 10 or 11** PC with a recent NVIDIA or AMD graphics card
- a **Mac** with Apple Silicon (M1 or newer); an Intel Mac works too, but renders much more slowly
- a **Linux** PC (x64) with a recent NVIDIA or AMD graphics card and its drivers

1. **Open a terminal.** On Windows, press the Windows key, type `PowerShell` and press Enter. On a Mac, press
   ⌘ Space, type `Terminal` and press Enter. On Linux, open your terminal.
2. **Paste the line for your computer and press Enter.**

   Windows:

   ```
   irm https://github.com/dan2756/ReelForge/releases/latest/download/install.ps1 | iex
   ```

   Mac or Linux:

   ```
   curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh | bash
   ```

   It downloads the newest ReelForge straight from GitHub into a ReelForge folder in your user folder, checks it and
   starts setup, so your browser, Windows and macOS have no download warning to show.
3. **Say yes, then answer a few questions.** ReelForge lists what it still needs and, when you click **Set up**,
   downloads Blender, ffmpeg and the sound effects into its own folder (and Python too, if your Mac or Linux PC
   doesn't have a recent one; Bun, which runs ReelForge's window, comes first by itself). Then it asks about your
   channel: what it's about, the format, where you post (TikTok, YouTube Shorts and Instagram Reels to start), and how
   your videos should look and sound. No accounts yet? It helps you make them, starting with a new Gmail for your
   channel. ReelForge's mascot, the anvil, keeps you company: he hammers away while it all downloads and hops when
   everything's ready.

<p align="center">
  <img src="docs/screenshots/first-run.png" width="49%" alt="Setup lists what ReelForge still needs and sets it all up with one click">
  <img src="docs/screenshots/setup-format.png" width="49%" alt="First-time setup: pick the format your channel starts with">
</p>

Rather use an installer on Windows? Download it from [reelforge.tools](https://reelforge.tools) and open it. It's
also on GitHub: open the [latest release](https://github.com/dan2756/ReelForge/releases/latest) and click the file
that ends in `Windows-Setup.exe` under **Assets**. If Windows says "Windows protected your PC", click **More info**,
then **Run anyway**: it says that about new apps that aren't code-signed yet. Setup starts when the installer
finishes. Both places have a zip for the Mac and a tar.gz for Linux too, if you'd rather download those yourself.

## Make your first video

First-time setup turns your answers into instructions for your AI, `CLAUDE.md` for Claude Code and `AGENTS.md` for Codex,
and saves them in the ReelForge folder (`C:\Users\<you>\ReelForge` on Windows and `~/ReelForge` on a Mac or Linux,
unless you picked another). Its last screen tells you what to do next.

![First-time setup's last screen: open this folder in Claude Code or Codex, tell it about your channel, say "make my first video", then post it from Publish](docs/screenshots/first-run-ready.png)

1. **Open the ReelForge folder in your AI.** In the Claude desktop app, go to **Code**, click **Open folder…** and
   pick the ReelForge folder (or run `claude` in a terminal inside it). For Codex, run `codex` in a terminal inside
   it.
2. **Tell it about your channel.** Drag a file about it into the chat (your notes, a doc, videos you like: whatever
   you have) or paste a description, and say:

   ```
   here's my channel
   ```

   First-time setup only asks a few questions, so this is where your AI gets the full picture. It keeps your words
   as the channel's brief (`my-studio/brief.md`), reads it every time and plans every video from it, and it asks
   before changing your answers to match. Skip this and it asks for one before your first video.
3. **Ask for your first video** in the words that screen gives you:

   ```
   make my first video
   ```

4. **Let it work.** Your AI picks a subject, writes the script, checks the facts, builds the scene in Blender and
   renders it, adds the text and the sound, then watches the finished video and fixes anything that's off. Rendering
   takes from about 15 minutes to an hour on a fast graphics card.
5. **Post it.** Open ReelForge (type `reelforge` in any terminal, or open the ReelForge icon: on your desktop on
   Windows, in Applications on a Mac, in your app menu on Linux) and go to **Publish**.

After that, say **make today's videos** whenever you want more, and give it a new file whenever your plans for the
channel change.

## Inside ReelForge

ReelForge has seven tabs. Open one straight from a terminal with `reelforge 1` to `reelforge 7`, or by name, like
`reelforge publish`. Everything works with the mouse or the keyboard: **1**-**7** switch tabs, **Tab** moves between
buttons and fields, **Enter** presses, **Esc** closes. ReelForge's window and its first-time setup are built
with [OpenTUI](https://github.com/anomalyco/opentui).

### Overview

Followers, views and likes on each platform you've connected, hour by hour, with a mark where each video went up,
plus your top videos (with their views 12 hours in) and how the latest one is doing. The bell at the top right
collects milestones, new videos ready to post and updates, and gets a red dot when there's something new. Click a
notification to see what it's about: a video that's taking off opens on the Videos tab, highlighted, and a finished
video is picked out on Publish. The big × on a notification's right deletes it, and Clear all deletes them all.

<p align="center">
  <img src="docs/screenshots/app-notifications.png" width="49%" alt="The Overview tab with the notifications open">
  <img src="docs/screenshots/app-notification-click.png" width="49%" alt="After clicking a notification: the video it's about, highlighted on the Videos tab">
</p>

### Videos

Every video on every platform in one table, scored against your typical video, with its views 12 hours after it went
up, so new and old videos compare fairly. Click a header to sort, and pick a video to see how its views grew after you
posted it. Export CSV saves every video with when it went up (date, weekday, hour and UTC time) and its views 1, 6,
12 and 24 hours in.

![The Videos tab](docs/screenshots/app-videos.png)

### Compare

Which platform is working for you: views per video, like rate and followers gained side by side, and how a typical
video grows over its first three days on each one.

![The Compare tab](docs/screenshots/app-compare.png)

### Publish

Every finished video waits here with its post already written. Each platform's button opens that site's upload page,
copies exactly the text it needs and shows the video in Explorer, Finder or your file manager, so you drag it in and
press Post. ReelForge spots the post by itself.
Under the list, Best time to post shows the part of the day your videos have done best in on each platform, by
their views in their first day, and when it next comes round, once there are enough videos to tell.

![The Publish tab](docs/screenshots/app-publish.png)

### Accounts

The platforms you post to, each connected with your @handle. ReelForge shows only the ones you've connected, so
there's never an empty card, chart or button for one you don't use. TikTok and YouTube need just your handle;
Instagram and X also need one log-in, in ReelForge's own browser window. There are no API keys to set up. No account
yet? Sign up opens the platform's own sign-up page with a few steps beside it (first-time setup offers the same, and a
new Gmail for your channel first). Disconnect hides a platform again without losing its stats.

<p align="center">
  <img src="docs/screenshots/app-accounts.png" width="49%" alt="The Accounts tab: TikTok, YouTube and Instagram connected, and X with its Connect box">
  <img src="docs/screenshots/setup-accounts.png" width="49%" alt="First-time setup's Your accounts step: a Gmail for your channel first, then a handle or Sign up for each platform">
</p>

### Profiles

Run more than one channel from one ReelForge. Each channel is a profile, with its own accounts, logins, stats,
notifications, Publish list and settings. The button with your channel's name at the top left switches between them
(or press **p**), and a red dot on it means another profile has something unread. **New profile** asks the same short
questions as your first channel did, right in the window, and helps you make the new channel's accounts: a Gmail
first, then each platform's sign-up page, in a private window of your browser so your first channel stays logged in.
Your first channel stays in the ReelForge folder itself, and each one you add gets its own folder in `profiles`, with
its own notes for your AI. Tell your AI about a new channel the way you did the first: "here's <its name>" and a file
about it. The hourly stats job reads every profile, and `reelforge -p "Channel name"` opens ReelForge on one. "Make
today's videos" makes every channel's, except one you set to post **Only when I ask** (a channel you're only trying
out, say).

![The profile menu: each channel with its platforms and unread notifications, New profile, this one's settings and Advanced settings](docs/screenshots/app-profiles.png)

### Settings

This channel's answers from first-time setup (**Change your answers** asks the questions again), how hard your AI
reasons on each video (**Max**, **High**, the standard, or **Fast**), and what ReelForge set up on your computer: the
hourly stats read, the `reelforge` command and the icon, each with a button to turn it on or off. At the bottom, the
danger zone: **Factory reset** puts every channel's settings, logins and stats in a backup and starts first-time setup
again, and **Uninstall** removes ReelForge. Both ask you to type your channel's name first, and neither deletes
anything: what they clear goes to a backup or the Recycle Bin (the Trash on a Mac).

![The Settings tab: the channel's answers, your AI's reasoning, what ReelForge set up on this computer, and the danger zone](docs/screenshots/app-settings.png)

## Updates

When a new version is out, the bell gets a red dot and the **Updates** tab (`reelforge 6`) shows what's new. Click
**Update and restart** to install it: the anvil hammers while it installs and hops once it's in. Your channel,
videos, stats and settings stay as they are, and your AI's instructions are refreshed for the new version.

<p align="center">
  <img src="docs/screenshots/app-updates.png" width="75%" alt="The Updates tab: a new version installs and restarts ReelForge in one click">
</p>

## FAQ

<details>
<summary><b>Windows says "Windows protected your PC". Is it safe?</b></summary>

<br>

Yes. Windows says that about new apps that aren't code-signed yet; it doesn't mean it found anything wrong. Click
**More info**, then **Run anyway**. Your browser may also warn that the file isn't commonly downloaded: open the
**⋯** menu next to the download, choose **Keep**, then **Keep anyway** (Edge asks you to click **Show more** first).

The one-line install in the [Quick start](#quick-start) doesn't go through your browser, so it skips both warnings.

</details>

<details>
<summary><b>Is ReelForge free?</b></summary>

<br>

Yes. ReelForge is free and open source. Making videos uses your own Claude Code or Codex plan.

</details>

<details>
<summary><b>Does it post for me?</b></summary>

<br>

No. ReelForge never posts, uploads or sends anything. Finished videos wait in the Publish tab, and you post them
yourself.

</details>

<details>
<summary><b>Can I install it somewhere else?</b></summary>

<br>

Yes, on any drive with room for your videos. On Windows, run this in the same PowerShell window before you paste
the install line, with your own folder:

```powershell
$env:REELFORGE_DIR = "D:\ReelForge"
```

On a Mac or Linux, put the folder in the install line, before `bash`:

```
curl -fsSL https://github.com/dan2756/ReelForge/releases/latest/download/install.sh | REELFORGE_DIR=/Volumes/Big/ReelForge bash
```

The Windows installer asks you where to put it as you click through it.

</details>

<details>
<summary><b>Where are my videos?</b></summary>

<br>

In the Publish tab, and as files in the ReelForge folder: every video has its own folder in `episodes`, and a copy of
each finished one goes to `completed videos`.

</details>

<details>
<summary><b>Do my stats update while ReelForge is closed?</b></summary>

<br>

Yes, if you said yes during first-time setup. Once an hour, while your computer is on, a small background job reads your
stats for about a minute, then stops. Turn it off or back on with `reelforge stats off` or `reelforge stats on`.

</details>

<details>
<summary><b>Can I have ReelForge open in more than one window?</b></summary>

<br>

Yes, as many as you like, say one on the Overview and one on Publish, or one for each of your channels. Windows on
the same channel take turns reading its stats, and as soon as one of them has read them, every window shows the new
numbers and notifications, so they always agree and your accounts are read only once. The hourly background job's
reads show up in them too.

</details>

<details>
<summary><b>Can I run more than one channel?</b></summary>

<br>

Yes. Add a profile for each one: click the button with your channel's name at the top left, then **New profile** (or
run `reelforge profiles new`). It asks the same questions as your first channel did and helps you make the new
channel's accounts. Its accounts, logins, stats, notifications and settings are its own. Your AI works on all of them
from the ReelForge folder: say which channel a video is for, like "make a video for Cool Epic Facts". Each channel's
notes are in its folder (`profiles/<name>/CLAUDE.md`), and the main `CLAUDE.md` lists them.

</details>

<details>
<summary><b>My AI doesn't know about my channel.</b></summary>

<br>

Make sure you opened the ReelForge folder itself, not the folder it's in: your AI reads `CLAUDE.md` (or `AGENTS.md`)
from there. First-time setup only asks a few questions, so give it the full picture too: drag a file about your
channel into the chat (or paste a description) and say "here's my channel". It keeps it as the channel's brief and
plans every video from it. To change your answers, run `reelforge channel`.

</details>

<details>
<summary><b>How do I change my answers?</b></summary>

<br>

Run `reelforge channel` (on Windows, **Change my channel answers** in the Start menu does the same). It starts from
your last answers, and when you finish it rewrites your AI's instructions and ReelForge's settings. For another
channel, open the profile menu and pick its settings, or run `reelforge -p "Channel name" channel`.

</details>

<details>
<summary><b>How do I get the best videos?</b></summary>

<br>

Use your strongest model. First-time setup sets Claude Code to Opus at high effort for the ReelForge folder, the
standard for every channel. For more (or less), open the **Settings** tab (`reelforge 7`, or **Advanced settings**
in the profile menu): **Max** reasons the most and makes the best video it can, and **Fast** makes quick drafts. With
Codex, pick your strongest model with `/model`.

</details>

<details>
<summary><b>Can I try things in a second copy without touching my real one?</b></summary>

<br>

Yes. Unpack your computer's download from the release into another folder and put a file called `TEST-COPY.txt` in
it. That copy's window says **TEST**, its stats, logins and settings are its own, and it never touches the
`reelforge` command, the hourly stats job or ReelForge's icon, which stay with your real ReelForge. Open it with its
own `ReelForge.bat` (Windows) or `./reelforge.sh` (Mac and Linux).

</details>

<details>
<summary><b>Something isn't working.</b></summary>

<br>

Run `reelforge doctor`. It checks everything ReelForge needs and says how to fix anything that fails. `reelforge
setup` repairs the setup.

</details>

<details>
<summary><b>Does it work the same on a Mac or Linux?</b></summary>

<br>

Yes. Setup gets everything ReelForge needs into its own folder on all three, so you don't need Homebrew or a package
manager: Blender from blender.org, ffmpeg from the builds ffmpeg.org points to, Bun (for ReelForge's window) from its
own releases, and a private Python if yours is older than 3.11. ReelForge reads your stats with Chrome or Edge if you have one, or with a Chromium setup downloads if you
don't. On a Mac, ReelForge goes in your Applications folder (so it's in Launchpad, Spotlight and the Dock) and opens in
Terminal; on Linux it goes in your app menu. The hourly stats job is a launchd agent on a Mac and a systemd timer (or
a cron job) on Linux. Every change is tested on Windows, on Macs with Apple Silicon and Intel, and on Linux.

blender.org has no Blender for ARM Linux, so on an ARM Linux PC install Blender 4.5 yourself (then setup finds it)
or point `STUDIO_BLENDER` at it.

</details>

<details>
<summary><b>My Mac says it can't check the file for malware.</b></summary>

<br>

That only happens with the zip from the release page, because macOS checks files your browser downloads. Open
**System Settings**, go to **Privacy & Security**, scroll down and click **Open Anyway** next to the file's name (on
macOS 14 and older, right-click the file and choose **Open** instead). Setup then clears that check for the ReelForge
folder, so it doesn't ask again. The one-line install in the [Quick start](#quick-start) doesn't go through your
browser, so it never asks.

</details>

<details>
<summary><b>Which commands are there?</b></summary>

<br>

- `reelforge` opens ReelForge.
- `reelforge 1` to `reelforge 7` open a tab: Overview, Videos, Compare, Publish, Accounts, Updates, Settings.
- `reelforge channel` changes your channel answers.
- `reelforge profiles` lists your channels, and `reelforge profiles new` adds one.
- `reelforge -p "Channel name"` opens ReelForge on one channel (it works with any command).
- `reelforge setup` sets up or repairs the tools.
- `reelforge doctor` checks everything.
- `reelforge stats on` and `reelforge stats off` turn the hourly stats on and off.
- `reelforge reset` starts over (a factory reset), and `reelforge uninstall` removes ReelForge.
- `reelforge help` lists the rest.

</details>

<details>
<summary><b>How do I uninstall it?</b></summary>

<br>

Run `reelforge uninstall`, or click **Uninstall…** at the bottom of the **Settings** tab. It lists what it removes and
asks you to type your channel's name, then:

- turns off the hourly stats read and the `reelforge` command, and puts ReelForge's icon (and on Windows its Windows
  Terminal profile) in the Recycle Bin or the Trash
- moves your videos and each channel's answers to **ReelForge videos and channels**, a folder beside ReelForge's
  (add `--remove-videos` to let them go with the rest)
- puts the ReelForge folder in the Recycle Bin or the Trash: the app, Blender, ffmpeg, Bun, your stats, logins and
  settings. Restore it from there if you change your mind, or empty the bin to get the space back.

Nothing is deleted for good, and videos kept outside the ReelForge folder aren't touched.

</details>

<details>
<summary><b>How do I start over?</b></summary>

<br>

Run `reelforge reset`, or click **Factory reset…** on the **Settings** tab. It moves every channel's settings, logins
and stats into a backup in `backups` and starts first-time setup again. Your videos stay where they are, and so do
Blender, ffmpeg and the sounds, so nothing is downloaded again. To undo it, move the backup's files back.

</details>

## License

ReelForge is free and open source under the [MIT license](LICENSE). Setup downloads Blender and ffmpeg from their
official sites, Bun from its GitHub releases (with the window's OpenTUI packages from npm) and the Mixkit sound
effects from Mixkit; the Kenney sound effects come with it. Details are in [THIRD_PARTY.md](THIRD_PARTY.md).
