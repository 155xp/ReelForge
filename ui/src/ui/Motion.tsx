// Motion: numbers that count up to where they're going, charts that grow in, the tab marker that slides, pop-ups that
// fade. Each runs on OpenTUI's timeline engine, which keeps the renderer drawing only while something moves (and in
// the tests and screenshots, which draw a frame now and then, jumps to the end).
//
// REELFORGE_MOTION=0 turns it all off: everything shows where it ends up straight away.

import { createTimeline, getTimelineEngine, type EasingFunctions } from "@opentui/core"
import { useRenderer } from "@opentui/react"
import { useEffect, useRef, useState } from "react"

export const MOTION = process.env.REELFORGE_MOTION !== "0"

export interface TweenOptions {
  /** Where it starts the first time (a count-up starts at 0); by default, where it's going. */
  from?: number
  ms?: number
  ease?: EasingFunctions
  delay?: number
}

/** A number easing to `target`: from `from` the first time, then from wherever it is when the target changes. */
export function useTween(target: number, { from, ms = 600, ease = "outExpo", delay = 0 }: TweenOptions = {}): number {
  const renderer = useRenderer()
  const [shown, setShown] = useState(MOTION && from !== undefined && Number.isFinite(target) ? from : target)
  const now = useRef(shown)
  now.current = shown
  useEffect(() => {
    const start = now.current
    if (!MOTION || start === target || !Number.isFinite(target) || !Number.isFinite(start)) {
      setShown(target)
      return
    }
    const box = { v: start }
    const tl = createTimeline({ duration: ms + delay + 1 }, renderer)
    tl.add(box, { v: target, duration: ms, ease, onUpdate: () => setShown(box.v), onComplete: () => setShown(target) }, delay)
    return () => {
      tl.pause()
      getTimelineEngine(renderer).unregister(tl)
    }
  }, [target, renderer])
  return shown
}

/** 0 to 1 over `ms`, again whenever `key` changes: a chart growing in, a panel fading in. */
export function useProgress(key: unknown, { ms = 700, ease = "outCirc", delay = 0 }: Omit<TweenOptions, "from"> = {}): number {
  const renderer = useRenderer()
  const [p, setP] = useState(MOTION ? 0 : 1)
  useEffect(() => {
    if (!MOTION) return
    setP(0)
    const box = { v: 0 }
    const tl = createTimeline({ duration: ms + delay + 1 }, renderer)
    tl.add(box, { v: 1, duration: ms, ease, onUpdate: () => setP(box.v), onComplete: () => setP(1) }, delay)
    return () => {
      tl.pause()
      getTimelineEngine(renderer).unregister(tl)
    }
  }, [key, renderer])
  return p
}
