// The mascot (src/ui/Mascot.tsx): drawn in half blocks at his fixed size, moving on his own timer without keeping the
// renderer's frame loop going, playing an intro once before his loop, and holding his best frame for pictures. Then
// where he stands: beside first-time setup's screens when the window has room (and not when it hasn't), under the
// channel questions' steps, beside the Updates tab, and asleep in an empty notifications drawer.

import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { join } from "node:path"
import { createTestRenderer } from "@opentui/core/testing"
import { createRoot } from "@opentui/react"
import { headless, type Headless } from "../scripts/headless"
import { find } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import type { SetupInit } from "../src/setup/App"
import { frameLayout } from "../src/setup/Frame"
import { MASCOT, Mascot } from "../src/ui/Mascot"
import { ANIMATIONS, MascotRenderable } from "../src/ui/mascot/reelforge-mascot"

async function draw(node: React.ReactNode, ms = 0) {
  const t = await createTestRenderer({ width: 60, height: 24 })
  const root = createRoot(t.renderer)
  root.render(node)
  await t.renderOnce()
  if (ms) await Bun.sleep(ms)
  await t.renderOnce()
  return {
    t,
    text: () => t.captureCharFrame(),
    close: () => {
      root.unmount()
      t.renderer.destroy()
    },
  }
}

const blocks = (frame: string) => [...frame].filter((c) => c === "▀" || c === "▄").length

describe("mascot", () => {
  test("his size", () => {
    expect(MASCOT).toEqual({ width: 43, height: 18 })
  })

  test("drawn in half blocks, inside his 43 x 18 cells", async () => {
    const d = await draw(<Mascot animation="idle" />)
    const rows = d.text().split("\n")
    expect(blocks(d.text())).toBeGreaterThan(200)
    rows.forEach((row, y) => {
      const used = [...row].map((c, x) => (c === " " ? -1 : x)).filter((x) => x >= 0)
      if (y >= MASCOT.height) expect(used).toEqual([])
      else for (const x of used) expect(x).toBeLessThan(MASCOT.width)
    })
    d.close()
  })

  test("moves on his own timer, and never keeps the frame loop running", async () => {
    const d = await draw(<Mascot animation="forge" />)
    const first = d.text()
    const live = (r: { live: boolean; getChildren: () => unknown[] }): boolean =>
      r.live || r.getChildren().some((c) => live(c as typeof r))
    expect(live(d.t.renderer.root as never)).toBe(false)
    await Bun.sleep(400)
    await d.t.renderOnce()
    expect(d.text()).not.toBe(first)
    d.close()
  })

  test("plays the intro once, then his loop", async () => {
    const total = ANIMATIONS.success.durations.reduce((a, b) => a + b, 0)
    const done: string[] = []
    const t = await createTestRenderer({ width: 60, height: 24 })
    const m = new MascotRenderable(t.renderer, { animation: "success", loop: false, onComplete: (a) => done.push(a) })
    t.renderer.root.add(m)
    await Bun.sleep(total + 150)
    expect(done).toEqual(["success"])
    expect(m.playing).toBe(false)
    expect(m.frameIndex).toBe(ANIMATIONS.success.frames.length - 1)
    t.renderer.destroy()

    const d = await draw(<Mascot once="wink" animation="idle" />, ANIMATIONS.wink.durations.reduce((a, b) => a + b, 0) + 60)
    const idle = await draw(<Mascot animation="idle" />)
    // back on the idle loop, at its first frame
    expect(d.text()).toBe(idle.text())
    d.close()
    idle.close()
  })

  test("holds a pose for pictures", async () => {
    const t = await createTestRenderer({ width: 60, height: 24 })
    const m = new MascotRenderable(t.renderer, { animation: "forge" })
    t.renderer.root.add(m)
    m.hold(3)
    await Bun.sleep(300)
    expect(m.frameIndex).toBe(3)
    expect(m.playing).toBe(false)
    t.renderer.destroy()
  })
})

// ---------------------------------------------------------------- where he stands

/** A logo grid of w x h cells, for the frame's layout. */
const grid = (w: number, h: number) => Array.from({ length: h }, () => Array.from({ length: w }, () => [" ", null, null] as [string, null, null]))
const INIT = { big: grid(95, 8), anvil: grid(11, 3) } as unknown as SetupInit

describe("the setup frame's room for him", () => {
  test("beside the content under the small logo in a 120 x 30 terminal, and the full logo once it's tall enough", () => {
    expect(frameLayout(INIT, 120, 30, 30, true)).toEqual({ logo: "anvil", mascot: true, content: 69, rows: 24 })
    expect(frameLayout(INIT, 122, 30, 30, false)).toEqual({ logo: "big", mascot: false, content: 116, rows: 18 })
    expect(frameLayout(INIT, 150, 42, 30, true)).toEqual({ logo: "big", mascot: true, content: 99, rows: 30 })
  })

  test("not when the content would get too narrow, or the window is short", () => {
    expect(frameLayout(INIT, 110, 40, 30, true).mascot).toBe(false)
    expect(frameLayout(INIT, 140, 25, 30, true)).toEqual({ logo: null, mascot: false, content: 134, rows: 23 })
  })
})

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }

/** He's drawn (rows of his half blocks) from this column on, below the window's top 5 rows (where its bell is drawn
 * the same way). */
const drawnAt = (h: Headless, from: number) =>
  h.t
    .captureCharFrame()
    .split("\n")
    .slice(5)
    .some((row) => [...row].slice(from).filter((c) => c === "▀" || c === "▄").length > 10)

describe("where he shows up", () => {
  setDefaultTimeout(30_000)
  let open: Headless | null = null
  afterEach(async () => {
    await open?.close()
    open = null
  })

  test("first-time setup: beside the tools in a 122 x 30 terminal, with every tool still on screen", async () => {
    open = await headless("setup", { start: "tools", preview: true }, 122, 30, PRELOAD)
    for (let i = 0; i < 40 && !find(open, "Desktop shortcut"); i++) await open.settle(100)
    expect(drawnAt(open, 75)).toBe(true)
    expect(find(open, "Downloads come only from the official sites")).not.toBeNull()
    expect(find(open, "Set up (about 570 MB)")).not.toBeNull()
  })

  test("first-time setup: not in a narrow terminal, which keeps its layout", async () => {
    open = await headless("setup", { start: "tools", preview: true }, 100, 30, PRELOAD)
    for (let i = 0; i < 40 && !find(open, "Desktop shortcut"); i++) await open.settle(100)
    expect(drawnAt(open, 60)).toBe(false)
  })

  test("the channel's questions: under the list of steps", async () => {
    open = await headless("setup", { start: "onboard", preview: true }, 122, 30, PRELOAD)
    await open.settle(2000)
    const rows = open.t.captureCharFrame().split("\n")
    const list = rows.findIndex((r) => r.includes("Review"))
    expect(list).toBeGreaterThan(0)
    expect(rows.slice(list + 1).some((r) => [...r].slice(0, 40).filter((c) => c === "▀" || c === "▄").length > 10)).toBe(true)
  })

  test("the Updates tab: beside the panels", async () => {
    open = await headless("dashboard", { demo: true, only_demos: true, tab: "updates" }, 180, 50, PRELOAD)
    await open.settle(2500)
    expect(drawnAt(open, 130)).toBe(true)
  })

  test("asleep in an empty notifications drawer, over what it says", async () => {
    open = await headless("dashboard", { demo: true, only_demos: true, tab: "overview", drawer: true }, 122, 30, PRELOAD)
    await open.settle(2500)
    open.bridge.emit("notes", { ...open.bridge.view<object>("notes"), items: [] })
    await open.settle(400)
    const rows = open.t.captureCharFrame().split("\n")
    const text = rows.findIndex((r) => r.includes("Nothing yet."))
    expect(text).toBeGreaterThan(0)
    // his feet are on the row above it, not under it
    expect([...rows[text - 1]!].slice(75).some((c) => c === "▀")).toBe(true)
    expect([...rows[text]!].slice(75).some((c) => c === "▀" || c === "▄")).toBe(false)
  })
})
