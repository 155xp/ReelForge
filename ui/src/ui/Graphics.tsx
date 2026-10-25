// Small pictures made of cells: a sparkline, a progress bar, sections of horizontal bars (Compare), and the block art
// (the logo from the Python side, the bell, a notification's ×).

import type { Renderable } from "@opentui/core"
import { useState } from "react"
import { blend, type Cell } from "../lib/chart"
import type { Segs } from "../lib/styled"
import { BELL, mix } from "../theme"
import { Cells } from "./Cells"
import { Line } from "./Line"

const EIGHTHS = " ▁▂▃▄▅▆▇█"
const LEFT_EIGHTHS = " ▏▎▍▌▋▊▉"
export const QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█" // by the parts filled: 1 top-left, 2 top-right, 4 bottom-left, 8 bottom-right

/** Bars for a list of numbers, `height` rows tall, coloured from dim (low) to the full colour (high). Wider data is
 * cut into `width` buckets, each showing its largest number. */
export function sparkline(data: number[], width: number, height: number, color: string, background: string): Cell[][] {
  const rows: Cell[][] = Array.from({ length: height }, () => Array.from({ length: width }, () => blank()))
  if (!data.length || width <= 0) return rows
  const buckets: number[] = []
  for (let i = 0; i < width; i++) {
    const a = Math.floor((i * data.length) / width)
    const b = Math.max(Math.floor(((i + 1) * data.length) / width), a + 1)
    buckets.push(Math.max(...data.slice(a, b)))
  }
  const lo = Math.min(...buckets)
  const hi = Math.max(...buckets)
  const dim = blend(color, 0.65, background)
  buckets.forEach((v, x) => {
    const share = hi > lo ? (v - lo) / (hi - lo) : 1
    const eighths = Math.max(1, Math.round(share * height * 8))
    const fg = mix(dim, color, share)
    for (let k = 0; k < height; k++) {
      const left = eighths - k * 8
      if (left <= 0) break
      rows[height - 1 - k]![x] = { ch: EIGHTHS[Math.min(left, 8)]!, fg, bg: null }
    }
  })
  return rows
}

function blank(): Cell {
  return { ch: " ", fg: null, bg: null }
}

export function Sparkline({ data, color, background, height = 2 }: { data: number[]; color: string; background: string; height?: number }) {
  const [width, setWidth] = useState(0)
  return (
    <Cells
      grid={sparkline(data, width, height, color, background)}
      width="100%"
      height={height}
      onSize={(w) => setWidth(w)}
    />
  )
}

/** A progress bar: done of total, or a sliding band while the total isn't known. */
export function ProgressBar({ done, total, color, track, width = 44, tick = 0 }: {
  done: number
  total: number | null
  color: string
  track: string
  width?: number
  tick?: number
}) {
  const row: Cell[] = []
  if (total) {
    const n = Math.min(Math.max(done / total, 0), 1) * width
    for (let x = 0; x < width; x++) {
      const fill = Math.min(Math.max(n - x, 0), 1)
      row.push(fill >= 1 ? { ch: "━", fg: color, bg: null } : fill > 0 ? { ch: "╸", fg: color, bg: null } : { ch: "━", fg: track, bg: null })
    }
  } else {
    const band = Math.max(Math.floor(width / 4), 3)
    const start = (tick % (width + band)) - band
    for (let x = 0; x < width; x++) row.push({ ch: "━", fg: x >= start && x < start + band ? color : track, bg: null })
  }
  return <Cells grid={[row]} width={width} height={1} />
}

/** Sections of horizontal bars, one row per platform, scaled to the section's largest number: each bar in whole cells
 * of background colour (no seams between them), then its last eighth-wide piece. */
export function HBars({ sections, muted }: { sections: [string, [string, number, string, string][]][]; muted: string }) {
  const [width, setWidth] = useState(0)
  const labelW = 11
  const valueW = 18
  const barW = Math.max(width - labelW - valueW, 4)
  const rows: Segs[] = []
  for (const [title, items] of sections) {
    rows.push([[title, `bold ${muted}`]])
    const top = Math.max(0, ...items.map((r) => r[1])) || 1
    for (const [label, value, color, shown] of items) {
      const n = (Math.max(value, 0) / top) * barW
      const whole = Math.floor(n)
      const part = (n % 1) * 8 >= 1 ? LEFT_EIGHTHS[Math.floor((n % 1) * 8)]! : ""
      rows.push([
        [label.padEnd(labelW).slice(0, labelW), color],
        [" ".repeat(whole), `on ${color}`],
        [part.padEnd(barW - whole), color],
        [" " + shown, ""],
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

// The bell, 3 rows tall: "B" is the bell, "R" the red dot at its top right while something is unread.
const BELL_QUAD = ["......BB....RRRR", "....BBBBBB..RRRR", "...BBBBBBBB.....", "...BBBBBBBB.....", "BBBBBBBBBBBBBB..", "......BB........"]
const BELL_HALF = ["...B..RR", "..BBB.RR", ".BBBBB..", ".BBBBB..", "BBBBBBB.", "...B...."]

export function bell(unread: boolean, quadrants: boolean, red: string): Cell[][] {
  const inks: Record<string, string> = unread ? { B: BELL, R: red } : { B: BELL }
  return blockArt(quadrants ? BELL_QUAD : BELL_HALF, inks, quadrants ? 2 : 1)
}

// The × that deletes a notification: a bold X 3 rows tall (4, half a row lower, beside an even number of lines).
const X_QUAD = [".###.......###", "...###...###..", ".....#####....", ".....#####....", "...###...###..", ".###.......###"]
const X_HALF = [".#....#", "..#..#.", "...##..", "...##..", "..#..#.", ".#....#"]
export const X_WIDTH = 7

export function cross(lines: number, quadrants: boolean, color: string): Cell[][] {
  let grid = quadrants ? X_QUAD : X_HALF
  if (lines % 2 === 0 && lines > 2) {
    const empty = ".".repeat(grid[0]!.length)
    grid = [empty, ...grid, empty]
  }
  return blockArt(grid, { "#": color }, quadrants ? 2 : 1)
}

/** The logo's cells as the Python side sends them (studio/logo.py cells): [character, colour, background]. */
export function logoCells(rows: [string, string | null, string | null][][]): Cell[][] {
  return rows.map((row) => row.map(([ch, fg, bg]) => ({ ch, fg, bg })))
}

export function textCells(text: string, fg: string): Cell[] {
  return [...text].map((ch) => ({ ch, fg, bg: null }))
}

export function widthOf(rows: Cell[][]): number {
  return Math.max(0, ...rows.map((r) => r.length))
}

