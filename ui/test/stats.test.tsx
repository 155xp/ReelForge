// The Stats tab, drawn without a terminal on demo data with its real Python side: the pills that put a platform
// in or out of the totals, the ranges, the hover read-out, the breakdowns, and how it fits windows big and small.
// (What the Python side adds up is tested in dashboard/tests/test_totals.py.)

import { TextAttributes } from "@opentui/core"
import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText, find } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import { columns, exact, signed, timeLabels, trimmed } from "../src/dashboard/Stats"
import { TAB_NAMES } from "../src/dashboard/state"
import type { TotalsRow, TotalsView } from "../src/dashboard/types"
import type { Slot } from "../src/lib/chart"
import { cellLen } from "../src/lib/styled"

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }
setDefaultTimeout(30_000)
let open: Headless | null = null

async function window(size: [number, number] = [180, 50], tab = "totals"): Promise<Headless> {
  open = await headless("dashboard", { demo: true, only_demos: true, tab }, size[0], size[1], PRELOAD)
  await open.settle(2500)
  return open
}

afterEach(async () => {
  await open?.close()
  open = null
})

const frame = (h: Headless) => h.t.captureCharFrame()
const rows = (h: Headless) => frame(h).split("\n")
const view = (h: Headless) => h.bridge.view<TotalsView>("totals")!

function activeTab(h: Headless): string {
  const names = Object.values(TAB_NAMES) as string[]
  const lit = h.t.captureSpans().lines[1]!.spans.find((s) => s.attributes & TextAttributes.BOLD && names.includes(s.text.trim()))
  return lit?.text.trim() ?? ""
}

/** Wait (up to 5 s) until ok(): each look comes after a settle, so the frame is never read mid-draw. */
async function until(h: Headless, ok: () => boolean) {
  for (let i = 0; i < 25; i++) {
    await h.settle(200)
    if (ok()) return
  }
}

describe("the Stats tab", () => {
  test("8 opens it: both charts with their numbers, a breakdown beside each, the pills and the ranges", async () => {
    const h = await window([180, 50], "overview")
    h.t.mockInput.pressKey("8")
    await until(h, () => frame(h).includes("BY PLATFORM"))
    expect(activeTab(h)).toBe("Stats")
    const f = frame(h)
    for (const text of ["FOLLOWERS", "LIKES", "Add up", "✓ TikTok", "✓ YouTube", "✓ Instagram", "✓ X", "24H", "ALL", "Added up", "gained", "share"])
      expect(f).toContain(text)
    expect(f.split("BY PLATFORM").length - 1).toBe(2)
    const followers = view(h).metrics.followers!
    expect(f).toContain(exact(followers.total!.value))
    expect(f).toContain(signed(followers.total!.gained))
    expect(f).toMatch(/since \w+ \d+/) // ALL: since the first reading
  })

  test("a pill leaves its platform out of the totals, and back in", async () => {
    const h = await window()
    const before = view(h).metrics.followers!.total!.value!
    await clickText(h, "✓ X", 1)
    await until(h, () => frame(h).includes("○ X"))
    expect(frame(h)).toContain("○ X")
    expect(frame(h)).toContain("left out")
    const after = view(h).metrics.followers!.total!.value!
    expect(after).toBeLessThan(before)
    expect(frame(h)).toContain(exact(after))
    await clickText(h, "○ X", 1)
    await until(h, () => frame(h).includes("✓ X"))
    expect(view(h).metrics.followers!.total!.value).toBe(before)
    expect(frame(h)).not.toContain("left out")
  })

  test("the ranges change both charts", async () => {
    const h = await window()
    await clickText(h, "24H", 1)
    await until(h, () => frame(h).includes("in 24h"))
    expect(frame(h).split("in 24h").length - 1).toBe(2)
    expect(view(h).metrics.likes!.n).toBe(24)
    await clickText(h, "7D", 1)
    await until(h, () => frame(h).includes("in 7d"))
    expect(view(h).metrics.followers!.n).toBe(168)
  })

  test("pointing at a chart reads the totals then, with each platform's part", async () => {
    const h = await window()
    const title = find(h, "FOLLOWERS")!
    const before = rows(h)[title[1]]
    await h.t.mockMouse.moveTo(title[0] + 60, title[1] + 8)
    await h.settle(300)
    const line = rows(h)[title[1]]!
    expect(line).not.toBe(before)
    expect(line).toMatch(/FOLLOWERS\s+\S+.*\d/)
    expect(line).toContain("TT ")
  })

  for (const [w, hh] of [
    [212, 52],
    [180, 50],
    [130, 34],
    [110, 40],
    [100, 40],
  ] as const) {
    test(`at ${w}x${hh}: the header keeps every tab and the bell, and nothing runs off the window`, async () => {
      const h = await window([w, hh])
      const all = rows(h)
      for (const name of Object.values(TAB_NAMES)) expect(all[1]).toContain(name)
      expect(all[0]).toMatch(/\d▌\s*$/) // the bell's unread count, in the top right corner
      for (const r of all) expect(cellLen(r)).toBeLessThanOrEqual(w)
      expect(frame(h)).toContain("FOLLOWERS")
      expect(frame(h)).toContain("BY PLATFORM")
      expect(frame(h)).toContain("Add up")
    })
  }
})

describe("its pieces", () => {
  const row = (name: string, value: number, gained: number, gains: (number | null)[]): TotalsRow => ({
    key: name.toLowerCase(),
    name,
    short: name.slice(0, 2),
    color: "#25f4ee",
    counted: true,
    left_out: false,
    value,
    gained,
    share: 0.5,
    gains,
    stale: null,
  })

  test("the breakdown's columns fit the width they get, numbers in full", () => {
    const rs = [row("TikTok", 127_812, 124_539, [1, 2]), row("Instagram", 39_380, 37_595, [3])]
    for (const w of [30, 46, 56, 90]) {
      const c = columns(rs, { value: 167_192, gained: 162_134 }, w)
      expect(c.name + c.now + 2 + c.gain + c.rest).toBe(w)
      expect(c.now).toBe("167,192".length)
      expect(c.gain).toBe("+162,134".length)
    }
    expect(columns(rs, null as never, 30).spark).toBe(0) // no room: no sparkline
    expect(columns(rs, null as never, 56).spark).toBeGreaterThan(6)
  })

  test("every platform's sparkline starts where the first one has a gain, so they line up", () => {
    const g = trimmed([row("A", 1, 1, [null, null, 1, 2]), row("B", 1, 1, [null, 4, 5, 6])])
    expect(g).toEqual([
      [null, 1, 2],
      [4, 5, 6],
    ])
  })

  test("a long chart's time axis shows dates, a week or less the hours and weekdays", () => {
    const slots = (n: number, stepH: number): Slot[] =>
      Array.from({ length: n }, (_, i) => {
        const hour = (i * stepH) % 24
        const day = 1 + Math.floor((i * stepH) / 24)
        return { label: "", when: "", hour, day, weekday: "Mon", clock: `${hour}`, date: `Oct ${day}`, }
      })
    const long = timeLabels(slots(132, 2), 110, 2)
    expect(long.every(([, l]) => l.startsWith("Oct "))).toBe(true)
    expect(long[long.length - 1]![1]).toBe("Oct 11") // today always has its date
    const week = timeLabels(slots(168, 1), 110, 1)
    expect(week.some(([, l]) => l === "Mon")).toBe(true)
  })

  test("numbers in full: 21,034, +1,203 and −40", () => {
    expect(exact(21_034.4)).toBe("21,034")
    expect(exact(null)).toBe("—")
    expect(signed(1_203)).toBe("+1,203")
    expect(signed(-40)).toBe("−40")
    expect(signed(null)).toBe("")
  })
})
