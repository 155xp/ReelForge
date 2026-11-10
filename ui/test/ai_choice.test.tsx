// First-time setup's "Which AI will make your videos?": tick Claude Code, Codex or both, like the platforms.
import { afterEach, expect, setDefaultTimeout, test } from "bun:test"
import { join } from "node:path"
import { headless, type Headless } from "../scripts/headless"
import { clickText } from "../scripts/shots"
import { ROOT } from "../src/bridge"

const PRELOAD = { REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py") }
setDefaultTimeout(30_000)
let open: Headless | null = null

afterEach(async () => {
  await open?.close()
  open = null
})

const frame = (h: Headless) => h.t.captureCharFrame()
// Windows' console uses √; macOS and Linux use ✓. Both mean selected.
const selected = (label: string) => new RegExp(`[✓√]   ${label}`)

test("your AI is a tick list: Claude Code, Codex or both, and none is a question still to answer", async () => {
  open = await headless("setup", { start: "onboard", preview: true }, 120, 40, PRELOAD)
  const h = open
  await h.settle(2000)
  expect(frame(h)).toContain("Which AI will make your videos? *")
  expect(frame(h)).toContain("Pick one or both.")
  expect(frame(h)).toMatch(selected("Claude Code")) // the saved answer: Claude Code
  expect(frame(h)).toContain("○   Codex")
  await clickText(h, "○   Codex", 2)
  expect(frame(h)).toMatch(selected("Codex"))
  expect(frame(h)).toMatch(selected("Claude Code")) // both ticked
  await clickText(h, "  Next  ", 4)
  expect(frame(h)).toContain("2/8  Your channel")
  await clickText(h, "  Back  ", 4)
  expect(frame(h)).toMatch(selected("Claude Code"))
  expect(frame(h)).toMatch(selected("Codex")) // kept
  await clickText(h, frame(h).match(selected("Claude Code"))![0], 2)
  await clickText(h, frame(h).match(selected("Codex"))![0], 2)
  await clickText(h, "  Next  ", 4)
  expect(frame(h)).toContain("1/8  You") // none ticked: it stays, asking for one
  expect(frame(h)).toContain("Please answer this one.")
  expect(h.exits).toEqual([])
})
