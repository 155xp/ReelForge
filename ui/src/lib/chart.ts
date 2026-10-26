// Charts drawn in terminal cells: stacked bars and lines, with round-number axes, event marks and a hover read-out.
//
// Bars are all the same width with a one-column gap between them (a chart too narrow for that gets combined buckets
// from the Python side: trends.frame_fit). A stacked bar is drawn in whole cells of background colour, which
// terminals (and the screenshots) show without seams: each cell takes the colour of the platform that fills most of
// it, so no thin slivers appear inside a stack, and only the top cell uses an eighth block (▁▂▃▄▅▆▇) so the bar's
// height lands within 1/8 of a row. Lines use thin box-drawing strokes; running totals can be drawn as a filled area
// with a smooth top edge instead. The x axis is in "slots" (buckets of time, or hours since posting).

import { DASH, MARK as MARK_COLOUR, mix } from "../theme"
import { interp } from "./format"
import { charWidth } from "./styled"

export const BACKGROUND = DASH.surface // charts sit on a panel
export const AXIS = DASH.border
export const LABEL = DASH.faint
export const GRID = mix(DASH.surface, DASH.border, 0.75)
export const HOVER = mix(DASH.surface, "#ffffff", 0.045)
export const MARK = MARK_COLOUR
export const EIGHTHS = " ▁▂▃▄▅▆▇█"

/** How bars are drawn beyond their numbers. */
export interface BarStyle {
  /** How far they've grown (0..1): the opening animation. The axes stay where the whole bars put them. */
  grow?: number
  /** Each bar a little darker at its foot, its true colour at the top of the chart. */
  fade?: boolean
}

/** A bar's colour `k` rows up a plot `ph` rows tall, faded towards its foot. */
export function fadeUp(color: string, k: number, ph: number): string {
  return mix(BACKGROUND, color, 0.6 + 0.4 * Math.min(k / Math.max(ph - 1, 1), 1))
}
const LADDER = [1, 2, 2.5, 5]

export interface Cell {
  ch: string
  fg: string | null
  bg: string | null
}

export interface Series {
  key: string
  name: string
  color: string
  values?: (number | null)[] // bars: one per slot
  faint?: boolean[] // bars: slots drawn dimmer (still filling up)
  xs?: number[] // lines: x in slots
  ys?: number[]
  fill?: boolean // lines: shade the cells under the line
  style?: string // lines: "line", or "area" (filled, with a smooth top edge)
}

export interface Mark {
  x: number // in slots
  label: string
}

export type XLabels = [number, string][] | ((pw: number) => [number, string][])

/** Python's round(): halves go to the even number. */
export function pyRound(x: number): number {
  const r = Math.round(x)
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r
}

function hex(color: string): string {
  const c = color.replace(/^#/, "")
  return c.length === 3 ? [...c].map((ch) => ch + ch).join("") : c
}

/** color moved `amount` of the way towards `into` (0 = unchanged, 1 = into). */
export function blend(color: string, amount: number, into = BACKGROUND): string {
  const a = hex(color)
  const b = hex(into)
  const mix = [0, 2, 4].map((i) =>
    pyRound(parseInt(a.slice(i, i + 2), 16) * (1 - amount) + parseInt(b.slice(i, i + 2), 16) * amount),
  )
  return "#" + mix.map((v) => v.toString(16).padStart(2, "0")).join("")
}

function roundTo(x: number, d: number): number {
  const f = 10 ** d
  return Math.round(x * f) / f
}

/** How many decimals (up to 3) it takes to write x exactly. */
function decimals(x: number): number {
  for (let d = 0; d < 4; d++) if (Math.abs(roundTo(x, d) - x) < 1e-9 * Math.max(Math.abs(x), 1)) return d
  return 3
}

function trimZeros(text: string): string {
  return text.includes(".") ? text.replace(/0+$/, "").replace(/\.$/, "") : text
}

/** Axis numbers: 0, 250, 2.5K, 10K, 1.2M. With the axis step given, every label on the axis stays distinct
 * (52,340 and 52,345 rather than two "52.34K"). */
export function fmtTick(v: number, step?: number | null): string {
  if (!Number.isFinite(v)) return "?"
  if (Math.abs(v) < 1e-9) return "0"
  const s = step && Number.isFinite(step) && step > 0 ? step : null
  for (const [size, suffix] of [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "K"],
  ] as const) {
    if (Math.abs(v) >= size * 0.9995 && (s === null || s >= size / 100)) {
      const d = s === null ? 2 : decimals(s / size)
      return trimZeros((v / size).toFixed(d)) + suffix
    }
  }
  const d = s === null || s >= 1 ? 0 : decimals(s)
  if (s !== null) return v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d })
  return trimZeros(v.toFixed(2)) || "0"
}

/** A 1, 2, 2.5 or 5 x 10^n step that cuts span into about `count` pieces. */
export function niceStep(span: number, count: number): number {
  if (!(span > 0) || !Number.isFinite(span)) return 1
  const raw = span / Math.max(count, 1)
  const mag = 10 ** Math.floor(Math.log10(raw))
  for (const m of [...LADDER, 10]) if (m * mag >= raw * (1 - 1e-12)) return m * mag
  return 10 * mag
}

/** [bottom, top, step] covering lo..hi in round steps, about `count` of them with the least space wasted; whole:
 * whole-number steps only (for counts). */
export function niceRange(lo: number, hi: number, count: number, whole = true): [number, number, number] {
  if (!(Number.isFinite(lo) && Number.isFinite(hi))) [lo, hi] = [0, 1]
  if (hi - lo < (whole ? 1 : Math.max(Math.abs(hi), 1) * 1e-9)) hi = lo + 1
  const mag = Math.floor(Math.log10(niceStep(hi - lo, count)))
  let best: [number, number, number, number] | null = null
  for (const k of [mag - 1, mag, mag + 1]) {
    for (const m of LADDER) {
      const step = m * 10 ** k
      if (whole && (step < 1 || Math.abs(step - Math.round(step)) > 1e-9)) continue
      const bottom = Math.floor(lo / step + 1e-9) * step
      const top = Math.ceil(hi / step - 1e-9) * step
      const steps = pyRound((top - bottom) / step)
      if (steps < 1 || steps > Math.max(count * 2, 2)) continue
      const score = Math.abs(steps - count) * 0.5 + (top - bottom - (hi - lo)) / (hi - lo)
      if (best === null || score < best[0] - 1e-9) best = [score, bottom, top, step]
    }
  }
  if (best === null) {
    const step = whole ? Math.max(pyRound(niceStep(hi - lo, count)), 1) : niceStep(hi - lo, count)
    return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step, step]
  }
  return [best[1], best[2], best[3]]
}

export class Canvas {
  cells = new Map<number, Cell>()
  constructor(
    readonly w: number,
    readonly h: number,
  ) {}

  get(r: number, c: number): Cell {
    return this.cells.get(r * this.w + c) ?? { ch: " ", fg: null, bg: null }
  }

  /** Draw a character; with bg null the cell keeps the background it had. */
  put(r: number, c: number, ch: string, fg: string | null = null, bg: string | null = null): void {
    if (r >= 0 && r < this.h && c >= 0 && c < this.w) {
      const old = this.cells.get(r * this.w + c)
      this.cells.set(r * this.w + c, { ch, fg, bg: bg ?? old?.bg ?? null })
    }
  }

  tint(r: number, c: number, bg: string): void {
    if (r >= 0 && r < this.h && c >= 0 && c < this.w) {
      const old = this.get(r, c)
      this.cells.set(r * this.w + c, { ch: old.ch, fg: old.fg, bg })
    }
  }

  /** Nothing drawn there: a grid line or the hover highlight doesn't count, a bar or an area does. */
  blank(r: number, c: number): boolean {
    const { ch, bg } = this.get(r, c)
    return (ch === " " || ch === "┈") && (bg === null || bg === HOVER)
  }

  row(r: number): Cell[] {
    return Array.from({ length: this.w }, (_, c) => this.get(r, c))
  }
}

/** Where the plot sits in the chart, how values map to rows and slots to columns. */
export class Layout {
  per = 1 // columns per slot
  first = 0 // the first slot drawn (bars show only the newest slots when there are more than columns)
  slots = 0 // how many slots are drawn
  bar = 0 // bar charts: how many columns wide each bar is (the rest of its slot is the gap after it)

  constructor(
    public lw: number, // left label width; the axis column comes after it
    public pw: number, // plot width
    public ph: number, // plot height
    public lo: number,
    public hi: number,
    public step: number,
  ) {}

  /** v as a height above the plot bottom, in rows (0..ph). */
  height(v: number): number {
    return this.hi > this.lo ? ((v - this.lo) / (this.hi - this.lo)) * this.ph : 0
  }

  /** The plot row a value falls in (0 = top). */
  row(v: number): number {
    if (!(v > this.lo)) return this.ph - 1
    return Math.min(Math.max(this.ph - 1 - Math.trunc(this.height(v) - 1e-9), 0), this.ph - 1)
  }

  /** The plot columns a slot is drawn in (at least one): [start, end). */
  columns(slot: number): [number, number] {
    const j = slot - this.first
    const c0 = Math.trunc(j * this.per)
    return [c0, Math.max(Math.trunc((j + 1) * this.per), c0 + 1)]
  }

  /** The plot column of x (in slots). On a bar chart it's a column of x's own bar, never the gap after it, so a mark
   * or an axis label lands on the bar it belongs to. */
  col(x: number): number {
    if (!this.bar) return Math.trunc((x - this.first) * this.per)
    const j = Math.floor(x)
    return this.columns(j)[0] + Math.min(Math.trunc((x - j) * this.bar), this.bar - 1)
  }

  /** The slot drawn in plot column c: the exact inverse of columns(). */
  slotAt(c: number): number | null {
    if (!(c >= 0 && c < this.pw) || this.slots <= 0) return null
    let j = Math.min(Math.trunc(c / this.per), this.slots - 1)
    while (j > 0 && Math.trunc(j * this.per) > c) j--
    while (j + 1 < this.slots && Math.trunc((j + 1) * this.per) <= c) j++
    return this.first + j
  }
}

/** Round-number labels by plot row: the top and bottom ones always, then the others that don't touch a label already
 * placed. */
export function yLabels(lay: Layout): Map<number, string> {
  const steps = lay.step > 0 ? Math.min(pyRound((lay.hi - lay.lo) / lay.step), 200) : 0
  const values = Array.from({ length: steps + 1 }, (_, k) => lay.hi - k * lay.step)
  const order = steps ? [0, steps, ...Array.from({ length: steps - 1 }, (_, i) => i + 1)] : [0]
  const out = new Map<number, string>()
  for (const k of order) {
    const r = k === 0 ? 0 : k === steps ? lay.ph - 1 : lay.row(values[k]!)
    if (!out.has(r) && [...out.keys()].every((q) => Math.abs(r - q) > 1)) out.set(r, fmtTick(values[k]!, lay.step))
  }
  return new Map([...out.entries()].sort((a, b) => a[0] - b[0]))
}

function layout(w: number, h: number, lo: number, hi: number, whole: boolean, xaxis: boolean): Layout {
  const ph = Math.max(h - (xaxis ? 2 : 0), 1)
  const [bottom, top, step] = niceRange(lo, hi, Math.max(Math.floor(ph / 3), 2), whole)
  const labels = yLabels(new Layout(0, 0, ph, bottom, top, step))
  const lw = Math.max(1, ...[...labels.values()].map((s) => s.length)) + 1
  return new Layout(lw, Math.max(w - lw - 1, 1), ph, bottom, top, step)
}

/** Map slots to columns; bars that wouldn't each get a column and a gap keep only the newest slots that do. */
function place(lay: Layout, slots: number, newestFirst = false): void {
  const n = Math.ceil(slots)
  if (newestFirst && n * 2 > lay.pw) {
    const keep = Math.max(Math.floor(lay.pw / 2), 1)
    lay.first = n - keep
    lay.slots = keep
    lay.per = lay.pw / keep
  } else {
    lay.first = 0
    lay.slots = n
    lay.per = lay.pw / Math.max(slots, 1e-9)
  }
}

function cells(text: string, fg: string | null): Cell[] {
  return [...text].map((ch) => ({ ch, fg, bg: null }))
}

/** The y labels (no rule beside them: the gridlines carry the eye across), the drawn plot, then the x axis, a faint
 * baseline with a tick under each label, and its labels. */
function frame(canvas: Canvas, lay: Layout, xlabels: XLabels, xaxis: boolean): Cell[][] {
  const xl = typeof xlabels === "function" ? xlabels(lay.pw) : xlabels
  const labels = yLabels(lay)
  const rows: Cell[][] = []
  for (let r = 0; r < lay.ph; r++) {
    const label = labels.get(r)
    const left = label !== undefined ? cells(label.padStart(lay.lw - 1) + "  ", LABEL) : cells(" ".repeat(lay.lw + 1), AXIS)
    rows.push([...left, ...canvas.row(r)])
  }
  if (xaxis) {
    const axis = Array<string>(lay.pw).fill("─")
    const under = Array<string>(lay.pw).fill(" ")
    let free = 0
    for (const [x, label] of xl) {
      const c = lay.col(x)
      if (!(c >= 0 && c < lay.pw)) continue
      axis[c] = "┬"
      const start = Math.min(Math.max(c - Math.floor(label.length / 2), 0), Math.max(lay.pw - label.length, 0))
      if (start >= free && start + label.length <= lay.pw) {
        ;[...label].forEach((ch, k) => (under[start + k] = ch))
        free = start + label.length + 2
      }
    }
    rows.push(cells(" ".repeat(lay.lw + 1) + axis.join(""), AXIS))
    rows.push(cells(" ".repeat(lay.lw + 1) + under.join("").slice(0, lay.pw), LABEL))
  }
  return rows
}

function grid(canvas: Canvas, lay: Layout): void {
  for (const r of yLabels(lay).keys()) {
    if (r < lay.ph - 1) for (let c = 0; c < lay.pw; c++) if (canvas.blank(r, c)) canvas.put(r, c, "┈", GRID)
  }
}

function hover(canvas: Canvas, lay: Layout, slot: number | null): void {
  if (slot === null || !(lay.first <= slot && slot < lay.first + lay.slots)) return
  const [a, b] = lay.columns(slot)
  for (let c = a; c < b; c++) for (let r = 0; r < lay.ph; r++) canvas.tint(r, c, HOVER)
}

/** A mark label in single-width characters only (an emoji or CJK title would push the row out of line). */
function markLabel(text: string, width = 28): string {
  return [...text]
    .filter((ch) => charWidth(ch) === 1)
    .join("")
    .slice(0, width)
    .trim()
}

/** Dotted lines where videos went up (through empty cells only), each labelled along the top row.
 *
 * Marks that land within a couple of columns of each other share one line and one label. A label reads to the right
 * of its mark, or to the left when there's no room on the right. When the labels don't all fit, they're all shortened
 * alike (down to three letters and "…") until every mark has one; a mark with no room even then is left out, so there
 * is never an arrow that doesn't say what it points at. */
function marksOn(canvas: Canvas, lay: Layout, marks: Mark[]): void {
  const groups: [number, string[]][] = []
  for (const m of [...marks].sort((a, b) => a.x - b.x)) {
    const c = lay.col(m.x)
    if (!(c >= 0 && c < lay.pw)) continue // outside what's drawn
    const last = groups[groups.length - 1]
    if (last && c - last[0] <= 2) last[1].push(markLabel(m.label))
    else groups.push([c, [markLabel(m.label)]])
  }
  if (!groups.length) return
  const texts = groups.map(([, labels]) => labels.filter(Boolean).join(" + "))
  const blank = Array.from({ length: lay.pw }, (_, k) => canvas.blank(0, k))

  const placeAll = (caps: number[]): ([string, number] | null)[] => {
    const out: ([string, number] | null)[] = []
    let end: number | null = null // the column just after the last label
    groups.forEach(([c], i) => {
      const text = texts[i]!
      const cap = caps[i]!
      // A label reading right starts one column after the last one; one reading left (ending in its arrow) keeps
      // three columns away, so two labels never run together as if they were one.
      const [afterR, afterL] = end === null ? [0, 0] : [end + 1, end + 3]
      let right = 0
      let left = 0
      while (c >= afterR && c + right < lay.pw && blank[c + right]) right++
      while (c - left >= afterL && blank[c - left]) left++
      const roomR = Math.min(cap, text.length, right - 2)
      const roomL = Math.min(cap, text.length, left - 2)
      const keep = Math.max(roomR, roomL)
      if (!text || keep < Math.min(4, text.length)) {
        out.push(null)
        return
      }
      const short = keep >= text.length ? text : text.slice(0, keep - 1).trimEnd() + "…"
      const spot: [string, number] = roomR >= keep ? ["▼ " + short, c] : [short + " ▼", c - short.length - 1]
      out.push(spot)
      end = spot[1] + spot[0].length
    })
    return out
  }

  const longest = Math.max(...texts.map((t) => t.length))
  let best = placeAll(texts.map(() => longest))
  for (let cap = longest - 1; cap > 3; cap--) {
    // too crowded: shorten them all alike (the last one can use what's left)
    if (best.every(Boolean)) break
    const trial = placeAll([...texts.slice(1).map(() => cap), longest])
    if (trial.filter(Boolean).length > best.filter(Boolean).length) best = trial
  }
  groups.forEach(([c], i) => {
    const spot = best[i]
    if (!spot) return
    const [label, first] = spot
    for (let r = 1; r < lay.ph; r++) if (canvas.blank(r, c)) canvas.put(r, c, "┊", blend(MARK, 0.5))
    ;[...label].forEach((ch, k) => canvas.put(0, first + k, ch, MARK))
  })
}

export interface Drawn {
  rows: Cell[][]
  lay: Layout
  /** What the caller drew it from (the bucket size an Overview chart picked, say). */
  meta?: unknown
}

/** Stacked bars, one per slot, series stacked bottom-up in the order given. Every bar is the same width with at least
 * a one-column gap after it; a chart too narrow even for that shows only its newest bars. */
export function bars(
  series: Series[],
  slots: number,
  w: number,
  h: number,
  xlabels: XLabels = [],
  marks: Mark[] = [],
  hovered: number | null = null,
  xaxis = true,
  style: BarStyle = {},
): Drawn {
  xaxis = xaxis && h >= 5
  const grow = Math.min(Math.max(style.grow ?? 1, 0), 1)
  const totals = Array.from({ length: slots }, (_, i) =>
    series.reduce((sum, s) => {
      const v = s.values?.[i]
      return v && Number.isFinite(v) ? sum + v : sum
    }, 0),
  )
  let peak = Math.max(0, ...totals) || 1
  if (marks.length) {
    // keep the top row clear of bars, so the marks' labels have somewhere to go
    const rows = Math.max(h - (xaxis ? 2 : 0), 2)
    peak *= rows / (rows - 1)
  }
  const lay = layout(w, h, 0, peak, true, xaxis)
  place(lay, slots, true)
  const canvas = new Canvas(lay.pw, lay.ph)
  hover(canvas, lay, hovered)
  grid(canvas, lay)
  const gap = lay.per >= 2 ? 1 : 0
  lay.bar = Math.max(Math.trunc(lay.per) - gap, 1)
  for (let i = lay.first; i < lay.first + lay.slots; i++) {
    const c0 = lay.columns(i)[0]
    const cols = [c0, Math.min(c0 + lay.bar, lay.pw)] as const
    const segments: [number, number, string][] = [] // (bottom, top, colour) in eighths of a row
    let top = 0
    for (const s of series) {
      const v = s.values?.[i]
      if (!v || !Number.isFinite(v)) continue
      const faint = s.faint?.[i] ?? false
      segments.push([top, top + lay.height(v) * 8 * grow, faint ? blend(s.color, 0.55) : s.color])
      top = segments[segments.length - 1]![1]
    }
    stack(canvas, lay, cols, segments, style.fade ?? false)
  }
  if (marks.length) marksOn(canvas, lay, marks)
  return { rows: frame(canvas, lay, xlabels, xaxis), lay }
}

/** One stacked bar. Each whole cell is the colour of the segment that fills most of it, so a boundary between
 * platforms lands on a cell edge and a platform too thin to see joins its neighbour (its number is still in the hover
 * read-out); only the top cell keeps 1/8-row precision, as an eighth block. That top piece takes the colour of the cell
 * under it unless one platform fills at least half a row of it, so it's never a thin line of another colour. */
function stack(canvas: Canvas, lay: Layout, cols: readonly [number, number], segments: [number, number, string][], fade = false) {
  const tone = (col: string, k: number) => (fade ? fadeUp(col, k, lay.ph) : col)
  if (!segments.length) return
  const top = segments[segments.length - 1]![1]
  const eighths = Math.trunc(pyRound(top))
  if (eighths <= 0) return
  const colour = (lo: number, hi: number): [string, number] => {
    let best = segments[segments.length - 1]![2]
    let cover = 0
    for (const [a, b, col] of segments) {
      const c = Math.min(b, hi) - Math.max(a, lo)
      if (c > cover) [best, cover] = [col, c]
    }
    return [best, cover]
  }
  const full = Math.floor(eighths / 8)
  const rest = eighths % 8
  for (let k = 0; k < Math.min(full, lay.ph); k++) {
    const col = colour(8 * k, 8 * k + 8)[0]
    for (let c = cols[0]; c < cols[1]; c++) canvas.put(lay.ph - 1 - k, c, " ", null, tone(col, k))
  }
  if (rest && full < lay.ph) {
    let [col, cover] = colour(8 * full, top)
    if (full && cover < 4) col = colour(8 * full - 8, 8 * full)[0]
    for (let c = cols[0]; c < cols[1]; c++) canvas.put(lay.ph - 1 - full, c, EIGHTHS[rest]!, tone(col, full))
  }
}

/** A y range that hugs the data, so change shows; it only starts at 0 when the data is near 0. */
function hug(values: number[]): [number, number] {
  const ys = values.filter(Number.isFinite)
  if (!ys.length) ys.push(0)
  let lo = Math.min(...ys)
  const hi = Math.max(...ys)
  if (hi <= lo) return [Math.max(lo - 1, 0), hi + 1]
  const padding = (hi - lo) * 0.08
  lo = lo - padding > 0 ? lo - padding : 0
  return [lo, hi + padding * 0.5]
}

function sortedPoints(s: Series): [number[], number[]] {
  const pts = (s.xs ?? [])
    .map((x, i) => [x, s.ys?.[i] ?? NaN] as [number, number])
    .filter(([x, y]) => Number.isFinite(x) && Number.isFinite(y))
    .sort((a, b) => a[0] - b[0] || a[1] - b[1])
  return [pts.map((p) => p[0]), pts.map((p) => p[1])]
}

/** A filled area whose top edge lands within 1/8 of a row (for running totals: views so far). */
function area(canvas: Canvas, lay: Layout, s: Series, style: BarStyle = {}): void {
  const [xs, ys] = sortedPoints(s)
  if (xs.length < 2) return
  const color = blend(s.color, 0.3)
  const tone = (k: number) => (style.fade ? mix(BACKGROUND, s.color, 0.3 + 0.45 * Math.min(k / Math.max(lay.ph - 1, 1), 1)) : color)
  const first = Math.max(Math.trunc((xs[0]! - lay.first) * lay.per), 0)
  const last = drawnTo(lay, first, xs, style.grow)
  for (let c = first; c <= last; c++) {
    const x = Math.min(Math.max((c + 0.5) / lay.per + lay.first, xs[0]!), xs[xs.length - 1]!)
    const eighths = Math.trunc(pyRound(Math.min(Math.max(lay.height(interp(xs, ys, x)), 0), lay.ph) * 8))
    const full = Math.floor(eighths / 8)
    const part = eighths % 8
    for (let k = 0; k < Math.min(full, lay.ph); k++) canvas.put(lay.ph - 1 - k, c, " ", null, tone(k))
    if (part && full < lay.ph) canvas.put(lay.ph - 1 - full, c, EIGHTHS[part]!, tone(full))
  }
}

/** The last column a line or area is drawn to: its last point's, or part of the way there while it draws in. */
function drawnTo(lay: Layout, first: number, xs: number[], grow = 1): number {
  const last = Math.min(Math.trunc(Math.ceil((xs[xs.length - 1]! - lay.first) * lay.per)) - 1, lay.pw - 1)
  return grow >= 1 ? last : first + Math.floor((last - first + 1) * Math.max(grow, 0)) - 1
}

function line(canvas: Canvas, lay: Layout, s: Series, fill: boolean, grow = 1): void {
  const [xs, ys] = sortedPoints(s)
  if (!xs.length) return
  if (xs.length === 1) {
    const c = Math.trunc((xs[0]! - lay.first) * lay.per)
    if (c >= 0 && c < lay.pw) canvas.put(lay.row(ys[0]!), c, "●", s.color)
    return
  }
  const first = Math.max(Math.trunc((xs[0]! - lay.first) * lay.per), 0)
  const last = drawnTo(lay, first, xs, grow)
  const shade = blend(s.color, 0.86)
  let prev: number | null = null
  for (let c = first; c <= last; c++) {
    const x = Math.min(Math.max((c + 0.5) / lay.per + lay.first, xs[0]!), xs[xs.length - 1]!)
    const r = lay.row(interp(xs, ys, x))
    if (fill) for (let rr = r + 1; rr < lay.ph; rr++) canvas.tint(rr, c, shade)
    if (prev === null || r === prev) canvas.put(r, c, "─", s.color)
    else {
      const up = r < prev
      canvas.put(prev, c, up ? "╯" : "╮", s.color)
      canvas.put(r, c, up ? "╭" : "╰", s.color)
      for (let rr = Math.min(r, prev) + 1; rr < Math.max(r, prev); rr++) canvas.put(rr, c, "│", s.color)
    }
    prev = r
  }
}

/** Lines (or areas) on an x axis of `slots` slots. The y range hugs the data (zero starts it at 0). */
export function lines(
  series: Series[],
  slots: number,
  w: number,
  h: number,
  xlabels: XLabels = [],
  marks: Mark[] = [],
  hovered: number | null = null,
  zero = false,
  whole = true,
  xaxis = true,
  style: BarStyle = {},
): Drawn {
  xaxis = xaxis && h >= 5
  const ys = series.flatMap((s) => (s.ys ?? []).filter(Number.isFinite))
  const [lo, hi] = ys.length ? (zero ? [0, Math.max(...ys)] : hug(ys)) : [0, 1]
  const lay = layout(w, h, lo, hi, whole, xaxis)
  place(lay, slots)
  const canvas = new Canvas(lay.pw, lay.ph)
  hover(canvas, lay, hovered)
  grid(canvas, lay)
  for (const s of [...series].sort((a, b) => Number(a.style !== "area") - Number(b.style !== "area"))) {
    // areas first, lines over them
    if (s.style === "area" && (s.xs?.length ?? 0) > 1) area(canvas, lay, s, style)
    else line(canvas, lay, s, s.fill ?? false, style.grow)
  }
  if (marks.length) marksOn(canvas, lay, marks)
  return { rows: frame(canvas, lay, xlabels, xaxis), lay }
}

/** What the Python side says about each bucket of a time axis (dashboard/service.py slot_info). */
export interface Slot {
  label: string // the hover read-out: Fri 7 PM, Fri 6–8 PM, Fri Oct 24, Oct 20–22
  when: string // after a number: at 8 PM, on Oct 20
  hour: number
  day: number
  weekday: string
  clock: string // 7 PM
  date: string // Oct 24
}

/** Labels for a time axis of buckets: round hours ("6 PM", the weekday at midnight) or dates. stepH: the buckets'
 * size in hours. */
export function clockLabels(slots: Slot[], pw: number, stepH: number): [number, string][] {
  const n = slots.length
  if (n < 2) return []
  const per = pw / n
  const out: [number, string][] = []
  if (stepH >= 24) {
    const every = [1, 2, 3, 5, 7, 14].find((k) => k * per >= 8) ?? 30
    slots.forEach((t, i) => {
      if ((n - 1 - i) % every === 0) out.push([i + 0.5, t.date])
    })
    return out
  }
  const every = [1, 2, 3, 4, 6, 12, 24].find((k) => (k / stepH) * per >= 8 && k % stepH === 0) ?? 48
  slots.forEach((t, i) => {
    if ((every <= 24 && t.hour % every === 0) || (every > 24 && t.hour === 0 && t.day % 2 === 0))
      out.push([i, t.hour === 0 ? t.weekday : t.clock])
  })
  return out
}

/** Labels for an hours-since-posting axis (x in hours): 0h, 6h, 12h ... or 1d, 2d ... */
export function ageLabels(hours: number, pw: number): [number, string][] {
  const per = pw / Math.max(hours, 1e-9)
  const every = [1, 2, 3, 6, 12, 24, 48, 96, 168].find((k) => k * per >= 7) ?? 336
  const out: [number, string][] = []
  for (let x = 0; x <= Math.trunc(hours); x += every)
    out.push([x, every >= 24 ? `${Math.floor(x / 24)}d` : `${x}h`])
  return out
}

/** The slot under column x of a drawn chart (x from the chart's left edge), or null. */
export function slotAtX(lay: Layout | null, x: number): number | null {
  return lay ? lay.slotAt(x - lay.lw - 1) : null
}

/** The pieces the tests look at directly. */
export const internals = { stack, marksOn, layout, hug }
