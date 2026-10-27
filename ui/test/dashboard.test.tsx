// The ReelForge window itself, drawn without a terminal on demo data with its real Python side: what fits where, the
// keys, clicks on chips, headers, the bell and the drawer's notifications, and the dialogs. (What the Python side
// does when they're pressed is tested in dashboard/tests/.)

import { TextAttributes } from "@opentui/core"
import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText, find } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import { DRAWER_WIDTH } from "../src/dashboard/Drawer"
import { TILE_ROWS } from "../src/dashboard/Overview"
import { TAB_NAMES, TOP_ROWS } from "../src/dashboard/state"
import { DASH } from "../src/theme"
import { toasts } from "../src/ui/Panels"

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }
setDefaultTimeout(30_000) // each test starts a real window (2.5 s to draw it) before its clicks and keys
let open: Headless | null = null

async function window(tab = "overview", size: [number, number] = [180, 50], drawer = false, more = {}): Promise<Headless> {
  open = await headless("dashboard", { demo: true, only_demos: true, tab, drawer, ...more }, size[0], size[1], PRELOAD)
  await open.settle(2500)
  return open
}

afterEach(async () => {
  await open?.close()
  open = null
  toasts.clear() // the pop-ups live in the module, so the next window would start with this one's
})

const frame = (h: Headless) => h.t.captureCharFrame()
const rows = (h: Headless) => frame(h).split("\n")

/** The tab that's open: its name bold in the header, where the others are plain. */
function activeTab(h: Headless): string {
  const names = Object.values(TAB_NAMES) as string[]
  const lit = h.t.captureSpans().lines[1]!.spans.find((s) => s.attributes & TextAttributes.BOLD && names.includes(s.text.trim()))
  return lit?.text.trim() ?? ""
}

const hex = (c: { toInts(): [number, number, number, number] }) => "#" + c.toInts().slice(0, 3).map((v) => v.toString(16).padStart(2, "0")).join("")

/** Row y as cells: each character with its background colour. */
function cells(h: Headless, y: number): { ch: string; bg: string }[] {
  const out: { ch: string; bg: string }[] = []
  for (const s of h.t.captureSpans().lines[y]!.spans) {
    const chars = [...s.text]
    for (let i = 0; i < s.width; i++) out.push({ ch: chars[i] ?? " ", bg: hex(s.bg) })
  }
  return out
}

const KEYS: Record<string, "ESCAPE" | "RETURN" | "TAB" | "DELETE"> = { escape: "ESCAPE", return: "RETURN", tab: "TAB", delete: "DELETE" }

async function press(h: Headless, key: string) {
  h.t.mockInput.pressKey(KEYS[key] ?? key)
  await h.settle(300)
}

/** Wait (up to 5 s) for what a click asked the Python side for: a slow computer takes longer than one settle. Each look
 * comes after a settle, as in clickText, so the frame is never read while the window is still drawing it. */
async function until(h: Headless, text: string) {
  for (let i = 0; i < 25; i++) {
    await h.settle(200)
    if (frame(h).includes(text)) return
  }
}

describe("the Overview fits", () => {
  for (const [w, hh, drawer] of [
    [110, 40, false],
    [150, 45, true],
    [200, 52, true],
  ] as const) {
    test(`at ${w}x${hh}${drawer ? " with the drawer open" : ""}: every tile names its platform, and nothing spills out of one`, async () => {
      const h = await window("overview", [w, hh], drawer)
      const top = TOP_ROWS + 1 // the header, its hairline, a row of space
      const edge = drawer ? w - DRAWER_WIDTH - 2 : w // the drawer covers the right-hand tiles
      // the tiles are the runs of the panels' colour along their first row, with the window's colour between them
      const first = cells(h, top).slice(0, edge)
      const gaps = first.map((c, x) => (c.bg === DASH.bg && x > 1 && x < edge - 1 && first[x - 1]!.bg === DASH.surface ? x : -1)).filter((x) => x >= 0)
      expect(gaps.length).toBe(drawer ? gaps.length : 4) // five tiles side by side
      for (let y = top; y < top + TILE_ROWS; y++) {
        const row = cells(h, y)
        for (const x of gaps) expect(row[x]).toEqual({ ch: " ", bg: DASH.bg })
      }
      const names = rows(h).slice(top, top + 2).join("")
      for (const name of [["All platforms", "All"], ["TikTok", "TT"], ["YouTube", "YT"]]) expect(name.some((n) => names.includes(n))).toBe(true)
    })
  }
})

describe("the header and the bell", () => {
  test("the bell sits in the top right corner with the unread count, and opens and closes the drawer", async () => {
    const h = await window("overview", [122, 30])
    expect(rows(h)[0]).toMatch(/\d▌\s*$/) // the unread count's pill, on the bell's shoulder
    expect(frame(h)).not.toContain("NOTIFICATIONS")
    await h.t.mockMouse.click(122 - 3, 1)
    await h.settle(400)
    expect(frame(h)).toContain("NOTIFICATIONS")
    await h.t.mockMouse.click(122 - 8, 0)
    await h.settle(400)
    expect(frame(h)).not.toContain("NOTIFICATIONS")
  })

  test("Quit quits", async () => {
    const h = await window()
    await clickText(h, " Quit ", 2)
    expect(h.exits).toEqual([{ code: 0, result: undefined }])
  })
})

describe("pop-ups", () => {
  test("a click anywhere on the pop-ups closes one, even on the row between two: nothing under them shows through", async () => {
    const h = await window("accounts", [180, 50], false, { unconnected: ["x"] })
    for (const n of [1, 2]) h.bridge.emit("toast", { title: `Pop-up ${n}`, body: "It stays until it's clicked.", timeout: 60 })
    await h.settle(500)
    const [x, y] = find(h, "Pop-up 1")!
    await h.t.mockMouse.click(x, y + 3) // under its title: its line, its padding, then the row between the two
    await h.settle(600)
    expect(frame(h)).not.toContain("Pop-up 1")
    expect(frame(h)).toContain("Pop-up 2")
  })
})

describe("keys", () => {
  test("1-6 switch tabs, but not while you type; Esc leaves the field", async () => {
    const h = await window()
    expect(activeTab(h)).toBe("Overview")
    await press(h, "2")
    expect(activeTab(h)).toBe("Videos")
    await press(h, "4")
    expect(activeTab(h)).toBe("Publish")
    for (let i = 0; i < 30 && !find(h, "What if everyone"); i++) await h.settle(100) // the picked video's caption
    await h.t.mockMouse.click(find(h, "What if everyone")![0] + 3, find(h, "What if everyone")![1])
    await h.settle(200)
    h.t.mockInput.pressKey("END")
    await h.t.mockInput.typeText(" 3")
    await h.settle(300)
    expect(activeTab(h)).toBe("Publish")
    expect(frame(h)).toContain("time? 3")
    await press(h, "escape")
    await press(h, "3")
    expect(activeTab(h)).toBe("Compare")
  })

  test("? opens the help, Esc closes it", async () => {
    const h = await window()
    await h.t.mockInput.typeText("?")
    await h.settle(300)
    expect(frame(h)).toContain("HOW REELFORGE WORKS")
    await press(h, "escape")
    expect(frame(h)).not.toContain("HOW REELFORGE WORKS")
  })

  test("Tab moves between buttons, and Enter presses one", async () => {
    const h = await window("updates")
    expect(frame(h)).not.toContain("HOW REELFORGE WORKS")
    for (let i = 0; i < 2; i++) await press(h, "tab") // Check now, then Release page... back round to Check now
    await press(h, "escape")
    await clickText(h, " Help ", 2)
    expect(frame(h)).toContain("HOW REELFORGE WORKS")
    await press(h, "return") // Close has the keyboard
    expect(frame(h)).not.toContain("HOW REELFORGE WORKS")
  })
})

describe("accounts", () => {
  test("a platform that isn't connected has a box for its @handle: a typo says why, Sign up shows the steps", async () => {
    const h = await window("accounts", [180, 50], false, { unconnected: ["x"] })
    expect(frame(h)).toContain("○ not connected")
    expect(frame(h)).toContain("Only connected platforms show up in ReelForge. Connect X here any time.")
    expect(frame(h)).toContain("Disconnect") // on the connected ones
    await clickText(h, "@yourname", 2)
    await h.t.mockInput.typeText("two words")
    await press(h, "return") // Enter connects
    expect(frame(h)).toContain("That isn't a handle")
    await clickText(h, " Sign up → ", 2)
    await until(h, "MAKE YOUR X ACCOUNT")
    expect(frame(h)).toContain("MAKE YOUR X ACCOUNT")
    expect(frame(h)).toContain("Pick a username that matches your channel")
    await press(h, "escape")
    expect(frame(h)).not.toContain("MAKE YOUR X ACCOUNT")
  })

  test("X's Connect button connects the @handle typed in its box (the demo saves nothing, and says so)", async () => {
    const h = await window("accounts", [180, 50], false, { unconnected: ["x"] })
    await clickText(h, "@yourname", 2)
    await h.t.mockInput.typeText("@mychannel")
    await h.settle(300)
    const at = find(h, " Connect ", find(h, "@mychannel")![1])! // on the box's row (the hint above says Connect too)
    await h.t.mockMouse.click(at[0] + 2, at[1])
    await until(h, "Demo mode: nothing is saved.")
    expect(frame(h)).toContain("Demo mode: nothing is saved.")
    expect(frame(h)).not.toContain("Something went wrong")
  })

  test("Open profile opens the platform's page (from a test, nothing opens: the page is listed)", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "reelforge-opened-"))
    const list = join(tmp, "opened.txt")
    try {
      open = await headless("dashboard", { demo: true, only_demos: true, tab: "accounts" }, 180, 50, { ...PRELOAD, REELFORGE_OPENED: list })
      const h = open
      await h.settle(2500)
      await clickText(h, "Open profile", 2) // TikTok's, the first panel
      for (let i = 0; i < 25 && !existsSync(list); i++) await h.settle(200)
      expect(readFileSync(list, "utf-8")).toBe("https://www.tiktok.com/@yourchannel\n")
      expect(frame(h)).not.toContain("Something went wrong")
    } finally {
      await open?.close()
      open = null
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  test("with nothing connected, ReelForge opens on Accounts and offers a Gmail first", async () => {
    const h = await window("", [180, 50], false, { unconnected: ["tiktok", "youtube", "instagram", "x"] })
    expect(activeTab(h)).toBe("Accounts")
    expect(frame(h)).toContain("No accounts connected yet")
    await clickText(h, " Make a Gmail first ", 2)
    await until(h, "MAKE A GMAIL FOR YOUR CHANNEL")
    expect(frame(h)).toContain("MAKE A GMAIL FOR YOUR CHANNEL")
    expect(frame(h)).not.toContain("Your @handle")
  })
})

describe("tables and charts", () => {
  test("a header sorts, and again flips the order", async () => {
    const h = await window("videos")
    expect(frame(h)).not.toContain("Views 12h ▼")
    await clickText(h, "Views 12h", 2)
    expect(frame(h)).toContain("Views 12h ▼")
    await clickText(h, "Views 12h ▼", 2)
    expect(frame(h)).toContain("Views 12h ▲")
  })

  test("Newest, Oldest and Most views beside Episodes sort the Compare tab's list, under the platform scoreboard", async () => {
    const h = await window("compare")
    const listed = () => h.bridge.view<{ items: { id: string }[] }>("episodes")!.items.map((i) => i.id).join()
    const settled = async (ok: () => boolean) => {
      for (let i = 0; i < 25 && !ok(); i++) await h.settle(200)
    }
    expect(rows(h).find((r) => r.includes("EPISODES"))).toContain("Newest   Oldest   Most views")
    const newest = listed().split(",")
    const oldest = [newest[0]!, ...newest.slice(1).reverse()].join()
    await clickText(h, " Oldest ", 2)
    await settled(() => listed() === oldest)
    expect(listed()).toBe(oldest)
    await clickText(h, " Most views ", 2)
    await settled(() => /\dK 4\/4/.test(frame(h)))
    expect(frame(h)).toMatch(/\d\.\dK 4\/4/) // each episode's views beside it
    expect(frame(h)).toContain("◆ Platform scoreboard")
    await clickText(h, " Newest ", 2)
    await settled(() => listed() === newest.join())
    expect(listed()).toBe(newest.join())
  })

  test("the range chips and a platform's key change the charts", async () => {
    const h = await window()
    expect(frame(h)).toContain("in 24h")
    await clickText(h, " 7D ", 2)
    expect(frame(h)).toContain("in 7d")
    await clickText(h, "■ TikTok", 2)
    const views = h.bridge.view<{ legend: [string, string][] }>("trends")!.legend
    expect(views.find((s) => s[0] === "■ TikTok")![1]).toContain("strike")
  })

  test("pointing at a bar reads its numbers", async () => {
    const h = await window()
    const title = find(h, "VIEWS")!
    const before = rows(h)[title[1]]
    await h.t.mockMouse.moveTo(title[0] + 30, title[1] + 8)
    await h.settle(300)
    expect(rows(h)[title[1]]).not.toBe(before)
    expect(rows(h)[title[1]]).toMatch(/VIEWS\s+\S+ \d+( |:)/)
  })
})

describe("the drawer", () => {
  const noteTitles = (h: Headless) => h.bridge.view<{ items: { title: [string, string][] }[] }>("notes")!.items.map((n) => n.title.map((s) => s[0]).join(""))

  test("a notification's × deletes it without opening it", async () => {
    const h = await window("overview", [180, 50], true)
    const before = noteTitles(h)
    const at = find(h, before[0]!.slice(0, 20))!
    await h.t.mockMouse.click([...rows(h)[at[1]]!].lastIndexOf("×"), at[1]) // its × (beside its title)
    await h.settle(500)
    expect(noteTitles(h)).toEqual(before.slice(1))
    expect(activeTab(h)).toBe("Overview")
  })

  test("Delete deletes the highlighted one; a click opens what it's about", async () => {
    const h = await window("overview", [180, 50], true)
    const before = noteTitles(h)
    await clickText(h, before[1]!.slice(0, 20), 2) // highlights it
    await press(h, "delete")
    expect(noteTitles(h)).toEqual([before[0]!, ...before.slice(2)])
    const video = noteTitles(h).find((t) => /^(Taking off|A video passed)/.test(t))!
    await clickText(h, video.slice(0, 20), 2)
    await clickText(h, video.slice(0, 20), 2)
    await h.settle(500)
    expect(activeTab(h)).toBe("Videos")
  })

  test("Esc closes it", async () => {
    const h = await window("overview", [180, 50], true)
    await press(h, "escape")
    expect(frame(h)).not.toContain("NOTIFICATIONS")
  })
})

describe("dialogs", () => {
  test("Remove asks what to do with the picked video; Cancel leaves it", async () => {
    const h = await window("publish", [200, 56])
    await clickText(h, " Remove ", 2)
    expect(frame(h)).toContain("REMOVE VIDEO")
    expect(frame(h)).toContain("demo_everyone_jumps.mp4")
    await clickText(h, " Cancel ", 2)
    expect(frame(h)).not.toContain("REMOVE VIDEO")
    expect(frame(h)).toContain("demo_everyone_jumps.mp4")
  })

  test("Fix episode lists the videos to file a post under", async () => {
    const h = await window("videos")
    await clickText(h, " Fix episode ", 2)
    expect(frame(h)).toContain("WHICH VIDEO IS THIS?")
    expect(frame(h)).toContain("Not one of my videos")
    await press(h, "escape")
    expect(frame(h)).not.toContain("WHICH VIDEO IS THIS?")
  })
})

describe("profiles", () => {
  test("the profile button names the profile; p opens its menu, which lists every profile, and Esc closes it", async () => {
    const h = await window("overview", [180, 50])
    expect(rows(h)[1]).toContain("Night Physics ▾")
    await press(h, "p")
    expect(frame(h)).toContain("PROFILES")
    expect(frame(h)).toContain("Tiny Worlds")
    expect(frame(h)).toContain("3 new")
    expect(frame(h)).toContain("New profile")
    expect(frame(h)).toContain("Settings for Night Physics")
    expect(frame(h)).not.toContain("Advanced settings")
    await press(h, "escape")
    expect(frame(h)).not.toContain("PROFILES")
    await clickText(h, "Night Physics ▾", 2)
    expect(frame(h)).toContain("PROFILES")
  })

  test("the status bar names each platform, or says TT YT IG X in a window too narrow for that, and when it read them", async () => {
    for (const [w, full] of [[64, false], [122, true]] as const) {
      const h = await window("overview", [w, 30], false, { screenshots: true })
      const bar = rows(h)[29]!
      expect(bar).toContain(full ? "● TikTok" : "● TT  ● YT  ● IG  ● X")
      expect(bar).toContain("updated")
      await open?.close()
      open = null
    }
  })

  test("picking another profile shows it in the same window, on its own Python side", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "reelforge-profiles-"))
    try {
      open = await headless("dashboard", { tab: "overview" }, 160, 40, {
        REELFORGE_BRIDGE_PRELOAD: join(ROOT, "ui", "test", "profiles_preload.py"),
        REELFORGE_TEST_ROOT: tmp,
        REELFORGE_PROFILE: "profiles/alpha",
      })
      const h = open
      await h.settle(2500)
      expect(rows(h)[1]).toContain("Alpha ▾")
      await press(h, "p")
      expect(frame(h)).toContain("Beta")
      await press(h, "3") // 1 the ReelForge folder's own, 2 Alpha, 3 Beta
      for (let i = 0; i < 30 && !rows(h)[1]!.includes("Beta ▾"); i++) await h.settle(200)
      expect(rows(h)[1]).toContain("Beta ▾")
      expect(activeTab(h)).toBe("Accounts") // nothing connected there yet: where you connect one
      expect(h.sides.active).not.toBe(h.bridge)
      expect(await Promise.race([h.bridge.exited.then(() => "exited"), Bun.sleep(8000).then(() => "running")])).toBe("exited")
      expect(readFileSync(join(tmp, "profiles", "last-opened.txt"), "utf-8").trim()).toBe("profiles/beta")
    } finally {
      await open?.close()
      open = null
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  test("a second channel's Sign up opens its page in a private window, so the other channel stays logged in", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "reelforge-profiles-"))
    try {
      open = await headless("dashboard", {}, 160, 44, {
        REELFORGE_BRIDGE_PRELOAD: join(ROOT, "ui", "test", "profiles_preload.py"),
        REELFORGE_TEST_ROOT: tmp,
        REELFORGE_PROFILE: "profiles/alpha",
      })
      const h = open
      await h.settle(2500)
      expect(activeTab(h)).toBe("Accounts") // nothing connected yet
      expect(frame(h)).toContain("New channel?")
      await clickText(h, " Sign up → ", 2) // TikTok's
      await until(h, "MAKE YOUR TIKTOK ACCOUNT")
      expect(frame(h)).toContain("MAKE YOUR TIKTOK ACCOUNT")
      expect(frame(h)).toContain("like @alpha")
      await clickText(h, "Open TikTok sign-up →", 2)
      await until(h, "Opened in a private Chrome window.")
      expect(frame(h)).toContain("Opened in a private Chrome window.") // a stand-in: nothing opens
    } finally {
      await open?.close()
      open = null
      rmSync(tmp, { recursive: true, force: true })
    }
  })
})
