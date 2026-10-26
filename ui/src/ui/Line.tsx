// Styled text from the Python side: a line whose chips and keys can be clicked, several lines, and parts fitted to
// the width they get.

import { TextAttributes, type Renderable } from "@opentui/core"
import { createContext, useContext, useState, type ReactNode } from "react"
import { fit } from "../lib/fit"
import { cellLen, lines, parseStyle, type Action, type Parts, type Segs } from "../lib/styled"
import { mix } from "../theme"

/** What clicking a chip or a key does: the app runs the action (dashboard/actions.ts). */
export const ActionContext = createContext<(action: Action) => void>(() => {})

export function useAction() {
  return useContext(ActionContext)
}

interface LineProps {
  segs: Segs | undefined
  /** The style for segments that have none. */
  base?: string
  width?: number | "auto" | `${number}%`
  flexGrow?: number
  flexShrink?: number
  bg?: string
}

/** One line of styled text; a segment with an action is a button. */
export function Line({ segs, base, width, flexGrow, flexShrink, bg }: LineProps) {
  const run = useAction()
  const [hover, setHover] = useState<number | null>(null)
  const list = segs ?? []
  const clickable = list.some((s) => s[2])
  const at = (node: Renderable, x: number) => {
    let col = 0
    for (let i = 0; i < list.length; i++) {
      const n = cellLen(list[i]![0])
      if (x - node.x >= col && x - node.x < col + n) return i
      col += n
    }
    return null
  }
  return (
    <text
      width={width}
      flexGrow={flexGrow}
      flexShrink={flexShrink ?? 0}
      bg={bg}
      wrapMode="none"
      onMouseDown={
        clickable
          ? function (this: Renderable, e) {
              const i = at(this, e.x)
              const action = i === null ? undefined : list[i]![2]
              if (action && e.button === 0) {
                e.stopPropagation()
                run(action)
              }
            }
          : undefined
      }
      onMouseMove={
        clickable
          ? function (this: Renderable, e) {
              const i = at(this, e.x)
              setHover(i !== null && list[i]![2] ? i : null)
            }
          : undefined
      }
      onMouseOut={clickable ? () => setHover(null) : undefined}
    >
      {list.map((s, i) => {
        const st = parseStyle(base && !s[1] ? base : s[1])
        let fg = st.fg
        let sbg = st.bg
        let attributes = st.attributes
        if (i === hover) {
          if (sbg) sbg = mix(sbg, "#ffffff", 0.12)
          else attributes |= TextAttributes.UNDERLINE
          if (fg) fg = mix(fg, "#ffffff", 0.15)
        }
        return (
          <span key={i} fg={fg} bg={sbg} attributes={attributes || undefined}>
            {s[0]}
          </span>
        )
      })}
    </text>
  )
}

/** Styled text over several lines (split at its newlines; nothing is wrapped). */
export function Lines({ segs, base, bg }: { segs: Segs | undefined; base?: string; bg?: string }) {
  return (
    <box flexDirection="column" flexShrink={0} backgroundColor={bg}>
      {lines(segs).map((line, i) => (
        <Line key={i} segs={line} base={base} />
      ))}
    </box>
  )
}

/** Parts fitted to the width this gets: the least important go first when it's narrow (lib/fit.ts). */
export function Fitted({
  parts,
  base,
  flexGrow = 0,
  right,
}: {
  parts: Parts | undefined
  base?: string
  flexGrow?: number
  /** Also fitted, kept at the right-hand end. */
  right?: Segs
}) {
  const [width, setWidth] = useState(0)
  const room = Math.max(width - (right ? cellLen(right.map((s) => s[0]).join("")) + 1 : 0), 1)
  return (
    <box
      flexDirection="row"
      height={1}
      flexGrow={flexGrow}
      flexShrink={flexGrow ? 1 : 0}
      minWidth={1}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      <Line segs={width ? fit(parts ?? [], room) : []} base={base} flexGrow={1} />
      {right ? <Line segs={right} /> : null}
    </box>
  )
}

/** A line of badges, with what badges are under it while the mouse is on it. */
export function BadgeLine({ parts, how, bg, fg }: { parts: Parts; how: string; bg: string; fg: string }) {
  const [hover, setHover] = useState(false)
  return (
    <box
      height={1}
      paddingLeft={1}
      paddingRight={1}
      flexShrink={0}
      onMouseOver={() => setHover(true)}
      onMouseOut={() => setHover(false)}
    >
      <Fitted parts={parts} />
      {hover ? (
        <box position="absolute" top={1} left={2} width={70} zIndex={40} backgroundColor={bg} border borderColor={fg} paddingLeft={1} paddingRight={1}>
          <text fg={fg} wrapMode="word">
            {how}
          </text>
        </box>
      ) : null}
    </box>
  )
}

/** Text that wraps at spaces to the width it gets (plain words, one style). */
export function Para({ children, fg, bold }: { children: ReactNode; fg?: string; bold?: boolean }) {
  return (
    <text fg={fg} wrapMode="word" attributes={bold ? TextAttributes.BOLD : undefined} flexShrink={0}>
      {children}
    </text>
  )
}
