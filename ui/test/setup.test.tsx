// The first-run screens, drawn without a terminal with their real Python side and a fresh computer's tools list
// (scripts/shots_preload.py): ticking what to set up, onboarding's steps and its Leave dialog, and the last screen's
// buttons. (The Python side's steps are tested in tests/test_setup_service.py.)

import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
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
    expect(frame(h)).toContain("1/9  You")
    await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("2/9  Your channel")
    expect(frame(h)).toContain("Night Physics")
    await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("3/9  Your format")
    expect(frame(h)).toContain("What if X doubled every 2 seconds?")
    await clickText(h, "  Back  ", 4)
    expect(frame(h)).toContain("2/9  Your channel")
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
    expect(frame(h)).toContain("5/9  Your accounts")
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
    expect(frame(h)).toContain("2/9  Your channel")
    await clickText(h, "Night Physics", 2) // the empty name's example
    await h.t.mockInput.typeText("Cool Epic Facts")
    await clickText(h, "Mind-bending", 2)
    await h.t.mockInput.typeText("Mind-blowing facts.")
    for (let step = 0; step < 3; step++) await clickText(h, "  Next  ", 4)
    expect(frame(h)).toContain("5/9  Your accounts")
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
    expect(frame(h)).toContain("Leave onboarding?")
    await clickText(h, "Keep going", 2)
    expect(frame(h)).not.toContain("Leave onboarding?")
    expect(h.exits).toEqual([])
    await press(h, "ESCAPE")
    await clickText(h, "  Leave  ", 3)
    expect(h.exits).toEqual([{ code: 0, result: undefined }])
  })
})

describe("ready", () => {
  test("Open ReelForge opens it on the Accounts tab when Instagram or X needs a log-in", async () => {
    const h = await screen("done", [130, 32])
    expect(frame(h)).toContain("You're all set!")
    expect(frame(h)).toContain("Background stats: Your stats will update every 60 minutes")
    await clickText(h, "Open ReelForge to log in", 2)
    expect(h.exits).toEqual([{ code: 0, result: { open: "dashboard", tab: "accounts" } }])
  })
})
