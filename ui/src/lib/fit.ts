// Titles and lines made of parts, each with an importance: 0 always shows, higher numbers go first when there isn't
// room for all of them (a chart's title on a narrow chart, a best-time line, the Videos tab's hint).

import { segsLen, truncate, type Parts, type Segs } from "./styled"

/** Join the parts, leaving out the least important (highest number, the last of those first) until they fit `width`.
 * If even the ones that always show don't fit, the last of them go too, so nothing is cut off halfway (a number, a
 * button); only a first part wider than everything is cut. */
export function fit(parts: Parts, width: number): Segs {
  const keep = [...parts]
  while (keep.length > 1 && keep.reduce((n, [t]) => n + segsLen(t), 0) > width) {
    let drop = 0
    for (let i = 0; i < keep.length; i++) {
      if (keep[i]![1] > keep[drop]![1] || (keep[i]![1] === keep[drop]![1] && i > drop)) drop = i
    }
    keep.splice(drop, 1)
  }
  return truncate(
    keep.flatMap(([t]) => t),
    Math.max(width, 1),
  )
}
