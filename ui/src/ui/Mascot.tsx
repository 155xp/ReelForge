// ReelForge's mascot: the anvil with eyes (assets/mascot), animated in cells. He winks hello on first-time setup,
// hammers while something downloads, thinks while the health check runs, hops when it's done, frowns when it failed,
// glances at each step of the channel's questions, and snoozes where there's nothing yet.
// The pictures of the window (scripts/shots.tsx, REELFORGE_MASCOT_STILL=1) hold each one on its best frame, and so
// does REELFORGE_MOTION=0, for anyone who'd rather he kept still.

import type { Renderable } from "@opentui/core"
import { extend } from "@opentui/react"
import { useState, type ReactNode } from "react"
import { mascotSize, MascotRenderable, type MascotAnimation, type MascotFit } from "./mascot/reelforge-mascot"

export type { MascotAnimation } from "./mascot/reelforge-mascot"

declare module "@opentui/react" {
  interface OpenTUIComponents {
    reelforgeMascot: typeof MascotRenderable
  }
}

extend({ reelforgeMascot: MascotRenderable })

/** The frame each animation is held on: the hammer coming down, the top of the hop, the wink. */
const POSE: Record<MascotAnimation, number> = {
  idle: 0,
  look: 2,
  forge: 3,
  think: 3,
  success: 5,
  error: 2,
  sleep: 0,
  heat: 4,
  wink: 4,
}

/** Held still: for pictures, or when he should be (read each time, so a script can set it after importing this). */
const still = () => Boolean(process.env.REELFORGE_MASCOT_STILL) || process.env.REELFORGE_MOTION === "0"

/** His size in cells with room for everything he does (the hammer, the hop, the Zzz): 43 x 18, the same for every
 * animation, so switching never moves anything. */
export const MASCOT = mascotSize("idle")
/** Just the anvil, for the animations that stay inside it (idle, look, wink): 35 x 11. */
export const MASCOT_BODY = mascotSize("idle", "animation")

/**
 * The mascot playing `animation` over and over, after playing `once` (if given) one time. A new `cue` plays `once`
 * again: `<Mascot once="look" cue={step} animation="idle" />` glances round at each new step. Held still, he shows
 * `once` (the moment the screen is about), else `animation`.
 */
export function Mascot({
  animation,
  once,
  cue = 0,
  fit,
  marginLeft,
  marginRight,
  marginTop,
}: {
  animation: MascotAnimation
  once?: MascotAnimation
  cue?: string | number
  /** "animation": only the anvil (MASCOT_BODY), for idle, look and wink; by default all of MASCOT. */
  fit?: MascotFit
  marginLeft?: number
  marginRight?: number
  marginTop?: number
}) {
  const id = `${once ?? ""}|${cue}`
  const [played, setPlayed] = useState<string | null>(null)
  const held = still()
  const intro = Boolean(once) && played !== id && !held
  const current = intro ? once! : animation
  const layout = { marginLeft, marginRight, marginTop, flexShrink: 0, fit }
  if (held) {
    const pose = once ?? animation
    return (
      <reelforgeMascot
        key={pose}
        {...layout}
        animation={pose}
        playing={false}
        ref={(r: MascotRenderable | null) => r?.hold(POSE[pose])}
      />
    )
  }
  return (
    <reelforgeMascot
      // a fresh one for each change, so the intro always starts at its first frame and the loop after it too
      key={`${current}|${intro ? id : "loop"}`}
      {...layout}
      animation={current}
      loop={!intro}
      onComplete={() => setPlayed(id)}
    />
  )
}

/** Where there's nothing yet: the mascot asleep over what it says, both in the middle, when the space has room for him
 * and two more rows; otherwise just what it says, as it was. (Moved down a whole number of rows: centring by half a
 * row would draw what it says over his feet.) */
export function Asleep({ children }: { children: ReactNode }) {
  const [room, setRoom] = useState<[number, number]>([0, 0])
  const fits = room[0] >= MASCOT.width && room[1] >= MASCOT.height + 2
  return (
    <box
      flexGrow={1}
      flexDirection="column"
      alignItems={fits ? "center" : "stretch"}
      paddingTop={fits ? Math.floor((room[1] - MASCOT.height - 2) / 2) : 0}
      onSizeChange={function (this: Renderable) {
        setRoom([this.width, this.height])
      }}
    >
      {fits ? <Mascot animation="sleep" /> : null}
      {children}
    </box>
  )
}
