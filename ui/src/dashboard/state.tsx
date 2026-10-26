// What every part of the window shares: the link to the Python side, the start-up facts, which tab and dialog are
// showing, the rows highlighted in each table, and what clicking a chip does.

import { createContext, useContext, useSyncExternalStore } from "react"
import type { Bridge } from "../bridge"
import type { Action } from "../lib/styled"
import type { Init } from "./types"

export const TABS = ["overview", "videos", "compare", "publish", "accounts", "updates"] as const
export type Tab = (typeof TABS)[number]
export const TAB_NAMES: Record<Tab, string> = {
  overview: "Overview",
  videos: "Videos",
  compare: "Compare",
  publish: "Publish",
  accounts: "Accounts",
  updates: "Updates",
}

export type Dialog =
  | { kind: "help" }
  | { kind: "log"; data: LogData }
  | { kind: "remove"; data: { path: string; note: import("../lib/styled").Segs; bin: string } }
  | { kind: "episode"; data: EpisodeData }
  | { kind: "signup"; data: SignupData }
  | { kind: "disconnect"; data: { key: string; title: string; note: import("../lib/styled").Segs } }

/** A sign-up guide (dashboard/service.py signup_guide): its steps, the button that opens the platform's own sign-up
 * page, and for an account (not the Gmail) a box for the @handle you end up with. */
export interface SignupData {
  key: string
  title: string
  why: string
  steps: string[]
  button: string
  account: boolean
}

export interface LogData {
  platforms: { key: string; name: string }[]
  start: string
  episodes: { id: number; title: string }[]
  last: Record<string, { followers: number | null; views: Record<string, number> }>
}

export interface EpisodeData {
  key: string
  note: import("../lib/styled").Segs
  options: import("../ui/Lists").Option[]
  current: string | null
}

/** The window's own state (what the Python side doesn't need to know), with a way to watch it. */
export class DashState {
  tab: Tab
  drawer: boolean
  dialog: Dialog | null = null
  picked: string | null = null // a card or account panel framed for a few seconds (a clicked notification)
  top: string | null = null // the highlighted row in Top performers
  video: string | null = null // ... on the Videos tab
  compareRow: string | null = null // ... in the Compare table
  note: string | null = null // the highlighted notification
  caption = ""
  tags = ""
  handles: Record<string, string> = {} // what's typed into each unconnected platform's @handle box
  handleErrors: Record<string, string> = {} // ... and what's wrong with it
  private listeners = new Set<() => void>()
  private version = 0
  private pickTimer: ReturnType<typeof setTimeout> | null = null

  constructor(
    readonly bridge: Bridge,
    readonly init: Init,
    readonly quit: (code?: number) => void,
  ) {
    this.tab = (TABS as readonly string[]).includes(init.tab) ? (init.tab as Tab) : "overview"
    this.drawer = init.drawer
    this.tags = init.default_tags
  }

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }
  snapshot = () => this.version

  set(patch: Partial<DashState>) {
    Object.assign(this, patch)
    this.version++
    for (const l of this.listeners) l()
  }

  setTab(tab: string) {
    if (!(TABS as readonly string[]).includes(tab)) return
    this.set({ tab: tab as Tab })
    this.bridge.send("tab_opened", tab)
  }

  toggleDrawer(open = !this.drawer) {
    this.set({ drawer: open })
    if (open) this.bridge.send("drawer_opened")
  }

  /** Connect a platform with the @handle typed for it: what's wrong with it shows under its box. */
  async connect(key: string, typed: string) {
    const error = await this.bridge.call<string | null>("connect", key, typed)
    this.set({ handles: { ...this.handles, [key]: typed }, handleErrors: { ...this.handleErrors, [key]: error ?? "" } })
  }

  /** Frame a card or account panel in yellow for a few seconds (one at a time). */
  pick(id: string) {
    if (this.pickTimer) clearTimeout(this.pickTimer)
    this.set({ picked: id })
    this.pickTimer = setTimeout(() => this.set({ picked: null }), 4000)
  }

  /** The highlighted video on the tab you're looking at ("<platform>|<post id>"). */
  highlighted(): string | null {
    return this.tab === "overview" ? this.top : this.tab === "videos" ? this.video : this.tab === "compare" ? this.compareRow : null
  }

  async openDialog(kind: "log" | "remove" | "episode" | "signup" | "disconnect", call: Promise<any>) {
    const data = await call
    if (data) this.set({ dialog: { kind, data } as Dialog })
  }

  /** What a chip or a chart key does when clicked. */
  run = (action: Action) => {
    const [name, ...args] = action
    const b = this.bridge
    switch (name) {
      case "tab":
        return this.setTab(String(args[0]))
      case "open_post":
        return b.send("open_post", this.highlighted())
      case "fix_episode":
        return void this.openDialog("episode", b.call("fix_episode", this.highlighted()))
      case "remove_picked":
        return void this.openDialog("remove", b.call("remove_menu", null))
      case "gmail":
        return void this.openDialog("signup", b.call("signup_guide", "gmail"))
      case "disconnect":
        return void this.openDialog("disconnect", b.call("disconnect_info", args[0]))
      case "close_drawer":
        return this.toggleDrawer(false)
      case "refresh":
        return b.send("refresh", false)
      case "help":
        return this.set({ dialog: { kind: "help" } })
      case "quit":
        return this.quit(0)
      default:
        return b.send(name, ...args)
    }
  }
}

export const DashContext = createContext<DashState>(null as unknown as DashState)

/** The window's state, re-rendering whenever it changes. */
export function useDash(): DashState {
  const s = useContext(DashContext)
  useSyncExternalStore(s.subscribe, s.snapshot)
  return s
}
