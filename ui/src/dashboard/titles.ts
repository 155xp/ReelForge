// Chart titles: the numbers that matter for the chart as drawn, or, while the mouse is over it, that slot's numbers.

import { MARK, type Series } from "../lib/chart"
import { fmtAge, fmtDelta, fmtNum, interp } from "../lib/format"
import type { Parts, Segs } from "../lib/styled"
import { DASH } from "../theme"
import type { MetricView, Variant } from "./types"

const MUTED = DASH.muted
const GOOD = DASH.good
const BAD = DASH.bad
const SHORT: Record<string, string> = { tiktok: "TT", youtube: "YT", instagram: "IG", x: "X" }

/** The bucket size a chart `columns` wide draws (trends.frame_fit): the finest whose bars each get two columns and a
 * gap, or failing that one column and a gap; the coarsest when even that's too many. */
export function pickVariant(variants: Variant[], columns: number): Variant {
  for (const per of [3, 2]) for (const v of variants) if (v.n * per <= columns) return v
  return variants[variants.length - 1]!
}

/** How much of a bar is an estimate (Series.guess: a gap in the readings), added up over its platforms. */
export function guessIn(series: Series[], slot: number): number {
  return series.reduce((n, s) => n + Math.min(Math.max(s.guess?.[slot] ?? 0, 0), Math.max(s.values?.[slot] ?? 0, 0)), 0)
}

/** An Overview chart's title as (text, importance) parts. A bar that's an estimate, all of it or part, says so when
 * the mouse is over it, its numbers marked ≈, and is never the best one. */
export function metricTitle(metric: string, m: MetricView, v: Variant | null, slot: number | null): Parts {
  const parts: Parts = [[[[`${metric.toUpperCase()}  `, "bold"]], 0]]
  if (!v || !m.summary) return parts
  if (slot !== null && slot >= 0 && slot < v.n) {
    // On a narrow chart the hovered bar's numbers matter more than the chart's name.
    const out: Parts = [
      [parts[0]![0], 2],
      [[[v.slots[slot]!.label + "  ", `bold ${MARK}`]], 0],
    ]
    const vals = v.series
      .map((s) => [s, s.values?.[slot]] as const)
      .filter(([, x]) => x !== null && x !== undefined) as [Series, number][]
    if (!vals.length) {
      out.push([[["no readings yet", MUTED]], 0])
      return out
    }
    const sum = vals.reduce((n, [, x]) => n + x, 0)
    const guess = guessIn(v.series, slot)
    const all = guess > 0 && guess >= sum * 0.999
    out.push([[[`${guess > 0 ? "≈" : ""}+${fmtNum(sum)}  `, "bold"]], 0])
    if (guess > 0) out.push([[[all ? "estimated  " : "partly estimated  ", MUTED]], 0])
    for (const [s, x] of vals) {
      const about = !all && (s.guess?.[slot] ?? 0) > 0 ? "≈" : ""
      out.push([[[`${SHORT[s.key] ?? s.key} ${about}${fmtNum(x)}  `, s.color]], 1])
    }
    if (slot === v.n - 1) out.push([[["so far", MUTED]], 3])
    return out
  }
  const s = m.summary
  const span = m.span ?? ""
  parts.push([[[v.unit + "   ", MUTED]], 5])
  if (s.latest !== null) parts.push([[[fmtNum(s.latest), "bold"], [" total   ", MUTED]], 0])
  if (s.gained)
    parts.push([
      [
        [fmtDelta(s.gained), s.gained > 0 ? GOOD : BAD],
        [` in ${span}   `, MUTED],
      ],
      1,
    ])
  if (s.pace !== null && m.hourly) parts.push([[[`now ${fmtNum(s.pace)}/h   `, MUTED]], 2])
  if (s.change !== null) {
    const up = s.change >= 0
    parts.push([[[`${up ? "▲" : "▼"} ${(Math.abs(s.change) * 100).toFixed(0)}% vs the ${span} before   `, up ? GOOD : BAD]], 3])
  }
  let best: [number, number] | null = null // the tallest bar, as drawn, of those with no estimate in them
  for (let i = 0; i < v.n; i++) {
    const vals = v.series.map((x) => x.values?.[i]).filter((x): x is number => x !== null && x !== undefined)
    if (!vals.length || guessIn(v.series, i) > 0) continue
    const sum = vals.reduce((a, b) => a + b, 0)
    if (!best || sum > best[0] || (sum === best[0] && i > best[1])) best = [sum, i]
  }
  if (best && best[0] > 0) parts.push([[[`best ${fmtNum(best[0])} ${v.slots[best[1]]!.when}`, MUTED]], 4])
  return parts
}

/** A views-since-posting chart's title while the mouse is over hour `slot` (each series' views then). */
export function hoursTitle(head: Segs, series: Series[], slot: number, ratio: boolean): Segs {
  const out: Segs = [...head, [`at ${fmtAge(slot + 1)}  `, `bold ${MARK}`]]
  const values: Record<string, number> = {}
  for (const s of series) {
    const xs = s.xs ?? []
    if (xs.length && xs[0]! <= slot + 1 && slot + 1 <= xs[xs.length - 1]!) {
      values[s.key] = interp(xs, s.ys ?? [], slot + 1)
      out.push([`${s.name} ${fmtNum(values[s.key])}  `, s.color])
    }
  }
  if (ratio && values.typical && values.this !== undefined)
    out.push([`${(values.this / values.typical).toFixed(1)}× typical`, "bold"])
  return out
}
