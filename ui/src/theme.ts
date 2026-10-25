// ReelForge's colours: the window's (green on near-black) and the first-run screens' (the logo's red on black).

export interface Theme {
  bg: string // the screen
  surface: string // the drawer, dialogs, inputs
  panel: string // the header bar
  border: string // boxes round charts, tables and lists
  text: string
  muted: string
  primary: string // the main button, the highlighted step
  primaryText: string // text on the main button
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
}

export const DASH: Theme = {
  bg: "#0a0c0f",
  surface: "#101318",
  panel: "#161a21",
  border: "#353941",
  text: "#d7dde6",
  muted: "#8b93a1",
  primary: "#3dff9a",
  primaryText: "#0a0c0f",
  button: "#1d2026",
  buttonText: "#d7dde6",
  good: "#3dff9a",
  warn: "#ffcc33",
  bad: "#ff4d5e",
  cursor: "#195438",
  cursorIdle: "#16352a",
  chip: "#1c222b",
  input: "#161a21",
  inputFocus: "#1d2129",
}

export const SETUP: Theme = {
  bg: "#000000",
  surface: "#0d0f12",
  panel: "#15181d",
  border: "#2a2e35",
  text: "#e8eaed",
  muted: "#8a94a3",
  primary: "#e8213a",
  primaryText: "#ffffff",
  button: "#17191c",
  buttonText: "#e8eaed",
  good: "#4ade80",
  warn: "#ffc83a",
  bad: "#ff5a4e",
  cursor: "#5c0d17",
  cursorIdle: "#39080e",
  chip: "#17191c",
  input: "#17191c",
  inputFocus: "#1f2226",
}

export const PICKED = "#ffcc33" // the frame round what a clicked notification is about
export const BELL = "#ffcc33"
export const MARK = "#ffcc33"
export const TYPICAL = "#ffb020"

/** Mix two #rrggbb colours: amount 0 is a, 1 is b. */
export function mix(a: string, b: string, amount: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16))
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16))
  return "#" + pa.map((v, i) => Math.round(v * (1 - amount) + pb[i]! * amount).toString(16).padStart(2, "0")).join("")
}
