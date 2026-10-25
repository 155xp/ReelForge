// Boxes: a panel with a rounded border, a dialog over everything, the pop-ups in the corner, and a little Markdown
// (release notes and onboarding's review).

import { TextAttributes, type Renderable, type ScrollBoxRenderable } from "@opentui/core"
import { forwardRef, useEffect, useState, useSyncExternalStore, type ReactNode } from "react"
import { FocusScope, useTheme } from "../lib/focus"
import type { Segs } from "../lib/styled"
import { mix } from "../theme"
import { Line } from "./Line"

export interface PanelProps {
  children?: ReactNode
  title?: string
  titleColor?: string
  borderColor?: string
  /** Heavy and yellow: what a clicked notification is about. */
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
  paddingX?: number
  bg?: string
  id?: string
  onRef?: (r: Renderable | null) => void
}

export function Panel(p: PanelProps) {
  const theme = useTheme()
  return (
    <box
      id={p.id}
      ref={p.onRef}
      border
      borderStyle={p.picked ? "heavy" : "rounded"}
      borderColor={p.picked ? "#ffcc33" : (p.borderColor ?? theme.border)}
      title={p.title ? ` ${p.title} ` : undefined}
      titleColor={p.titleColor}
      flexDirection="column"
      width={p.width}
      height={p.height}
      flexGrow={p.flexGrow}
      flexBasis={p.flexGrow ? 0 : undefined}
      flexShrink={p.flexShrink ?? 1}
      minWidth={p.minWidth}
      maxWidth={p.maxWidth}
      minHeight={p.minHeight}
      maxHeight={p.maxHeight}
      marginTop={p.marginTop}
      marginRight={p.marginRight}
      marginBottom={p.marginBottom}
      paddingLeft={p.paddingX ?? 1}
      paddingRight={p.paddingX ?? 1}
      backgroundColor={p.bg}
      overflow="hidden"
    >
      {p.children}
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
  return (
    <box
      position="absolute"
      left={0}
      top={0}
      width="100%"
      height="100%"
      zIndex={50}
      backgroundColor={theme.bg + "b3"}
      alignItems="center"
      justifyContent="center"
      onMouseDown={(e) => e.stopPropagation()}
    >
      <FocusScope name={name}>
        <box
          border
          borderStyle="heavy"
          borderColor={theme.primary}
          backgroundColor={theme.surface}
          flexDirection="column"
          width={width}
          maxWidth="95%"
          maxHeight="90%"
          paddingLeft={2}
          paddingRight={2}
          paddingTop={1}
          paddingBottom={1}
        >
          <text fg={theme.primary} attributes={TextAttributes.BOLD} marginBottom={1} flexShrink={0}>
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
}

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
    const toast: Toast = {
      id: this.next++,
      title: t.title ?? "",
      body: t.body ?? "",
      severity,
      until: Date.now() + (t.timeout ?? 5) * 1000,
    }
    this.list = [...this.list, toast].slice(-6)
    this.changed()
    setTimeout(() => this.drop(toast.id), (t.timeout ?? 5) * 1000)
  }
  drop(id: number) {
    this.list = this.list.filter((t) => t.id !== id)
    this.changed()
  }
  private changed() {
    for (const l of this.listeners) l()
  }
}

export const toasts = new Toasts()

/** The pop-ups in the bottom-right corner (each goes after its time, or when clicked). */
export function ToastStack() {
  const theme = useTheme()
  const list = useSyncExternalStore(toasts.subscribe, toasts.get)
  if (!list.length) return null
  return (
    <box position="absolute" right={1} bottom={1} width={52} zIndex={80} flexDirection="column" gap={1}>
      {list.map((t) => {
        const color = t.severity === "error" ? theme.bad : t.severity === "warning" ? theme.warn : theme.primary
        return (
          <box
            key={t.id}
            flexDirection="row"
            backgroundColor={mix(theme.surface, "#ffffff", 0.04)}
            flexShrink={0}
            onMouseDown={() => toasts.drop(t.id)}
          >
            <box width={1} backgroundColor={color} />
            <box flexDirection="column" flexGrow={1} paddingLeft={1} paddingRight={1}>
              {t.title ? (
                <text fg={color} attributes={TextAttributes.BOLD} wrapMode="word">
                  {t.title}
                </text>
              ) : null}
              <text fg={theme.text} wrapMode="word">
                {t.body}
              </text>
            </box>
          </box>
        )
      })}
    </box>
  )
}

// ---------------------------------------------------------------- markdown

/** Inline Markdown in a line: **bold**, `code`, _italic_ and [links](url) (shown as their text). */
export function inline(text: string, base: string, code: string): Segs {
  const out: Segs = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|(?<![\w])_[^_]+_(?![\w])|\[[^\]]+\]\([^)]+\))/g
  let last = 0
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push([text.slice(last, m.index), base])
    const t = m[0]
    if (t.startsWith("**")) out.push([t.slice(2, -2), `bold ${base}`])
    else if (t.startsWith("`")) out.push([t.slice(1, -1), code])
    else if (t.startsWith("_")) out.push([t.slice(1, -1), `italic ${base}`])
    else out.push([t.slice(1, t.indexOf("]")), `underline ${base}`])
    last = m.index! + t.length
  }
  if (last < text.length) out.push([text.slice(last), base])
  return out
}

/** Markdown, simply: headings, bullets, paragraphs, code blocks, and the inline styles above. */
export function Markdown({ text, heading }: { text: string; heading?: string }) {
  const theme = useTheme()
  const code = `${theme.primary}`
  const blocks: ReactNode[] = []
  const lines = (text ?? "").replace(/\r/g, "").split("\n")
  let para: string[] = []
  let fence: string[] | null = null
  const flush = () => {
    if (para.length) {
      blocks.push(<Wrapped key={blocks.length} segs={inline(para.join(" "), theme.text, code)} />)
      para = []
    }
  }
  for (const raw of lines) {
    if (fence) {
      if (raw.trim().startsWith("```")) {
        blocks.push(
          <box key={blocks.length} flexDirection="column" backgroundColor={theme.panel} paddingLeft={1} flexShrink={0}>
            {fence.map((l, i) => (
              <text key={i} fg={theme.muted} wrapMode="char">
                {l || " "}
              </text>
            ))}
          </box>,
        )
        fence = null
      } else fence.push(raw)
      continue
    }
    const line = raw.trimEnd()
    if (line.trim().startsWith("```")) {
      flush()
      fence = []
    } else if (/^#{1,6}\s/.test(line)) {
      flush()
      const level = line.match(/^#+/)![0].length
      blocks.push(
        <box key={blocks.length} marginTop={blocks.length ? 1 : 0} flexShrink={0}>
          <Line segs={inline(line.replace(/^#+\s*/, ""), `bold ${level <= 2 ? (heading ?? theme.primary) : theme.text}`, code)} />
        </box>,
      )
    } else if (/^\s*[-*]\s+/.test(line)) {
      flush()
      const indent = line.match(/^\s*/)![0].length
      blocks.push(
        <box key={blocks.length} flexDirection="row" paddingLeft={indent} flexShrink={0}>
          <text fg={theme.muted} width={2} flexShrink={0}>
            {"• "}
          </text>
          <Wrapped segs={inline(line.replace(/^\s*[-*]\s+/, ""), theme.text, code)} />
        </box>,
      )
    } else if (!line.trim()) {
      flush()
      if (blocks.length) blocks.push(<box key={blocks.length} height={1} flexShrink={0} />)
    } else para.push(line.trim())
  }
  flush()
  return (
    <box flexDirection="column" flexShrink={0}>
      {blocks}
    </box>
  )
}

/** Styled text that wraps at spaces to its width. */
export function Wrapped({ segs, flexGrow = 1 }: { segs: Segs; flexGrow?: number }) {
  return (
    <text wrapMode="word" flexGrow={flexGrow} flexShrink={1}>
      {segs.map((s, i) => {
        const words = (s[1] ?? "").split(/\s+/)
        const attributes =
          (words.includes("bold") ? TextAttributes.BOLD : 0) |
          (words.includes("italic") ? TextAttributes.ITALIC : 0) |
          (words.includes("underline") ? TextAttributes.UNDERLINE : 0)
        const fg = words.find((w) => w.startsWith("#"))
        return (
          <span key={i} fg={fg} attributes={attributes || undefined}>
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

const TRACK = "#14181e"
const THUMB = "#474a4f"

/** A scrolling area (the mouse wheel scrolls it), with scrollbars in the window's colours. */
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
  const bar = { trackOptions: { foregroundColor: THUMB, backgroundColor: TRACK } }
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
