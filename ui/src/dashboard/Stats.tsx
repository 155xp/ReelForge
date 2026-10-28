// The Stats tab: your followers and your likes added up across the platforms you count, over time. The platforms
// at the top left are ticked while they count in the totals (click one to leave it out, or back in), the range is at
// the top right, and each chart is the total as a filled area, hatched where it's an estimate (the computer was off),
// with a mark where each video went up; point at it for the totals then, with each platform's part. Beside each chart
// (under it in a narrow window): every platform's number now, what it gained over the range, its share of the total
// and what it gained bucket by bucket.

import type { Renderable } from "@opentui/core"
import { useCallback, useState } from "react"
import { useView } from "../bridge"
import { clockLabels, lines as drawLines, MARK, type Drawn, type Slot } from "../lib/chart"
import { cellLen, segsLen, type Parts, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Button } from "../ui/Button"
import { Chart } from "../ui/Chart"
import { sparkline } from "../ui/Graphics"
import { Line } from "../ui/Line"
import { useProgress } from "../ui/Motion"
import { Panel, Scroll } from "../ui/Panels"
import { useDash } from "./state"
import type { TotalsMetric, TotalsRow, TotalsToggle, TotalsView } from "./types"

const METRICS = ["followers", "likes"] as const
/** Narrower than this, each chart's breakdown goes under it instead of beside it. */
export const SIDE_BY_SIDE = 120
/** The breakdown's width beside its chart: about a quarter of the window, within these. */
export const BREAKDOWN_WIDTH: [number, number] = [46, 60]

/** A count in full: 21,034. */
export function exact(n: number | null | undefined): string {
  return n === null || n === undefined || !Number.isFinite(n) ? "—" : Math.round(n).toLocaleString("en-US")
}

/** +1,203 or −40. */
export function signed(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return ""
  const r = Math.round(n)
  return (r >= 0 ? "+" : "−") + Math.abs(r).toLocaleString("en-US")
}

export function Stats() {
  const s = useDash()
  const view = useView<TotalsView>(s.bridge, "totals")
  const [width, setWidth] = useState(0)
  const side = width >= SIDE_BY_SIDE
  const beside = Math.min(Math.max(Math.round(width * 0.28), BREAKDOWN_WIDTH[0]), BREAKDOWN_WIDTH[1])
  // The charts grow in again on a new range, or when a platform goes in or out of the totals.
  const animate = `${view?.range}|${(view?.toggles ?? []).map((t) => (t.counted ? t.key : "")).join(",")}`
  return (
    <box
      flexDirection="column"
      flexGrow={1}
      marginTop={1}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      <Controls view={view} width={width} />
      {side ? (
        <box flexDirection="column" flexGrow={1} flexBasis={0} marginTop={1} gap={1}>
          {METRICS.map((m) => (
            <box key={m} flexDirection="row" flexGrow={1} flexBasis={0} gap={1}>
              <TotalChart metric={m} view={view?.metrics[m]} animate={animate} flexGrow={1} />
              <Breakdown view={view?.metrics[m]} animate={animate} width={beside} />
            </box>
          ))}
        </box>
      ) : (
        // A narrow window: each chart with its breakdown under it, scrolling.
        <Scroll flexGrow={1} scrollY>
          {METRICS.map((m) => (
            <box key={m} flexDirection="column" flexShrink={0} marginTop={1} gap={1}>
              <TotalChart metric={m} view={view?.metrics[m]} animate={animate} height={16} />
              <Breakdown view={view?.metrics[m]} animate={animate} />
            </box>
          ))}
        </Scroll>
      )}
    </box>
  )
}

// ---------------------------------------------------------------- the platforms and the range

/** The ranges, the chosen one filled, the others plain words (the Overview's look). */
function rangeSegs(segs: Segs | undefined): Segs {
  return (segs ?? [])
    .filter((seg) => seg[0].trim())
    .flatMap((seg, i): Segs => {
      const gap: Segs = i ? [["  ", ""]] : []
      return seg[2] ? [...gap, [seg[0], DASH.muted, seg[2]]] : [...gap, [seg[0], `bold ${DASH.text} on ${mix(DASH.raised, "#ffffff", 0.05)}`]]
    })
}

const ADD_UP = "Add up"

/** A pill's label: ticked or not, and the platform's name (or TT / YT / IG / X when there's no room). */
function pillLabel(t: TotalsToggle, short: boolean): string {
  return `${t.counted && t.has ? "✓" : "○"} ${short ? t.short : t.name}`
}

/** The columns a row of pills takes: "Add up", then each pill (a button: its label and two spaces either side) and the
 * space after it. */
function pillsWidth(toggles: TotalsToggle[], short: boolean): number {
  return cellLen(ADD_UP) + 2 + toggles.reduce((n, t) => n + cellLen(pillLabel(t, short)) + 4 + 1, 0)
}

/** "Add up" and a pill for each platform you've connected, then the ranges: on one row while they fit, else two. */
function Controls({ view, width }: { view: TotalsView | undefined; width: number }) {
  const s = useDash()
  const toggles = view?.toggles ?? []
  const ranges = rangeSegs(view?.ranges)
  const room = width - 1 // its padding
  const short = pillsWidth(toggles, false) > room
  const oneRow = pillsWidth(toggles, short) + 4 + segsLen(ranges) <= room
  const pills = (
    <box flexDirection="row" height={1} flexShrink={0}>
      <text fg={DASH.faint} wrapMode="none" marginRight={2} flexShrink={0}>
        {ADD_UP}
      </text>
      {toggles.map((t) => {
        const on = t.counted && t.has
        return (
          <Button
            key={t.key}
            id={`count-${t.key}`}
            label={pillLabel(t, short)}
            variant={on ? "default" : "ghost"}
            accent={on ? t.color : undefined}
            disabled={!t.has}
            marginRight={1}
            onPress={() => s.bridge.send("count_platform", t.key)}
          />
        )
      })}
    </box>
  )
  if (!view) return <box height={1} flexShrink={0} />
  return oneRow ? (
    <box flexDirection="row" height={1} flexShrink={0} paddingLeft={1}>
      {pills}
      <box flexGrow={1} />
      <Line segs={ranges} />
    </box>
  ) : (
    <box flexDirection="column" flexShrink={0} paddingLeft={1} gap={1}>
      {pills}
      <Line segs={ranges} />
    </box>
  )
}

// ---------------------------------------------------------------- the charts

/** A chart's time axis: clockLabels' round hours (the weekday at midnight) while it spans a week or less, the dates
 * at midnight on a longer one (weekdays would repeat). */
export function timeLabels(slots: Slot[], pw: number, stepH: number): [number, string][] {
  if (stepH >= 24 || slots.length * stepH <= 24 * 7) return clockLabels(slots, pw, stepH)
  const day = (24 / stepH) * (pw / Math.max(slots.length, 1)) // columns a day
  const every = [1, 2, 3, 5, 7, 14, 30].find((k) => k * day >= 9) ?? 60
  const midnights = slots.flatMap((t, i): [number, string][] => (t.hour === 0 ? [[i, t.date]] : []))
  // counted back from the newest, so today always has its date
  return midnights.filter((_, k) => (midnights.length - 1 - k) % every === 0)
}

/** A chart's title while the mouse is over bucket `slot`: when it was, the total then and what the bucket added, and
 * each counted platform's part. A bucket drawn as an estimate, all of it or part, says so with its numbers marked ≈
 * (the total only when it's an estimate itself); so does a platform estimated then (in a gap in its readings) while
 * the total isn't. */
export function hoverTitle(view: TotalsMetric, slot: number): Parts {
  const head: Parts = [
    [[[`${view.name}  `, "bold"]], 2],
    [[[`${view.slots?.[slot]?.label ?? ""}  `, `bold ${MARK}`]], 0],
  ]
  const h = view.hover?.[slot]
  if (!h) return [...head, [[["not read then", DASH.muted]], 0]]
  const share = h.share ?? 0
  const out: Parts = [...head, [[[(h.estimated ? "≈" : "") + exact(h.total), "bold"], ["  ", ""]], 0]]
  if (h.gain !== null && Math.round(h.gain) !== 0)
    out.push([[[`${share > 0 ? "≈" : ""}${signed(h.gain)}  `, h.gain > 0 ? DASH.good : DASH.bad]], 1])
  if (share > 0) out.push([[[`${share >= 0.999 ? "estimated" : "partly estimated"}  `, DASH.muted]], 0])
  for (const r of view.rows ?? []) {
    const v = h.each[r.key]
    const guess = !h.estimated && h.est?.includes(r.key) ? "≈" : ""
    if (v !== undefined && v !== null) out.push([[[`${r.short} ${guess}${exact(v)}  `, r.color]], 3])
  }
  if (slot === (view.n ?? 0) - 1) out.push([[["now", DASH.muted]], 4])
  return out
}

/** The counted platforms added up: a filled area that hugs the numbers (so growth shows), with the time along the
 * bottom and a mark where each video went up. */
function TotalChart({ metric, view, animate, flexGrow, height }: { metric: string; view: TotalsMetric | undefined; animate: string; flexGrow?: number; height?: number }) {
  const draw = useCallback(
    (w: number, h: number, hover: number | null, grow: number): Drawn =>
      drawLines(view!.series!, view!.n!, w, h, (pw) => timeLabels(view!.slots!, pw, view!.step_h!), view!.marks ?? [], hover, false, true, true, {
        grow,
        fade: true,
      }),
    [view],
  )
  const title = (hover: number | null): Parts => {
    if (!view?.title) return [[[[view?.name ?? metric.toUpperCase(), "bold"]], 0]]
    return hover === null ? view.title : hoverTitle(view, hover)
  }
  return (
    <Chart
      title={title}
      draw={view?.series?.length ? (view.empty ? null : draw) : null}
      empty={view ? view.empty : " "}
      sub={view?.note ? <Line segs={view.note} /> : undefined}
      animate={animate}
      flexGrow={flexGrow}
      height={height}
    />
  )
}

// ---------------------------------------------------------------- the breakdown

/** Where a breakdown's columns go in `w` columns: the names, each platform's number now and its gain over the chart's
 * span, then while there's room what it gained in each bucket (a sparkline) and its share of the total. */
export function columns(rows: TotalsRow[], total: TotalsMetric["total"], w: number) {
  const now = Math.max(3, cellLen(exact(total?.value)), ...rows.map((r) => cellLen(exact(r.value))))
  const gain = Math.max(cellLen(GAINED), cellLen(signed(total?.gained)), ...rows.map((r) => cellLen(signed(r.gained))))
  const longest = Math.max(cellLen("BY PLATFORM"), cellLen("Added up"), ...rows.map((r) => cellLen(r.name) + 2)) + 1
  const name = Math.max(Math.min(longest, w - now - 2 - gain), 1)
  const rest = Math.max(w - name - now - 2 - gain, 0) // for the sparkline and the share
  const spark = rest - 2 - SHARE >= 6 ? rest - 2 - SHARE : 0 // two spaces before it, then the percentage
  return { name, now, gain, rest, spark }
}

type Columns = ReturnType<typeof columns>
const GAINED = "gained"
const SHARE = 6 // the share's column: " share" over " 100%"

/** What a sparkline's columns are, for the header over it: per hour, per 6h, per day. */
function per(stepH: number | undefined): string {
  if (!stepH) return ""
  if (stepH === 1) return "per hour"
  if (stepH % 24 === 0) return stepH === 24 ? "per day" : `per ${stepH / 24} days`
  return `per ${stepH}h`
}

/** The buckets a breakdown's sparklines cover: from the first one any platform has a gain for (a range longer than
 * the history starts empty) to now, the same for every platform so they line up. */
export function trimmed(rows: TotalsRow[]): (number | null)[][] {
  const first = Math.min(...rows.map((r) => r.gains.findIndex((g) => g !== null)).filter((i) => i >= 0))
  return rows.map((r) => (Number.isFinite(first) ? r.gains.slice(first) : r.gains))
}

/** One platform's lines (`tall` of them): its name, its number now and its gain, then what it gained in each bucket
 * (a sparkline `tall` rows high, the text on its top row), or when it was last read once that's a while ago, and its
 * share of the total; one left out (or not read yet) says so instead. */
export function rowLines(r: TotalsRow, gains: (number | null)[], c: Columns, grow: number, tall = 1): Segs[] {
  const counted = r.counted
  const segs: Segs = [
    [((counted ? "● " : "○ ") + r.name).slice(0, c.name).padEnd(c.name), counted ? `bold ${r.color}` : DASH.faint],
    [exact(r.value).padStart(c.now), counted ? `bold ${DASH.text}` : DASH.faint],
    ["  ", ""],
    [signed(r.gained).padStart(c.gain), !counted ? DASH.faint : (r.gained ?? 0) >= 0 ? DASH.good : DASH.bad],
  ]
  if (c.rest < 6) return [segs]
  if (!counted) return [[...segs, [`  ${r.value === null ? "not read yet" : "left out"}`.slice(0, c.rest), DASH.faint]]]
  const pct = r.share === null ? "" : `${Math.round(r.share * 100)}%`
  if (!c.spark) return [[...segs, [pct.padStart(c.rest), DASH.muted]]]
  if (r.stale) return [[...segs, ["  " + r.stale.slice(0, c.spark).padEnd(c.spark), DASH.faint], [pct.padStart(SHARE), DASH.muted]]]
  const grid = sparkline(gains.map((g) => Math.max(g ?? 0, 0)), c.spark, tall, r.color, DASH.surface, grow)
  const spark = (k: number): Segs => (grid[k] ?? []).map((cell) => [cell.ch, cell.fg ?? ""])
  const lead = " ".repeat(c.name + c.now + 2 + c.gain + 2)
  return grid.map((_, k) => (k === 0 ? [...segs, ["  ", ""], ...spark(0), [pct.padStart(SHARE), DASH.muted]] : [[lead, ""], ...spark(k)]))
}

/** Every platform's number now, its gain over the chart's span, what it gained bucket by bucket and its share of the
 * total; then the counted ones added up. */
function Breakdown({ view, animate, width }: { view: TotalsMetric | undefined; animate: string; width?: number }) {
  const [size, setSize] = useState<[number, number]>([0, 0])
  const grow = useProgress(animate, { ms: 700 })
  const rows = view?.rows ?? []
  const gains = trimmed(rows)
  const [w, h] = size
  const total = view?.total
  const c = columns(rows, total, w)
  // While there's room: a row of space under each platform, and its sparkline two rows high.
  const tall = c.spark && h >= rows.length * 3 + 4 ? 2 : 1
  const roomy = h >= rows.length * 2 + 4
  const head: Segs = [
    ["BY PLATFORM".slice(0, c.name).padEnd(c.name), "bold"],
    ["now".padStart(c.now), DASH.faint],
    ["  ", ""],
    [GAINED.padStart(c.gain), DASH.faint],
    ...(c.spark ? ([["  " + per(view?.step_h).slice(0, c.spark).padEnd(c.spark), DASH.faint], ["share".padStart(SHARE), DASH.faint]] as Segs) : []),
    ...(!c.spark && c.rest >= 6 ? ([["share".padStart(c.rest), DASH.faint]] as Segs) : []),
  ]
  const totalLine: Segs = total
    ? [
        ["Added up".slice(0, c.name).padEnd(c.name), `bold ${DASH.text}`],
        [exact(total.value).padStart(c.now), `bold ${DASH.text}`],
        ["  ", ""],
        [signed(total.gained).padStart(c.gain), (total.gained ?? 0) >= 0 ? DASH.good : DASH.bad],
      ]
    : []
  const body = (
    <box
      flexDirection="column"
      flexGrow={1}
      onSizeChange={function (this: Renderable) {
        if (this.width !== w || this.height !== h) setSize([this.width, this.height])
      }}
    >
      {w > 0 ? (
        <>
          <Line segs={head} />
          <box height={1} flexShrink={0} />
          {rows.map((r, i) => {
            const lines = rowLines(r, gains[i] ?? [], c, grow, tall)
            return (
              <box key={r.key} flexDirection="column" flexShrink={0} marginBottom={roomy ? 1 : 0}>
                {lines.map((l, k) => (
                  <Line key={k} segs={l} />
                ))}
                {lines.length < tall ? <box height={tall - lines.length} flexShrink={0} /> : null}
              </box>
            )
          })}
          {totalLine.length ? (
            <>
              <text fg={DASH.border} wrapMode="none" height={1} flexShrink={0} marginTop={roomy ? 0 : 1}>
                {"─".repeat(w)}
              </text>
              <Line segs={totalLine} />
            </>
          ) : null}
        </>
      ) : null}
    </box>
  )
  return width ? (
    <Panel width={width} flexShrink={0} paddingBottom={1}>
      {body}
    </Panel>
  ) : (
    <Panel flexShrink={0} height={rows.length * 3 + 7} paddingBottom={1}>
      {body}
    </Panel>
  )
}

export const internals = { pillsWidth }
