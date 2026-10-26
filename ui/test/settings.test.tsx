// The Settings tab (7), drawn without a terminal on demo data with its real Python side: what it shows, and the
// danger zone's dialogs, which do nothing until the channel's name is typed (and nothing at all in the demo).

import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import { typedMatches } from "../src/dashboard/Settings"

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }
setDefaultTimeout(30_000)
let open: Headless | null = null

async function window(size: [number, number] = [150, 45]): Promise<Headless> {
  open = await headless("dashboard", { demo: true, only_demos: true, tab: "settings" }, size[0], size[1], PRELOAD)
  await open.settle(3000)
  return open
}

afterEach(async () => {
  await open?.close()
  open = null
})

const frame = (h: Headless) => h.t.captureCharFrame()

describe("the Settings tab", () => {
  test("shows the channel, your AI's reasoning, this computer and the danger zone", async () => {
    const h = await window()
    const f = frame(h)
    if (process.env.SHOW) console.log(f)
    for (const text of ["THIS CHANNEL", "YOUR AI'S REASONING", "ON THIS COMPUTER", "DANGER ZONE", "Factory reset…", "Uninstall…", "Change your answers"])
      expect(f).toContain(text)
  })

  test("7 opens it", async () => {
    open = await headless("dashboard", { demo: true, only_demos: true, tab: "overview" }, 150, 45, PRELOAD)
    await open.settle(2500)
    open.t.mockInput.pressKey("7")
    await open.settle(1500)
    expect(frame(open)).toContain("DANGER ZONE")
  })

  test("the demo resets and uninstalls nothing: no dialog opens", async () => {
    const h = await window()
    await clickText(h, "Factory reset…")
    await h.settle(800)
    expect(frame(h)).not.toContain("Type ")
    await clickText(h, "Uninstall…")
    await h.settle(800)
    expect(frame(h)).not.toContain("UNINSTALL REELFORGE")
  })
})

describe("typing the name", () => {
  test("matches in any case, with spaces squeezed, and never when empty", () => {
    expect(typedMatches("night  physics ", "Night Physics")).toBe(true)
    expect(typedMatches("Night", "Night Physics")).toBe(false)
    expect(typedMatches("", "")).toBe(false)
  })
})
