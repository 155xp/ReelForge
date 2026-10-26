// A table (header, rows of cells, one highlighted row) and a list of options (each one or more lines). Both scroll
// with the mouse wheel, keep the highlighted one in view, and take the arrow keys while they have the keyboard: Enter
// (or a click on the highlighted one) picks it, a click on a table's header sorts by that column.

import type { KeyEvent, MouseEvent, Renderable } from "@opentui/core"
import { useEffect, useRef, useState, type ReactNode } from "react"
import { useFocus, useTheme } from "../lib/focus"
import { pad, type Segs } from "../lib/styled"
import { Cells } from "./Cells"
import { Line } from "./Line"

export interface Column {
  key: string
  label: Segs
  width: number
  right: boolean
}

export interface Row {
  key: string | null
  cells: Segs[]
}

export interface TableData {
  columns: Column[]
  rows: Row[]
}

const ZEBRA = "#0e1114"
const TRACK = "#14181e"
const THUMB = "#474a4f"

/** A one-column scrollbar: `visible` of `total` lines shown, from `offset`. */
function Scrollbar({ total, visible, offset, height }: { total: number; visible: number; offset: number; height: number }) {
  if (total <= visible || height <= 0) return null
  const size = Math.max(1, Math.round((visible / total) * height))
  const start = Math.min(height - size, Math.round((offset / Math.max(total - visible, 1)) * (height - size)))
  const grid = Array.from({ length: height }, (_, y) => [
    { ch: "▐", fg: y >= start && y < start + size ? THUMB : TRACK, bg: null },
  ])
  return <Cells grid={grid} width={1} height={height} />
}

function move(key: KeyEvent, index: number, count: number, page: number): number | null {
  switch (key.name) {
    case "up":
      return Math.max(index - 1, 0)
    case "down":
      return Math.min(index + 1, count - 1)
    case "pageup":
      return Math.max(index - page, 0)
    case "pagedown":
      return Math.min(index + page, count - 1)
    case "home":
      return 0
    case "end":
      return count - 1
  }
  return null
}

function isEnter(key: KeyEvent): boolean {
  return key.name === "return" || key.name === "enter"
}

export interface TableProps {
  id: string
  data: TableData | undefined
  selected?: string | null
  onSelect?: (key: string | null) => void
  onActivate?: (key: string) => void
  onSort?: (column: string) => void
  zebra?: boolean
  /** Rows tall (the header comes on top); otherwise it takes the room it's given. */
  rowsShown?: number
  flexGrow?: number
  /** Show the highlighted row even while the table doesn't have the keyboard. */
  cursor?: boolean
}

export function Table(props: TableProps) {
  const theme = useTheme()
  const columns = props.data?.columns ?? []
  const rows = props.data?.rows ?? []
  const keys = rows.map((r) => r.key)
  const index = props.selected ? keys.indexOf(props.selected) : -1
  const [offset, setOffset] = useState(0)
  const [height, setHeight] = useState(props.rowsShown ?? 0)
  const shown = Math.max((props.rowsShown ?? height) - 0, 1)
  const select = (i: number) => {
    const key = rows[i]?.key ?? null
    if (key !== null) props.onSelect?.(key)
  }
  const { ref, focused, focus } = useFocus(props.id, {
    onKey: (key) => {
      if (isEnter(key) && index >= 0 && props.selected) {
        props.onActivate?.(props.selected)
        return true
      }
      const next = move(key, Math.max(index, 0), rows.length, Math.max(shown - 1, 1))
      if (next === null || !rows.length) return false
      select(next)
      return true
    },
  })
  // keep the highlighted row in view
  const view = useRef({ offset, shown })
  view.current = { offset, shown }
  useEffect(() => {
    if (index < 0) return
    const { offset: o, shown: s } = view.current
    if (index < o) setOffset(index)
    else if (index >= o + s) setOffset(index - s + 1)
  }, [index])
  useEffect(() => {
    const most = Math.max(rows.length - shown, 0)
    if (offset > most) setOffset(most)
  }, [rows.length, shown, offset])

  const widths = columns.map((c) => c.width + 2)
  const header: Segs = columns.flatMap((c) => [[" ", ""], ...pad(c.label, c.width, c.right), [" ", ""]] as Segs)
  const clickHeader = function (this: Renderable, e: MouseEvent) {
    if (!props.onSort) return
    let x = e.x - this.x
    for (let i = 0; i < columns.length; i++) {
      if (x < widths[i]!) {
        if (columns[i]!.key && columns[i]!.label.length) props.onSort(columns[i]!.key)
        return
      }
      x -= widths[i]!
    }
  }
  const visible = rows.slice(offset, offset + shown)
  return (
    <box
      ref={ref}
      flexDirection="column"
      flexGrow={props.rowsShown ? 0 : (props.flexGrow ?? 1)}
      flexShrink={props.rowsShown ? 0 : 1}
      height={props.rowsShown ? props.rowsShown + 1 : undefined}
      minHeight={2}
      onMouseDown={() => focus()}
      onMouseScroll={(e) => {
        const d = e.scroll?.direction === "up" ? -3 : e.scroll?.direction === "down" ? 3 : 0
        setOffset((o) => Math.min(Math.max(o + d, 0), Math.max(rows.length - shown, 0)))
      }}
    >
      <box height={1} flexShrink={0} onMouseDown={clickHeader}>
        <Line segs={header} base="bold" />
      </box>
      <box
        flexDirection="row"
        flexGrow={1}
        onSizeChange={function (this: Renderable) {
          if (!props.rowsShown) setHeight(this.height)
        }}
      >
        <box flexDirection="column" flexGrow={1}>
          {visible.map((row, i) => {
            const at = offset + i
            const cells: Segs = columns.flatMap((c, j) => [[" ", ""], ...pad(row.cells[j] ?? [], c.width, c.right), [" ", ""]] as Segs)
            const bg =
              at === index && (focused || props.cursor !== false)
                ? focused
                  ? theme.cursor
                  : theme.cursorIdle
                : props.zebra && at % 2 === 1
                  ? ZEBRA
                  : undefined
            return (
              <box
                key={`${row.key ?? "row"}-${at}`}
                height={1}
                backgroundColor={bg}
                onMouseDown={(e) => {
                  if (e.button !== 0 || row.key === null) return
                  if (row.key === props.selected) props.onActivate?.(row.key)
                  else props.onSelect?.(row.key)
                }}
              >
                <Line segs={cells} bg={bg} />
              </box>
            )
          })}
        </box>
        <Scrollbar total={rows.length} visible={shown} offset={offset} height={shown} />
      </box>
    </box>
  )
}

export interface Option {
  id: string
  lines: Segs[]
  disabled?: boolean
}

export interface OptionListProps {
  id: string
  items: Option[]
  selected?: string | null
  onSelect?: (id: string) => void
  onActivate?: (id: string) => void
  onMenu?: (id: string) => void
  /** Drawn at the right of each option, in the middle of its height (a notification's ×). */
  aside?: (item: Option, lines: number) => ReactNode
  flexGrow?: number
  /** A blank line after each option. */
  spaced?: boolean
  bg?: string
  onDelete?: (id: string) => void
  /** Height in lines, when it shouldn't take all the room it's given. */
  maxLines?: number
  empty?: ReactNode
}

export function OptionList(props: OptionListProps) {
  const theme = useTheme()
  const items = props.items
  const index = props.selected ? items.findIndex((it) => it.id === props.selected) : -1
  const [offset, setOffset] = useState(0)
  const [height, setHeight] = useState(props.maxLines ?? 0)
  const tall = (it: Option) => it.lines.length + (props.spaced ? 1 : 0)
  const fits = (from: number) => {
    let n = 0
    let used = 0
    for (let i = from; i < items.length; i++) {
      used += tall(items[i]!)
      if (used > height && n > 0) break
      n++
    }
    return n
  }
  const shown = Math.max(fits(offset), 1)
  const pick = (i: number) => {
    const it = items[i]
    if (it && !it.disabled) props.onSelect?.(it.id)
  }
  const { ref, focused, focus } = useFocus(props.id, {
    onKey: (key) => {
      if (isEnter(key) && props.selected) {
        props.onActivate?.(props.selected)
        return true
      }
      if (key.name === "delete" && props.selected && props.onDelete) {
        props.onDelete(props.selected)
        return true
      }
      const next = move(key, Math.max(index, 0), items.length, Math.max(shown - 1, 1))
      if (next === null || !items.length) return false
      pick(next)
      return true
    },
  })
  useEffect(() => {
    if (index < 0) return
    if (index < offset) setOffset(index)
    else if (index >= offset + shown) {
      let o = offset
      while (o < index && index >= o + fits(o)) o++
      setOffset(o)
    }
  }, [index, height])
  useEffect(() => {
    if (offset >= items.length && items.length) setOffset(Math.max(items.length - 1, 0))
  }, [items.length, offset])
  const totalLines = items.reduce((n, it) => n + tall(it), 0)
  const linesBefore = items.slice(0, offset).reduce((n, it) => n + tall(it), 0)
  const visible = items.slice(offset, offset + shown)
  return (
    <box
      ref={ref}
      flexDirection="row"
      flexGrow={props.maxLines ? 0 : (props.flexGrow ?? 1)}
      height={props.maxLines ? Math.min(props.maxLines, Math.max(totalLines, 1)) : undefined}
      flexShrink={1}
      backgroundColor={props.bg}
      onMouseDown={() => focus()}
      onMouseScroll={(e) => {
        const d = e.scroll?.direction === "up" ? -1 : e.scroll?.direction === "down" ? 1 : 0
        setOffset((o) => Math.min(Math.max(o + d, 0), Math.max(items.length - 1, 0)))
      }}
      onSizeChange={function (this: Renderable) {
        setHeight(this.height)
      }}
    >
      <box flexDirection="column" flexGrow={1}>
        {!items.length && props.empty}
        {visible.map((it, i) => {
          const at = offset + i
          const bg = at === index ? (focused ? theme.cursor : theme.cursorIdle) : undefined
          return (
            <box
              key={it.id}
              flexDirection="column"
              flexShrink={0}
              onMouseDown={(e) => {
                if (it.disabled) return
                if (e.button === 2) {
                  pick(at)
                  props.onMenu?.(it.id)
                  return
                }
                if (e.button !== 0) return
                if (it.id === props.selected) props.onActivate?.(it.id)
                else pick(at)
              }}
            >
              <box flexDirection="row" backgroundColor={bg}>
                <box flexDirection="column" flexGrow={1}>
                  {it.lines.map((line, j) => (
                    <Line key={j} segs={line} />
                  ))}
                </box>
                {props.aside?.(it, it.lines.length)}
              </box>
              {props.spaced ? <box height={1} /> : null}
            </box>
          )
        })}
      </box>
      <Scrollbar total={totalLines} visible={height} offset={linesBefore} height={height} />
    </box>
  )
}
