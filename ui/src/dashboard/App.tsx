// ReelForge's window: the header (the anvil, the profile button, six tabs with a marker that slides to the open one,
// Refresh / Help / Quit and the bell), the tab, the status bar at the foot (each platform, when the stats were read,
// any read under way, the keys), the notifications drawer sliding in from the right, dialogs, and pop-ups. Keys: 1-6
// switch tabs, r / R refresh, p the profiles, Esc closes the drawer or leaves a text field, Tab moves between buttons
// and fields, Ctrl+Q quits.

import { TextAttributes, type KeyEvent, type Renderable } from "@opentui/core"
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useView, type Bridge } from "../bridge"
import { FocusContext, FocusManager, ThemeContext } from "../lib/focus"
import { cellLen, segsLen, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Cells } from "../ui/Cells"
import { bell, BELL_WIDTH, logoCells, shade, widthOf } from "../ui/Graphics"
import { ActionContext, Line } from "../ui/Line"
import { useProgress, useTween } from "../ui/Motion"
import { ToastStack, toasts } from "../ui/Panels"
import { Accounts } from "./Accounts"
import { Compare } from "./Compare"
import { Dialogs } from "./Dialogs"
import { Drawer } from "./Drawer"
import { Overview } from "./Overview"
import { ProfileButton } from "./Profiles"
import { Publish } from "./Publish"
import { DashContext, DashState, TAB_NAMES, TABS, useDash, type Nav } from "./state"
import type { Init, NotesView, UpdateView } from "./types"
import { Updates } from "./Updates"
import { Videos } from "./Videos"

export function DashboardApp({ bridge, init, quit, nav }: { bridge: Bridge; init: Init; quit: (code?: number) => void; nav?: Nav }) {
  const state = useMemo(() => new DashState(bridge, init, quit, nav), [bridge, init, quit, nav])
  const focus = useMemo(() => new FocusManager(), [])
  useEffect(() => {
    const offs = [
      bridge.on("toast", (t) => toasts.add(t)),
      bridge.on("tab", (d) => state.set({ tab: d.tab })),
      bridge.on("pick", (d) => state.pick(d.id)),
      bridge.on("focus", (d) => setTimeout(() => focus.focus(d.id), 50)),
      bridge.on("exit", (d) => quit(d.code ?? 0)),
      // A picked video's caption and hashtags, for the Publish form (whichever tab is open when it's picked).
      bridge.on("form", (d) => state.set({ caption: d.caption ?? "", tags: d.tags ?? "" })),
    ]
    if (state.drawer) bridge.send("drawer_opened")
    return () => offs.forEach((off) => off())
  }, [bridge, state, focus, quit])
  return (
    <ThemeContext.Provider value={DASH}>
      <FocusContext.Provider value={focus}>
        <DashContext.Provider value={state}>
          <ActionContext.Provider value={state.run}>
            <Window focus={focus} />
          </ActionContext.Provider>
        </DashContext.Provider>
      </FocusContext.Provider>
    </ThemeContext.Provider>
  )
}

function Window({ focus }: { focus: FocusManager }) {
  const s = useDash()
  const renderer = useRenderer()
  // The copy buttons' fallback when the system clipboard can't be reached: the terminal's own (OSC 52).
  useEffect(() => s.bridge.on("clipboard", (d) => void renderer.copyToClipboardOSC52(d.text)), [s, renderer])
  useKeyboard((key: KeyEvent) => {
    if (key.ctrl && (key.name === "q" || key.name === "c")) return s.quit(0)
    if (key.name === "escape") {
      if (s.dialog) return s.set({ dialog: null })
      if (focus.typing) return focus.blur()
      if (s.drawer) return s.toggleDrawer(false)
      return
    }
    if (focus.handleKey(key)) return
    if (s.dialog || focus.typing || key.ctrl || key.meta) return
    if (/^[1-6]$/.test(key.name)) return s.setTab(TABS[Number(key.name) - 1]!)
    if (key.name === "r") return s.bridge.send("refresh", key.shift)
    if (key.name === "p") return s.openProfiles()
    if (key.name === "?" || key.sequence === "?") return s.set({ dialog: { kind: "help" } })
  })
  return (
    <box flexDirection="column" width="100%" height="100%" backgroundColor={DASH.bg}>
      <Header />
      <TabContent />
      <StatusBar />
      <Drawer />
      <Dialogs />
      <ToastStack />
    </box>
  )
}

/** The open tab. A tab you switch to slides in a few columns from the side you moved towards and comes up out of the
 * window's colour. */
function TabContent() {
  const s = useDash()
  const i = Math.max(TABS.indexOf(s.tab), 0)
  const last = useRef(i)
  const dir = i >= last.current ? 1 : -1
  useEffect(() => {
    last.current = i
  }, [i])
  const p = useProgress(s.tab, { ms: 220, ease: "outQuad" })
  const shift = Math.round((1 - p) * 3) * dir
  const veil = Math.round((1 - p) * 0xd0)
  return (
    <box flexDirection="column" flexGrow={1} paddingLeft={1 + Math.max(shift, 0)} paddingRight={1 + Math.max(-shift, 0)}>
      {s.tab === "overview" && <Overview />}
      {s.tab === "videos" && <Videos />}
      {s.tab === "compare" && <Compare />}
      {s.tab === "publish" && <Publish />}
      {s.tab === "accounts" && <Accounts />}
      {s.tab === "updates" && <Updates />}
      {veil > 8 ? <box position="absolute" left={0} top={0} width="100%" height="100%" zIndex={20} backgroundColor={DASH.bg + veil.toString(16).padStart(2, "0")} /> : null}
    </box>
  )
}

// ---------------------------------------------------------------- the header

const ANVIL_STOPS = ["#ffffff", "#d3d8de", "#8e97a3"]

/** How the header fits the window's width: the gap between tabs, the actions as words or signs, the profile's name
 * cut short, and the anvil, given up in that order. */
function headerFit(width: number, name: string, anvilW: number, tabsW: (gap: number) => number) {
  const bellW = BELL_WIDTH + 4
  const fixed = (anvil: boolean) => 1 + (anvil ? anvilW + 2 : 0) + 4 + bellW + 2
  for (const anvil of [true, false])
    for (const [gap, words] of [
      [4, true],
      [3, false],
      [2, false],
    ] as const) {
      const actions = words ? 29 : 10
      const room = width - fixed(anvil) - tabsW(gap) - actions
      if (room >= Math.min(cellLen(name), 12) + 6) return { anvil, gap, words, nameRoom: room - 6 }
    }
  return { anvil: false, gap: 2, words: false, nameRoom: 6 }
}

function Header() {
  const s = useDash()
  const { width } = useTerminalDimensions()
  const anvil = useMemo(() => shade(logoCells(s.init.anvil), ANVIL_STOPS), [s.init.anvil])
  const update = useView<UpdateView>(s.bridge, "update")
  const labels = TABS.map((t) => TAB_NAMES[t] + (t === "updates" && update?.newer ? " ●" : ""))
  const tabsW = (gap: number) => labels.reduce((n, l) => n + cellLen(l), 0) + gap * (labels.length - 1)
  const profile = useView<{ name: string }>(s.bridge, "profile") ?? s.init.profile
  const fit = headerFit(width, profile.name, widthOf(anvil), tabsW)
  return (
    <box flexDirection="column" flexShrink={0}>
      <box flexDirection="row" height={3} flexShrink={0} paddingLeft={1}>
        {fit.anvil && anvil.length ? <Cells grid={anvil} marginRight={2} /> : null}
        <ProfileButton room={fit.nameRoom} />
        <Tabs labels={labels} gap={fit.gap} />
        <box flexGrow={1} />
        <box flexDirection="column" justifyContent="center" flexShrink={0} marginRight={2}>
          <Line
            segs={
              fit.words
                ? [
                    ["↻ Refresh", DASH.muted, ["refresh"]],
                    ["    ", ""],
                    ["? Help", DASH.muted, ["help"]],
                    ["    ", ""],
                    ["Quit", DASH.muted, ["quit"]],
                  ]
                : [
                    ["↻", DASH.muted, ["refresh"]],
                    ["   ", ""],
                    ["?", DASH.muted, ["help"]],
                    ["   ", ""],
                    ["✕", DASH.muted, ["quit"]],
                  ]
            }
          />
        </box>
        <Bell />
      </box>
      <text fg={DASH.border} wrapMode="none" height={1} flexShrink={0}>
        {"─".repeat(Math.max(width, 1))}
      </text>
    </box>
  )
}

/** The tabs: the open one white and bold with a short bar under it that slides to whichever you pick; a red dot on
 * Updates when a new version is out. */
function Tabs({ labels, gap }: { labels: string[]; gap: number }) {
  const s = useDash()
  const [hover, setHover] = useState<number | null>(null)
  const starts: number[] = []
  let x = 0
  for (const l of labels) {
    starts.push(x)
    x += cellLen(l) + gap
  }
  const i = Math.max(TABS.indexOf(s.tab), 0)
  const at = useTween(starts[i]!, { ms: 220, ease: "outQuad" })
  const wide = useTween(cellLen(TAB_NAMES[TABS[i]!]), { ms: 220, ease: "outQuad" })
  const from = Math.round(at)
  return (
    <box flexDirection="column" flexShrink={0} marginLeft={3}>
      <box height={1} />
      <box flexDirection="row" height={1}>
        {TABS.map((tab, k) => {
          const on = k === i
          const name = TAB_NAMES[tab]
          return (
            <text
              key={tab}
              marginRight={k < TABS.length - 1 ? gap : 0}
              fg={on ? DASH.text : k === hover ? mix(DASH.muted, DASH.text, 0.6) : DASH.muted}
              attributes={on ? TextAttributes.BOLD : undefined}
              wrapMode="none"
              onMouseOver={() => setHover(k)}
              onMouseOut={() => setHover((h) => (h === k ? null : h))}
              onMouseDown={() => s.setTab(tab)}
            >
              {name}
              {labels[k] !== name ? <span fg={DASH.bad}> ●</span> : ""}
            </text>
          )
        })}
      </box>
      <text wrapMode="none" height={1}>
        <span>{" ".repeat(Math.max(from, 0))}</span>
        <span fg={DASH.text}>{"▔".repeat(Math.max(Math.round(at + wide) - from, 1))}</span>
      </text>
    </box>
  )
}

/** The bell, with how many notifications are unread on its shoulder; it opens and closes the drawer. */
function Bell() {
  const s = useDash()
  const notes = useView<NotesView>(s.bridge, "notes")
  const [hover, setHover] = useState(false)
  const unread = notes?.unread ?? 0
  const art = useMemo(() => bell(s.init.quadrants, s.drawer || hover ? "#ffffff" : mix(DASH.text, DASH.muted, 0.35)), [s.init.quadrants, s.drawer, hover])
  const badge = unread > 9 ? "9+" : String(unread)
  return (
    <box
      flexDirection="row"
      height={3}
      flexShrink={0}
      paddingLeft={1}
      paddingRight={1}
      backgroundColor={s.drawer ? DASH.surface : hover ? mix(DASH.bg, "#ffffff", 0.04) : undefined}
      onMouseOver={() => setHover(true)}
      onMouseOut={() => setHover(false)}
      onMouseDown={(e) => {
        e.stopPropagation()
        s.toggleDrawer()
      }}
    >
      <Cells grid={art} />
      <box width={unread ? cellLen(badge) + 2 : 2} flexShrink={0} marginLeft={-1}>
        {unread ? (
          <text wrapMode="none">
            <span fg={DASH.bad}>▐</span>
            <span fg="#ffffff" bg={DASH.bad} attributes={TextAttributes.BOLD}>
              {badge}
            </span>
            <span fg={DASH.bad}>▌</span>
          </text>
        ) : null}
      </box>
    </box>
  )
}

// ---------------------------------------------------------------- the status bar

const KEYS: [string, string][] = [
  ["1-6", "tabs"],
  ["r", "refresh"],
  ["p", "profiles"],
  ["?", "help"],
]

/** The foot of the window: each platform (click one for Accounts), when the stats were read and any read under way
 * (the Python side's header line), and the keys at the right while there's room. */
function StatusBar() {
  const s = useDash()
  const header = useView<{ line: Segs; short?: Segs }>(s.bridge, "header")
  const [width, setWidth] = useState(0)
  const keys: Segs = KEYS.flatMap(([k, what], i) => [
    [i ? "   " : "", ""],
    [k, DASH.muted],
    [` ${what}`, DASH.faint],
  ])
  const full = header?.line ?? []
  const short = header?.short ?? full
  const room = width - 4 // its padding
  const line = segsLen(full) <= room ? full : short
  const showKeys = segsLen(line) + segsLen(keys) + 4 <= room
  return (
    <box
      flexDirection="row"
      height={1}
      flexShrink={0}
      paddingLeft={2}
      paddingRight={2}
      backgroundColor={mix(DASH.bg, DASH.surface, 0.7)}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      <Line segs={line} />
      <box flexGrow={1} />
      {showKeys ? <Line segs={keys} /> : null}
    </box>
  )
}
