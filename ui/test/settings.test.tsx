// The Settings tab (7), drawn without a terminal with its real Python side, on demo data and on a channel set up in a
// scratch folder: what it shows, and the danger zone's dialogs, which do nothing until the channel's name is typed
// (and nothing at all in the demo).

import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText, find } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import { typedMatches } from "../src/dashboard/Settings"
import { toasts } from "../src/ui/Panels"

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
  toasts.clear() // the pop-ups live in the module, so the next window would start with this one's
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

  test("the danger zone runs across the bottom, under everything else", async () => {
    const h = await window()
    const lines = frame(h).split("\n")
    const at = (text: string) => lines.findIndex((l) => l.includes(text))
    expect(at("DANGER ZONE")).toBeGreaterThan(at("ON THIS COMPUTER"))
    expect(at("ON THIS COMPUTER")).toBeGreaterThan(at("YOUR AI'S REASONING"))
    const top = lines[at("DANGER ZONE")]!
    expect(top.indexOf("DANGER ZONE")).toBeLessThan(10) // from the left edge: the whole width, not one half
    expect(lines.slice(at("DANGER ZONE")).join("\n")).toContain("Uninstall…")
  })

  test("the demo resets and uninstalls nothing: no dialog opens", async () => {
    const h = await window()
    await clickText(h, "Factory reset…")
    await h.settle(800)
    expect(frame(h)).not.toContain("Type ")
    toasts.clear() // its "nothing is reset" pop-up sits over Uninstall… in the corner for a few seconds
    await h.settle(300)
    await clickText(h, "Uninstall…")
    await h.settle(800)
    expect(frame(h)).not.toContain("UNINSTALL REELFORGE")
  })
})

describe("the danger zone on a channel that's set up", () => {
  let tmp = ""
  afterEach(async () => {
    await open?.close() // first: its Python side has the scratch folder's stats open
    open = null
    toasts.clear()
    if (tmp) rmSync(tmp, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 })
    tmp = ""
  })

  async function settings(): Promise<Headless> {
    tmp = mkdtempSync(join(tmpdir(), "reelforge-settings-"))
    open = await headless("dashboard", { tab: "settings" }, 150, 45, {
      REELFORGE_BRIDGE_PRELOAD: join(ROOT, "ui", "test", "settings_preload.py"),
      REELFORGE_TEST_ROOT: tmp,
    })
    await open.settle(3000)
    return open
  }

  const asked = () => (existsSync(join(tmp, ".reelforge-pending.json")) ? JSON.parse(readFileSync(join(tmp, ".reelforge-pending.json"), "utf-8")) : null)

  async function closed(h: Headless) {
    for (let i = 0; i < 25 && !h.exits.length; i++) await h.settle(200)
  }

  /** Click text in the dialog: the first time it's on screen below `under` (the tab behind has the same words). */
  async function clickBelow(h: Headless, under: string, text: string, dx = 2) {
    const top = find(h, under)
    const at = top && find(h, text, top[1])
    if (!at) throw new Error(`"${text}" isn't on screen under "${under}"`)
    await h.t.mockMouse.click(at[0] + dx, at[1])
    await h.settle(500)
  }

  test("factory reset does nothing until the channel's name is typed, then asks for it and closes ReelForge", async () => {
    const h = await settings()
    await clickText(h, "Factory reset…")
    await h.settle(800)
    expect(frame(h)).toContain("FACTORY RESET")
    expect(frame(h)).toContain("Type Night Physics to confirm")
    expect(frame(h)).toContain("Your videos stay where they are")
    await h.t.mockInput.typeText("Night")
    await h.settle(300)
    await clickText(h, "Reset ReelForge")
    h.t.mockInput.pressKey("RETURN")
    await h.settle(800)
    expect(asked()).toBeNull()
    expect(h.exits).toEqual([])
    await h.t.mockInput.typeText(" PHYSICS")
    await h.settle(300)
    await clickText(h, "Reset ReelForge")
    await closed(h)
    expect(asked()?.do).toBe("reset")
    expect(h.exits.map((e) => e.code)).toEqual([75]) // the launcher starts ReelForge again and does it first
    expect(existsSync(join(tmp, "my-studio", "answers.json"))).toBe(true) // nothing moved by the window itself
  })

  test("uninstall says where the videos go, can let them go too, and asks once the name is typed", async () => {
    const h = await settings()
    await clickText(h, "Uninstall…")
    await h.settle(800)
    const f = frame(h)
    expect(f).toContain("UNINSTALL REELFORGE")
    expect(f).toContain("Moved first to")
    expect(f).toContain("(STUDIO_DRY_SYSTEM)") // the computer's settings are left alone here
    await clickText(h, "Cancel")
    await h.settle(500)
    expect(frame(h)).not.toContain("UNINSTALL REELFORGE")
    expect(asked()).toBeNull()
    await clickText(h, "Uninstall…")
    await h.settle(800)
    await h.t.mockInput.typeText("night physics")
    await h.settle(300)
    await clickText(h, "▐█▌", 0) // Keep them: off
    await h.settle(300)
    expect(frame(h)).toContain("They go to the Recycle Bin with the rest")
    await clickBelow(h, "Type Night Physics", "Uninstall ReelForge")
    await closed(h)
    expect(asked()).toMatchObject({ do: "uninstall", keep: false })
    expect(h.exits.map((e) => e.code)).toEqual([75])
  })
})

describe("typing the name", () => {
  test("matches in any case, with spaces squeezed, and never when empty", () => {
    expect(typedMatches("night  physics ", "Night Physics")).toBe(true)
    expect(typedMatches("Night", "Night Physics")).toBe(false)
    expect(typedMatches("", "")).toBe(false)
  })
})
