# Sound

The videos have no voiceover, so sound design carries the energy: ambience, rising beds, a hit on every milestone,
the climax loudest. Two things ruin it, and QA checks for both: **static** and **loudness**.

## No static, ever

Listeners hear these as "super loud static", even when the numbers look fine:

- **Beds and long effects come from recordings only** (`assets/sfx`: `wind_bed`, `city_traffic`, `engine_hum`,
  `space_ambience`, `bass_rumble`, `rocket_turbine`...). Never synthesize ambience out of noise (surf, crowds,
  rain, wind, engines, jets, whooshes): it reads as static. `pipeline/post/sfx_generate.py` only makes short tonal
  accents (coins, ka-ching, shimmer, shutter); the `jet` and `whoosh` synths in `audio_mix.py` are noise and are
  banned in new videos.
- **Know a sample's length before you repeat it.** `hud_blip` is a 5-second computer-noise burst, not a blip:
  13 copies stacked in 3.5 s once piled into eight seconds of loud noise. For quick repeated accents use a synth
  (`notify`, `ding`, `coin`) or a sample under ~1 s.
- **Loudness as heard, not just RMS.** The ear is most sensitive at 1-5 kHz, so hiss there sounds far louder than
  its RMS says. QA's report has an A-weighted line ("as heard") for exactly this.

QA FAILs: **no static or hiss** (2+ hiss-like seconds outside the glitch and rewind), **no loudness blasts**
(any 3 s more than +8 dB over the median as heard; WARN above +6.5), **no piled-up sounds** (a sample longer than
1 s with more than 4 copies playing at once). A WARN in any of them is a reason to fix the mix, not to ship.

## Loudness

Every mix is mastered to the channel's target (`my-studio/studio.toml` -> `[sound] target_lufs`, set in
first-time setup) by `pipeline/post/loudness.py`. QA FAILs a video louder than the target + 2 LU integrated, a loudest
3 s above the target + 8, or a true peak above the limit (-6 dBTP at the default).

The default, -25.5 LUFS, is quieter than most uploads on purpose. These videos are booms, rumbles and risers with
no voice: at -15 LUFS (a normal level for music and speech) they were reported as "insanely loud", and -25.5
fixed it. Don't raise it for one video. If you want it louder for the whole channel, run `reelforge channel` and pick
another level.

`target_rms_db` in a cue sheet only balances the mix internally; it doesn't set how loud the video is.

## The cue sheet (`"audio": {"mixer": "samples", ...}`)

`pipeline/post/audio_mix.py` builds the mix from the spec. Cue types:

| Cue | What it does |
|---|---|
| `beds` | a looped sound over `[from, to)` with `gain` and `rate` curves `[[t, v], ...]` (`"rate": "gears"` revs an engine up a gear per doubling) |
| `hits` | a one-shot at `at`; `"align": "peak"` lands its loudest moment on `at` (QA checks those are audible), `"end"` ends it there |
| `scatter` | one random sound from `pool` per cluster of series events (e.g. every window burst) |
| `ticks` | a short synthesized blip (or `synth`) at every time in a series event list (e.g. each doubling) |
| `rewind` | the finished mix of `source` played backwards into `[from, to)`, accelerating like the picture |
| `cut_at` | everything except hits and the rewind stops dead here (the overflow) |

Synths available in `hits`/`ticks`: `ding`, `notify`, `coin`, `shutter`, `pop`, `squeak` (and the banned `jet`,
`whoosh`).

## Adding sounds

Approved free sources: **Mixkit** (free licence: commercial use, no attribution, no redistribution of the files)
and **Kenney** (CC0). Put the file in `assets/sfx/<source>/`, add a manifest entry (`file`, `source`, `id` or
`title`, licence note), run `python -I pipeline/post/sfx_cache.py`, then use its name in a cue sheet. Check its
length and listen for noise before you rely on it.
