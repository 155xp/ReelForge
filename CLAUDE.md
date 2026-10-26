<!-- reelforge-bootstrap: first-time setup replaces this file with one written for your channel. -->
# ReelForge (not set up yet)

This folder is **ReelForge**, a kit for making faceless short-form videos with you, Claude: Blender builds
and renders each scene, Python draws the text and mixes the sound, ffmpeg encodes, an automatic QA gate checks
every video, and the **ReelForge** window (type `reelforge` in a terminal) is where the person you're working with
sees their stats and posts from, by hand.

It hasn't been set up for their channel yet. First-time setup replaces this file with a full CLAUDE.md written from
their answers (their channel, format, platforms, style, caption rules and quality bar).

## Getting them set up

1. **Install.** If there is no `.venv` folder here, ask them to double-click `setup.bat` (Windows) or run
   `./setup.sh` (macOS/Linux). It lists what ReelForge still needs, sets it all up inside this folder once they
   say yes, then checks everything. You can run it for them only if they agree to all of it: `setup.bat -Yes` /
   `./setup.sh --yes` downloads Blender 4.5 (about 400 MB), ffmpeg (60-150 MB), the sound effects (about 55 MB)
   and Bun with the ReelForge window's packages (about 60 MB) into this folder (on macOS/Linux also a private Python
   if theirs is older than 3.11, and Chromium if they have no Chrome or Edge), adds the `reelforge` command to their PATH and ReelForge's icon (a desktop shortcut on
   Windows, ReelForge in Applications on macOS, an app-menu entry on Linux).
2. **Their channel.** Either they run `channel.bat` / `./channel.sh` (a few questions in a full-screen box), or you
   interview them here in the chat:
   - Get the questions: `.venv\Scripts\python -m studio channel --questions` (macOS/Linux: `.venv/bin/python`).
     Each has a key, options and a default.
   - Ask them conversationally, a few at a time, offering the options as choices and the defaults as suggestions.
     Skip questions whose `only_if` doesn't apply. `background_stats` adds an hourly background job that reads
     their stats while ReelForge is closed: ask it plainly; their answer is the permission.
   - No account on a platform yet? Help them make it: each handle question has its `signup` page and steps, and the
     first has `gmail`, a new Gmail just for the channel to offer first (it signs them in to YouTube, and the
     others can sign up with it). They sign up themselves, in their own browser: never make an account for them or
     ask for a password. A handle they skip, they can connect later on ReelForge's Accounts tab (tab 5).
   - Write their answers to `my-studio/answers.json` (`{"key": value, ...}`), then run
     `.venv\Scripts\python -m studio channel --answers my-studio/answers.json`. It checks the answers and says
     what to fix.
3. **Read the new CLAUDE.md** that first-time setup wrote, and follow it from then on.
4. `.venv\Scripts\python -m studio doctor` checks everything at any time; `--render-test` also renders a frame.
5. **More channels later?** Each one is a profile with its own folder in `profiles/`: `reelforge profiles new` runs the
   same interview for it (or, interviewing them in chat, `--new --answers FILE.json`). The CLAUDE.md first-time
   setup writes then lists every channel and where its notes are. A new channel's accounts are best made in a private
   window of their browser, so their first channel stays logged in: the `gmail` item's `another_channel` says how.

## Always

- Never post, upload or send anything. Finished videos go to ReelForge's Publish tab (tab 4), and they post by
  hand.
- Use your strongest model at high effort for video work.
- Read `README.md` for what the kit does, and `docs/` for the pipeline, the quality bar and the sound rules.
