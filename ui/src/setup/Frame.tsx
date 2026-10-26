// What every first-run screen shares: the three steps across the top (the ones done ticked, the current one lit), then
// the logo: the full one, "reel" in white and "forge" in red with the forge's glow under it, when the window has room
// for it, the anvil with the name beside it when it's smaller, none when it's short. No box round the window: the
// screens sit on the same calm dark as ReelForge's own window, and what's inside never pushes off the edge at any size.
// When the window is wide enough, the mascot stands in the bottom right corner, beside what the screen shows, under
// the full logo in a tall window and the small one otherwise (he matters more on these screens than the bigger logo
// does).

import { useTerminalDimensions } from "@opentui/react"
import { useMemo, type ReactNode } from "react"
import { useTheme } from "../lib/focus"
import { cellLen, type Segs } from "../lib/styled"
import { along, EMBER, mix } from "../theme"
import { Cells } from "../ui/Cells"
import { logoCells, shade, widthOf } from "../ui/Graphics"
import { Line } from "../ui/Line"
import { MASCOT } from "../ui/Mascot"
import { useProgress } from "../ui/Motion"
import type { SetupInit } from "./App"

const WHITE = "#ffffff"
const RED = "#e8213a"
/** The logo's white shaded to a pale grey at its foot, and its red from bright to deep. */
const WHITE_SHADE = ["#ffffff", "#ffffff", "#d9dde3"]
const RED_SHADE = ["#ff3b52", "#e8213a", "#b8102a"]

/** The steps across the top: the ones done ticked in green, the current one white and bold with a red dot, the rest
 * faint, joined by short rules. */
export function stepTitle(init: SetupInit, current: string, faint = "#5d6470", good = "#3ddc97"): Segs {
  const keys = init.steps.map(([k]) => k)
  const here = keys.indexOf(current)
  const out: Segs = []
  init.steps.forEach(([, label], n) => {
    if (n) out.push(["   ───   ", mix(faint, "#000000", 0.35)])
    if (n < here) out.push([`${init.check} ${label}`, good])
    else if (n === here) out.push(["● ", RED], [label, `bold ${WHITE}`])
    else out.push([`○ ${label}`, faint])
  })
  return out
}

/** Shorter than this, the screens drop the small logo too, to keep their room for what they ask. */
const LOGO_MIN_HEIGHT = 26
/** The mascot's column: a gap, then him. */
const MASCOT_COLUMN = MASCOT.width + 2
/** The least a screen keeps for itself beside him (a 120-column terminal leaves it 67). */
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
  // the rows left under each logo: under the steps (and the row over them), the logo with its padding (and the glow
  // under the full one), and the row over the content
  const rows = (logo: FrameLayout["logo"]) => height - 3 - (logo === "big" ? big.h + 4 : logo === "anvil" ? anvil.h + 1 : 0)
  const inside = width - 8
  if (mascot && inside - MASCOT_COLUMN >= CONTENT_MIN) {
    const logo = pick(bigMinHeight + MASCOT_MORE_ROWS)
    if (logo && rows(logo) >= MASCOT.height) return { logo, mascot: true, content: inside - MASCOT_COLUMN, rows: rows(logo) }
  }
  const logo = pick(bigMinHeight)
  return { logo, mascot: false, content: inside, rows: rows(logo) }
}

/** The full logo, each colour shaded down its height. */
function bigLogo(rows: [string, string | null, string | null][][]) {
  const cells = logoCells(rows)
  const h = cells.length
  return cells.map((row, y) =>
    row.map((c) => (c.fg ? { ...c, fg: along(c.fg.toLowerCase() === RED ? RED_SHADE : WHITE_SHADE, h > 1 ? y / (h - 1) : 0) } : c)),
  )
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
  const big = useMemo(() => bigLogo(init.big), [init.big])
  const anvil = useMemo(() => shade(logoCells(init.anvil), WHITE_SHADE), [init.anvil])
  const layout = frameLayout(init, width, height, bigMinHeight, Boolean(mascot))
  const showBig = layout.logo === "big"
  const showAnvil = layout.logo === "anvil"
  const title = fit(stepTitle(init, step, theme.faint, theme.good), init, step, width - 4)
  // the forge's glow under the logo warms up as the screen opens
  const glow = useProgress("logo", { ms: 900, ease: "outQuad" })
  const glowW = Math.min(widthOf(big) + 10, width - 8)
  return (
    <box flexDirection="column" width="100%" height="100%" backgroundColor={theme.bg} paddingLeft={4} paddingRight={4}>
      <box flexDirection="row" justifyContent="center" height={1} marginTop={1} flexShrink={0}>
        <Line segs={title} />
      </box>
      {showBig || showAnvil ? (
        <box flexDirection="column" alignItems="center" paddingTop={showBig ? 2 : 1} flexShrink={0}>
          {showBig ? (
            <>
              <Cells grid={big} />
              <text wrapMode="none" height={1} marginTop={1}>
                {[...Array(Math.max(glowW, 0)).keys()].map((x) => {
                  // red into ember and back, fading out at both ends, brighter as it warms up
                  const t = x / Math.max(glowW - 1, 1)
                  const edge = Math.min(t, 1 - t) * 2
                  return (
                    <span key={x} fg={mix(theme.bg, along([EMBER[0], EMBER[1], EMBER[0]], t), Math.min(1, edge * 1.6) * glow)}>
                      ▀
                    </span>
                  )
                })}
              </text>
            </>
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
      <box flexDirection="row" flexGrow={1} flexShrink={1} minHeight={0} marginTop={1} overflow="hidden">
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
  )
}

/** The steps for the top, in `room` cells: all three, else just the current one, else none. */
function fit(full: Segs, init: SetupInit, step: string, room: number): Segs {
  if (cellLen(full.map((s) => s[0]).join("")) <= room) return full
  const n = init.steps.findIndex(([k]) => k === step)
  const one: Segs = [
    ["● ", RED],
    [`${n + 1}/${init.steps.length}  ${init.steps[n]?.[1] ?? ""}`, `bold ${WHITE}`],
  ]
  return cellLen(one.map((s) => s[0]).join("")) <= room ? one : []
}
