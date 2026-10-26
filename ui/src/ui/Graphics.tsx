// Small pictures made of cells: sparklines (one series, or the platforms stacked), the big numbers on the Overview's
// tiles, a progress bar, sections of horizontal bars (Compare), and the block art (the anvil from the Python side, the
// bell).

import type { Renderable } from "@opentui/core"
import { useState } from "react"
import type { Cell } from "../lib/chart"
import type { Segs } from "../lib/styled"
import { along, BELL, mix } from "../theme"
import { Cells } from "./Cells"
import { Line } from "./Line"

const EIGHTHS = " ▁▂▃▄▅▆▇█"
const LEFT_EIGHTHS = " ▏▎▍▌▋▊▉"
export const QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█" // by the parts filled: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right

function blank(): Cell {
  return { ch: " ", fg: null, bg: null }
}

function buckets(data: number[], width: number): number[] {
  const out: number[] = []
  for (let i = 0; i < width; i++) {
    const a = Math.floor((i * data.length) / width)
    const b = Math.max(Math.floor(((i + 1) * data.length) / width), a + 1)
    out.push(Math.max(...data.slice(a, b).map((v) => (Number.isFinite(v) ? v : 0))))
  }
  return out
}

/** Bars for a list of numbers, `height` rows tall, each to an eighth of a row. Older readings (the left) are dimmer and
 * every column is lighter towards its top, so the newest hours stand out. Wider data is cut into `width` buckets, each
 * showing its largest number; grow (0..1) is how far the bars have risen (the opening animation). */
export function sparkline(data: number[], width: number, height: number, color: string, background: string, grow = 1): Cell[][] {
  const rows: Cell[][] = Array.from({ length: height }, () => Array.from({ length: width }, blank))
  if (!data.length || width <= 0) return rows
  const cols = buckets(data, width)
  const hi = Math.max(...cols)
  if (!(hi > 0)) return rows
  cols.forEach((v, x) => {
    const eighths = Math.max(v > 0 ? 1 : 0, Math.round((v / hi) * height * 8 * grow))
    const age = 0.4 + 0.6 * (x / Math.max(width - 1, 1))
    for (let k = 0; k < height; k++) {
      const left = eighths - k * 8
      if (left <= 0) break
      const lift = 0.55 + 0.45 * ((k + 1) / height)
      rows[height - 1 - k]![x] = { ch: EIGHTHS[Math.min(left, 8)]!, fg: mix(background, color, age * lift), bg: null }
    }
  })
  return rows
}

export interface Stacked {
  color: string
  values: number[]
}

/** The platforms' sparklines stacked (the All platforms tile): each column split between them, newer columns brighter.
 * Where two platforms meet inside a cell, the lower one is drawn as eighths on the upper one's colour. */
export function stackedSparkline(stacks: Stacked[], width: number, height: number, background: string, grow = 1): Cell[][] {
  const rows: Cell[][] = Array.from({ length: height }, () => Array.from({ length: width }, blank))
  const n = Math.max(0, ...stacks.map((s) => s.values.length))
  if (!n || width <= 0) return rows
  const cols = stacks.map((s) => buckets(s.values.length ? s.values : [0], width))
  const totals = Array.from({ length: width }, (_, x) => cols.reduce((sum, c) => sum + (c[x] ?? 0), 0))
  const hi = Math.max(...totals)
  if (!(hi > 0)) return rows
  for (let x = 0; x < width; x++) {
    const age = 0.4 + 0.6 * (x / Math.max(width - 1, 1))
    const segs: { to: number; color: string }[] = []
    let acc = 0
    stacks.forEach((s, i) => {
      const v = cols[i]![x] ?? 0
      if (!(v > 0)) return
      acc += (v / hi) * height * grow
      segs.push({ to: acc, color: mix(background, s.color, age) })
    })
    if (!segs.length) continue
    const top = Math.max(acc, 1 / 8)
    for (let r = 0; r < height; r++) {
      const inCell = segs.filter((s, i) => s.to > r && (i ? segs[i - 1]!.to : 0) < r + 1)
      if (!inCell.length) continue
      const lower = inCell[0]!
      const upper = inCell[inCell.length - 1]!
      const y = height - 1 - r
      if (top >= r + 1) {
        const f = Math.round((lower.to - r) * 8)
        rows[y]![x] = f <= 0 || f >= 8 || lower === upper ? { ch: "█", fg: f <= 0 ? upper.color : lower.color, bg: null } : { ch: EIGHTHS[f]!, fg: lower.color, bg: upper.color }
      } else rows[y]![x] = { ch: EIGHTHS[Math.max(1, Math.min(8, Math.round((top - r) * 8)))]!, fg: upper.color, bg: null }
    }
  }
  return rows
}

export function Sparkline({ data, color, background, height = 2, grow = 1 }: { data: number[]; color: string; background: string; height?: number; grow?: number }) {
  const [width, setWidth] = useState(0)
  return <Cells grid={sparkline(data, width, height, color, background, grow)} width="100%" height={height} onSize={(w) => setWidth(w)} />
}

export function StackedSparkline({ stacks, background, height = 2, grow = 1 }: { stacks: Stacked[]; background: string; height?: number; grow?: number }) {
  const [width, setWidth] = useState(0)
  return <Cells grid={stackedSparkline(stacks, width, height, background, grow)} width="100%" height={height} onSize={(w) => setWidth(w)} />
}

// ---------------------------------------------------------------- the big numbers

// 3 x 5 pixels a character, drawn with half blocks so the pixels are square and the numbers match the pixel anvil.
const FACE: Record<string, string[]> = {
  "0": ["###", "#.#", "#.#", "#.#", "###"],
  "1": ["##.", ".#.", ".#.", ".#.", "###"],
  "2": ["###", "..#", "###", "#..", "###"],
  "3": ["###", "..#", ".##", "..#", "###"],
  "4": ["#.#", "#.#", "###", "..#", "..#"],
  "5": ["###", "#..", "###", "..#", "###"],
  "6": ["###", "#..", "###", "#.#", "###"],
  "7": ["###", "..#", "..#", "..#", "..#"],
  "8": ["###", "#.#", "###", "#.#", "###"],
  "9": ["###", "#.#", "###", "..#", "###"],
  K: ["#.#", "#.#", "##.", "#.#", "#.#"],
  M: ["#...#", "##.##", "#.#.#", "#...#", "#...#"],
  B: ["##.", "#.#", "##.", "#.#", "##."],
  ".": [".", ".", ".", ".", "#"],
  "+": ["...", ".#.", "###", ".#.", "..."],
  "−": ["...", "...", "###", "...", "..."],
  "-": ["...", "...", "###", "...", "..."],
  "—": ["...", "...", "###", "...", "..."],
}

/** The sub-pixels of `text` in the big face: 6 rows (the top one empty), a pixel's gap between characters. Null when
 * the face has no shape for one of its characters. */
export function faceGrid(text: string): string[] | null {
  const rows = ["", "", "", "", "", ""]
  for (const [i, ch] of [...text].entries()) {
    const g = FACE[ch]
    if (!g) return null
    const gap = i ? "." : ""
    rows[0] += gap + ".".repeat(g[0]!.length)
    for (let r = 0; r < 5; r++) rows[r + 1] += gap + g[r]
  }
  return rows
}

/** Columns `text` takes in the big face (Infinity when it can't be drawn in it). */
export function faceWidth(text: string): number {
  const g = faceGrid(text)
  return g ? g[0]!.length : Infinity
}

/** `text` in the big face, three rows tall, shaded from the first colour at the top to the last at the bottom. */
export function faceCells(text: string, stops: readonly string[]): Cell[][] {
  const grid = faceGrid(text)
  if (!grid) return []
  return blockArt(grid, { "#": stops[0]! }, 1).map((row, y) => row.map((c) => (c.fg ? { ...c, fg: along(stops, y / 2) } : c)))
}

export function BigNumber({ text, stops }: { text: string; stops: readonly string[] }) {
  return <Cells grid={faceCells(text, stops)} />
}

// ---------------------------------------------------------------- bars

/** A progress bar: done of total, or a sliding band while the total isn't known; the forge's gradient along it. */
export function ProgressBar({ done, total, color, track, width = 44, tick = 0, stops }: {
  done: number
  total: number | null
  color: string
  track: string
  width?: number
  tick?: number
  stops?: readonly string[]
}) {
  const row: Cell[] = []
  const ink = (x: number) => (stops ? along(stops, x / Math.max(width - 1, 1)) : color)
  if (total) {
    const n = Math.min(Math.max(done / total, 0), 1) * width
    for (let x = 0; x < width; x++) {
      const fill = Math.min(Math.max(n - x, 0), 1)
      row.push(fill >= 1 ? { ch: "━", fg: ink(x), bg: null } : fill > 0 ? { ch: "╸", fg: ink(x), bg: null } : { ch: "━", fg: track, bg: null })
    }
  } else {
    const band = Math.max(Math.floor(width / 4), 3)
    const start = (tick % (width + band)) - band
    for (let x = 0; x < width; x++) row.push({ ch: "━", fg: x >= start && x < start + band ? ink(x) : track, bg: null })
  }
  return <Cells grid={[row]} width={width} height={1} />
}

/** Sections of horizontal bars, one row per platform, scaled to the section's largest number: each bar in whole cells
 * of background colour (no seams between them), then its last eighth-wide piece. */
export function HBars({ sections, muted, grow = 1 }: { sections: [string, [string, number, string, string][]][]; muted: string; grow?: number }) {
  const [width, setWidth] = useState(0)
  const labelW = 12
  const valueW = 12
  const barW = Math.max(width - labelW - valueW, 4)
  const rows: Segs[] = []
  for (const [title, items] of sections) {
    rows.push([[title, muted]])
    const top = Math.max(0, ...items.map((r) => r[1])) || 1
    for (const [label, value, color, shown] of items) {
      const n = (Math.max(value, 0) / top) * barW * grow
      const whole = Math.floor(n)
      const part = (n % 1) * 8 >= 1 ? LEFT_EIGHTHS[Math.floor((n % 1) * 8)]! : ""
      rows.push([
        [label.padEnd(labelW).slice(0, labelW), color],
        [" ".repeat(whole), `on ${color}`],
        [part.padEnd(barW - whole), color],
        ["  " + shown, "bold"],
      ])
    }
    rows.push([])
  }
  return (
    <box
      flexDirection="column"
      flexShrink={0}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      {rows.map((r, i) => (
        <Line key={i} segs={r} />
      ))}
    </box>
  )
}

// ---------------------------------------------------------------- block art

/** Block art from a grid of sub-pixels: `across` sub-pixels a cell (2 with quadrant characters, 1 with half blocks),
 * two down; each letter in `inks` is drawn in its colour, "." is empty. */
export function blockArt(grid: string[], inks: Record<string, string>, across: 1 | 2): Cell[][] {
  const rows: Cell[][] = []
  for (let y = 0; y < grid.length; y += 2) {
    const row: Cell[] = []
    for (let x = 0; x < grid[0]!.length; x += across) {
      const subs: string[] = []
      for (const dy of [0, 1]) for (let dx = 0; dx < across; dx++) subs.push(grid[y + dy]?.[x + dx] ?? ".")
      const ink = subs.find((s) => s in inks)
      if (!ink) {
        row.push(blank())
        continue
      }
      let bits = 0
      subs.forEach((s, i) => {
        if (s === ink) bits |= across === 2 ? 1 << i : 3 << (2 * i) // a half block's sub-pixel fills both quarters
      })
      row.push({ ch: QUADRANTS[bits]!, fg: inks[ink]!, bg: null })
    }
    rows.push(row)
  }
  return rows
}

// The bell, 3 rows by 5 columns (quadrants; 5 by 3 in half blocks), its clapper under it.
const BELL_QUAD = ["....##....", "..######..", "..######..", ".########.", "##########", "....##...."]
const BELL_HALF = ["..#..", ".###.", ".###.", "#####", "#####", "..#.."]
export const BELL_WIDTH = 5

/** The bell in one colour (the count of unread notifications sits on its shoulder: see the header). */
export function bell(quadrants: boolean, color: string = BELL): Cell[][] {
  return blockArt(quadrants ? BELL_QUAD : BELL_HALF, { "#": color }, quadrants ? 2 : 1)
}

/** The logo's cells as the Python side sends them (studio/logo.py cells): [character, colour, background]. */
export function logoCells(rows: [string, string | null, string | null][][]): Cell[][] {
  return rows.map((row) => row.map(([ch, fg, bg]) => ({ ch, fg, bg })))
}

/** The anvil shaded down its height: a polished face, darker feet. */
export function shade(rows: Cell[][], stops: readonly string[]): Cell[][] {
  const h = rows.length
  return rows.map((row, y) => row.map((c) => (c.fg ? { ...c, fg: along(stops, h > 1 ? y / (h - 1) : 0) } : c)))
}

export function textCells(text: string, fg: string): Cell[] {
  return [...text].map((ch) => ({ ch, fg, bg: null }))
}

export function widthOf(rows: Cell[][]): number {
  return Math.max(0, ...rows.map((r) => r.length))
}
