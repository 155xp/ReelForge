// The Overview's cards and titles never cut anything off; the big numbers, sparklines and the bell are block art in one
// colour per cell; release notes' Markdown reads as clean lists; the Python side's colours come out in the window's
// palette (src/dashboard/cards.ts, src/lib/fit.ts, src/ui/Graphics.tsx, src/ui/Panels.tsx, src/theme.ts).

import { describe, expect, test } from "bun:test"
import { cardLines, wrapLines } from "../src/dashboard/cards"
import { metricTitle, pickVariant } from "../src/dashboard/titles"
import type { MetricView, Variant } from "../src/dashboard/types"
import { fit } from "../src/lib/fit"
import { fmtNum, shortNum } from "../src/lib/format"
import { plain, segsLen, type Parts } from "../src/lib/styled"
import { PLATFORM, restyle, tone } from "../src/theme"
import { bell, BELL_WIDTH, faceCells, faceWidth, sparkline, stackedSparkline } from "../src/ui/Graphics"
import { inline, mdBlocks } from "../src/ui/Panels"

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

describe("release notes' Markdown", () => {
  const NOTES = [
    "## What's new in 1.0.5",
    "",
    "- **A new window, built with [OpenTUI](https://github.com/anomalyco/opentui).** ReelForge's window, setup's screens",
    "  and its questions are rebuilt on OpenTUI.",
    "- **Macs and Linux PCs.** Everything works there too.",
    "  - **One-line install:** paste `curl -fsSL https://x/install.sh | bash`",
    "    into Terminal.",
    "  - **Nothing to install first.**",
    "",
    "| Your computer | Download |",
    "|---|---|",
    "| **Windows** | `irm https://x \\| iex` |",
  ].join("\n")

  test("a wrapped bullet stays one item, nested ones go a level in, a table becomes items", () => {
    const blocks = mdBlocks(NOTES)
    expect(blocks.map((b) => b.kind)).toEqual(["heading", "gap", "item", "item", "item", "item", "gap", "item"])
    const items = blocks.filter((b) => b.kind === "item")
    expect(items.map((b) => b.depth)).toEqual([0, 0, 1, 1, 0])
    expect(items[0]!.text.endsWith("setup's screens and its questions are rebuilt on OpenTUI.")).toBe(true)
    expect(items[2]!.text).toBe("**One-line install:** paste `curl -fsSL https://x/install.sh | bash` into Terminal.")
    expect(items[4]!.text).toBe("**Windows**: `irm https://x | iex`")
  })

  test("a link inside bold shows as its text, still bold", () => {
    const segs = inline("**A window, built with [OpenTUI](https://x/y).** Rest \\*x\\*", "#fff", "#0f0")
    expect(plain(segs)).toBe("A window, built with OpenTUI. Rest *x*")
    expect(segs.find((s) => s[0] === "OpenTUI")![1]).toBe("underline bold #fff")
  })

  test("no gap at the start or the end, and blank lines never pile up", () => {
    const blocks = mdBlocks("\n\n\nHello\n\n\n\n---\n\n- one\n\n")
    expect(blocks.map((b) => b.kind)).toEqual(["para", "gap", "item"])
  })
})

describe("block art", () => {
  test("the bell is three rows of blocks in one colour", () => {
    for (const quads of [true, false]) {
      const rows = bell(quads, "#e8eaed")
      expect(rows.length).toBe(3)
      expect(new Set(rows.map((r) => r.length))).toEqual(new Set([BELL_WIDTH]))
      expect(new Set(rows.flat().filter((c) => c.ch !== " ").map((c) => c.fg))).toEqual(new Set(["#e8eaed"]))
    }
  })

  test("the big numbers: every character a tile shows has a shape, three rows tall, a column between characters", () => {
    for (const text of ["17.3K", "2.27K", "285", "2.66M", "1.2B", "0"]) {
      const rows = faceCells(text, ["#ffffff", "#888888"])
      expect(rows.length).toBe(3)
      expect(Math.max(...rows.map((r) => r.length))).toBe(faceWidth(text))
    }
    expect(faceWidth("17.3K")).toBe(17) // 3 + 1 + 3 + 1 + 1 + 1 + 3 + 1 + 3
    expect(faceWidth("1.2x")).toBe(Infinity) // a character it has no shape for: not drawn in the face at all
    const shades = faceCells("8", ["#ffffff", "#000000"]).map((r) => r.find((c) => c.fg)?.fg)
    expect(shades[0]).toBe("#ffffff") // white at the top, darker down the number
    expect(shades[2]).not.toBe("#ffffff")
  })

  test("sparklines keep to their size, eighths of a row, and grow in from nothing", () => {
    const data = [0, 1, 4, 9, 16, 25, 36, 49]
    const full = sparkline(data, 8, 2, "#25f4ee", "#12151a")
    expect(full.length).toBe(2)
    expect(full.every((r) => r.length === 8)).toBe(true)
    expect(full[0]![7]!.ch).toBe("█") // the newest, tallest reading fills its column
    const none = sparkline(data, 8, 2, "#25f4ee", "#12151a", 0)
    expect(none.flat().every((c) => c.ch === " " || c.ch === "▁")).toBe(true)
    const stacked = stackedSparkline([{ color: "#ff0000", values: [1, 2] }, { color: "#0000ff", values: [1, 2] }], 2, 2, "#000000")
    expect(stacked[0]![1]!.ch).toBe("█") // the tallest column reaches the top
    expect(stacked[1]![0]!.ch).toBe("▄") // two platforms in one cell: the lower as eighths on the upper's colour
    expect(stacked[1]![0]!.bg).not.toBeNull()
  })
})

describe("the palette", () => {
  test("the Python side's colours, in styles and on their own, come out in the window's", () => {
    expect(tone("#ff4040")).toBe(PLATFORM.youtube!) // YouTube's red
    expect(tone("bold #3dff9a on #1f5c45")).not.toContain("#3dff9a")
    expect(tone("#25f4ee")).toBe("#25f4ee") // TikTok's stays
    const msg = JSON.parse('{"d": {"color": "#FF4040", "caption": "#fyp #ff4040ish #facade"}}', restyle)
    expect(msg.d.color).toBe(PLATFORM.youtube!)
    expect(msg.d.caption).toBe("#fyp #ff4040ish #facade") // a hashtag is never a colour
  })
})
