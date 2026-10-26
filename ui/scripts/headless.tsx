// The window drawn without a terminal, on OpenTUI's test renderer, with the real Python side: what the screenshots
// (scripts/shots.tsx) and the window's tests (test/) use.

import "./quiet"
import { createTestRenderer, type TestRendererSetup } from "@opentui/core/testing"
import { createRoot } from "@opentui/react"
import type { Bridge } from "../src/bridge"
import type { Init } from "../src/dashboard/types"
import { Root, Sides } from "../src/root"
import { SetupApp, type SetupInit } from "../src/setup/App"

export interface Headless {
  t: TestRendererSetup
  /** The Python side the window started with (after switching profiles: sides.active). */
  bridge: Bridge
  sides: Sides
  /** Let the window take in what the Python side sent: a few frames, a pause, a few more. */
  settle: (ms?: number) => Promise<void>
  exits: { code: number; result?: object }[]
  close: () => Promise<void>
}

export async function headless(
  screen: "dashboard" | "setup",
  options: Record<string, unknown>,
  width: number,
  height: number,
  env: Record<string, string> = {},
): Promise<Headless> {
  const sides = new Sides({ STUDIO_DRY_SYSTEM: "1", ...env }, "")
  const opened = await sides.open<Init | SetupInit>(screen, options)
  const bridge = opened.bridge
  sides.adopt(bridge)
  const t = await createTestRenderer({ width, height })
  const exits: { code: number; result?: object }[] = []
  const quit = (code = 0, result?: object) => void exits.push({ code, result })
  const root = createRoot(t.renderer)
  if (screen === "setup") root.render(<SetupApp bridge={bridge} init={opened.init as SetupInit} quit={quit} options={options} />)
  else root.render(<Root sides={sides} first={{ kind: "dashboard", bridge, init: opened.init as Init, n: 0 }} quit={quit} />)
  const settle = async (ms = 400) => {
    for (let i = 0; i < 3; i++) await t.renderOnce()
    await Bun.sleep(ms)
    for (let i = 0; i < 3; i++) await t.renderOnce()
  }
  return {
    t,
    bridge,
    sides,
    settle,
    exits,
    close: async () => {
      const { done } = await sides.stop()
      await Promise.race([done, Bun.sleep(5000)])
      sides.active?.kill()
      bridge.kill()
      root.unmount()
      t.renderer.destroy()
    },
  }
}

if (import.meta.main) {
  // bun scripts/headless.tsx dashboard '{"demo": true, "tab": "videos"}' 180 50
  const [screen = "dashboard", raw = "{}", w = "180", h = "50"] = process.argv.slice(2)
  const h1 = await headless(screen as "dashboard", JSON.parse(raw), Number(w), Number(h))
  await h1.settle(2500)
  console.log(h1.t.captureCharFrame())
  await h1.close()
  process.exit(0)
}
