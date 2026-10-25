// The Overview's cards and titles never cut anything off, and the bell and a notification's × are block art in one
// colour per cell (src/dashboard/cards.ts, src/lib/fit.ts, src/ui/Graphics.tsx).

import { describe, expect, test } from "bun:test"
import { cardLines, wrapLines } from "../src/dashboard/cards"
import { metricTitle, pickVariant } from "../src/dashboard/titles"
import type { MetricView, Variant } from "../src/dashboard/types"
import { fit } from "../src/lib/fit"
import { fmtNum, shortNum } from "../src/lib/format"
import { plain, segsLen, type Parts } from "../src/lib/styled"
import { BELL } from "../src/theme"
import { bell, cross, X_WIDTH } from "../src/ui/Graphics"

const VALUES = { followers: 12_900, views: 1_234_567, likes: 98_765 }
const CHANGES = { followers: 1_030, views: 19_400, likes: -40 }

describe("cards", () => {
  test("short numbers", () => {
    const cases: [number | null, string][] = [
      [null, "—"], [999, "999"], [1_030, "1K"], [9_940, "9.9K"], [12_900, "13K"], [999_600, "1M"], [1_234_567, "1.2M"],
      [-19_400, "-19K"],
    ]
    for (const [n, text] of cases) expect(shortNum(n)).toBe(text)
    expect([fmtNum(950), fmtNum(1_234), fmtNum(12_345), fmtNum(1_234_567)]).toEqual(["950", "1.23K", "12.3K", "1.23M"])
  })

  test("card lines always fit", () => {
    for (let width = 0; width < 60; width++) {
      for (const line of cardLines(VALUES, CHANGES, width)) {
        expect(segsLen(line)).toBeLessThanOrEqual(width)
        expect(plain(line)).not.toContain("…")
      }
    }
  })

  test("card lines shorten in order", () => {
    const lines = (width: number) => cardLines(VALUES, CHANGES, width).map(plain)
    expect(lines(40)[0]).toBe("  12.9K followers +1.03K 24h") // room for everything
    expect(lines(24)[0]).toBe("12.9K followers +1.03K") // the " 24h" goes first
    expect(lines(21)).toEqual(["12.9K followers +1K", "1.23M views     +19K", "98.8K likes     −40"])
    expect(lines(13)).toEqual(["13K followers", "1.2M views", "99K likes"]) // labels outlast the changes
    expect(lines(5)).toEqual([" 13K", "1.2M", " 99K"])
  })

  test("messages wrap instead of cutting off", () => {
    const text = [[["not tracking yet", ""]], [["Accounts tab: add your handle", ""]]] as [string, string][][]
    expect(wrapLines(text, 20).map(plain)).toEqual(["not tracking yet", "Accounts tab: add", "your handle"])
  })

  test("titles drop whole parts", () => {
    const parts: Parts = [
      [[["LIKES  ", ""]], 0],
      [[["198.6K total   ", ""]], 0],
      [[["+38K in 24h", ""]], 1],
    ]
    expect(plain(fit(parts, 30))).toBe("LIKES  198.6K total   ")
    expect(plain(fit(parts, 12))).toBe("LIKES  ") // not "LIKES  198.6"
  })
})

describe("chart titles", () => {
  const slot = (i: number) => ({ label: `Fri ${i} PM`, when: `at ${i} PM`, hour: i, day: 24, weekday: "Fri", clock: `${i} PM`, date: "Oct 24" })
  const variant = (step: number, n: number): Variant => ({
    step_h: step,
    n,
    unit: step === 1 ? "per hour" : `per ${step}h`,
    slots: Array.from({ length: n }, (_, i) => slot(i)),
    series: [{ key: "tiktok", name: "TikTok", color: "#25f4ee", values: Array.from({ length: n }, (_, i) => i + 1) }],
    marks: [],
  })

  test("a narrow chart draws combined buckets: two columns and a gap a bar, or one and a gap", () => {
    const variants = [variant(1, 24), variant(2, 12), variant(3, 8)]
    expect(pickVariant(variants, 72).step_h).toBe(1) // 24 bars x 3 columns
    expect(pickVariant(variants, 50).step_h).toBe(2)
    expect(pickVariant(variants, 30).step_h).toBe(3) // two columns and a gap at 3 hours beats one column at 1
    expect(pickVariant([variant(1, 24), variant(2, 12)], 30).step_h).toBe(2) // else one column and a gap
    expect(pickVariant(variants, 10).step_h).toBe(3) // the coarsest when nothing fits
  })

  test("the title reads the hovered bar's numbers", () => {
    const m: MetricView = { span: "24h", hourly: true, summary: { latest: 52_000, gained: 1_200, pace: 80, change: 0.25 } }
    const v = variant(1, 24)
    const still = plain(fit(metricTitle("views", m, v, null), 200))
    expect(still).toContain("VIEWS  per hour   52.0K total   +1.20K in 24h   now 80/h   ▲ 25% vs the 24h before")
    expect(still).toContain("best 24 at 23 PM")
    const hovered = plain(fit(metricTitle("views", m, v, 5), 200))
    expect(hovered).toBe("VIEWS  Fri 5 PM  +6  TT 6  ")
  })
})

describe("block art", () => {
  test("the bell is three rows of blocks, with its red dot only while something is unread", () => {
    for (const quads of [true, false]) {
      for (const unread of [false, true]) {
        const rows = bell(unread, quads, "#ff4d5e")
        expect(rows.length).toBe(3)
        expect(new Set(rows.map((r) => r.length))).toEqual(new Set([8]))
        const colours = new Set(rows.flat().filter((c) => c.ch !== " ").map((c) => c.fg))
        expect(colours).toEqual(new Set(unread ? [BELL, "#ff4d5e"] : [BELL]))
      }
    }
  })

  test("a notification's × is three rows, or four (half a row lower) beside an even number of lines", () => {
    for (const quads of [true, false]) {
      for (let lines = 1; lines <= 6; lines++) {
        const rows = cross(lines, quads, "#6e7681")
        expect(rows.length).toBe(lines % 2 === 0 && lines > 2 ? 4 : 3)
        expect(Math.max(...rows.map((r) => r.length))).toBe(X_WIDTH)
      }
    }
  })
})
