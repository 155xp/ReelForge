// The Overview's cards: followers, views and likes, each with its 24-hour change, made to fit the card's width
// without cutting anything off.

import { fmtNum, shortNum } from "../lib/format"
import { cellLen, segsLen, type Segs } from "../lib/styled"

export const CARD_LABELS = ["followers", "views", "likes"] as const
const MUTED = "#8b93a1"
const GOOD = "#3dff9a"
const BAD = "#ff4d5e"

type Fmt = (n: number | null | undefined) => string

/** A card's three lines. As the card narrows, the margin goes first, then the " 24h" after each change, then the
 * changes get shorter (+1.03K -> +1K), then the totals (12.9K -> 13K), then the lining up, then the changes, then the
 * labels. */
export function cardLines(
  values: Record<string, number | null | undefined>,
  changes: Record<string, number | null | undefined>,
  width: number,
): Segs[] {
  const build = (
    valueFmt: Fmt,
    changeFmt: Fmt | null,
    suffix: string,
    margin: number | null,
    aligned: boolean,
    labels = true,
  ): Segs[] => {
    const shown = Object.fromEntries(CARD_LABELS.map((k) => [k, valueFmt(values[k])])) as Record<string, string>
    const numberW = margin === null ? 0 : Math.max(...Object.values(shown).map((s) => cellLen(s))) + margin
    return CARD_LABELS.map((k) => {
      const line: Segs = [[shown[k]!.padStart(numberW), "bold"]]
      if (labels) line.push([" " + (aligned ? k.padEnd(9) : k), MUTED])
      const n = changeFmt ? changes[k] : null
      if (n) line.push([` ${n > 0 ? "+" : "−"}${changeFmt!(Math.abs(n))}${suffix}`, n > 0 ? GOOD : BAD])
      return line
    })
  }
  const steps: [Fmt, Fmt | null, string, number | null, boolean][] = [
    [fmtNum, fmtNum, " 24h", 2, true],
    [fmtNum, fmtNum, " 24h", 0, true],
    [fmtNum, fmtNum, "", 0, true],
    [fmtNum, shortNum, "", 0, true],
    [shortNum, shortNum, "", 0, true],
    [shortNum, shortNum, "", 0, false],
    [shortNum, shortNum, "", null, false],
    [shortNum, null, "", 0, true],
    [shortNum, null, "", null, false],
  ]
  for (const step of steps) {
    const lines = build(...step)
    if (lines.every((l) => segsLen(l) <= width)) return lines
  }
  return build(shortNum, null, "", 0, false, false).map((l) => (segsLen(l) <= width ? l : []))
}

/** Each line of the text, wrapped at spaces to fit the width (a word too long for it is left out). */
export function wrapLines(lines: Segs[], width: number): Segs[] {
  const out: Segs[] = []
  for (const line of lines) {
    let rest = line
    while (segsLen(rest) > width) {
      const text = rest.map((s) => s[0]).join("")
      const cut = text.lastIndexOf(" ", width)
      if (cut <= 0) break
      out.push(slice(rest, 0, cut))
      rest = slice(rest, cut + 1, text.length)
    }
    if (segsLen(rest) <= width) out.push(rest)
  }
  return out
}

/** Characters a..b of styled text. */
function slice(segs: Segs, a: number, b: number): Segs {
  const out: Segs = []
  let at = 0
  for (const s of segs) {
    const end = at + s[0].length
    const from = Math.max(a, at)
    const to = Math.min(b, end)
    if (to > from) out.push([s[0].slice(from - at, to - at), s[1], s[2]])
    at = end
  }
  return out
}
