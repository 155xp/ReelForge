# The episode pipeline

Turns one `episodes/<id>/episode.json` into a finished 9:16 video (1080×1920, 30 fps) with a cover and captions,
checked by an automatic QA gate and listed in ReelForge's Publish tab. All visuals are procedural (no downloaded 3D
models): Blender builds and renders the world, Python draws the text and HUD and mixes the sound, ffmpeg encodes.

Your channel's rules (video length, loudness, caption format, platforms) come from `my-studio/studio.toml`, which
onboarding writes. Commands below use Windows paths; on macOS/Linux use `.venv/bin/python` and `/`.

A ReelForge folder can make videos for more than one channel (each is a profile: `studio/profiles.py`). The first
channel's episodes are in `episodes/`; another channel's are in its own folder, `profiles/<name>/episodes/`, and every
step follows the rules of the channel whose folder the episode is in (its `my-studio/studio.toml`), shipping to its own
`completed videos/`. Start one with `python -m studio -p <name> new-episode <slug>`, and run every command from the
ReelForge folder.

## Tools

| Tool | Where it comes from | Override |
|---|---|---|
| Blender 4.5 LTS | `tools/` (setup downloads 4.5.5), or an installed 4.5 | env `STUDIO_BLENDER` |
| ffmpeg + ffprobe | `tools/ffmpeg` (setup downloads it: gyan.dev on Windows, Martin Riedl's builds on macOS, BtbN's on Linux), or winget, Homebrew or PATH | env `STUDIO_FFMPEG` |
| Python 3.11+ with numpy, Pillow, Jinja2 | the kit's `.venv` (setup makes it, on macOS/Linux from `tools/python` if there was no recent Python) | |
| Bun, for ReelForge's window (OpenTUI, `ui/`) | `tools/bun` (setup downloads it from Bun's GitHub releases), or a Bun of your own on the PATH | env `REELFORGE_BUN` |
| Fonts | Georgia + Consolas on Windows; Georgia + JetBrains Mono on macOS; DejaVu serif + JetBrains Mono on Linux | env `STUDIO_FONTS_DIR` |

`python -m studio doctor` checks all of them. Eevee renders about 1.5-4 frames a second at 1080×1920 on a fast
GPU (an RTX 3090 does a 67 s video in 10-25 minutes); slower GPUs take longer. On a Mac, Blender renders with Metal:
Apple Silicon is quick, an Intel Mac much slower.

## Make an episode

From the kit folder:

```
.venv\Scripts\python -m studio new-episode snowball_doubling      (episodes\epNN_snowball_doubling\)
.venv\Scripts\python pipeline\make_episode.py episodes\<id> --steps build,stills --stills 1,8,15,22,31,40,48,56,62,66
.venv\Scripts\python pipeline\make_episode.py episodes\<id> --steps render
.venv\Scripts\python pipeline\make_episode.py episodes\<id> --steps post
   (look at build\qa\report.md and build\qa\sheet_*.jpg, write build\qa\review.md, then:)
.venv\Scripts\python pipeline\make_episode.py episodes\<id> --steps ship
```

| Step | What it does | Output |
|---|---|---|
| `build` | Blender builds the world and applies the effect from the spec | `build/scene.blend`, `build/series.json`, `build/build.log` |
| `stills` | renders preview frames (`--stills 1,15,31`, in seconds) | `build/stills/s_####.jpg` |
| `render` | renders every frame up to `render_until` (resumable: rerun to continue) | `build/frames/f_####.jpg` |
| `post` | `audio` + `video` + `cover` + `caption` + `qa` | `final/<id>.mp4`, `final/cover.jpg`, `final/caption*.txt`, `build/qa/` |
| `qa` | `pipeline/qa.py` checks the **final mp4** (see below). Fails the run on any FAIL | `build/qa/report.md`, `qa.json`, `sheet_*.jpg` |
| `ship` | `deliver` + `clean` + `check` | |
| `deliver` | copies the video, cover and captions to `completed videos/<id> - <title>/`, **only if QA passed on this exact file and `build/qa/review.md` says APPROVED** | `completed videos/...` |
| `clean` | deletes `build/frames`, `stills`, `preview` (about 0.6 GB a video) once delivered | |
| `check` | confirms ReelForge's Publish tab lists the video with the right caption and hashtags, and prints each platform's post (same as `python -m studio publish-check episodes\<id>`) | |

**If you change the world or the effect, delete `build/frames` before rendering again.** Rendering skips frames
that already exist.

Check the text and HUD at chosen seconds without rendering the whole video (needs `build/frames` for those
seconds, or shows black behind the text):
`.venv\Scripts\python pipeline\post\compose.py episodes\<id> --preview 2,19,47,64` -> `build/preview/`.

### What QA checks

Streams (h264 1080×1920 30 fps yuv420p, AAC stereo 48 kHz), duration inside the channel's length, frame count,
no unintended black or frozen frames, the seamless loop (last frame = first frame) when `loop_to_start` is set,
no clipping, loudness (integrated, loudest 3 s, true peak) against the channel's target, no unintended silence,
no static or hiss, no loudness blasts as heard (A-weighted), no long sample piled on itself, key sound hits
audible on cue, story lines (no overlaps, no line under 1.2 s, none wrapping past 2 lines), the HUD covering the
timeline and readable on every background (4.5:1 contrast), and the caption rules. Intended exceptions come from
the spec (`blackout`, glitches with `stutter`, the rewind hold) or an optional
`"qa": {"black_ok": [[t0, t1]], "frozen_ok": [...], "silent_ok": [...]}` block.

## Captions

The caption is **one short hook line, the spec's `title`**. The `caption` step writes:
- `caption.txt`: caption, blank line, hashtags (the Publish tab reads it)
- `caption_<platform>.txt` for every platform you post to: TikTok and Instagram get the caption + hashtags,
  YouTube gets the caption as the title and the hashtags as the description, X gets the caption (hashtags only if
  you allowed them in onboarding)

It fails if the spec breaks the channel's rules (too many hashtags, no room for TikTok's first hashtag, hashtags in
the title).

## episode.json

`examples/demo_doubling_duck/episode.json` is the full reference for a doubling episode (real sound effects with a
cue sheet, the overflow and a rewind loop); `examples/demo_disaster_pov/episode.json` and
`examples/demo_everyone_jumps/episode.json` show the end-card format (a blackout, then the question and one real
fact).

| Key | Meaning |
|---|---|
| `id`, `title`, `series` | the folder name, the one-line hook (also the caption), the series name |
| `fps`, `duration`, `render_until` | 30 fps; `duration` inside your channel's length. Frames after `render_until` are post-only (e.g. the rewind) |
| `render` | `samples`, `motion_blur`, `shadow_scale` (0.5 avoids Eevee "shadow buffer full"), `shutter`, `blur_depth_scale` |
| `world` | `type` = a module in `pipeline/blender/worlds/`, plus its options (seed, camera...) |
| `effect` | `type` = a module in `pipeline/blender/effects/`, plus its parameters |
| `layout` | `line_y` (a number, or `[[t, y], ...]` to follow the shot), `title_y`, `avoid_subject` |
| `title_card` | `{"start", "end", "scrim"}`: the question at the top |
| `lines` | `[start, end, "text"]` second-person story lines, optionally `[s, e, "text", {"scrim": 0.85, "y": 1150}]` |
| `line_style` | `{"scrim": 0.5}` for every line |
| `hud` | `chapters` (label/value/sub per time range, optional `color`), `vars` (`{var}` -> a series + a formatter in `post/compose.py` `FORMATS`: `int_commas`, `mach`, `miles`, `seconds`, `distance_imperial`, `times`, `raw`) |
| `speedlines`, `speedlines_center` | `[[t, intensity], ...]` radial speed lines drawn in post |
| `flashes` | `{"at", "rise", "fall", "max", "color"}` full-screen flashes |
| `glitches` | post glitch windows (`start`, `end`, `strength`, optional `ramp_from`, `stutter`) |
| `rewind` + `loop_to_start` | play the video backwards (accelerating) into the first frame, so it loops |
| `cta` | `{"start", "end", "text", "sub", "y"}`: the follow call-to-action, e.g. over the rewind |
| `blackout`, `end_card` | a black gap, then the question + one real fact |
| `audio` | `"mixer": "samples"` -> a cue sheet for `post/audio_mix.py` (beds, hits, scatter, ticks, rewind, cut_at; see its docstring); otherwise the synth `post/audio.py` |
| `cover` | `time`, `kicker`, `keyword`, `tail` for the thumbnail |
| `hashtags` | the channel's maximum, written without `#` |
| `preview_times`, `qa` | default seconds for `stills`; QA exceptions |

## The scene library

Worlds build a place; effects animate what happens in it and return per-frame data for the HUD and the sound.

| World | What it is | Used with |
|---|---|---|
| `street` | a small town's Main Street at true scale: shops, a church with a 50 m steeple, parked cars, a bus, people, then farmland, a downtown with a supertall, mountains and clouds; holds up from 15 cm to about 10 km up, and knocks things over as something grows (a "crush field") | `grow` (the duck demo) |
| `disaster_city` | `city_balcony` built wider so the camera can turn its head, with close-up detail, a coast, keyframable sky, sun glow and haze | `approach` (the meteor demo) |
| `plaza` | a cobbled square with a fountain, a Paris-sized city round it (river, quays, bridges, parks, towers, suburbs), tens of thousands of people, and the real Earth below at true scale | `everyone` (the jump demo) |
| `city_balcony` | a low-poly city seen from a balcony, up an avenue to a skyline and mountains | `render_distance`, and the base of `disaster_city` |

| Effect | What it does |
|---|---|
| `grow` | the doubling engine: a subject (`duck`, `donut`, `soccer_ball`, `beach_ball`) doubles in size every 2 s past real milestones (hydrant, you, a bus, the tallest building, Everest, space, the Moon, Earth) to the integer overflow, with 16 shots anchored to its size, debris and dust as it flattens the town |
| `approach` | a threat comes at you, seen first-person: a `meteor` (an airburst with a flash, a mushroom cloud, fires, a quake, a dust wall and the blast wave, timed from the real blast physics for its yield and distance) or an experimental `wave`; head turns, flinches, zoom, shake and knock-back |
| `everyone` | everyone on Earth does one thing at once (a jump or a pose): the crowd fills the square, the city, the country and the planet with a counter, a countdown, a slow-motion freeze and the Earth's real push-back |
| `render_distance` | a building block for "reality had a bug": the render distance shrinks to zero and objects unload with a "missing texture" flash (no example yet: give it a moving camera and a recorded-sound cue sheet) |
| `lookdev` | a camera tour of a world, one shot per frame (set fps to 1 and render stills) to check a look |

Shared helpers: `rf_common.py` (mesh builder, haze + "missing texture" material wrapper, sky, grid, camera, sun),
`look.py` (golden-hour sky, haze and bloom), `camrig.py` (shot lists with hard cuts, eased moves, screen
projection, shake), `growth.py` (doubling maths), `facades.py`, and `parts/`: `person`, `car`,
`aircraft` (and satellites), `landmarks` at true height, `nature` (mountains, clouds), `display` (a seven-segment
display), `subjects` (growable subjects), `space` (Earth, Moon, a shattering Moon, orbit rings, placement at true
angular size), `crowd` (instanced crowds of tens of thousands with poses and reactions) and `globe` (the real
Earth from 50 m to 30,000 km, city lights, and `population_within()` for "how many people live within X km").

Every module's docstring lists its spec keys and the series and events it returns. `--steps stills` skips stills
that already exist, so delete `build/stills` before re-rendering stills after a change.

## Adding a new scene

1. **Effect module** `pipeline/blender/effects/<name>.py` with `apply(spec, info) -> series`. `info` comes from
   the world (camera, positions, objects). Animate whatever happens and return per-frame series for the HUD
   (`{"fps", "frames", "<series>": [...]}`) plus `events` the sound design can use. `keyframe_insert()` ignores
   Blender's default interpolation: call `rf.set_interpolation(...)` after keying.
2. **World module** `pipeline/blender/worlds/<name>.py` with `build(spec) -> info`, or reuse one above.
3. New HUD number formats go in `FORMATS` in `pipeline/post/compose.py`.
4. `new-episode`, edit `episode.json`, `build,stills`, look at every still, then `render`, `post`.

Keep modules reusable: a later episode should only need a new spec. Never change a module an existing episode
uses in a way that changes that episode's output; make a new module instead.

## Sound effects

`assets/sfx/manifest.json` lists every sound (name -> file, source, licence). Kenney (CC0) and the kit's own
synthesized accents ship with the kit; Mixkit sounds (free licence, no redistribution) are downloaded by setup.
`pipeline/post/sfx_cache.py` converts them all to 48 kHz WAV in `assets/sfx/_cache/`. To add a sound: put the file
in `assets/sfx/<source>/`, add a manifest entry with its licence, then use its name in a cue sheet. Read
`docs/SOUND.md` first. Run anything that reads downloaded files with `python -I`.

## Publishing

ReelForge (`reelforge 4`) lists every `episodes/<id>/final/<id>.mp4` on its Publish tab (tab 4), newest first,
with the post pre-filled from `episode.json`'s `title` and the hashtag line of `final/caption.txt`. You post by
hand from there; nothing in the kit posts for you.
