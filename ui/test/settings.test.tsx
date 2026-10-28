// The Settings tab, drawn without a terminal with its real Python side, on demo data and on a channel set up in a
// scratch folder: what it shows, the tab order (moved with a click and the arrows, a drag or the keyboard, and kept for
// the next window), and the danger zone's dialogs, which do nothing until the channel's name is typed (and nothing at
// all in the demo).

import { TextAttributes } from "@opentui/core"
import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText, find } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import { typedMatches } from "../src/dashboard/Settings"
import { TAB_NAMES } from "../src/dashboard/state"
import { toasts } from "../src/ui/Panels"

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }
const BIN = process.platform === "win32" ? "Recycle Bin" : "Trash" // what dashboard/desktop.py calls it here
setDefaultTimeout(30_000)
let open: Headless | null = null

async function window(size: [number, number] = [150, 72]): Promise<Headless> {
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
const NAMES = Object.values(TAB_NAMES) as string[]
const DEFAULT = ["Overview", "Videos", "Compare", "Stats", "Accounts", "Settings", "Updates"]

/** The tabs along the top, left to right (Publish is the button at the right, not one of them). */
function header(h: Headless): string[] {
  const row = frame(h).split("\n")[1]!
  const tabs = row.slice(0, row.indexOf("│")) // up to the Publish button's box
  return NAMES.filter((n) => tabs.includes(` ${n}`)).sort((a, b) => tabs.indexOf(` ${a}`) - tabs.indexOf(` ${b}`))
}

/** The Settings tab's Tab order, left to right, checking each tab's number on the way. */
function strip(h: Headless): string[] {
  const row = frame(h).split("\n").find((r) => /\b1 [A-Z]\w+ {2,}2 [A-Z]/.test(r)) ?? ""
  const items = [...row.matchAll(/\b(\d) ([A-Z]\w+)/g)]
  items.forEach((m, i) => expect(m[1]).toBe(String(i + 1)))
  return items.map((m) => m[2]!)
}

/** The open tab: its name bold in the header, where the others are plain. */
function activeTab(h: Headless): string {
  const lit = h.t.captureSpans().lines[1]!.spans.find((s) => s.attributes & TextAttributes.BOLD && NAMES.includes(s.text.trim()))
  return lit?.text.trim() ?? ""
}

describe("the Settings tab", () => {
  test("shows the channel, the FAQ, this computer and the danger zone, and no setting for your AI's reasoning", async () => {
    const h = await window()
    const f = frame(h)
    if (process.env.SHOW) console.log(f)
    for (const text of ["THIS CHANNEL", "FAQ", "▸ Which model does my AI use, and how hard does it think?", "▸ Something isn't working.", "ON THIS COMPUTER", "DANGER ZONE", "Factory reset…", "Uninstall…", "Change your answers"])
      expect(f).toContain(text)
    for (const gone of ["REASONING", "Max", "High", "Fast", "the standard"]) expect(f).not.toContain(gone)
  })

  test("Settings and Updates are the last two tabs, so 6 opens it and 7 Updates", async () => {
    open = await headless("dashboard", { demo: true, only_demos: true, tab: "overview" }, 150, 72, PRELOAD)
    await open.settle(2500)
    expect(header(open)).toEqual(DEFAULT)
    open.t.mockInput.pressKey("6")
    await open.settle(1500)
    expect(frame(open)).toContain("DANGER ZONE")
    expect(activeTab(open)).toBe("Settings")
    expect(strip(open)).toEqual(DEFAULT)
    expect(frame(open)).toContain("Publish has its own green button at the top right, and u opens it.")
    open.t.mockInput.pressKey("7")
    await open.settle(800)
    expect(activeTab(open)).toBe("Updates")
  })

  test("the danger zone runs across the bottom, under everything else", async () => {
    const h = await window()
    const lines = frame(h).split("\n")
    const at = (text: string) => lines.findIndex((l) => l.includes(text))
    expect(at("DANGER ZONE")).toBeGreaterThan(at("ON THIS COMPUTER"))
    expect(at("ON THIS COMPUTER")).toBeGreaterThan(at("Does ReelForge cost anything?"))
    const top = lines[at("DANGER ZONE")]!
    expect(top.indexOf("DANGER ZONE")).toBeLessThan(10) // from the left edge: the whole width, not one half
    expect(lines.slice(at("DANGER ZONE")).join("\n")).toContain("Uninstall…")
  })

  test("a question opens its answer under it, one at a time, and closes again", async () => {
    const h = await window()
    await clickText(h, "How do I make a video?", 3)
    let f = frame(h)
    expect(f).toContain("▾ How do I make a video?")
    expect(f).toContain("Then say make my first video")
    const lines = f.split("\n")
    const at = (text: string) => lines.findIndex((l) => l.includes(text))
    expect(at("Then say make my first video")).toBeGreaterThan(at("How do I make a video?"))
    expect(at("Then say make my first video")).toBeLessThan(at("My AI doesn't know about my channel."))
    await clickText(h, "Does ReelForge post for me?", 3)
    f = frame(h)
    expect(f).not.toContain("Then say make my first video")
    expect(f).toContain("▾ Does ReelForge post for me?")
    expect(f).toContain("ReelForge never posts, uploads or sends anything")
    await clickText(h, "Does ReelForge post for me?", 3)
    expect(frame(h)).not.toContain("never posts, uploads")
    expect(frame(h)).toContain("▸ Does ReelForge post for me?")
  })

  test("the first answer is the honest one: your AI app picks the model and how hard it thinks", async () => {
    const h = await window()
    await clickText(h, "Which model does my AI use", 3)
    const f = frame(h)
    for (const text of ["Your AI app decides that, not ReelForge.", "Opus at high effort", "can't control it everywhere:", "• The Claude desktop app uses the model and effort", "/model or /effort"])
      expect(f).toContain(text)
  })

  test("with the keyboard: the arrows move through the questions and Enter or Space opens one", async () => {
    const h = await window()
    await clickText(h, "Where are my videos?", 3) // it takes the keyboard, and opens
    expect(frame(h)).toContain("and as files:")
    h.t.mockInput.pressArrow("down")
    await h.settle(300)
    h.t.mockInput.pressKey("RETURN")
    await h.settle(300)
    expect(frame(h)).toContain("▾ Do my stats update while ReelForge is closed?")
    expect(frame(h)).toContain("once an hour")
    expect(frame(h)).not.toContain("and as files:")
    h.t.mockInput.pressKey(" ")
    await h.settle(300)
    expect(frame(h)).not.toContain("once an hour")
  })

  test("in a narrow window the FAQ goes under the channel's answers, and every question still fits", async () => {
    const h = await window([90, 60])
    const lines = frame(h).split("\n")
    const at = (text: string) => lines.findIndex((l) => l.includes(text))
    expect(at("FAQ  click a question")).toBeGreaterThan(at("Change your answers"))
    expect(lines[at("FAQ  click a question")]!.indexOf("FAQ")).toBeLessThan(10)
    expect(frame(h)).toContain("▸ Which model does my AI use, and how hard does it think?")
    for (const [w, hh] of [[64, 24], [40, 20], [200, 52]] as const) {
      h.t.resize(w, hh) // drawn whole at every size: a column too narrow to wrap would blank the window
      await h.settle(300)
      expect(frame(h)).toContain("THIS CHANNEL")
    }
    expect(frame(h)).toContain("FAQ  click a question for its answer")
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

describe("the tab order", () => {
  test("a click picks a tab and the arrows move it: the header, the numbers and the help follow", async () => {
    const h = await window()
    expect(frame(h)).toContain("TAB ORDER")
    await clickText(h, "5 Accounts", 3)
    for (let i = 0; i < 4; i++) await clickText(h, "← Move left", 3)
    const moved = ["Accounts", "Overview", "Videos", "Compare", "Stats", "Settings", "Updates"]
    expect(strip(h)).toEqual(moved)
    expect(header(h)).toEqual(moved)
    expect(frame(h)).toContain("Demo mode: this order isn't kept.")
    await clickText(h, "← Move left", 3) // at the far left already: nothing moves
    expect(strip(h)).toEqual(moved)
    await clickText(h, "Move right →", 3)
    expect(strip(h).slice(0, 3)).toEqual(["Overview", "Accounts", "Videos"])
    h.t.mockInput.pressKey("2")
    await h.settle(800)
    expect(activeTab(h)).toBe("Accounts")
    await h.t.mockInput.typeText("?")
    await h.settle(500)
    const help = frame(h)
    expect(help).toContain("Accounts (2)")
    expect(help).toContain("Videos (3)")
    expect(help.indexOf("Overview (1)")).toBeLessThan(help.indexOf("Accounts (2)"))
    expect(help.indexOf("Accounts (2)")).toBeLessThan(help.indexOf("Videos (3)"))
    expect(help).not.toContain("Publish (")
    const [x, y] = find(h, "Overview (1)")! // down the help to Publish, after the tabs, with its key
    for (let i = 0; i < 30 && !frame(h).includes("The green button at the top right opens it."); i++) {
      await h.t.mockMouse.scroll(x + 2, y + 2, "down")
      await h.settle(100)
    }
    const end = frame(h)
    expect(end).toContain("Publish (u)")
    expect(end).toContain("The green button at the top right opens it.")
    if (end.includes("Updates (7)")) expect(end.indexOf("Updates (7)")).toBeLessThan(end.indexOf("Publish (u)"))
  })

  test("a tab dragged to the far left goes there, and Reset to default puts them all back", async () => {
    const h = await window()
    const from = find(h, "7 Updates")!
    const to = find(h, "1 Overview")!
    await h.t.mockMouse.drag(from[0] + 3, from[1], to[0], to[1])
    await h.settle(500)
    const dragged = ["Updates", ...DEFAULT.slice(0, 6)]
    expect(strip(h)).toEqual(dragged)
    expect(header(h)).toEqual(dragged)
    await clickText(h, "Reset to default", 3)
    expect(strip(h)).toEqual(DEFAULT)
    expect(header(h)).toEqual(DEFAULT)
    // dragged off the row (up into the panel's title, here): where along the row still decides
    const stats = find(h, "4 Stats")!
    const videos = find(h, "2 Videos")!
    await h.t.mockMouse.drag(stats[0] + 3, stats[1], videos[0], videos[1] - 2)
    await h.settle(500)
    expect(strip(h)).toEqual(["Overview", "Stats", "Videos", "Compare", "Accounts", "Settings", "Updates"])
  })

  test("with the keyboard: ← → pick a tab and Shift+← → move it", async () => {
    const h = await window()
    await clickText(h, "3 Compare", 3)
    h.t.mockInput.pressArrow("right") // Stats
    await h.settle(200)
    for (let i = 0; i < 4; i++) {
      h.t.mockInput.pressArrow("right", { shift: true }) // the last one, at the far right already, does nothing
      await h.settle(200)
    }
    expect(strip(h)).toEqual(["Overview", "Videos", "Compare", "Accounts", "Settings", "Updates", "Stats"])
    h.t.mockInput.pressArrow("left") // Updates
    h.t.mockInput.pressArrow("left", { shift: true }) // straight after, before the row is drawn again
    await h.settle(300)
    expect(strip(h).slice(4)).toEqual(["Updates", "Settings", "Stats"])
    h.t.mockInput.pressKey("5") // the number keys still open tabs while the row has the keyboard
    await h.settle(800)
    expect(activeTab(h)).toBe("Updates")
  })

  test("in a narrow window the row wraps, and every tab still has its number", async () => {
    const h = await window([70, 60])
    expect(frame(h)).toContain("TAB ORDER")
    const f = frame(h)
    DEFAULT.forEach((name, i) => expect(f).toContain(`${i + 1} ${name}`))
    expect(f).toContain("Reset to default")
  })
})

describe("the tab order on a channel that's set up", () => {
  let tmp = ""
  afterEach(async () => {
    await open?.close()
    open = null
    toasts.clear()
    if (tmp) rmSync(tmp, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 })
    tmp = ""
  })

  async function settings(tab = "settings"): Promise<Headless> {
    tmp ||= mkdtempSync(join(tmpdir(), "reelforge-tab-order-"))
    open = await headless("dashboard", { tab }, 150, 45, {
      REELFORGE_BRIDGE_PRELOAD: join(ROOT, "ui", "test", "settings_preload.py"),
      REELFORGE_TEST_ROOT: tmp,
    })
    await open.settle(3000)
    return open
  }

  const kept = () => {
    const f = join(tmp, "dashboard", "data", "tab-order.json")
    return existsSync(f) ? JSON.parse(readFileSync(f, "utf-8")).order : null
  }

  test("an order you pick is kept, and the next window opens with it; the default keeps nothing", async () => {
    let h = await settings()
    expect(kept()).toBeNull()
    await clickText(h, "5 Accounts", 3)
    for (let i = 0; i < 4; i++) await clickText(h, "← Move left", 3)
    expect(kept()).toEqual(["accounts", "overview", "videos", "compare", "totals", "settings", "updates"])
    expect(frame(h)).not.toContain("Demo mode")
    await open!.close()
    h = await settings("overview")
    expect(header(h)).toEqual(["Accounts", "Overview", "Videos", "Compare", "Stats", "Settings", "Updates"])
    h.t.mockInput.pressKey("1")
    await h.settle(1000)
    expect(activeTab(h)).toBe("Accounts")
    h.t.mockInput.pressKey("6")
    await h.settle(1500)
    await clickText(h, "Reset to default", 3)
    expect(kept()).toBeNull()
    expect(header(h)).toEqual(DEFAULT)
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
    open = await headless("dashboard", { tab: "settings" }, 150, 64, {
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

  /** Wait (up to 5 s) for a dialog the Python side fills in: a slow computer takes longer than one settle. Each look
   * comes after a settle, so the frame is never read while the window is still drawing it. */
  async function until(h: Headless, text: string) {
    for (let i = 0; i < 25; i++) {
      await h.settle(200)
      if (frame(h).includes(text)) return
    }
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
    await until(h, "FACTORY RESET")
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
    await until(h, "UNINSTALL REELFORGE")
    const f = frame(h)
    expect(f).toContain("UNINSTALL REELFORGE")
    expect(f).toContain("Moved first to")
    expect(f).toContain("(STUDIO_DRY_SYSTEM)") // the computer's settings are left alone here
    await clickText(h, "Cancel")
    await h.settle(500)
    expect(frame(h)).not.toContain("UNINSTALL REELFORGE")
    expect(asked()).toBeNull()
    await clickText(h, "Uninstall…")
    await until(h, "UNINSTALL REELFORGE")
    await h.t.mockInput.typeText("night physics")
    await h.settle(300)
    await clickText(h, "▐█▌", 0) // Keep them: off
    await h.settle(300)
    expect(frame(h)).toContain(`They go to the ${BIN} with the rest`)
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
