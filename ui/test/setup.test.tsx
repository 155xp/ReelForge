// The first-run screens, drawn without a terminal with their real Python side and a fresh computer's tools list
// (scripts/shots_preload.py): ticking what to set up, the channel's questions and their Leave dialog, the frame at any
// size, and the last screen's Copy prompt button (the prompt itself isn't shown), and its other buttons. (The Python
// side's steps are tested in tests/test_setup_service.py.)

import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText, find } from "../scripts/shots"
import { ROOT } from "../src/bridge"

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }
setDefaultTimeout(30_000) // each test starts the real screens (2 s to draw them) before its clicks and keys
let open: Headless | null = null

async function screen(start: string, size: [number, number] = [120, 40]): Promise<Headless> {
  open = await headless("setup", { start, preview: true }, size[0], size[1], PRELOAD)
  await open.settle(2000)
  return open
}

afterEach(async () => {
  await open?.close()
  open = null
})

const frame = (h: Headless) => h.t.captureCharFrame()

async function press(h: Headless, key: "ESCAPE" | "RETURN" | "TAB" | " ") {
  if (key === " ") await h.t.mockInput.typeText(" ")
  else h.t.mockInput.pressKey(key)
  await h.settle(300)
}

describe("the tools", () => {
  test("one list, one button, and a tick turned off comes off the total", async () => {
    const h = await screen("tools")
    for (let i = 0; i < 40 && !find(h, "Desktop shortcut"); i++) await h.settle(100)
    expect(frame(h)).toContain("C:\\Users\\you\\ReelForge")
    expect(frame(h)).toContain("Set up (about 570 MB)")
    await h.t.mockMouse.click(find(h, "Sound effects")![0] - 5, find(h, "Sound effects")![1]) // its tick
    await h.settle(300)
    expect(frame(h)).toContain("Set up (about 515 MB)")
    await clickText(h, "Skip for now", 2)
    await h.settle(500)
    expect(frame(h)).toContain("Sound library") // the downloads screen: with nothing to download, just the sounds
  })

  test("Esc leaves", async () => {
    const h = await screen("tools")
    await press(h, "ESCAPE")
    expect(h.exits).toEqual([{ code: 0, result: undefined }])
  })
})

describe("onboarding", () => {
  test("Next and Back walk the steps, from the answers saved last time", async () => {
    const h = await screen("onboard", [140, 46])
    expect(frame(h)).toContain("1/8  You")
    await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("2/8  Your channel")
    expect(frame(h)).toContain("Night Physics")
    await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("3/8  Your format")
    expect(frame(h)).toContain("What if X doubled every 2 seconds?")
    await clickText(h, "  Back  ", 4)
    expect(frame(h)).toContain("2/8  Your channel")
  })

  test("a different format brings its own suggestions", async () => {
    const h = await screen("onboard", [140, 46])
    await clickText(h, "  Next  ", 4)
    await clickText(h, "  Next  ", 4)
    const before = h.bridge
    expect(before).toBeTruthy()
    expect(frame(h)).toContain("Doubling")
    await clickText(h, "What if <disaster> hit your city?", 2)
    await h.settle(500)
    expect(frame(h)).not.toContain("Doubling")
  })

  test("Your accounts: a platform's sign-up guide hands back the @handle you made", async () => {
    const h = await screen("onboard", [140, 46])
    for (let step = 0; step < 4; step++) await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("5/8  Your accounts")
    expect(frame(h)).toContain("Make a Gmail")
    await clickText(h, "No account? Sign up", 2) // TikTok's, the first
    expect(frame(h)).toContain("Make your TikTok account")
    expect(frame(h)).toContain("Pick a username that matches your channel")
    await press(h, "TAB") // from the button that opens the page to the box for the handle
    await h.t.mockInput.typeText("not a handle!")
    await press(h, "RETURN")
    expect(frame(h)).toContain("isn't a handle")
    for (let i = 0; i < 13; i++) h.t.mockInput.pressKey("BACKSPACE")
    await h.t.mockInput.typeText("tiktok.com/@nightphysics")
    await press(h, "RETURN")
    expect(frame(h)).not.toContain("Make your TikTok account")
    expect(frame(h)).toContain("@nightphysics")
    expect(h.exits).toEqual([])
  })

  test("a new profile's Your accounts: a Gmail for it first, and its sign-ups open in a private window", async () => {
    open = await headless("setup", { start: "onboard", preview: true, new: true }, 140, 46, PRELOAD)
    const h = open
    await h.settle(2000)
    await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("2/8  Your channel")
    await clickText(h, "Night Physics", 2) // the empty name's example
    await h.t.mockInput.typeText("Cool Epic Facts")
    await clickText(h, "Mind-bending", 2)
    await h.t.mockInput.typeText("Mind-blowing facts.")
    for (let step = 0; step < 3; step++) await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("5/8  Your accounts")
    expect(frame(h)).toContain("make a Gmail for Cool Epic Facts first")
    await clickText(h, "No account? Sign up", 2) // TikTok's
    expect(frame(h)).toContain("like @coolepicfacts")
    await clickText(h, "Open TikTok sign-up →", 2)
    expect(frame(h)).toContain("Opened in a private Chrome window.") // a stand-in: nothing opens
    expect(h.exits).toEqual([])
  })

  test("Esc asks first; Keep going stays, Leave leaves", async () => {
    const h = await screen("onboard", [140, 46])
    await press(h, "ESCAPE")
    expect(frame(h)).toContain("Leave without saving?")
    await clickText(h, "Keep going", 2)
    expect(frame(h)).not.toContain("Leave without saving?")
    expect(h.exits).toEqual([])
    await press(h, "ESCAPE")
    await clickText(h, "▐ Leave ▌", 3) // the button, not the title above it
    expect(h.exits).toEqual([{ code: 0, result: undefined }])
  })
})

describe("the frame", () => {
  test("fits any size: the steps along the top, the step's title, and its buttons all in view", async () => {
    for (const [w, hh] of [[60, 18], [90, 24], [120, 30], [200, 60]] as const) {
      const h = await screen("onboard", [w, hh])
      const lines = frame(h).split("\n")
      expect(lines.length).toBeGreaterThanOrEqual(hh)
      expect(lines.slice(0, 3).join("")).toContain("Your channel") // the steps (or just this one, when narrow)
      expect(frame(h)).toContain("1/8  You")
      const next = find(h, "Next")
      expect(next).not.toBeNull()
      expect(next![1]).toBeLessThan(hh - 1) // above the last row, with a row of space under it
      expect(frame(h)).not.toContain("╔") // no box round the window any more
      await open?.close()
      open = null
    }
  })

  // Every first-run screen, resized while it's open the way a person drags a window: nothing pushes into the frame's
  // padding down each side, every button is there in full (they move onto another row when they don't fit side by side), and the first words aren't cut
  // off at the scrollbar. A button is "label|other label" when it can say either, and ends in "?" when it's only there
  // on some computers (Check again, while the health check finds something to fix). "label^18" is a button inside the
  // scroll area (Copy prompt, right under step 1): it's on screen from 18 rows up, and a shorter window scrolls to it.
  const SIZES = [[40, 16], [40, 36], [46, 14], [56, 20], [66, 18], [80, 24], [100, 30], [160, 46], [120, 40]] as const
  const waitFor = async (h: Headless, text: string) => {
    for (let i = 0; i < 50 && !find(h, text); i++) await h.settle(100)
  }
  const SCREENS: [string, string, string[], string, (h: Headless) => Promise<void>][] = [
    ["the tools", "tools", ["Set up (about 570 MB)", "Skip for now"], "Let's get ReelForge ready. Everything goes into this folder", (h) => waitFor(h, "Desktop shortcut")],
    ["the downloads", "tools", ["Next: your channel|Continue", "Check again?"], "Sound library", async (h) => {
      await waitFor(h, "Desktop shortcut")
      await clickText(h, "Skip for now", 2)
      await waitFor(h, "Health check")
      await h.settle(300)
    }],
    ["the questions", "onboard", ["Back", "Next"], "Welcome! Answer a few questions and your AI will know your channel inside out.", async () => {}],
    ["the last screen", "done", ["Copy prompt^18", "Open ReelForge to log in", "Close"], "You're all set! Night Physics is ready to make videos.", async () => {}],
  ]
  for (const [name, start, buttons, words, ready] of SCREENS)
    test(`${name}: whole at every size while it's resized, with its buttons and words in full`, async () => {
      const h = await screen(start, [120, 40])
      await ready(h)
      const wanted = buttons.filter((b) => !b.endsWith("?") || find(h, b.slice(0, -1))).map((b) => b.replace(/\?$/, ""))
      const wrong: string[] = []
      for (const [w, hh] of SIZES) {
        h.t.resize(w, hh)
        await h.settle(50)
        const rows = frame(h).split("\n").slice(0, hh).map((r) => [...r])
        const at = `${w}x${hh}`
        // the frame keeps 4 columns clear down each side: nothing on the screen pushes into them
        if (rows.some((r) => r.slice(0, 4).join("").trim() || r.slice(w - 4).join("").trim())) wrong.push(`${at}: edges`)
        // from a column on (the words' own, past the list of steps), without the scrollbar's thumb, as one line of text
        const text = (from: number) =>
          rows.map((r) => r.slice(from).join("").replace(/[█▀▄]/g, " ")).join(" ").replace(/\s+/g, " ")
        for (const b of wanted) {
          const [labels, minRows] = b.split("^")
          if (minRows && hh < Number(minRows)) continue
          if (!labels!.split("|").some((label) => text(0).includes(label))) wrong.push(`${at}: button "${labels}"`)
        }
        if (!text(find(h, words.split(" ")[0]!)?.[0] ?? 0).includes(words)) wrong.push(`${at}: "${words}"`)
      }
      expect(wrong).toEqual([])
    })
})

describe("ready", () => {
  test("the last screen has a Copy prompt button, not the prompt itself, and it copies the prompt with the folder in it", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "reelforge-copied-"))
    const copied = join(tmp, "copied.txt")
    try {
      open = await headless("setup", { start: "done", preview: true }, 130, 50, { ...PRELOAD, REELFORGE_COPIED: copied })
      const h = open
      await h.settle(2000)
      if (process.env.SHOW) console.log(frame(h))
      // the screen's words in order, without the mascot, the scrollbar and the buttons' ends, as one line
      const text = frame(h).replace(/[█▀▄▌▐]/g, " ").replace(/\s+/g, " ")
      expect(text).toContain(
        "1. Copy the prompt for your AI with the button below. It has your ReelForge folder's path in it, so there's " +
          "nothing to drag in. Copy prompt 2. Paste it into Claude Code",
      )
      expect(text).not.toContain("I make videos for my channel") // the button copies it; the screen doesn't show it
      expect(text).not.toContain("drag a file")
      expect(text).not.toContain("here's my channel")
      expect(text).not.toContain("Show this folder") // the prompt has the folder in it
      await clickText(h, "Copy prompt", 2)
      for (let i = 0; i < 25 && !existsSync(copied); i++) await h.settle(200)
      expect(readFileSync(copied, "utf-8")).toBe(
        "I make videos for my channel, Night Physics, with ReelForge. My ReelForge folder is:\nC:\\Users\\you\\ReelForge\n\n" +
          "Work in that folder from now on. First read the notes it has for you, and follow them: CLAUDE.md if you're " +
          "Claude, AGENTS.md if you're another AI. Then make my first video.\n-- copied --\n",
      )
      await h.settle(100)
      expect(frame(h).replace(/[▌▐]/g, " ").replace(/\s+/g, " ")).toContain("Copied Now paste it into your AI.")
      expect(h.exits).toEqual([]) // copying leaves the screen open
    } finally {
      await open?.close()
      open = null
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  test("in a 120x30 window Copy prompt sits right under step 1, on screen, and has the keyboard", async () => {
    const h = await screen("done", [120, 30])
    const rows = frame(h).split("\n").slice(0, 30)
    const step = rows.findIndex((r) => r.includes("1. Copy the prompt for your AI"))
    const copy = rows.findIndex((r) => r.includes("Copy prompt"))
    expect(step).toBeGreaterThan(0)
    expect(copy).toBeGreaterThan(step)
    expect(copy - step).toBeLessThanOrEqual(4) // straight under step 1 (two rows at this width), not in the button row
    expect(rows.findIndex((r) => r.includes("Open ReelForge to log in"))).toBeGreaterThan(copy)
    expect(frame(h)).not.toContain("I make videos for my channel")
    expect(frame(h)).not.toContain("Show this folder")
  })

  test("setup run again on a channel: Copy prompt copies the update prompt, still with the folder in it", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "reelforge-copied-"))
    const copied = join(tmp, "copied.txt")
    try {
      open = await headless("setup", { start: "done", preview: true, again: true }, 130, 50, { ...PRELOAD, REELFORGE_COPIED: copied })
      const h = open
      await h.settle(2000)
      const text = frame(h).replace(/[█▀▄▌▐]/g, " ").replace(/\s+/g, " ")
      expect(text).toContain("You're all set! Night Physics's answers are updated.")
      expect(text).not.toContain("I make videos for my channel")
      expect(text).toContain("2. Paste it into Claude Code")
      expect(text).toContain("It reads the updated notes and tells you what changed")
      expect(text).not.toContain("Then make my first video")
      await clickText(h, "Copy prompt", 2)
      for (let i = 0; i < 25 && !existsSync(copied); i++) await h.settle(200)
      const got = readFileSync(copied, "utf-8")
      expect(got).toContain("My ReelForge folder is:\nC:\\Users\\you\\ReelForge\n\nWork in that folder.")
      expect(got).toContain("Then tell me in a few lines what changed, and use it from my next video on.\n-- copied --\n")
    } finally {
      await open?.close()
      open = null
      rmSync(tmp, { recursive: true, force: true })
    }
  })

  test("Open ReelForge opens it on the Accounts tab when Instagram or X needs a log-in", async () => {
    const h = await screen("done", [130, 50]) // tall enough for the background stats, under what's next
    expect(frame(h)).toContain("You're all set!")
    expect(frame(h)).toContain("Background stats: Your stats will update every 60 minutes")
    await clickText(h, "Open ReelForge to log in", 2)
    expect(h.exits).toEqual([{ code: 0, result: { open: "dashboard", tab: "accounts" } }])
  })
})
