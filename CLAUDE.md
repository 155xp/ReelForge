<!-- reelforge-bootstrap: onboarding replaces this file with one written for your channel. -->
# ReelForge (not set up yet)

This folder is **ReelForge**, a kit for making faceless short-form videos with you, Claude: Blender builds
and renders each scene, Python draws the text and mixes the sound, ffmpeg encodes, an automatic QA gate checks
every video, and the **ReelForge** window (type `reelforge` in a terminal) is where the person you're working with
sees their stats and posts from, by hand.

It hasn't been set up for their channel yet. Onboarding replaces this file with a full CLAUDE.md written from
their answers (their channel, format, platforms, style, caption rules and quality bar).

## Getting them set up

1. **Install.** If there is no `.venv` folder here, ask them to double-click `setup.bat` (Windows) or run
   `./setup.sh` (macOS/Linux). It lists what ReelForge still needs, sets it all up inside this folder once they
   say yes, then checks everything. You can run it for them only if they agree to all of it: `setup.bat -Yes` /
   `./setup.sh --yes` downloads Blender 4.5 (about 400 MB), ffmpeg (about 115 MB, Windows) and the sound effects
   (about 55 MB) into this folder, adds the `reelforge` command to their PATH and, on Windows, a desktop shortcut.
2. **Onboard.** Either they run `onboard.bat` / `./onboard.sh` (a short interview in a full-screen box), or you
   interview them here in the chat:
   - Get the questions: `.venv\Scripts\python -m studio onboard --questions` (macOS/Linux: `.venv/bin/python`).
     Each has a key, options and a default.
   - Ask them conversationally, a few at a time, offering the options as choices and the defaults as suggestions.
     Skip questions whose `only_if` doesn't apply. `background_stats` adds an hourly background job that reads
     their stats while ReelForge is closed: ask it plainly; their answer is the permission.
   - Write their answers to `my-studio/answers.json` (`{"key": value, ...}`), then run
     `.venv\Scripts\python -m studio onboard --answers my-studio/answers.json`. It checks the answers and says
     what to fix.
3. **Read the new CLAUDE.md** that onboarding wrote, and follow it from then on.
4. `.venv\Scripts\python -m studio doctor` checks everything at any time; `--render-test` also renders a frame.

## Always

- Never post, upload or send anything. Finished videos go to ReelForge's Publish tab (tab 4), and they post by
  hand.
- Use your strongest model at max effort for video work.
- Read `README.md` for what the kit does, and `docs/` for the pipeline, the quality bar and the sound rules.
