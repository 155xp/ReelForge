// The charts in cells: round-number axes, bar heights to the eighth, areas, marks (src/lib/chart.ts).

import { describe, expect, test } from "bun:test"
import {
  ageLabels,
  bars,
  Canvas,
  clockLabels,
  EIGHTHS,
  fmtTick,
  HOVER,
  internals,
  Layout,
  lines,
  niceRange,
  yLabels,
  type Cell,
  type Series,
  type Slot,
} from "../src/lib/chart"

const plain = (row: Cell[]) => row.map((c) => c.ch).join("")
const series = (key: string, color: string, values: (number | null)[]): Series => ({ key, name: key, color, values })

describe("axes", () => {
  test("nice ranges", () => {
    expect(niceRange(0, 23, 4)).toEqual([0, 25, 5])
    expect(niceRange(0, 0.4, 4)).toEqual([0, 1, 1]) // counts step by whole numbers
    const [lo, hi, step] = niceRange(1180, 1630, 3, false)
    expect(lo).toBeLessThanOrEqual(1180)
    expect(hi).toBeGreaterThanOrEqual(1630)
    expect([100, 200, 250]).toContain(step)
  })

  test("tick labels", () => {
    expect([0, 250, 2500, 10000, 1_200_000].map((v) => fmtTick(v))).toEqual(["0", "250", "2.5K", "10K", "1.2M"])
  })

  test("count axes use whole round steps", () => {
    for (const hi of [7, 10, 23, 99, 1000, 2500, 33333]) {
      const [, top, step] = niceRange(0, hi, 4)
      expect(step).toBe(Math.round(step))
      const mantissa = step / 10 ** Math.floor(Math.log10(step))
      expect([1, 2, 2.5, 5]).toContain(Math.round(mantissa * 1e6) / 1e6)
      expect(top).toBeGreaterThanOrEqual(hi)
    }
  })

  test("axis labels stay distinct", () => {
    for (const ys of [[1001, 1004], [1001, 1003], [1234567, 1234567, 1234567, 1234567], [52340, 52351]]) {
      const [lo, hi] = internals.hug(ys)
      const labels = [...yLabels(internals.layout(60, 10, lo, hi, true, true)).values()]
      expect(new Set(labels).size).toBe(labels.length)
    }
  })

  test("time axes: round hours, the weekday at midnight, dates for days", () => {
    const hours: Slot[] = Array.from({ length: 24 }, (_, i) => ({
      label: "", when: "", hour: i, day: 1, weekday: "Fri", clock: `${i % 12 || 12} ${i < 12 ? "AM" : "PM"}`, date: "Oct 1",
    }))
    const labels = clockLabels(hours, 96, 1)
    expect(labels[0]).toEqual([0, "Fri"])
    expect(labels.map((l) => l[1])).toContain("6 AM")
    const days: Slot[] = Array.from({ length: 30 }, (_, i) => ({
      label: "", when: "", hour: 0, day: i + 1, weekday: "Mon", clock: "12 AM", date: `Oct ${i + 1}`,
    }))
    const daily = clockLabels(days, 120, 24)
    expect(daily[daily.length - 1]).toEqual([29.5, "Oct 30"]) // counted back from today
  })
})

describe("bars", () => {
  test("size and heights", () => {
    const { rows, lay } = bars([series("a", "#25f4ee", [0, 4, 8, null])], 4, 40, 12, [[0, "x"]])
    expect(rows.length).toBe(12)
    expect(rows.every((r) => r.length <= 40)).toBe(true)
    expect(lay.hi).toBeGreaterThanOrEqual(8) // the tallest bar fits under the top of the axis
    expect(plain(rows[rows.length - 1]!)).toContain("x")
  })

  test("stacks have no slivers", () => {
    // Inside a stack every cell is one colour (the platform filling most of it); a platform too thin to see joins its
    // neighbour, and only the top cell is a partial block.
    const a = series("a", "#ff0000", [1.5, 9.0, 4.0])
    const b = series("b", "#0000ff", [1.5, 2.6, 0.0])
    const x = series("x", "#ffffff", [0.1, 0.1, 0.1]) // the white X series: never a white sliver
    const { rows, lay } = bars([a, b, x], 3, 40, 14)
    for (const row of rows.slice(0, lay.ph)) {
      for (const cell of row.slice(lay.lw + 1)) {
        if (EIGHTHS.slice(1, 8).includes(cell.ch)) expect([null, HOVER]).toContain(cell.bg)
        expect([cell.fg, cell.bg]).not.toContain("#ffffff")
      }
    }
  })

  test("a thin top joins the cell below", () => {
    // Red fills four rows exactly and white adds an eighth: the top eighth is red, not a white line. White filling
    // most of a row's top piece does show.
    const lay = new Layout(2, 1, 6, 0, 10, 5)
    for (const [whiteTop, color] of [
      [33, "#ff0000"],
      [38, "#ffffff"],
    ] as const) {
      const canvas = new Canvas(1, 6)
      internals.stack(canvas, lay, [0, 1], [
        [0, 32, "#ff0000"],
        [32, whiteTop, "#ffffff"],
      ])
      const cell = canvas.get(lay.ph - 1 - 4, 0)
      expect([cell.ch, cell.fg]).toEqual([EIGHTHS[whiteTop - 32]!, color])
    }
  })

  test("bars keep a gap", () => {
    // Two or more columns per slot: every bar is the same width with a one-column gap after it.
    const a = series("a", "#25f4ee", Array(12).fill(5))
    for (const w of [40, 47, 60, 75, 100]) {
      const { rows, lay } = bars([a], 12, w, 8)
      const bottom = rows[lay.ph - 1]!.slice(lay.lw + 1).map((c) => (c.bg === "#25f4ee" ? "#" : ".")).join("")
      const runs = bottom.split(".").filter(Boolean).map((r) => r.length)
      expect(runs.length).toBe(12)
      expect(new Set(runs).size).toBe(1) // all the same width
    }
  })

  test("bars use the whole width", () => {
    const { rows, lay } = bars([series("a", "#25f4ee", [1, 2, 3])], 3, 50, 10)
    expect(lay.lw + 1 + lay.pw).toBe(50)
    expect(rows.every((r) => r.length <= 50)).toBe(true)
  })

  test("hover maps every column back to its bar", () => {
    for (const slots of [7, 24, 28, 30, 48]) {
      for (const w of [40, 63, 100, 137, 200]) {
        const a = series("a", "#25f4ee", Array.from({ length: slots }, (_, i) => (i % 5) + 1))
        const { rows, lay } = bars([a], slots, w, 12)
        expect(rows.every((r) => r.length <= w)).toBe(true)
        for (let c = 0; c < lay.pw; c++) {
          const slot = lay.slotAt(c)
          expect(slot).not.toBeNull()
          const [start, end] = lay.columns(slot!)
          expect(c >= start && c < end).toBe(true)
        }
      }
    }
  })

  test("more slots than columns keeps the newest", () => {
    const a = series("a", "#25f4ee", Array.from({ length: 48 }, (_, i) => (i % 2 === 0 ? 10 : 1)))
    const { lay } = bars([a], 48, 40, 10)
    expect(lay.first + lay.slots).toBe(48)
    expect(lay.slots).toBeLessThanOrEqual(lay.pw)
  })
})

describe("lines and marks", () => {
  test("area and line", () => {
    const area: Series = { key: "this", name: "this", color: "#25f4ee", xs: [0, 5, 10], ys: [0, 50, 100], style: "area" }
    const line: Series = { key: "typical", name: "typical", color: "#ffb020", xs: [0, 10], ys: [0, 60] }
    const { rows } = lines([area, line], 10, 60, 14, (pw) => ageLabels(10, pw), [], null, true)
    expect(rows.length).toBe(14)
    const body = rows.map(plain).join("")
    expect([..."─╭╯╮╰"].some((ch) => body.includes(ch))).toBe(true)
  })

  test("marks close together share a label", () => {
    const canvas = new Canvas(40, 6)
    const lay = new Layout(2, 40, 6, 0, 10, 5)
    internals.marksOn(canvas, lay, [
      { x: 5.0, label: "one" },
      { x: 5.05, label: "two" },
      { x: 30, label: "far" },
    ])
    const top = plain(canvas.row(0))
    expect(top).toContain("one + two")
    expect(top).toContain("far")
  })

  test("marks get a clear top row", () => {
    const { rows } = bars([series("a", "#25f4ee", Array(10).fill(10))], 10, 60, 12, [], [{ x: 5.5, label: "car" }])
    expect(plain(rows[0]!)).toContain("▼ car")
  })

  test("marks and labels land on their bars", () => {
    // A mark late in a bucket, and a label in the middle of one, point at that bucket's bar, not the gap after it.
    const xl: [number, string][] = Array.from({ length: 6 }, (_, i) => [i + 0.5, "x"])
    const { rows, lay } = bars([series("a", "#25f4ee", Array(6).fill(1))], 6, 30, 10, xl, [{ x: 1.9, label: "car" }])
    expect(lay.per - lay.bar).toBeGreaterThan(1)
    const start = lay.columns(1)[0]
    const at = plain(rows[0]!).indexOf("▼") - lay.lw - 1
    expect(at >= start && at < start + lay.bar).toBe(true)
    const axis = plain(rows[lay.ph]!).slice(lay.lw + 1)
    for (let i = 0; i < 6; i++) {
      const c = lay.col(i + 0.5)
      expect(axis[c]).toBe("┬")
      const s = lay.columns(i)[0]
      expect(c >= s && c < s + lay.bar).toBe(true)
    }
  })

  test("crowded marks are shortened, not dropped", () => {
    const canvas = new Canvas(18, 6)
    const lay = new Layout(2, 18, 6, 0, 10, 5)
    internals.marksOn(canvas, lay, [
      { x: 0.2, label: "world dropped" },
      { x: 12.2, label: "raindrop size" },
    ])
    const top = plain(canvas.row(0))
    expect(top.split("▼").length - 1).toBe(2)
    expect(top.startsWith("▼ wor") && top.includes("▼ rai")).toBe(true)
  })

  test("a mark with no room is left out", () => {
    const canvas = new Canvas(20, 6)
    const lay = new Layout(2, 20, 6, 0, 10, 5)
    for (let c = 0; c < 20; c++) canvas.put(0, c, " ", null, "#25f4ee") // a bar fills the top row
    internals.marksOn(canvas, lay, [{ x: 8, label: "car" }])
    const body = Array.from({ length: 6 }, (_, r) => plain(canvas.row(r))).join("")
    expect(body).not.toContain("▼") // no arrow that doesn't say what it is
    expect(body).not.toContain("┊")
  })
})
