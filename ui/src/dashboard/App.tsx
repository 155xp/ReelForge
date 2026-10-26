// ReelForge's window: the header (logo, the profile button, platforms, Refresh / Help / Quit), the bell in the corner,
// six tabs, the notifications drawer on the right, dialogs, and pop-ups. Keys: 1-6 switch tabs, r / R refresh, p the
// profiles, Esc closes the drawer or leaves a text field, Tab moves between buttons and fields, Ctrl+Q quits.

import { TextAttributes, type KeyEvent } from "@opentui/core"
import { useKeyboard, useRenderer } from "@opentui/react"
import { useEffect, useMemo, useState } from "react"
import { useView, type Bridge } from "../bridge"
import { FocusContext, FocusManager, ThemeContext } from "../lib/focus"
import { segsLen } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Cells } from "../ui/Cells"
import { bell, logoCells } from "../ui/Graphics"
import { ActionContext, Line } from "../ui/Line"
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
  })
  return (
    <box flexDirection="column" width="100%" height="100%" backgroundColor={DASH.bg}>
      <Top />
      <TabBar />
      <box flexDirection="row" flexGrow={1}>
        <box flexDirection="column" flexGrow={1} paddingLeft={1} paddingRight={1}>
          {s.tab === "overview" && <Overview />}
          {s.tab === "videos" && <Videos />}
          {s.tab === "compare" && <Compare />}
          {s.tab === "publish" && <Publish />}
          {s.tab === "accounts" && <Accounts />}
          {s.tab === "updates" && <Updates />}
        </box>
        {s.drawer && <Drawer />}
      </box>
      <Dialogs />
      <ToastStack />
    </box>
  )
}

/** The header's grey bar (the anvil, the profile button, each platform, when the stats were read, Refresh / Help /
 * Quit), then the bell. */
function Top() {
  const s = useDash()
  const header = useView<{ line: import("../lib/styled").Segs; short?: import("../lib/styled").Segs }>(s.bridge, "header")
  const [room, setRoom] = useState(0)
  // TT YT IG X beside the profile button when the names don't fit
  const line = header && room && header.short && segsLen(header.line) > room ? header.short : header?.line
  const notes = useView<NotesView>(s.bridge, "notes")
  const [hover, setHover] = useState(false)
  const anvil = useMemo(() => logoCells(s.init.anvil), [s.init.anvil])
  const actions: import("../lib/styled").Segs = [
    [" Refresh ", "#c9d1d9 on #1c222b", ["refresh"]],
    [" ", ""],
    [" Help ", "#c9d1d9 on #1c222b", ["help"]],
    [" ", ""],
    [" Quit ", "#c9d1d9 on #1c222b", ["quit"]],
  ]
  return (
    <box flexDirection="row" height={3} flexShrink={0}>
      <box flexDirection="row" flexGrow={1} flexShrink={1} height={3} backgroundColor={DASH.panel}>
        <Cells grid={anvil} marginLeft={1} marginRight={1} />
        <ProfileButton />
        {/* the platforms and status give way in a narrow window, so the bell keeps its corner */}
        <box
          flexGrow={1}
          flexShrink={1}
          flexBasis={0}
          paddingLeft={3}
          justifyContent="center"
          overflow="hidden"
          onSizeChange={function (this: import("@opentui/core").Renderable) {
            setRoom(Math.max(this.width - 3, 0))
          }}
        >
          <Line segs={line} />
        </box>
        <box paddingLeft={1} paddingRight={1} justifyContent="center" flexShrink={0}>
          <Line segs={actions} />
        </box>
      </box>
      <box
        marginLeft={4}
        marginRight={1}
        backgroundColor={hover ? mix(DASH.panel, "#ffffff", 0.06) : undefined}
        onMouseOver={() => setHover(true)}
        onMouseOut={() => setHover(false)}
        onMouseDown={(e) => {
          e.stopPropagation()
          s.toggleDrawer()
        }}
      >
        <Cells grid={bell(Boolean(notes?.unread), s.init.quadrants, DASH.bad)} />
      </box>
    </box>
  )
}

/** The tabs: the open one lit, with a line under them; a red dot on Updates when a new version is out. */
function TabBar() {
  const s = useDash()
  const update = useView<UpdateView>(s.bridge, "update")
  let x = 0
  const spans: { tab: string; start: number; width: number }[] = []
  for (const tab of TABS) {
    const label = ` ${TAB_NAMES[tab]}${tab === "updates" && update?.newer ? " ●" : ""} `
    spans.push({ tab, start: x, width: label.length })
    x += label.length + 1
  }
  const active = spans.find((t) => t.tab === s.tab)!
  return (
    <box flexDirection="column" height={2} flexShrink={0}>
      <box flexDirection="row" height={1}>
        {TABS.map((tab) => {
          const on = tab === s.tab
          return (
            <text
              key={tab}
              marginRight={1}
              fg={on ? DASH.primaryText : DASH.muted}
              bg={on ? DASH.primary : undefined}
              attributes={on ? TextAttributes.BOLD : undefined}
              onMouseDown={() => s.setTab(tab)}
            >
              {` ${TAB_NAMES[tab]}`}
              {tab === "updates" && update?.newer ? <span fg={on ? DASH.primaryText : DASH.bad}> ●</span> : ""}
              {" "}
            </text>
          )
        })}
      </box>
      <text fg={DASH.border} wrapMode="none" flexShrink={0}>
        <span fg={DASH.border}>{"━".repeat(active.start)}</span>
        <span fg={DASH.primary}>{"━".repeat(active.width)}</span>
        <span fg={DASH.border}>{"━".repeat(400)}</span>
      </text>
    </box>
  )
}
