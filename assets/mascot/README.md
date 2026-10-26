# ReelForge mascot

The anvil, redrawn as a clean 35×22 pixel sprite and animated nine ways. Every
GIF, PNG and terminal frame comes from the same sprite, so they always match.

Open `preview.html` in a browser to see all of them on a dark or light background.

| Animation | Use it for | Loop |
| --- | --- | --- |
| `idle` | Default state: breathing, blinking, the hot face shimmering | 3.25s |
| `look` | Glances left and right, then blinks | 2.69s |
| `forge` | Hammer strikes with sparks: working, rendering, loading | 1.26s |
| `think` | Eyes up, dots counting: waiting on a reply | 2.40s |
| `success` | Happy hop with sparkles: done, export finished | 1.45s |
| `error` | Shakes with X eyes, then a sad puff of smoke | 1.70s |
| `sleep` | Forge cools down, snoozing with Zzz: idle for a long time, offline | 3.00s |
| `heat` | Heats to white-hot and cools: charging, processing | 1.20s |
| `wink` | Winks with a sparkle: hello, tips, easter eggs | 1.98s |

## Files

```
gifs/1x/        43×36    for CSS scaling (see below)
gifs/4x/        172×144
gifs/8x/        344×288
gifs/16x/       688×576
gifs/black-8x/  344×288 on solid black, for places that handle transparency badly
png/            reelforge-anvil-*.png: just the anvil (logo, icon, favicon source)
                reelforge-still-*.png: the idle pose on the GIF canvas (reduced-motion stand-in)
opentui/        terminal version for OpenTUI
source/         generate.py, which rebuilds everything above
```

All GIFs share one 43×36 canvas with the anvil standing in the same spot, so
swapping one for another never shifts your layout. The space above the anvil is
for the hammer, sparks and Zzz. Backgrounds are transparent; the body is
near-black, so on a black page it looks just like your original artwork.

## Website and app

```html
<img src="/mascot/reelforge-forge.gif" width="344" height="288" alt="ReelForge mascot hammering">
```

Pixel art stays crisp only at whole-number scales. For any other size, use the
1x file and let CSS do the scaling:

```css
.mascot { width: 172px; height: 144px; image-rendering: pixelated; }
```

To respect reduced motion, swap in the still:

```html
<picture>
  <source srcset="/mascot/reelforge-still-8x.png" media="(prefers-reduced-motion: reduce)">
  <img src="/mascot/reelforge-idle.gif" width="344" height="288" alt="ReelForge mascot">
</picture>
```

Brand colours from the sprite: red `#f71e27`, hot orange `#fd4b33`, eyes
`#ff3b2e`, body `#171618`, bevel grey `#4e4a4f`.

## OpenTUI

OpenTUI's `ImageRenderable` shows a GIF as a single still image, so the
animations also ship as frame data, plus a renderable that draws them with
`▀`/`▄` half-block characters. That works in any truecolor terminal (Windows
Terminal, iTerm2, kitty, WezTerm, Ghostty, VS Code) with no image protocol, and
transparent pixels let whatever is behind the mascot show through.

Copy `opentui/reelforge-mascot.ts` and `opentui/reelforge-frames.ts` into your
project. Tested with `@opentui/core` 0.5.10 and 0.7.0 on Bun 1.4.

```ts
import { createCliRenderer } from "@opentui/core"
import { MascotRenderable } from "./reelforge-mascot"

const renderer = await createCliRenderer({ exitOnCtrlC: true })
const mascot = new MascotRenderable(renderer, { animation: "forge" })
renderer.root.add(mascot)

// when the render finishes:
await mascot.play("success", { loop: false })
mascot.play("idle")
```

| Option | Default | |
| --- | --- | --- |
| `animation` | `"idle"` | Any of the names above |
| `playing` | `true` | `false` holds the current frame |
| `speed` | `1` | Playback rate |
| `loop` | `true` | `false` plays once, holds the last frame and calls `onComplete` |
| `fit` | `"canvas"` | `"canvas"`: always 43×18 cells. `"animation"`: only what this animation draws (`idle` is 35×11) |
| `scale` | `1` | `2` draws each pixel as 2 columns by 1 row, for big splash screens |
| `onComplete` | | Called with the animation name when a non-looping animation ends |

Layout options such as `position`, `left`, `top` and `margin` work as on any
other renderable. Every option is also a property you can set later. There are
`play(name, { loop })`, `pause()` and `resume()` methods, too. The renderer's
frame loop only runs while the mascot is actually animating.

**React** (`@opentui/react`): register the class once, then use it as a tag.
`opentui/react-example.tsx` is a complete app.

```tsx
import { extend } from "@opentui/react"
import { MascotRenderable } from "./reelforge-mascot"

declare module "@opentui/react" {
  interface OpenTUIComponents {
    reelforgeMascot: typeof MascotRenderable
  }
}
extend({ reelforgeMascot: MascotRenderable })

<reelforgeMascot animation={busy ? "forge" : "idle"} />
```

**Demo:** with `@opentui/core` installed, `bun opentui/demo.ts` shows every
animation. Use ← → to switch, space to pause, `f`/`s` to toggle fit and scale.
Add `--cycle` to step through them automatically.

## Changing the art

Everything is drawn in `source/generate.py`: the sprite is the text grid near
the top, and each animation is a short function below it. After editing it, run
this (needs Pillow) to rebuild the GIFs, PNGs, `opentui/reelforge-frames.ts` and
`preview.html`:

```
python source/generate.py
```
