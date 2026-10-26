// Surfaces: a panel (a step lighter than the window, no box drawn round it), a dialog over everything, the pop-ups in
// the corner (they slide in and fade out), and a little Markdown (release notes and the review in first-time setup).

import { TextAttributes, type Renderable, type ScrollBoxRenderable } from "@opentui/core"
import { forwardRef, useEffect, useState, useSyncExternalStore, type ReactNode } from "react"
import { FocusScope, useTheme } from "../lib/focus"
import { parseStyle, type Segs } from "../lib/styled"
import { mix, PICKED } from "../theme"
import { useProgress, useTween } from "./Motion"

export interface PanelProps {
  children?: ReactNode
  /** The panel's name, bold at its top left. */
  title?: string
  titleColor?: string
  /** Beside the title, quieter: a number or a hint. */
  sub?: ReactNode
  /** At the right end of the title row: a chip, a range picker. */
  right?: ReactNode
  /** Lit along its left edge for a few seconds: what a clicked notification is about. */
  picked?: boolean
  width?: number | "auto" | `${number}%`
  height?: number | "auto" | `${number}%`
  flexGrow?: number
  flexShrink?: number
  minWidth?: number
  maxWidth?: number
  minHeight?: number
  maxHeight?: number
  marginTop?: number
  marginRight?: number
  marginBottom?: number
  marginLeft?: number
  paddingX?: number
  paddingTop?: number
  paddingBottom?: number
  gap?: number
  bg?: string
  id?: string
  onRef?: (r: Renderable | null) => void
}

/** A panel: a block of the surface colour, its title on its first row. The left edge is always there (in the panel's
 * own colour), so lighting it for a clicked notification moves nothing. */
export function Panel(p: PanelProps) {
  const theme = useTheme()
  const bg = p.bg ?? theme.surface
  const glow = useTween(p.picked ? 1 : 0, { ms: p.picked ? 180 : 900, ease: "outQuad" })
  const pad = p.paddingX ?? 2
  return (
    <box
      id={p.id}
      ref={p.onRef}
      border={["left"]}
      borderStyle="heavy"
      borderColor={mix(bg, PICKED, glow)}
      flexDirection="column"
      width={p.width}
      height={p.height}
      flexGrow={p.flexGrow}
      flexBasis={p.flexGrow ? 0 : undefined}
      flexShrink={p.flexShrink ?? 1}
      minWidth={p.minWidth ?? 0}
      maxWidth={p.maxWidth}
      minHeight={p.minHeight}
      maxHeight={p.maxHeight}
      marginTop={p.marginTop}
      marginRight={p.marginRight}
      marginBottom={p.marginBottom}
      marginLeft={p.marginLeft}
      paddingLeft={Math.max(pad - 1, 0)}
      paddingRight={pad}
      paddingTop={p.paddingTop ?? 1}
      paddingBottom={p.paddingBottom ?? 0}
      gap={p.gap}
      backgroundColor={bg}
      overflow="hidden"
    >
      {p.title || p.right ? <PanelHead title={p.title} titleColor={p.titleColor} sub={p.sub} right={p.right} /> : null}
      {p.children}
    </box>
  )
}

/** A title row: the name, something quieter beside it, and what goes at the right end. */
export function PanelHead({ title, titleColor, sub, right }: { title?: string; titleColor?: string; sub?: ReactNode; right?: ReactNode }) {
  const theme = useTheme()
  return (
    <box flexDirection="row" height={1} flexShrink={0} marginBottom={1}>
      {title ? (
        <text fg={titleColor ?? theme.text} attributes={TextAttributes.BOLD} wrapMode="none" flexShrink={0}>
          {title}
        </text>
      ) : null}
      <box flexGrow={1} flexShrink={1} minWidth={0} paddingLeft={title ? 2 : 0} overflow="hidden">
        {sub}
      </box>
      {right ? (
        <box flexShrink={0} paddingLeft={1} flexDirection="row">
          {right}
        </box>
      ) : null}
    </box>
  )
}

/** A dialog in the middle of the window, over everything else (which dims). Tab stays inside it. */
export function Modal({
  name,
  title,
  width = 100,
  children,
}: {
  name: string
  title: string
  width?: number
  children: ReactNode
}) {
  const theme = useTheme()
  const shown = useProgress(name, { ms: 160 })
  return (
    <box
      position="absolute"
      left={0}
      top={0}
      width="100%"
      height="100%"
      zIndex={50}
      backgroundColor={theme.bg + Math.round(0x40 + 0x80 * shown).toString(16).padStart(2, "0")}
      alignItems="center"
      justifyContent="center"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <FocusScope name={name}>
        <box
          border
          borderStyle="rounded"
          borderColor={mix(theme.border, "#ffffff", 0.08)}
          backgroundColor={theme.surface}
          flexDirection="column"
          width={width}
          maxWidth="95%"
          maxHeight="90%"
          paddingLeft={3}
          paddingRight={3}
          paddingTop={1}
          paddingBottom={1}
        >
          <text fg={theme.text} attributes={TextAttributes.BOLD} marginBottom={1} flexShrink={0}>
            {title}
          </text>
          {children}
        </box>
      </FocusScope>
    </box>
  )
}

// ---------------------------------------------------------------- pop-ups

export interface Toast {
  id: number
  title: string
  body: string
  severity: "information" | "warning" | "error"
  until: number
  leaving: boolean
}

const FADE_MS = 280

class Toasts {
  list: Toast[] = []
  private next = 1
  private listeners = new Set<() => void>()
  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }
  get = () => this.list
  add(t: { title?: string; body?: string; severity?: string; timeout?: number }) {
    const severity = (["warning", "error"].includes(t.severity ?? "") ? t.severity : "information") as Toast["severity"]
    const ms = (t.timeout ?? 5) * 1000
    const toast: Toast = { id: this.next++, title: t.title ?? "", body: t.body ?? "", severity, until: Date.now() + ms, leaving: false }
    this.list = [...this.list, toast].slice(-6)
    this.changed()
    setTimeout(() => this.leave(toast.id), Math.max(ms - FADE_MS, 0))
  }
  /** Fade it out, then let it go. */
  leave(id: number) {
    if (!this.list.some((t) => t.id === id && !t.leaving)) return
    this.list = this.list.map((t) => (t.id === id ? { ...t, leaving: true } : t))
    this.changed()
    setTimeout(() => this.drop(id), FADE_MS)
  }
  drop(id: number) {
    this.list = this.list.filter((t) => t.id !== id)
    this.changed()
  }
  /** Let them all go at once (a test's next window starts without the last one's). */
  clear() {
    this.list = []
    this.changed()
  }
  private changed() {
    for (const l of this.listeners) l()
  }
}

export const toasts = new Toasts()

/** The pop-ups in the bottom-right corner (each goes after its time, or when clicked). */
export function ToastStack() {
  const list = useSyncExternalStore(toasts.subscribe, toasts.get)
  if (!list.length) return null
  return (
    <box position="absolute" right={2} bottom={2} width={54} zIndex={80} flexDirection="column" gap={1}>
      {list.map((t) => (
        <ToastCard key={t.id} toast={t} />
      ))}
    </box>
  )
}

function ToastCard({ toast: t }: { toast: Toast }) {
  const theme = useTheme()
  const shown = useTween(t.leaving ? 0 : 1, { from: 0, ms: t.leaving ? FADE_MS : 220, ease: "outQuad" })
  const color = t.severity === "error" ? theme.bad : t.severity === "warning" ? theme.warn : theme.focus
  const bg = mix(theme.bg, mix(theme.surface, "#ffffff", 0.05), shown)
  return (
    <box
      flexDirection="row"
      backgroundColor={bg}
      flexShrink={0}
      marginLeft={Math.round((1 - shown) * 6)}
      onMouseDown={() => toasts.leave(t.id)}
    >
      <box width={1} backgroundColor={mix(theme.bg, color, shown)} />
      <box flexDirection="column" flexGrow={1} paddingLeft={2} paddingRight={2} paddingTop={1} paddingBottom={1}>
        {t.title ? (
          <text fg={mix(theme.bg, color === theme.focus ? theme.text : color, shown)} attributes={TextAttributes.BOLD} wrapMode="word">
            {t.title}
          </text>
        ) : null}
        <text fg={mix(theme.bg, theme.muted, shown)} wrapMode="word">
          {t.body}
        </text>
      </box>
    </box>
  )
}

// ---------------------------------------------------------------- markdown

/** Inline Markdown in a line: **bold**, `code`, _italic_, [links](url) and <links> (shown as their text), nested
 * (a link inside bold stays bold), and \* style escapes. */
export function inline(text: string, base: string, code: string): Segs {
  const out: Segs = []
  const re = /(\*\*(.+?)\*\*|`([^`]+)`|(?<![\w\\])_([^_]+)_(?![\w])|\[([^\]]+)\]\([^)\s]+\)|<(https?:\/\/[^>\s]+)>)/g
  let last = 0
  const plain = (t: string) => {
    if (t) out.push([t.replace(/\\([\\`*_[\]()#|<>-])/g, "$1"), base])
  }
  for (const m of text.matchAll(re)) {
    plain(text.slice(last, m.index))
    if (m[2] !== undefined) out.push(...inline(m[2], `bold ${base}`, code))
    else if (m[3] !== undefined) out.push([m[3], code])
    else if (m[4] !== undefined) out.push(...inline(m[4], `italic ${base}`, code))
    else if (m[5] !== undefined) out.push(...inline(m[5], `underline ${base}`, code))
    else out.push([m[6]!, `underline ${base}`])
    last = m.index! + m[0].length
  }
  plain(text.slice(last))
  return out
}

export type MdBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "item"; depth: number; mark: string; text: string }
  | { kind: "para"; text: string }
  | { kind: "code"; lines: string[] }
  | { kind: "gap" }

/** Markdown as blocks: a list item's wrapped lines join it (so it wraps as one), a table's rows become items (its
 * first column in bold), and blank lines and rules become one gap, never at the start or the end. */
export function mdBlocks(text: string): MdBlock[] {
  const out: MdBlock[] = []
  const indents: number[] = [] // the open lists' indents, outermost first
  let fence: string[] | null = null
  let blank = true
  const gap = () => {
    if (out.length && out.at(-1)!.kind !== "gap") out.push({ kind: "gap" })
  }
  const cells = (row: string) =>
    row.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"))
  for (const raw of (text ?? "").replace(/\r/g, "").split("\n")) {
    if (fence) {
      if (raw.trim().startsWith("```")) {
        out.push({ kind: "code", lines: fence })
        fence = null
      } else fence.push(raw)
      continue
    }
    const line = raw.trimEnd()
    const last = out.at(-1)
    const bullet = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/)
    if (!line.trim()) {
      blank = true
      continue
    }
    if (line.trim().startsWith("```")) {
      if (blank) gap()
      fence = []
    } else if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      gap()
      indents.length = 0
    } else if (/^#{1,6}\s/.test(line)) {
      gap()
      out.push({ kind: "heading", level: line.match(/^#+/)![0].length, text: line.replace(/^#+\s*/, "").replace(/\s#+$/, "") })
      indents.length = 0
    } else if (/^\s*\|.*\|\s*$/.test(line)) {
      if (blank) gap()
      const row = cells(line)
      if (row.every((c) => /^:?-+:?$/.test(c))) {
        if (last?.kind === "item") out.pop() // the row above was the table's header
      } else {
        const [first = "", ...rest] = row.filter((c) => c)
        out.push({ kind: "item", depth: 0, mark: "•", text: rest.length ? `**${first.replace(/\*\*/g, "")}**: ${rest.join(" · ")}` : first })
      }
      indents.length = 0
    } else if (bullet) {
      if (blank && last?.kind !== "item") gap()
      const indent = bullet[1]!.length
      while (indents.length && indents.at(-1)! > indent) indents.pop()
      if (!indents.length || indents.at(-1)! < indent) indents.push(indent)
      const depth = indents.length - 1
      const mark = /^\d/.test(bullet[2]!) ? bullet[2]!.replace(")", ".") : depth ? "◦" : "•"
      out.push({ kind: "item", depth, mark, text: bullet[3]! })
    } else if (!blank && (last?.kind === "item" || last?.kind === "para")) {
      last.text += " " + line.trim() // a wrapped line goes on with its item or paragraph
    } else if (blank && last?.kind === "item" && /^\s{2,}/.test(line)) {
      last.text += " " + line.trim() // a later paragraph of the same item
    } else {
      gap()
      out.push({ kind: "para", text: line.trim() })
      indents.length = 0
    }
    blank = false
  }
  if (fence) out.push({ kind: "code", lines: fence })
  while (out.at(-1)?.kind === "gap") out.pop()
  return out
}

/** Markdown, simply: headings, bullets (each wrapping under its own text), paragraphs, code blocks, tables as a list,
 * and the inline styles above. `spaced` puts a blank line between top-level items (release notes: easier to scan). */
export function Markdown({ text, heading, spaced }: { text: string; heading?: string; spaced?: boolean }) {
  const theme = useTheme()
  const code = `${mix(theme.text, theme.warn, 0.35)} on ${theme.panel}`
  const all = mdBlocks(text)
  return (
    <box flexDirection="column" flexShrink={0} paddingRight={1}>
      {all.map((b, i) => {
        const prev = all[i - 1]
        if (spaced && b.kind === "item" && !b.depth && prev?.kind === "item")
          return [<box key={`${i}-gap`} height={1} flexShrink={0} />, item(b, i)]
        return b.kind === "item" ? item(b, i) : block(b, i)
      })}
    </box>
  )

  function item(b: Extract<MdBlock, { kind: "item" }>, i: number) {
    return (
      <box key={i} flexDirection="row" paddingLeft={b.depth * 2} flexShrink={0}>
        <text fg={theme.faint} width={b.mark.length + 1} flexShrink={0}>
          {b.mark + " "}
        </text>
        <Wrapped segs={inline(b.text, theme.text, code)} />
      </box>
    )
  }

  function block(b: Exclude<MdBlock, { kind: "item" }>, i: number) {
    if (b.kind === "gap") return <box key={i} height={1} flexShrink={0} />
    if (b.kind === "code")
      return (
        <box key={i} flexDirection="column" backgroundColor={theme.panel} paddingLeft={2} paddingTop={1} paddingBottom={1} flexShrink={0}>
          {b.lines.map((l, j) => (
            <text key={j} fg={theme.muted} wrapMode="char">
              {l || " "}
            </text>
          ))}
        </box>
      )
    // In a row, so a paragraph wraps to the width and never grows downwards (the empty gap the notes used to have).
    const style = b.kind === "heading" ? `bold ${b.level <= 2 ? (heading ?? theme.text) : theme.text}` : theme.text
    return (
      <box key={i} flexDirection="row" flexShrink={0}>
        <Wrapped segs={inline(b.text, style, code)} />
      </box>
    )
  }
}

/** Styled text that wraps at spaces to its width. */
export function Wrapped({ segs, flexGrow = 1 }: { segs: Segs; flexGrow?: number }) {
  return (
    <text wrapMode="word" flexGrow={flexGrow} flexShrink={1}>
      {segs.map((s, i) => {
        const st = parseStyle(s[1])
        return (
          <span key={i} fg={st.fg} bg={st.bg} attributes={st.attributes || undefined}>
            {s[0]}
          </span>
        )
      })}
    </text>
  )
}

/** Measure the width a box gets (for things drawn to fit it). */
export function useWidth(initial = 0): [number, (this: Renderable) => void] {
  const [width, setWidth] = useState(initial)
  return [
    width,
    function (this: Renderable) {
      setWidth(this.width)
    },
  ]
}

/** A tick every `ms` milliseconds while `on` (a spinner, a sliding progress bar). */
export function useTick(on: boolean, ms = 120): number {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!on) return
    const t = setInterval(() => setTick((n) => n + 1), ms)
    return () => clearInterval(t)
  }, [on, ms])
  return tick
}

/** A scrolling area (the mouse wheel scrolls it), with a thin scrollbar in the window's colours. */
export const Scroll = forwardRef<
  ScrollBoxRenderable,
  {
    children?: ReactNode
    flexGrow?: number
    flexShrink?: number
    height?: number
    maxHeight?: number
    scrollX?: boolean
    scrollY?: boolean
  }
>(function Scroll(p, ref) {
  const theme = useTheme()
  const bar = { trackOptions: { foregroundColor: mix(theme.bg, theme.muted, 0.35), backgroundColor: mix(theme.bg, theme.surface, 0.5) } }
  return (
    <scrollbox
      ref={ref}
      flexGrow={p.flexGrow}
      flexShrink={p.flexShrink ?? 1}
      height={p.height}
      maxHeight={p.maxHeight}
      scrollX={p.scrollX ?? false}
      scrollY={p.scrollY ?? true}
      focusable={false}
      verticalScrollbarOptions={bar}
      horizontalScrollbarOptions={bar}
    >
      {p.children}
    </scrollbox>
  )
})
