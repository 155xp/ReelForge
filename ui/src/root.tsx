// The window round the profiles (one for each channel, studio/profiles.py): it shows one profile at a time, and moves
// between them, and to onboarding for a new profile (or this one's settings) and back, without leaving the terminal.
// Each profile gets a Python side of its own (REELFORGE_PROFILE): switching starts the new one, then lets the old one
// go, and a stats read the old one has under way finishes by itself, into its own profile.

import { useMemo, useState } from "react"
import { Bridge } from "./bridge"
import { DashboardApp } from "./dashboard/App"
import type { Nav } from "./dashboard/state"
import type { Init } from "./dashboard/types"
import { SetupApp, type SetupInit } from "./setup/App"
import { toasts } from "./ui/Panels"

/** The Python sides the window has started: the one it shows, and earlier ones still finishing a read. */
export class Sides {
  active: Bridge | null = null
  private finishing = new Set<Bridge>()
  /** The Python side the window shows stopped by itself. */
  onFailed: (bridge: Bridge) => void = () => {}

  /** env: what every Python side gets on top of this process's environment; log: where its stderr goes ("": kept
   * in memory, for the tests). */
  constructor(
    private env: Record<string, string> = {},
    private log?: string,
  ) {}

  /** Start a Python side for a screen ("dashboard" or "setup"), on a profile (undefined: the launcher's). */
  async open<T>(screen: string, opts: object, profile?: string): Promise<{ bridge: Bridge; init: T }> {
    const env = { ...this.env, ...(profile !== undefined ? { REELFORGE_PROFILE: profile } : {}) }
    const bridge = new Bridge({ env, log: this.log })
    try {
      const init = await bridge.start<T>(screen, opts)
      return { bridge, init }
    } catch (e) {
      bridge.kill()
      throw e
    }
  }

  /** Show this one from now on; the one before stops (finishing its read first, if it has one under way). */
  adopt(bridge: Bridge) {
    const old = this.active
    this.active = bridge
    bridge.on("closed", () => {
      if (bridge === this.active) this.onFailed(bridge)
    })
    if (old && old !== bridge) {
      this.finishing.add(old)
      void old
        .stop()
        .then(() => Promise.race([old.exited, Bun.sleep(600_000)]))
        .finally(() => {
          old.kill()
          this.finishing.delete(old)
        })
    }
  }

  /** How many earlier Python sides are still finishing. */
  get busy(): number {
    return [...this.finishing].filter((b) => !b.closed).length
  }

  /** Stop them all: busy while one is still finishing a stats read (or an update), which the window waits for. */
  async stop(): Promise<{ busy: boolean; done: Promise<unknown> }> {
    const busy = this.active ? await this.active.stop() : false
    const still = [...this.finishing].filter((b) => !b.closed)
    const done = Promise.all([this.active?.exited, ...still.map((b) => b.exited)])
    return { busy: busy || still.length > 0, done }
  }
}

export type View =
  | { kind: "dashboard"; bridge: Bridge; init: Init; n: number }
  | {
      kind: "setup"
      bridge: Bridge
      init: SetupInit
      options: Record<string, unknown>
      back: { key: string; tab: string }
      n: number
    }

/** The window: the profile it shows, or onboarding inside it. */
export function Root({ sides, first, quit }: { sides: Sides; first: View; quit: (code?: number, result?: object) => void }) {
  const [view, setView] = useState<View>(first)
  const nav: Nav = useMemo(
    () => ({
      profile: async (key: string, tab?: string) => {
        try {
          const next = await sides.open<Init>("dashboard", { tab, switched: true }, key)
          sides.adopt(next.bridge)
          setView((v) => ({ kind: "dashboard", bridge: next.bridge, init: next.init, n: v.n + 1 }))
        } catch (e) {
          toasts.add({ title: "Couldn't open that profile", body: String((e as Error)?.message ?? e), severity: "error", timeout: 10 })
        }
      },
      onboard: async (mode: "new" | "settings", tab = "overview") => {
        if (view.kind !== "dashboard") return
        const here = view.init.profile.key
        const opts = { start: "onboard", new: mode === "new", embedded: true }
        try {
          const next = await sides.open<SetupInit>("setup", opts, here)
          sides.adopt(next.bridge)
          setView((v) => ({ kind: "setup", bridge: next.bridge, init: next.init, options: opts, back: { key: here, tab }, n: v.n + 1 }))
        } catch (e) {
          toasts.add({ title: "Couldn't start onboarding", body: String((e as Error)?.message ?? e), severity: "error", timeout: 10 })
        }
      },
    }),
    [sides, view],
  )
  if (view.kind === "setup") {
    // Inside the window, its last screen (or leaving it) goes back to the window: on the profile it made or changed,
    // or the one it came from.
    const back = (_code?: number, result?: object) => {
      const r = (result ?? {}) as { open?: string; tab?: string; profile?: string }
      if (r.open === "dashboard") return void nav.profile(r.profile ?? view.back.key, r.tab ?? view.back.tab)
      void nav.profile(view.back.key, view.back.tab)
    }
    return <SetupApp key={view.n} bridge={view.bridge} init={view.init} quit={back} options={view.options} />
  }
  return <DashboardApp key={view.n} bridge={view.bridge} init={view.init} quit={quit} nav={nav} />
}
