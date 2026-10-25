// A titled chart: it redraws to fit its size, says which slot the mouse is over (the title then reads that slot's
// numbers), and shows a hint instead of an empty grid when there's nothing to draw yet.

import { useMemo, useState } from "react"
import { slotAtX, type Drawn } from "../lib/chart"
import { useTheme } from "../lib/focus"
import type { Parts, Segs } from "../lib/styled"
import { Cells } from "./Cells"
import { Fitted, Line } from "./Line"
import { Panel } from "./Panels"

export const EMPTY = "Not enough history yet. ReelForge saves a snapshot on every refresh, so this fills in as it runs."

export interface ChartProps {
  /** The title: parts fitted to the width (or a line), worked out from the hovered slot and the drawn chart. */
  title: (hover: number | null, drawn: Drawn | null) => Parts | Segs
  /** Draw the chart at this size (columns, rows) with this slot hovered; null: nothing to draw. */
  draw: ((w: number, h: number, hover: number | null) => Drawn) | null
  empty?: string | null
  flexGrow?: number
  height?: number | `${number}%`
  minHeight?: number
  width?: number | `${number}%`
  marginRight?: number
  /** No box round it (the Accounts tab's followers chart sits inside its panel). */
  bare?: boolean
}

function isParts(t: Parts | Segs): t is Parts {
  return t.length > 0 && Array.isArray(t[0]) && Array.isArray((t[0] as unknown[])[0])
}

export function Chart(p: ChartProps) {
  const theme = useTheme()
  const [size, setSize] = useState<[number, number]>([0, 0])
  const [hover, setHover] = useState<number | null>(null)
  const [w, h] = size
  const drawn = useMemo(
    () => (p.draw && w >= 10 && h >= 4 ? p.draw(w, h, hover) : null),
    [p.draw, w, h, hover],
  )
  const title = p.title(hover, drawn)
  const body = p.draw ? (
    <Cells
      grid={drawn?.rows ?? []}
      width="100%"
      flexGrow={1}
      onSize={(cw, ch) => (cw !== w || ch !== h) && setSize([cw, ch])}
      onMouseMove={(x) => {
        const slot = slotAtX(drawn?.lay ?? null, x)
        if (slot !== hover) setHover(slot)
      }}
      onMouseOut={() => setHover(null)}
    />
  ) : (
    <box flexGrow={1} alignItems="center" justifyContent="center" paddingLeft={2} paddingRight={2}>
      <text fg={theme.muted} wrapMode="word">
        {p.empty || EMPTY}
      </text>
    </box>
  )
  const head = isParts(title) ? <Fitted parts={title} base={theme.muted} /> : <Line segs={title} base={theme.muted} />
  if (p.bare)
    return (
      <box flexDirection="column" flexGrow={p.flexGrow} flexBasis={p.flexGrow ? 0 : undefined} height={p.height} minHeight={p.minHeight} width={p.width} overflow="hidden">
        {head}
        {body}
      </box>
    )
  return (
    <Panel flexGrow={p.flexGrow} height={p.height} minHeight={p.minHeight} width={p.width} marginRight={p.marginRight}>
      {head}
      {body}
    </Panel>
  )
}
