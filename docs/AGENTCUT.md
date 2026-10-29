# AgentCut: headless editing with HyperFrames

Say **“open agentcut and make a video about ___”** or **“use HyperFrames to make a
video about ___”** to the agent working in this folder. It reads the channel brief,
plans the video, writes a composition, renders it and checks the result. “Open”
means use the headless commands; no editor window opens. The current coding agent
supplies the creative decisions, so no separate model account is required.

AgentCut is ReelForge's optional editing entry point. Its renderer is
[HyperFrames](https://github.com/heygen-com/hyperframes), an existing open-source
HTML-to-video engine, pinned to **0.8.214**. Use it for cuts, footage, image
sequences, motion graphics and audio. Blender remains available for generated 3D
scenes. See [HEADLESS-EDITING.md](HEADLESS-EDITING.md) for the tool comparison and
choice of engine.

## Install the optional editor

Use ReelForge's Python: `.venv/bin/python` on macOS/Linux or
`.venv\Scripts\python` on Windows. Substitute that executable for `python` in
these commands, run from the ReelForge folder:

```sh
python -m studio agentcut install
python -m studio agentcut doctor
python -m studio agentcut schema
```

Installation requires **Node.js 22 or newer and npm**. It runs `npm ci` with
ReelForge's bundled package manifest and lockfile in `tools/agentcut/`, keeping the
engine and its exact dependencies separate from the ReelForge window. ffmpeg and
ffprobe come from ReelForge's setup or `STUDIO_FFMPEG`. HyperFrames renders through
headless Chrome. Installation runs `browser ensure`, which finds a compatible browser
or downloads a managed Chrome Headless Shell into `~/.cache/hyperframes/chrome`.
Set `HYPERFRAMES_BROWSER_PATH` to use your own compatible executable. No window opens.
Use `doctor` to check Node, ffmpeg, ffprobe and Chrome before rendering; missing optional
speech/music models or Docker do not block this local editing workflow.
`REELFORGE_NODE` and `REELFORGE_NPM` can name specific runtime executables.

`agentcut` with no arguments prints the agent workflow. `status` reports the
installation state. `schema` describes the HTML composition contract and links to
the upstream authoring references. `python -m studio hyperframes` is an alias for
the same commands. Choosing this backend in onboarding does not install it.

## Choose a backend and start a video

First-time setup's backend question sets `video.backend` to `blender` or
`agentcut`. Existing channels keep Blender until they change that answer.
Override the preference for one episode:

```sh
python -m studio new-episode moon --backend blender
python -m studio agentcut new moon --topic "Why does the Moon look larger near the horizon?"
# Equivalent editing starter:
python -m studio new-episode moon --backend agentcut
```

For another channel, add `-p NAME` after `studio`. The starter writes
`episode.json` for ReelForge's story text, sound and captions, `facts.md` for
claims and media credits, and an **`edit/index.html`** composition. Put media in
**`edit/media/`**. `--topic` also saves the request in `agentcut-task.md`.
These are draft inputs: creating the episode does not produce a finished video
or grant approval.

## Author the composition

Read the channel brief and production log first. Plan the hook, shot changes,
payoff and ending around the available media. Record each asset's source and
licence, and each factual claim's evidence, in `facts.md`. Inspect files before
choosing trims:

```sh
python -m studio agentcut inspect "PATH/clip.mp4"
```

Edit `edit/index.html` using the
[HyperFrames composition format](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes/references/format.md).
Its root declares a composition ID, **1080×1920** dimensions and a finite
`data-duration` matching `episode.json`'s `render_until`. ReelForge renders at the
episode's `fps`. Usually set `duration` equal to `render_until`; an existing
ReelForge end card can extend the final episode.

Timed clips use `data-start`, `data-duration` and `data-track-index`. Media paths
resolve relative to the HTML file. This example shows two shots and an audio bed;
replace the source files with your own media and extend the composition to the
channel's required duration:

```html
<!doctype html>
<html>
  <head>
    <style>
      html, body { margin: 0; }
      #main { position: relative; width: 1080px; height: 1920px; overflow: hidden; }
      video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
    </style>
  </head>
  <body>
    <div id="main" data-composition-id="main" data-start="0"
         data-duration="6" data-width="1080" data-height="1920" data-no-timeline>
      <video id="wide" class="clip" src="media/wide.mp4" muted playsinline
             data-start="0" data-duration="3" data-media-start="2" data-track-index="0"></video>
      <video id="detail" class="clip" src="media/detail.mp4" muted playsinline
             data-start="3" data-duration="3" data-track-index="0"></video>
      <audio id="ambience" class="clip" src="media/ambience.wav" data-volume="0.5"
             data-start="0" data-duration="6" data-track-index="1"></audio>
    </div>
  </body>
</html>
```

Use `data-media-start` for source trims and `data-playback-rate` for speed.
Give video either `muted` or `data-has-audio="true"` to make the sound choice
explicit. Audio supports gain and fades through HyperFrames' media attributes.
Keep source trims within the actual file and make the final shot cover the end
of the composition.

For motion graphics and image movement, use HyperFrames' supported seekable
animation runtimes. A paused GSAP timeline must be registered under the same
composition ID; custom drawing can derive each frame from the `hf-seek` event's
time. Follow the [animation reference](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes/references/runtimes.md).
A wall-clock timer or unseeded randomness can produce a preview that differs from
the rendered video. Keep required scripts, images, fonts and audio local so the
composition does not depend on a CDN during capture.

Fill in `episode.json` too: title, timed story `lines`, CTA, cover and hashtags.
ReelForge adds those overlays after the composition render. Leave room for them
in the edit and avoid writing the same story text twice. All channel rules from
[QUALITY.md](QUALITY.md) and [SOUND.md](SOUND.md) still apply. Static image holds
may fail frozen-frame QA; give each shot meaningful motion or document an
intentional hold.

## Validate, render and review

Replace `episodes/ep01_moon` with the folder printed by the starter:

```sh
python -m studio agentcut validate episodes/ep01_moon
python -m studio agentcut render episodes/ep01_moon
python pipeline/make_episode.py episodes/ep01_moon --steps post
```

`validate` runs HyperFrames' lint and metadata checks and verifies the composition
against the episode dimensions and duration. It does not certify the finished
video's picture, sound or facts. `render` captures the edit with headless Chrome,
encodes it and supplies preview stills and frames for ReelForge. It does not run
Blender. The pipeline's existing `build,stills,render` steps choose this same
renderer from `episode.json`'s `backend`.

`post` adds ReelForge overlays, masters the edit's audio to the channel loudness,
writes the cover and platform captions, then runs the existing QA gate on the
final MP4. The starter selects `audio.mixer = "agentcut"` to use the composition's
audio. To use ReelForge's recorded sound cue sheet instead, select `samples` and
write its cues as described in [SOUND.md](SOUND.md). A composition with no audible
media is silent; normal QA rejects unintended silence.

Inspect every contact sheet, full-resolution frames at key beats, the cover,
both loudness reports and factual sources. Fix failures, rerender and repeat.
Write `build/qa/review.md` with what you checked and fixed, ending in `APPROVED`
only when the finished video clears the bar. Never fabricate approval or bypass
QA. Then deliver:

```sh
python pipeline/make_episode.py episodes/ep01_moon --steps ship
```

Delivery keeps ReelForge's fresh-QA and review gates and the standard Publish
layout: `final/<id>.mp4`, `final/cover.jpg`, `final/caption.txt` and platform
captions. Log the result in the channel's production log. The person posts from
ReelForge's Publish tab by hand; never upload or post through the editing engine.
