# Examples

Episode specs to learn from and start new episodes from (`reelforge new-episode <slug> --from <name>`). They are
references for the pipeline, not videos to post as they are: make every episode's subject your own. The three
demos each have a `facts.md` with a source for every number on screen.

| Example | Format | What it shows |
|---|---|---|
| `demo_doubling_duck` | What if X doubled every 2 seconds? | "What if a rubber duck doubled in size every 2 seconds?" (67 s): the `street` world and `grow` effect, real milestones tagged on screen, a counter, real sound effects with a cue sheet, the integer overflow, and a rewind into the first frame (a seamless loop) with the follow call-to-action. |
| `demo_disaster_pov` | What if \<a disaster\> hit your city? | "What if a meteor exploded 15 miles away?" (74 s): the `disaster_city` world and `approach` effect, first person from a balcony, the blast wave's real timing, a countdown counter, a blackout, then an end card with a real fact. |
| `demo_everyone_jumps` | What if everyone on Earth did X at once? | "What if everyone on Earth jumped at the same time?" (67 s): the `plaza` world and `everyone` effect, a crowd that grows to the whole planet, a countdown, a slow-motion freeze and the real physics of the landing, then an end card. |

`reelforge new-episode <slug>` starts from the example for your format. To try the pipeline without touching your
channel: `reelforge doctor --render-test` builds the duck scene in a temporary folder and renders one frame. To make a
full video from an example, start a new episode from it, change the title, and run the pipeline
(`docs/PIPELINE.md`).
