// Styled text as the Python side sends it (dashboard/view.py): segments of [text, style] or [text, style, action].
// A style is a few words: bold, dim, italic, underline, strike, a text colour, and "on" a background colour.

import { TextAttributes } from "@opentui/core"
import type { ReactNode } from "react"

export type Action = [string, ...unknown[]]
export type Seg = [string, string?, Action?]
export type Segs = Seg[]
export type Parts = [Segs, number][]

export interface Style {
  fg?: string
  bg?: string
  attributes: number
}

const cache = new Map<string, Style>()

export function parseStyle(style: string | undefined): Style {
  const key = style ?? ""
  const hit = cache.get(key)
  if (hit) return hit
  const out: Style = { attributes: 0 }
  const words = key.split(/\s+/).filter(Boolean)
  for (let i = 0; i < words.length; i++) {
    const w = words[i]!
    if (w === "on") {
      out.bg = words[++i]
    } else if (w === "bold") out.attributes |= TextAttributes.BOLD
    else if (w === "dim") out.attributes |= TextAttributes.DIM
    else if (w === "italic") out.attributes |= TextAttributes.ITALIC
    else if (w === "underline") out.attributes |= TextAttributes.UNDERLINE
    else if (w === "strike") out.attributes |= TextAttributes.STRIKETHROUGH
    else if (w.startsWith("#")) out.fg = w
  }
  cache.set(key, out)
  return out
}

/** Terminal columns a string takes: wide characters (CJK, most emoji) take two. */
export function cellLen(text: string): number {
  let n = 0
  for (const ch of text) n += charWidth(ch)
  return n
}

export function charWidth(ch: string): number {
  const c = ch.codePointAt(0) ?? 0
  if (c === 0 || (c >= 0x300 && c <= 0x36f) || c === 0x200d || (c >= 0xfe00 && c <= 0xfe0f)) return 0
  if (
    (c >= 0x1100 && c <= 0x115f) ||
    (c >= 0x2e80 && c <= 0xa4cf && c !== 0x303f) ||
    (c >= 0xac00 && c <= 0xd7a3) ||
    (c >= 0xf900 && c <= 0xfaff) ||
    (c >= 0xfe30 && c <= 0xfe4f) ||
    (c >= 0xff00 && c <= 0xff60) ||
    (c >= 0xffe0 && c <= 0xffe6) ||
    (c >= 0x1f300 && c <= 0x1faff) ||
    (c >= 0x20000 && c <= 0x3fffd)
  )
    return 2
  return 1
}

export function plain(segs: Segs | undefined): string {
  return (segs ?? []).map((s) => s[0]).join("")
}

export function segsLen(segs: Segs | undefined): number {
  return cellLen(plain(segs))
}

/** Segments split at their newlines: one list of segments per line. */
export function lines(segs: Segs | undefined): Segs[] {
  const out: Segs[] = [[]]
  for (const seg of segs ?? []) {
    const pieces = seg[0].split("\n")
    pieces.forEach((piece, i) => {
      if (i) out.push([])
      if (piece) out[out.length - 1]!.push([piece, seg[1], seg[2]])
    })
  }
  return out
}

/** The first `width` columns of the segments (nothing is wrapped). */
export function truncate(segs: Segs, width: number): Segs {
  const out: Segs = []
  let room = Math.max(width, 0)
  for (const seg of segs) {
    if (room <= 0) break
    const n = cellLen(seg[0])
    if (n <= room) {
      out.push(seg)
      room -= n
      continue
    }
    let text = ""
    for (const ch of seg[0]) {
      const w = charWidth(ch)
      if (w > room) break
      text += ch
      room -= w
    }
    out.push([text, seg[1], seg[2]])
    break
  }
  return out
}

/** Pad the segments with spaces to `width` columns. */
export function pad(segs: Segs, width: number, right = false): Segs {
  const n = segsLen(segs)
  if (n >= width) return truncate(segs, width)
  const space: Seg = [" ".repeat(width - n), ""]
  return right ? [space, ...segs] : [...segs, space]
}

/** The segment (and its action) at column x, if any. */
export function segAt(segs: Segs, x: number): Seg | undefined {
  let col = 0
  for (const seg of segs) {
    const n = cellLen(seg[0])
    if (x >= col && x < col + n) return seg
    col += n
  }
  return undefined
}

export function seg(text: string, style = "", action?: Action): Seg {
  return action ? [text, style, action] : [text, style]
}

/** Segments as spans inside a <text>. */
export function spans(segs: Segs | undefined, base?: string): ReactNode[] {
  return (segs ?? []).map((s, i) => {
    const st = parseStyle(base && !s[1] ? base : s[1])
    return (
      <span key={i} fg={st.fg} bg={st.bg} attributes={st.attributes || undefined}>
        {s[0]}
      </span>
    )
  })
}
