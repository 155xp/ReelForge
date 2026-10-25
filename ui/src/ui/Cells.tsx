// A grid of cells drawn straight into OpenTUI's buffer: the charts, the sparklines, the logo, the bell and a
// notification's ×. Each cell has a character, a colour and a background (null: whatever is under it).

import { RGBA, type MouseEvent, type OptimizedBuffer, type Renderable } from "@opentui/core"
import type { Cell } from "../lib/chart"

const colours = new Map<string, RGBA>()
const CLEAR = RGBA.fromValues(0, 0, 0, 0)

export function rgba(hex: string | null | undefined): RGBA {
  if (!hex) return CLEAR
  let c = colours.get(hex)
  if (!c) colours.set(hex, (c = RGBA.fromHex(hex)))
  return c
}

export function draw(buffer: OptimizedBuffer, grid: Cell[][], x0: number, y0: number, width: number, height: number) {
  for (let y = 0; y < Math.min(grid.length, height); y++) {
    const row = grid[y]!
    for (let x = 0; x < Math.min(row.length, width); x++) {
      const cell = row[x]!
      if (cell.ch === " " && !cell.bg) continue
      if (cell.bg) buffer.setCell(x0 + x, y0 + y, cell.ch, rgba(cell.fg ?? "#ffffff"), rgba(cell.bg))
      else buffer.setCellWithAlphaBlending(x0 + x, y0 + y, cell.ch, rgba(cell.fg ?? "#ffffff"), CLEAR)
    }
  }
}

interface CellsProps {
  grid: Cell[][]
  width?: number | "auto" | `${number}%`
  height?: number | "auto" | `${number}%`
  flexGrow?: number
  onSize?: (width: number, height: number) => void
  onMouseMove?: (x: number, y: number) => void
  onMouseOut?: () => void
  onMouseDown?: (x: number, y: number, e: MouseEvent) => void
  marginLeft?: number
  marginRight?: number
}

/** The grid at this box's place; mouse positions come back relative to its top left. */
export function Cells(props: CellsProps) {
  const { grid } = props
  // A grid that grows takes the room it's given (and says how much, so it can be drawn to fit); others are as big as
  // what they show.
  const w = props.width ?? Math.max(0, ...grid.map((r) => r.length))
  const h = props.height ?? (props.flexGrow ? undefined : grid.length)
  return (
    <box
      width={w}
      height={h}
      flexGrow={props.flexGrow}
      flexBasis={props.flexGrow ? 0 : undefined}
      flexShrink={props.flexGrow ? 1 : 0}
      marginLeft={props.marginLeft}
      marginRight={props.marginRight}
      renderAfter={function (this: Renderable, buffer: OptimizedBuffer) {
        draw(buffer, grid, this.x, this.y, this.width, this.height)
      }}
      onSizeChange={
        props.onSize
          ? function (this: Renderable) {
              props.onSize!(this.width, this.height)
            }
          : undefined
      }
      onMouseMove={
        props.onMouseMove
          ? function (this: Renderable, e) {
              props.onMouseMove!(e.x - this.x, e.y - this.y)
            }
          : undefined
      }
      onMouseOut={props.onMouseOut}
      onMouseDown={
        props.onMouseDown
          ? function (this: Renderable, e) {
              props.onMouseDown!(e.x - this.x, e.y - this.y, e)
            }
          : undefined
      }
    />
  )
}
