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

test("your AI is a tick list: Claude Code, Codex or both, and none is a question still to answer", async () => {
  open = await headless("setup", { start: "onboard", preview: true }, 120, 40, PRELOAD)
  const h = open
  await h.settle(2000)
  expect(frame(h)).toContain("Which AI will make your videos? *")
  expect(frame(h)).toContain("Pick one or both.")
  expect(frame(h)).toContain("√   Claude Code") // the saved answer: Claude Code
  expect(frame(h)).toContain("○   Codex")
  await clickText(h, "○   Codex", 2)
  expect(frame(h)).toContain("√   Codex")
  expect(frame(h)).toContain("√   Claude Code") // both ticked
  await clickText(h, "  Next  ", 4)
  expect(frame(h)).toContain("2/8  Your channel")
  await clickText(h, "  Back  ", 4)
  expect(frame(h)).toContain("√   Claude Code")
  expect(frame(h)).toContain("√   Codex") // kept
  await clickText(h, "√   Claude Code", 2)
  await clickText(h, "√   Codex", 2)
  await clickText(h, "  Next  ", 4)
  expect(frame(h)).toContain("1/8  You") // none ticked: it stays, asking for one
  expect(frame(h)).toContain("Please answer this one.")
  expect(h.exits).toEqual([])
})
