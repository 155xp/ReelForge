// What every first-run screen shares: one double-line box round the whole terminal, the three steps on its top edge
// (the current one lit), and the logo at the top: the full one when the window has room for it, the anvil with the
// name beside it when it's smaller, none when it's short. The box stays whole at any size: its sides are a border of
// the box inside (so they're always as tall as it), what's inside never pushes its edges off the window, and the
// steps on the top edge shrink to the current one when they don't fit. When the window is wide enough, the mascot
// stands in the bottom right corner, beside what the screen shows, under the full logo in a tall window and the small
// one otherwise (he matters more on these screens than the bigger logo does).

import { TextAttributes } from "@opentui/core"
import { useTerminalDimensions } from "@opentui/react"
import { useMemo, type ReactNode } from "react"
import { useTheme } from "../lib/focus"
import { cellLen, type Segs } from "../lib/styled"
import { Cells } from "../ui/Cells"
import { logoCells, widthOf } from "../ui/Graphics"
import { Line } from "../ui/Line"
import { MASCOT } from "../ui/Mascot"
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
/** The mascot's column: a gap, then him. */
const MASCOT_COLUMN = MASCOT.width + 2
/** The least a screen keeps for itself beside him (a 120-column terminal leaves it 69). */
const CONTENT_MIN = 66
/** Beside him a screen's content is narrower, so it wraps onto more rows: the full logo over both takes this many
 * more rows than the screen needs for it on its own. */
const MASCOT_MORE_ROWS = 8

export interface FrameLayout {
  logo: "big" | "anvil" | null
  mascot: boolean
  /** The columns and rows the screen's own content gets. */
  content: number
  rows: number
}

/** Which logo the frame shows in a window this size, whether the mascot stands beside the content, and the room that
 * leaves the content (Work sizes its progress bars by it, Onboard puts him under its steps when they leave him his). */
export function frameLayout(init: SetupInit, width: number, height: number, bigMinHeight: number, mascot: boolean): FrameLayout {
  const big = { w: widthOf(logoCells(init.big)), h: init.big.length }
  const anvil = { w: widthOf(logoCells(init.anvil)), h: init.anvil.length }
  const pick = (bigMin: number) =>
    width >= big.w + 8 && height >= bigMin ? "big" : height >= LOGO_MIN_HEIGHT && width >= anvil.w + 20 ? "anvil" : null
  // the rows left under each logo, inside the top and bottom edges
  const rows = (logo: FrameLayout["logo"]) => height - 2 - (logo === "big" ? big.h + 2 : logo === "anvil" ? anvil.h + 1 : 0)
  const inside = width - 6
  if (mascot && inside - MASCOT_COLUMN >= CONTENT_MIN) {
    const logo = pick(bigMinHeight + MASCOT_MORE_ROWS)
    if (logo && rows(logo) >= MASCOT.height) return { logo, mascot: true, content: inside - MASCOT_COLUMN, rows: rows(logo) }
  }
  const logo = pick(bigMinHeight)
  return { logo, mascot: false, content: inside, rows: rows(logo) }
}

export function Frame({
  init,
  step,
  bigMinHeight,
  mascot,
  children,
}: {
  init: SetupInit
  step: string
  bigMinHeight: number
  /** The mascot (ui/Mascot.tsx at its full size, MASCOT), when there's room for him. */
  mascot?: ReactNode
  children: ReactNode
}) {
  const theme = useTheme()
  const { width, height } = useTerminalDimensions()
  const big = useMemo(() => logoCells(init.big), [init.big])
  const anvil = useMemo(() => logoCells(init.anvil), [init.anvil])
  const layout = frameLayout(init, width, height, bigMinHeight, Boolean(mascot))
  const showBig = layout.logo === "big"
  const showAnvil = layout.logo === "anvil"
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
        <box flexDirection="row" flexGrow={1} flexShrink={1} minHeight={0}>
          <box flexDirection="column" flexGrow={1} flexShrink={1} minHeight={0}>
            {children}
          </box>
          {layout.mascot ? (
            <box flexDirection="column" justifyContent="flex-end" flexShrink={0} marginLeft={MASCOT_COLUMN - MASCOT.width}>
              {mascot}
            </box>
          ) : null}
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
