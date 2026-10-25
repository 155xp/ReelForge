// ReelForge's window, run by Bun (studio/ui.py starts it):
//
//   bun src/main.tsx dashboard '{"tab": "publish", "demo": false}'     the ReelForge window
//   bun src/main.tsx setup '{"start": "tools"}'                        the first-run screens
//
// It starts the Python side (studio/bridge.py) for everything it shows, and exits with the window's exit code (75:
// ReelForge updated itself, so the launcher starts it again). What the last first-run screen asks for (open ReelForge
// on a tab) is written to REELFORGE_RESULT for the launcher.

import { createCliRenderer, type CliRenderer } from "@opentui/core"
import { createRoot } from "@opentui/react"
import { writeFileSync } from "node:fs"
import { Bridge } from "./bridge"
import { DashboardApp } from "./dashboard/App"
import type { Init } from "./dashboard/types"
import { SetupApp, type SetupInit } from "./setup/App"

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
  const bridge = new Bridge()
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
    const busy = await bridge.stop()
    renderer?.destroy()
    if (busy) {
      process.stdout.write("Finishing the stats read that was running (it closes its browser first)…\n")
      await bridge.exited
    } else await Promise.race([bridge.exited, Bun.sleep(3000)])
    process.exit(code) // 75: updated (the launcher says so, and starts ReelForge again)
  }

  let init: unknown
  try {
    init = await bridge.start(screen, options)
  } catch (e) {
    fail(bridge, e)
    return
  }
  renderer = await createCliRenderer({ exitOnCtrlC: false, autoFocus: false, targetFps: 30 })
  bridge.on("closed", () => {
    if (leaving) return
    renderer?.destroy()
    fail(bridge, new Error(bridge.failure ?? "ReelForge's Python side stopped."))
  })
  const root = createRoot(renderer)
  if (screen === "setup") root.render(<SetupApp bridge={bridge} init={init as SetupInit} quit={quit} options={options} />)
  else root.render(<DashboardApp bridge={bridge} init={init as Init} quit={quit} />)
}

/** The Python side couldn't start, or stopped: say why on the plain terminal and exit 1. */
function fail(bridge: Bridge, e: unknown): never {
  const log = process.env.REELFORGE_LOG
  const lines = [
    `ReelForge's window couldn't run: ${e instanceof Error ? e.message : String(e)}`,
    bridge.errors,
    log ? `The details are in ${log}` : "",
    "If this keeps happening, run: reelforge doctor",
  ].filter(Boolean)
  process.stderr.write(lines.join("\n") + "\n")
  bridge.kill()
  process.exit(1)
}

await main()
