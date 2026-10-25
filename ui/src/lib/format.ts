// Numbers the way the Python side writes them (dashboard/analytics.py and dashboard/view.py), for what the window
// works out itself: the cards as they narrow, and the read-outs as the mouse moves over a chart.

export function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—"
  const a = Math.abs(n)
  if (a >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (a >= 10_000) return `${(n / 1_000).toFixed(1)}K`
  if (a >= 1_000) return `${(n / 1_000).toFixed(2)}K`
  return n.toFixed(0)
}

export function fmtDelta(n: number | null | undefined): string {
  if (n === null || n === undefined) return ""
  return (n >= 0 ? "+" : "−") + fmtNum(Math.abs(n))
}

export function fmtPct(x: number | null | undefined): string {
  return x === null || x === undefined ? "—" : `${(x * 100).toFixed(1)}%`
}

export function fmtAge(hours: number): string {
  if (hours < 1) return `${(hours * 60).toFixed(0)}m`
  if (hours < 48) return `${hours.toFixed(0)}h`
  return `${(hours / 24).toFixed(0)}d`
}

/** A number in as few characters as it reads in: 13K, 9.4K, 1K, 1.2M (fmtNum keeps more digits). */
export function shortNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—"
  let v: number
  let suffix: string
  if (Math.abs(n) >= 999_500) [v, suffix] = [n / 1_000_000, "M"]
  else if (Math.abs(n) >= 999.5) [v, suffix] = [n / 1_000, "K"]
  else return n.toFixed(0)
  return (Math.abs(v) >= 9.95 ? v.toFixed(0) : v.toFixed(1).replace(/0$/, "").replace(/\.$/, "")) + suffix
}

/** Linear interpolation along points sorted by x (the ends hold their values). */
export function interp(xs: number[], ys: number[], x: number): number {
  let i = 0
  while (i < xs.length && xs[i]! < x) i++
  if (i <= 0) return ys[0]!
  if (i >= xs.length) return ys[ys.length - 1]!
  const x0 = xs[i - 1]!
  const x1 = xs[i]!
  return ys[i - 1]! + (ys[i]! - ys[i - 1]!) * (x1 > x0 ? (x - x0) / (x1 - x0) : 1)
}
