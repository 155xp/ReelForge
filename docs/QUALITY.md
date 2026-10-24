# The quality bar

QA (`pipeline/qa.py`) catches technical faults. This page is everything it can't: what makes a viewer stop on the
first frame and watch to the end. Every video is held to it before it ships.

## The standard: the whole video is captivating, start to finish

- **Seconds 0-2 hook hard.** Motion and something strange from the first frame, and the title question lands
  immediately. No slow establishing shot.
- **No dead air, ever.** Every 2-3 s something new: a number jump, a milestone, a camera move, a hit, a reveal. If
  a viewer could look away for 3 s and miss nothing, that stretch is broken.
- **Escalation accelerates.** Each beat is bigger than the last, and the final 20 s are the most spectacular.
  Nothing winds down in the back half.
- **The payoff lands**, in picture and sound, and the ending (the follow call-to-action) keeps the loop seamless
  when the format loops.
- **Sound carries the energy:** ambience, rising beds, a punchy hit on every milestone, the climax loudest
  (within the loudness target, see `SOUND.md`).

Before approving, watch it in your head as a viewer scrolling TikTok: would you stop on the first frame, and would
you watch to the end? If not, it isn't done.

## Banned faults

The three demo scenes in `examples/` (`demo_*`) are the minimum visual standard. These faults get a video rejected:

- **Same-shot stretches.** The composition must visibly change at least every ~8 s: camera moves (whip round,
  orbit, look back, push in, pull out), a new setting, or a new event. Never 30 s of one framing.
- **Claims you can't see.** Every story line must be visibly true on screen at that moment. "Bigger than a bus"
  shows a bus next to it; "buildings can't stop it" shows buildings bending or breaking; "through the clouds" shows
  clouds streaming past. If you can't show it, cut or change the line.
- **An unreadable subject.** It is never washed out by haze, never semi-transparent, never out of frame while a
  line talks about it, and big enough to read on a phone (roughly 15-45% of the frame's height).
- **Plain primitives up close.** Anything filling more than ~20% of the frame needs detail: panels, windows, seams,
  texture, rim light, highlights (a balloon has a knot, a string, a sheen and stretch).
- **Flat, milky pictures.** No flat white or grey skies filling the frame, no haze over the whole image. Keep rich
  blacks in space and clear subject/background separation. Let escalation show in light and colour too (golden
  hour, re-entry glow, space blue-black).
- **Escalation without spectacle.** Every ~10 s something visibly bigger happens: destruction, shockwaves, debris,
  vapour, glow, a planet appearing.
- **Text problems.** Never white-on-white, never over the subject. The counter has no box and no channel name and
  must read on any background (QA measures it).
- **Facts that aren't true yet.** No line or HUD label before its fact is true (`facts.md`).

## How to check

1. **Stills before rendering:** `--steps build,stills` at 10+ key moments, and look at every one. Put them next to
   the example scene's at matching moments. Fix and repeat until they clear this page.
2. **After rendering:** look at every `build/qa/sheet_*.jpg` and the cover, then at **full-resolution frames from
   the final mp4** at every story line, every big moment (milestones, hits, the payoff) and the last frame. For
   example, a frame at 21.5 s:
   `ffmpeg -ss 21.5 -i episodes\<id>\final\<id>.mp4 -frames:v 1 frame_21.5.png`
3. **Sound:** read both per-second loudness lines in `build/qa/report.md` (plain and as heard). Every scene has
   sound, no dead gaps, the climax is the loudest part as heard, key hits land on cue, nothing clips, no static.
4. **Facts:** re-check `facts.md` against the lines and the HUD.
5. Write `build/qa/review.md`: what you checked, what you fixed, and the verdict `APPROVED` or `REJECTED: why`.
   `ship` refuses a video without an APPROVED review.

**If you're not sure a video is right, don't ship it.** Fix it, or leave it out and say why in the production log.

## Lessons from building the scene library

- Give a generated Blender image its colour space *before* writing its pixels (changing it afterwards reloads the
  image blank).
- Aerial shots need a larger near clip per shot (`"clip"` in the shot options), or distant surfaces z-fight.
- Area lights over wet ground need `specular_factor = 0`, or they paint rectangles on it.
- Eevee motion blur leaves light trails under a camera-locked subject at high speed; it reads as a light-trail
  effect, but keep it off things that shouldn't smear.
- People are stylised stand-ins with no walk cycle: keep them mid-distance, moving along paths.
