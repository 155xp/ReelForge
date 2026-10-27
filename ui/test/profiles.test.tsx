// Deleting a profile and bringing it back, drawn without a terminal with the real Python side on a ReelForge folder of
// its own in a scratch folder (ui/test/profiles_preload.py: the first channel, Alpha and Beta), the window on Alpha:
// from the profile menu and from the Settings tab's Profiles panel, each behind a dialog that does nothing until the
// profile's name is typed, then Restore. (What the Python side does is tested in tests/test_profiles.py.)

import { afterEach, describe, expect, setDefaultTimeout, test } from "bun:test"
import { existsSync, mkdtempSync, readdirSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText } from "../scripts/shots"
import { ROOT } from "../src/bridge"
import { toasts } from "../src/ui/Panels"

setDefaultTimeout(60_000) // each test starts a real window on its own scratch folder, then waits on its Python side
let open: Headless | null = null
let tmp = ""

afterEach(async () => {
  await open?.close() // first: its Python side has the scratch folder's files open
  open = null
  toasts.clear() // the pop-ups live in the module, so the next window would start with this one's
  if (tmp) rmSync(tmp, { recursive: true, force: true, maxRetries: 20, retryDelay: 250 })
  tmp = ""
})

const frame = (h: Headless) => h.t.captureCharFrame()
const said = () => toasts.get().map((t) => `${t.title}: ${t.body}`)
const backups = () => (existsSync(join(tmp, "backups")) ? readdirSync(join(tmp, "backups")) : [])
const beta = () => existsSync(join(tmp, "profiles", "beta", "profile.toml"))

async function onAlpha(tab: string, size: [number, number] = [160, 50]): Promise<Headless> {
  tmp = mkdtempSync(join(tmpdir(), "reelforge-delete-"))
  open = await headless("dashboard", { tab }, size[0], size[1], {
    REELFORGE_BRIDGE_PRELOAD: join(ROOT, "ui", "test", "profiles_preload.py"),
    REELFORGE_TEST_ROOT: tmp,
    REELFORGE_PROFILE: "profiles/alpha",
  })
  await open.settle(2500)
  return open
}

/** Wait (up to 8 s) for what the Python side does: a slow computer takes longer than one settle. Each look comes after
 * a settle, so the frame is never read while the window is still drawing it. */
async function until(h: Headless, ok: () => boolean) {
  for (let i = 0; i < 40; i++) {
    await h.settle(200)
    if (ok()) return
  }
}

describe("deleting a profile", () => {
  test("from the profile menu: Delete asks for its name, and only then moves it whole into backups", async () => {
    const h = await onAlpha("overview")
    h.t.mockInput.pressKey("p")
    await h.settle(500)
    expect(frame(h)).toContain(" Delete ") // beside Beta: not beside Alpha (this window's) or the first channel
    expect(frame(h)).toContain("Del deletes")
    h.t.mockInput.pressArrow("down") // from Alpha (2) to Beta (3)
    await h.settle(300)
    h.t.mockInput.pressKey("DELETE")
    await until(h, () => frame(h).includes("DELETE BETA"))
    expect(frame(h)).toContain("Nothing is deleted for good.")
    expect(frame(h)).toContain("Type Beta to confirm")
    await clickText(h, "Delete Beta", 2) // nothing until its name is typed
    h.t.mockInput.pressKey("RETURN")
    await h.settle(800)
    expect(beta()).toBe(true)
    await h.t.mockInput.typeText("beta")
    await h.settle(300)
    h.t.mockInput.pressKey("RETURN")
    await until(h, () => !beta() && said().some((t) => t.startsWith("Profile deleted")))
    expect(beta()).toBe(false)
    expect(backups().filter((b) => b.startsWith("deleted-profile-beta-"))).toHaveLength(1)
    expect(said().find((t) => t.startsWith("Profile deleted"))).toContain("Restore on the Settings tab brings it back.")
  })

  test("never this window's own profile or the first one: Delete on them says why, and stays in the menu", async () => {
    const h = await onAlpha("overview")
    h.t.mockInput.pressKey("p")
    await h.settle(500)
    h.t.mockInput.pressKey("DELETE") // Alpha, this window's own
    await h.settle(500)
    expect(said().join("\n")).toContain("This window is showing Alpha. Switch to another profile first")
    expect(frame(h)).toContain("PROFILES")
    h.t.mockInput.pressArrow("up") // the first channel
    await h.settle(300)
    h.t.mockInput.pressKey("DELETE")
    await h.settle(500)
    expect(said().join("\n")).toContain("it lives in the ReelForge folder itself, so it can't be deleted")
    expect(frame(h)).not.toContain("DELETE MY CHANNEL")
    expect(backups()).toEqual([])
  })

  test("from the Settings tab: Profiles deletes one, lists it as deleted, and Restore brings it back", async () => {
    const h = await onAlpha("settings", [160, 72])
    await until(h, () => frame(h).includes("PROFILES"))
    let f = frame(h)
    if (process.env.SHOW) console.log(f)
    expect(f).toContain("this window: switch to another profile to delete it")
    expect(f).toContain("your first channel, in the ReelForge folder itself: it stays")
    expect(f).toContain("+ New profile")
    expect(f).not.toContain("DELETED")
    await clickText(h, "Delete…", 2) // Beta's: the only one this window can delete
    await until(h, () => frame(h).includes("DELETE BETA"))
    await h.t.mockInput.typeText("Beta")
    await h.settle(300)
    await clickText(h, "Delete Beta", 2)
    await until(h, () => frame(h).includes("kept whole in backups until you restore them"))
    f = frame(h)
    expect(f).toContain("DELETED")
    expect(f).toContain("deleted today at")
    expect(beta()).toBe(false)
    await clickText(h, " Restore ", 1)
    await until(h, () => beta() && !frame(h).includes("kept whole in backups until you restore them"))
    expect(beta()).toBe(true)
    expect(backups()).toEqual([])
    expect(said().join("\n")).toContain("Beta is back, as it was.")
  })

  test("the demo's Profiles panel shows its channels and a deleted one, and deletes or restores nothing", async () => {
    open = await headless("dashboard", { demo: true, only_demos: true, tab: "settings" }, 160, 80, {
      REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py"),
    })
    const h = open
    await until(h, () => frame(h).includes("Old Experiments"))
    const f = frame(h)
    for (const text of ["PROFILES", "Night Physics", "Tiny Worlds", "Delete…", "Old Experiments", "deleted yesterday at 9:12 PM", "Restore"])
      expect(f).toContain(text)
    await clickText(h, "Delete…", 2)
    await h.settle(500)
    expect(frame(h)).not.toContain("DELETE TINY WORLDS")
    await clickText(h, " Restore ", 1)
    await h.settle(500)
    expect(said().filter((t) => t.startsWith("Demo mode"))).toHaveLength(2)
  })
})
