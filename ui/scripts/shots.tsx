// The README's screenshots, drawn: each screen on OpenTUI's test renderer with the real Python side on demo data
// (sample data from scripts/shots_preload.py), clicked through where a picture needs it, then written as an SVG of a
// terminal window. scripts/screenshots.py turns the SVGs into PNGs.
//
//   bun scripts/shots.tsx <out folder> [name ...]      every shot, or just these

import "./quiet"
import { TextAttributes, type CapturedFrame } from "@opentui/core"
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join, resolve } from "node:path"
import { ROOT } from "../src/bridge"
import { DASH, SETUP } from "../src/theme"
import { headless, type Headless } from "./headless"

type Size = [number, number]
const APP: Size = [180, 50]
const GUIDE: Size = [200, 56]

interface Shot {
  screen: "dashboard" | "setup"
  options: Record<string, unknown>
  size: Size
  folder: "docs/screenshots" | "dashboard/docs"
  then?: (h: Headless) => Promise<void>
}

const demo = (tab: string, drawer = false) => ({ demo: true, screenshots: true, only_demos: true, tab, drawer })

export const SHOTS: Record<string, Shot> = {
  "first-run": { screen: "setup", options: { start: "tools" }, size: [120, 34], folder: "docs/screenshots", then: waitForItems },
  "setup-format": { screen: "setup", options: { start: "onboard" }, size: [140, 46], folder: "docs/screenshots", then: toFormatStep },
  // Your accounts as a new channel sees it: the three recommended platforms, one handle typed in and two to sign up for
  "setup-accounts": { screen: "setup", options: { start: "onboard" }, size: [140, 46], folder: "docs/screenshots", then: toAccountsStep },
  "first-run-ready": { screen: "setup", options: { start: "done" }, size: [130, 32], folder: "docs/screenshots" },
  "app-overview": { screen: "dashboard", options: demo("overview"), size: APP, folder: "docs/screenshots" },
  "app-notifications": { screen: "dashboard", options: demo("overview", true), size: APP, folder: "docs/screenshots" },
  "app-videos": { screen: "dashboard", options: demo("videos"), size: APP, folder: "docs/screenshots" },
  "app-compare": { screen: "dashboard", options: demo("compare"), size: APP, folder: "docs/screenshots" },
  // wide enough for every upload button in one view
  "app-publish": { screen: "dashboard", options: demo("publish"), size: GUIDE, folder: "docs/screenshots", then: pickFirstVideo },
  // X left unconnected, so Accounts shows its Connect box
  "app-accounts": { screen: "dashboard", options: { ...demo("accounts"), unconnected: ["x"] }, size: APP, folder: "docs/screenshots" },
  // the profile button's menu: the demo's two channels (Delete beside the other one), New profile and this one's settings
  "app-profiles": { screen: "dashboard", options: demo("overview"), size: APP, folder: "docs/screenshots", then: openProfiles },
  // the Settings tab: the channel's answers, the FAQ with its first answer open, this computer, the profiles (with the
  // demo's deleted one), and the danger zone (tall enough for all of it)
  "app-settings": { screen: "dashboard", options: demo("settings"), size: [180, 82], folder: "docs/screenshots", then: openFirstAnswer },
  // the Stats tab: followers and likes added up across the platforms, each with its breakdown
  "app-stats": { screen: "dashboard", options: demo("totals"), size: APP, folder: "docs/screenshots" },
  "app-updates": { screen: "dashboard", options: demo("updates"), size: APP, folder: "docs/screenshots" },
  "app-notification-click": { screen: "dashboard", options: demo("overview", true), size: APP, folder: "docs/screenshots", then: clickAVideoNote },
  overview: { screen: "dashboard", options: demo("overview", true), size: GUIDE, folder: "dashboard/docs" },
  "notification-click": { screen: "dashboard", options: demo("overview", true), size: GUIDE, folder: "dashboard/docs", then: clickAVideoNote },
  updates: { screen: "dashboard", options: demo("updates"), size: GUIDE, folder: "dashboard/docs" },
}

/** Where some text is on screen: [column, row] of its first character, or null. */
export function find(h: Headless, text: string, from = 0): [number, number] | null {
  const rows = h.t.captureCharFrame().split("\n")
  for (let y = from; y < rows.length; y++) {
    const x = [...rows[y]!].join("").indexOf(text)
    if (x >= 0) return [[...rows[y]!.slice(0, x)].length, y]
  }
  return null
}

export async function clickText(h: Headless, text: string, dx = 1): Promise<void> {
  const at = find(h, text)
  if (!at) throw new Error(`"${text}" isn't on screen`)
  await h.t.mockMouse.click(at[0] + dx, at[1])
  await h.settle(500)
}

async function waitForItems(h: Headless) {
  for (let i = 0; i < 50 && !find(h, "Desktop shortcut"); i++) await h.settle(100)
}

async function toFormatStep(h: Headless) {
  await h.settle(800)
  for (let step = 0; step < 2; step++) await clickText(h, "  Next  ", 4)
  await h.settle(800)
}

async function toAccountsStep(h: Headless) {
  await h.settle(800)
  for (let step = 0; step < 4; step++) await clickText(h, "  Next  ", 4)
  await h.settle(800)
}

async function openProfiles(h: Headless) {
  await h.t.mockInput.pressKey("p")
  await h.settle(800)
}

async function openFirstAnswer(h: Headless) {
  await clickText(h, "Which model does my AI use", 3)
}

async function pickFirstVideo(h: Headless) {
  await clickText(h, "demo_", 2)
}

/** Click the newest notification about a video (taking off, or passing a views milestone) in the drawer. */
async function clickAVideoNote(h: Headless) {
  const notes = h.bridge.view<{ items: { title: [string, string][] }[] }>("notes")
  const title = notes?.items.map((n) => n.title.map((s) => s[0]).join("")).find((t) => /^(Taking off|A video passed)/.test(t))
  if (!title) throw new Error("no notification about a video")
  await clickText(h, title.slice(0, 20), 2) // highlights it
  await clickText(h, title.slice(0, 20), 2) // opens it
  await h.settle(1000)
}

// ---------------------------------------------------------------- the picture

const CW = 12 // a cell, in px (JetBrains Mono at 20px)
const CH = 24
const PAD = 8
const BAR = 40 // the window's title bar
const COLS = 8 // a cell is 8 sub-columns by 24 sub-rows: halves, quadrants and eighths all land on that grid
const SUBROWS = 24
const QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"
const BLOCKS: Record<string, [number, number, number, number][]> = {
  "█": [[0, 8, 0, 24]],
  "▀": [[0, 8, 0, 12]],
  "▐": [[4, 8, 0, 24]],
  "▔": [[0, 8, 0, 3]],
  "▕": [[7, 8, 0, 24]],
}
for (let k = 1; k <= 7; k++) BLOCKS[String.fromCodePoint(0x2580 + k)] = [[0, 8, 24 - 3 * k, 24]] // ▁▂▃▄▅▆▇
for (let k = 1; k <= 7; k++) BLOCKS[String.fromCodePoint(0x2590 - k)] = [[0, k, 0, 24]] // ▏▎▍▌▋▊▉
;[...QUADRANTS].forEach((ch, bits) => {
  if (!bits || BLOCKS[ch]) return
  BLOCKS[ch] = [0, 1, 2, 3].filter((p) => (bits >> p) & 1).map((p) => [(p % 2) * 4, (p % 2) * 4 + 4, Math.floor(p / 2) * 12, Math.floor(p / 2) * 12 + 12])
})

function hex(c: { toInts(): [number, number, number, number] }): string | null {
  const [r, g, b, a] = c.toInts()
  if (a === 0) return null
  return "#" + [r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

/** The frame as an SVG terminal window, block characters drawn as exact rectangles (a browser's fonts leave seams
 * between them, or have none at all), the way Windows Terminal draws them. */
export function svg(frame: CapturedFrame, background: string, title = "ReelForge"): string {
  const W = frame.cols * CW + 2 * PAD
  const H = BAR + frame.rows * CH + PAD
  // The kit's own font, inside the SVG (a browser won't always load a font from a file link).
  const font = (name: string) =>
    "data:font/ttf;base64," + readFileSync(join(ROOT, "assets", "fonts", name)).toString("base64")
  const out: string[] = [
    `<svg xmlns="http://www.w3.org/2000/svg" width="1600" viewBox="0 0 ${W} ${H}">`,
    `<style>@font-face{font-family:"JBM";src:url("${font("JetBrainsMono-Regular.ttf")}")}` +
      `@font-face{font-family:"JBM";font-weight:bold;src:url("${font("JetBrainsMono-Bold.ttf")}")}` +
      `text{font-family:"JBM",monospace;font-size:20px;white-space:pre}</style>`,
    `<rect width="${W}" height="${H}" rx="10" fill="#292929"/>`,
    ...[["#ff5f57", 22], ["#febc2e", 42], ["#28c840", 62]].map(([c, x]) => `<circle cx="${x}" cy="${BAR / 2}" r="6.5" fill="${c}"/>`),
    `<text x="${W / 2}" y="${BAR / 2 + 6}" text-anchor="middle" style="font-family:Helvetica,Arial,sans-serif;font-size:16px;font-weight:bold" fill="#d7d7d7">${esc(title)}</text>`,
    `<rect x="${PAD}" y="${BAR}" width="${frame.cols * CW}" height="${frame.rows * CH}" fill="${background}"/>`,
  ]
  const backs: string[] = []
  const rects: string[] = []
  const texts: string[] = []
  frame.lines.forEach((line, row) => {
    const y = BAR + row * CH
    let col = 0
    for (const span of line.spans) {
      const fg = hex(span.fg) ?? "#ffffff"
      const bg = hex(span.bg)
      const chars = [...span.text]
      const step = span.width / Math.max(chars.length, 1)
      if (bg && bg !== background)
        backs.push(`<rect x="${PAD + col * CW}" y="${y}" width="${span.width * CW + 0.6}" height="${CH + 0.6}" fill="${bg}" shape-rendering="crispEdges"/>`)
      let run = ""
      let runStart = col
      const flush = (end: number) => {
        if (run.trim()) {
          const bold = span.attributes & TextAttributes.BOLD ? ' font-weight="bold"' : ""
          const deco = [span.attributes & TextAttributes.UNDERLINE ? "underline" : "", span.attributes & TextAttributes.STRIKETHROUGH ? "line-through" : ""].filter(Boolean).join(" ")
          texts.push(
            `<text x="${PAD + runStart * CW}" y="${y + 18.5}" fill="${fg}"${bold}${deco ? ` text-decoration="${deco}"` : ""} textLength="${(end - runStart) * CW}" lengthAdjust="spacingAndGlyphs">${esc(run)}</text>`,
          )
        }
        run = ""
      }
      chars.forEach((ch, i) => {
        const at = col + i * step
        const parts = BLOCKS[ch]
        if (parts) {
          flush(at)
          for (const [c0, c1, r0, r1] of parts)
            rects.push(
              `<rect x="${(PAD + at * CW + (c0 * CW) / COLS).toFixed(2)}" y="${(y + (r0 * CH) / SUBROWS).toFixed(2)}" width="${(((c1 - c0) * CW) / COLS + 1).toFixed(2)}" height="${(((r1 - r0) * CH) / SUBROWS + 1).toFixed(2)}" fill="${fg}" shape-rendering="crispEdges"/>`,
            )
          runStart = at + step
          return
        }
        if (!run) runStart = at
        run += ch
      })
      flush(col + span.width)
      col += span.width
    }
  })
  return [...out, ...backs, ...rects, ...texts, "</svg>"].join("\n")
}

export async function take(name: string, outDir: string): Promise<string> {
  const shot = SHOTS[name]
  if (!shot) throw new Error(`no shot called ${name}`)
  process.env.REELFORGE_MASCOT_STILL = "1" // the mascot holds the moment each screen is about (ui/Mascot.tsx)
  const env = {
    REELFORGE_BRIDGE_PRELOAD: join(ROOT, "scripts", "shots_preload.py"),
    REELFORGE_QUADRANTS: "1", // the logo's, bell's and ×'s 2 x 2 blocks, as Windows Terminal draws them
    STUDIO_DRY_SYSTEM: "1",
    WT_SESSION: "screenshots", // ✓ rather than √, as in Windows Terminal
    REELFORGE_SHOT: name, // for the sample data that's only in one picture
  }
  const h = await headless(shot.screen, shot.options, shot.size[0], shot.size[1], env)
  try {
    await h.settle(2500)
    if (shot.then) await shot.then(h)
    await h.settle(600)
    const path = join(outDir, `${name}.svg`)
    writeFileSync(path, svg(h.t.captureSpans(), shot.screen === "setup" ? SETUP.bg : DASH.bg))
    return path
  } finally {
    await h.close()
  }
}

if (import.meta.main) {
  const [out = "shots", ...names] = process.argv.slice(2)
  const dir = resolve(out)
  mkdirSync(dir, { recursive: true })
  for (const name of names.length ? names : Object.keys(SHOTS)) {
    const path = await take(name, dir)
    console.log(`${name}\t${SHOTS[name]!.folder}\t${path}`)
  }
  process.exit(0)
}
