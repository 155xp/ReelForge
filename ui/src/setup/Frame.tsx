// What every first-run screen shares: one double-line box round the whole terminal, the three steps on its top edge
// (the current one lit), and the logo at the top: the full one when the window has room for it, the anvil with the
// name beside it when it's smaller, none when it's short. The box stays whole at any size: its sides are a border of
// the box inside (so they're always as tall as it), what's inside never pushes its edges off the window, and the
// steps on the top edge shrink to the current one when they don't fit.

import { TextAttributes } from "@opentui/core"
import { useTerminalDimensions } from "@opentui/react"
import { useMemo, type ReactNode } from "react"
import { useTheme } from "../lib/focus"
import { cellLen, type Segs } from "../lib/styled"
import { Cells } from "../ui/Cells"
import { logoCells, widthOf } from "../ui/Graphics"
import { Line } from "../ui/Line"
import type { SetupInit } from "./App"

const WHITE = "#ffffff"
const RED = "#e8213a"

/** The frame's title: the three first-run steps, the current one lit. */
export function stepTitle(init: SetupInit, current: string): Segs {
  const keys = init.steps.map(([k]) => k)
  const here = keys.indexOf(current)
  const out: Segs = [[" ", ""]]
  init.steps.forEach(([, label], n) => {
    if (n) out.push(["  ·  ", "#5b6270"])
    if (n < here) out.push([`${init.check} ${label}`, "#4ade80"])
    else if (n === here) out.push([`${n + 1} ${label}`, `bold ${WHITE}`])
    else out.push([`${n + 1} ${label}`, "#8a94a3"])
  })
  out.push([" ", ""])
  return out
}

/** Shorter than this, the screens drop the small logo too, to keep their room for what they ask. */
const LOGO_MIN_HEIGHT = 26

export function Frame({
  init,
  step,
  bigMinHeight,
  children,
}: {
  init: SetupInit
  step: string
  bigMinHeight: number
  children: ReactNode
}) {
  const theme = useTheme()
  const { width, height } = useTerminalDimensions()
  const big = useMemo(() => logoCells(init.big), [init.big])
  const anvil = useMemo(() => logoCells(init.anvil), [init.anvil])
  const showBig = width >= widthOf(big) + 8 && height >= bigMinHeight
  const showAnvil = !showBig && height >= LOGO_MIN_HEIGHT && width >= widthOf(anvil) + 20
  const title = fit(stepTitle(init, step), init, step, width - 6)
  const tw = cellLen(title.map((s) => s[0]).join(""))
  const left = Math.max(Math.floor((width - 2 - tw) / 2), 0)
  const red = theme.primary
  return (
    <box flexDirection="column" width="100%" height="100%" backgroundColor={theme.bg}>
      <text wrapMode="none" height={1} flexShrink={0}>
        <span fg={red}>{"╔" + "═".repeat(left)}</span>
        {title.map((s, i) => {
          const bold = (s[1] ?? "").includes("bold")
          const fg = (s[1] ?? "").split(" ").find((w) => w.startsWith("#"))
          return (
            <span key={i} fg={fg ?? theme.text} attributes={bold ? TextAttributes.BOLD : undefined}>
              {s[0]}
            </span>
          )
        })}
        <span fg={red}>{"═".repeat(Math.max(width - 2 - left - tw, 0)) + "╗"}</span>
      </text>
      <box
        flexDirection="column"
        flexGrow={1}
        flexShrink={1}
        minHeight={0}
        overflow="hidden"
        border={["left", "right"]}
        borderStyle="double"
        borderColor={red}
        paddingLeft={2}
        paddingRight={2}
      >
        {showBig || showAnvil ? (
          <box flexDirection="row" justifyContent="center" paddingTop={1} paddingBottom={showBig ? 1 : 0} flexShrink={0}>
            {showBig ? (
              <Cells grid={big} />
            ) : (
              <box flexDirection="row">
                <Cells grid={anvil} />
                <box justifyContent="center" marginLeft={2}>
                  <Line segs={[["reel", `bold ${WHITE}`], ["forge", `bold ${RED}`]]} />
                </box>
              </box>
            )}
          </box>
        ) : null}
        <box flexDirection="column" flexGrow={1} flexShrink={1} minHeight={0}>
          {children}
        </box>
      </box>
      <text fg={red} wrapMode="none" height={1} flexShrink={0}>
        {"╚" + "═".repeat(Math.max(width - 2, 0)) + "╝"}
      </text>
    </box>
  )
}

/** The steps for the top edge, in room cells: all three, else just the current one, else none. */
function fit(full: Segs, init: SetupInit, step: string, room: number): Segs {
  if (cellLen(full.map((s) => s[0]).join("")) <= room) return full
  const n = init.steps.findIndex(([k]) => k === step)
  const one: Segs = [[` ${n + 1}/${init.steps.length}  ${init.steps[n]?.[1] ?? ""} `, `bold ${WHITE}`]]
  return cellLen(one[0]![0]) <= room ? one : []
}
