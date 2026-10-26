// ReelForge's window, run by Bun (studio/ui.py starts it):
//
//   bun src/main.tsx dashboard '{"tab": "publish", "demo": false}'     the ReelForge window
//   bun src/main.tsx setup '{"start": "tools"}'                        the first-run screens
//
// It starts the Python side (studio/bridge.py) for everything it shows, and exits with the window's exit code (75:
// ReelForge updated itself, so the launcher starts it again). What the last first-run screen asks for (open ReelForge
// on a tab) is written to REELFORGE_RESULT for the launcher.
//
// The window shows one profile (one for each channel, studio/profiles.py) at a time. Switching starts a new Python
// side on the profile picked (REELFORGE_PROFILE) and lets the old one go: a stats read it has under way finishes by
// itself, into its own profile, and the window waits for it only when it closes. New profile and a profile's
// settings show onboarding inside the window the same way, then the window again.

import { createCliRenderer, type CliRenderer } from "@opentui/core"
import { createRoot } from "@opentui/react"
import { writeFileSync } from "node:fs"
import { Sides, Root, type View } from "./root"
import type { Init } from "./dashboard/types"
import { SetupApp, type SetupInit } from "./setup/App"
import type { Bridge } from "./bridge"

const [screen = "dashboard", raw = "{}"] = process.argv.slice(2)
let options: Record<string, unknown> = {}
try {
  options = JSON.parse(raw)
} catch {
  options = {}
}

export interface Exit {
  (code?: number, result?: object): void
}

async function main(): Promise<void> {
  const sides = new Sides()
  let renderer: CliRenderer | null = null
  let leaving = false

  const quit: Exit = async (code = 0, result) => {
    if (leaving) return
    leaving = true
    if (result && process.env.REELFORGE_RESULT) {
      try {
        writeFileSync(process.env.REELFORGE_RESULT, JSON.stringify(result))
      } catch {
        // the launcher simply won't open anything next
      }
    }
    const { busy, done } = await sides.stop()
    renderer?.destroy()
    if (busy) {
      process.stdout.write("Finishing the stats read that was running (it closes its browser first)…\n")
      await done
    } else await Promise.race([done, Bun.sleep(3000)])
    process.exit(code) // 75: updated (the launcher says so, and starts ReelForge again)
  }

  let first: View
  try {
    const opened = await sides.open<Init | SetupInit>(screen, options)
    sides.adopt(opened.bridge)
    first =
      screen === "setup"
        ? { kind: "setup", bridge: opened.bridge, init: opened.init as SetupInit, options, back: { key: ".", tab: "overview" }, n: 0 }
        : { kind: "dashboard", bridge: opened.bridge, init: opened.init as Init, n: 0 }
  } catch (e) {
    fail(sides.active, e)
    return
  }
  renderer = await createCliRenderer({ exitOnCtrlC: false, autoFocus: false, targetFps: 30 })
  sides.onFailed = (bridge) => {
    if (leaving) return
    renderer?.destroy()
    fail(bridge, new Error(bridge.failure ?? "ReelForge's Python side stopped."))
  }
  const root = createRoot(renderer)
  if (first.kind === "setup") {
    // The first-run screens on their own (setup, reelforge onboard): their last screen closes the window, and the
    // launcher opens ReelForge if it asked for that.
    root.render(<SetupApp bridge={first.bridge} init={first.init} quit={quit} options={options} />)
  } else root.render(<Root sides={sides} first={first} quit={quit} />)
}

/** The Python side couldn't start, or stopped: say why on the plain terminal and exit 1. */
function fail(bridge: Bridge | null, e: unknown): never {
  const log = process.env.REELFORGE_LOG
  const lines = [
    `ReelForge's window couldn't run: ${e instanceof Error ? e.message : String(e)}`,
    bridge?.errors ?? "",
    log ? `The details are in ${log}` : "",
    "If this keeps happening, run: reelforge doctor",
  ].filter(Boolean)
  process.stderr.write(lines.join("\n") + "\n")
  bridge?.kill()
  process.exit(1)
}

await main()
