// ReelForge's colours. The window is calm and dark: near-black, panels a step lighter instead of boxes, white and greys
// for everything that's the app's own, so the only colours are the platforms' (TikTok cyan, YouTube red, Instagram
// purple, X white), green and red for up and down, amber for the marks where a video went up, and the forge's red to
// ember gradient on the few buttons that do the main thing. First-time setup shares these colours, with the logo's red.

export interface Theme {
  bg: string // the screen
  surface: string // panels and tiles, the drawer, dialogs
  panel: string // code blocks and other insets
  raised: string // what's under the mouse or picked: a chip, a highlighted row
  border: string // hairlines, and the few borders left
  text: string
  muted: string
  faint: string // labels, axes, times
  primary: string // the main button (one colour, where a gradient can't go)
  primaryText: string // text on the main button
  accent: [string, string] // the main button's gradient
  button: string // other buttons
  buttonText: string
  good: string
  warn: string
  bad: string
  cursor: string // a list's or table's highlighted row while it has the keyboard
  cursorIdle: string // the same row while something else has it
  chip: string
  input: string // a text field's background
  inputFocus: string
  focus: string // the edge that says what has the keyboard
}

/** The forge: the logo's red into ember. */
export const EMBER: [string, string] = ["#e8213a", "#ff7a33"]

export const DASH: Theme = {
  bg: "#0b0d10",
  surface: "#12151a",
  panel: "#171a20",
  raised: "#1e232b",
  border: "#252a33",
  text: "#e8eaed",
  muted: "#8c939e",
  faint: "#5d6470",
  primary: "#ef3f3a",
  primaryText: "#ffffff",
  accent: EMBER,
  button: "#1e232b",
  buttonText: "#e8eaed",
  good: "#3ddc97",
  warn: "#f5c451",
  bad: "#ff5c6c",
  cursor: "#262c36",
  cursorIdle: "#1b1f26",
  chip: "#1e232b",
  input: "#181b21",
  inputFocus: "#1d2128",
  focus: "#e8eaed",
}

/** First-time setup: the window's own calm dark, the logo's red on its main buttons and the step you're on. */
export const SETUP: Theme = {
  ...DASH,
  primary: "#e8213a",
}

export const PICKED = "#f5c451" // the edge round what a clicked notification is about
export const BELL = "#e8eaed"
export const MARK = "#f5c451"
export const TYPICAL = "#ffb020"

/** The platforms' own colours (the Python side has its own idea of YouTube's red: see RESTYLE). */
export const PLATFORM: Record<string, string> = {
  tiktok: "#25f4ee",
  youtube: "#e8213a",
  instagram: "#b46cff",
  x: "#e7e9ea",
}

/** The Python side's colours (dashboard/view.py, its platforms, notifications and chips), as this window draws them.
 * Its views carry colours inside styled text; every message from it passes through restyle(), so the contract stays as
 * it is and the window keeps one palette. */
const RESTYLE: Record<string, string> = {
  "#ff4040": PLATFORM.youtube!, // YouTube
  "#3dff9a": DASH.good,
  "#ff4d5e": DASH.bad,
  "#8b93a1": DASH.muted,
  "#c9d1d9": DASH.text,
  "#1c222b": DASH.raised, // a chip
  "#1f5c45": "#2d333d", // the chosen chip (24H of 24H 48H 7D 30D)
  "#4a515c": DASH.faint,
  "#5c6370": DASH.faint,
  "#3a4049": "#3a3f48",
  "#0a0c0f": DASH.bg,
  "#ffcc33": MARK,
  "#7aa2f7": "#8ab4ff", // an update
  "#ff8a3d": "#ff8a3d", // taking off
}

const HEX = /#[0-9a-fA-F]{6}\b/g

/** A colour (or a style with colours in it) in this window's palette. */
export function tone(text: string): string {
  return text.indexOf("#") < 0 ? text : text.replace(HEX, (h) => RESTYLE[h.toLowerCase()] ?? h)
}

/** JSON.parse's reviver for messages from the Python side: every colour in them in this window's palette. */
export function restyle(_key: string, value: unknown): unknown {
  return typeof value === "string" && value.length <= 64 && value.indexOf("#") >= 0 ? tone(value) : value
}

/** Mix two #rrggbb colours: amount 0 is a, 1 is b. */
export function mix(a: string, b: string, amount: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  const t = Math.min(Math.max(amount, 0), 1)
  return "#" + pa.map((v, i) => Math.round(v * (1 - t) + pb[i]! * t).toString(16).padStart(2, "0")).join("")
}

/** A colour along a list of stops, t from 0 to 1. */
export function along(stops: readonly string[], t: number): string {
  if (stops.length === 1) return stops[0]!
  const x = Math.min(Math.max(t, 0), 1) * (stops.length - 1)
  const i = Math.min(Math.floor(x), stops.length - 2)
  return mix(stops[i]!, stops[i + 1]!, x - i)
}
