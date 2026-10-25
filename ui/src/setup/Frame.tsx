// What every first-run screen shares: one double-line box round the whole terminal, the three steps on its top edge
// (the current one lit), a hint on its bottom edge, and the logo at the top: the full one when the window has room
// for it, otherwise the anvil with the name beside it.

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

export function Frame({
  init,
  step,
  hint,
  bigMinHeight,
  children,
}: {
  init: SetupInit
  step: string
  hint: string
  bigMinHeight: number
  children: ReactNode
}) {
  const theme = useTheme()
  const { width, height } = useTerminalDimensions()
  const big = useMemo(() => logoCells(init.big), [init.big])
  const anvil = useMemo(() => logoCells(init.anvil), [init.anvil])
  const showBig = width >= widthOf(big) + 8 && height >= bigMinHeight
  const title = stepTitle(init, step)
  const tw = cellLen(title.map((s) => s[0]).join(""))
  const left = Math.max(Math.floor((width - 2 - tw) / 2), 0)
  const hw = cellLen(hint)
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
      <box flexDirection="row" flexGrow={1}>
        <text fg={red} width={1} flexShrink={0}>
          {"║\n".repeat(Math.max(height - 2, 0))}
        </text>
        <box flexDirection="column" flexGrow={1} paddingLeft={2} paddingRight={2}>
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
          {children}
        </box>
        <text fg={red} width={1} flexShrink={0}>
          {"║\n".repeat(Math.max(height - 2, 0))}
        </text>
      </box>
      <text wrapMode="none" height={1} flexShrink={0}>
        <span fg={red}>{"╚" + "═".repeat(Math.max(width - 3 - hw, 0))}</span>
        <span fg={theme.muted}>{hint}</span>
        <span fg={red}>{"═╝"}</span>
      </text>
    </box>
  )
}
