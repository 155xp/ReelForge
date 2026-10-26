// Which button, list, table or field has the keyboard. Tab and Shift+Tab move through them in reading order (top to
// bottom, left to right, as they're laid out right now); a dialog keeps Tab inside itself. The one with the keyboard
// gets the keys first (Enter presses a button, the arrows move through a list), then the app's own keys run.

import type { BoxRenderable, KeyEvent, Renderable } from "@opentui/core"
import { createContext, useContext, useEffect, useRef, useSyncExternalStore, type ReactNode } from "react"
import { DASH, type Theme } from "../theme"

export interface Focusable {
  id: string
  scope: string
  node: () => Renderable | null
  /** Handle a key while this has the keyboard; true if it did. */
  onKey?: (key: KeyEvent) => boolean
  /** A text field: it types the keys itself, so the app's one-key shortcuts don't run. */
  input?: boolean
  disabled?: () => boolean
}

export class FocusManager {
  focused: string | null = null
  private items = new Map<string, Focusable>()
  private listeners = new Set<() => void>()
  scopes: string[] = ["app"]

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private changed() {
    for (const l of this.listeners) l()
  }

  register(f: Focusable): () => void {
    this.items.set(f.id, f)
    return () => {
      if (this.items.get(f.id) === f) {
        this.items.delete(f.id)
        if (this.focused === f.id) this.blur()
      }
    }
  }

  has(id: string): boolean {
    return this.items.has(id)
  }

  focus(id: string | null) {
    if (id === this.focused) return
    this.focused = id
    this.changed()
  }

  blur() {
    this.focus(null)
  }

  get current(): Focusable | undefined {
    return this.focused ? this.items.get(this.focused) : undefined
  }

  /** Whether a text field has the keyboard (the app's one-key shortcuts wait). */
  get typing(): boolean {
    return Boolean(this.current?.input)
  }

  pushScope(name: string) {
    this.scopes.push(name)
    this.changed()
  }

  popScope(name: string) {
    const i = this.scopes.lastIndexOf(name)
    if (i > 0) this.scopes.splice(i, 1)
    this.changed()
  }

  get scope(): string {
    return this.scopes[this.scopes.length - 1]!
  }

  /** Everything Tab reaches in the top scope, in reading order. */
  order(): Focusable[] {
    const out: [Focusable, number, number][] = []
    for (const f of this.items.values()) {
      if (f.scope !== this.scope || f.disabled?.()) continue
      const n = f.node()
      if (!n || !isShown(n) || n.width <= 0 || n.height <= 0) continue
      out.push([f, n.y, n.x])
    }
    return out.sort((a, b) => a[1] - b[1] || a[2] - b[2]).map((x) => x[0])
  }

  cycle(dir: 1 | -1) {
    const items = this.order()
    if (!items.length) return
    const i = items.findIndex((f) => f.id === this.focused)
    const next = i < 0 ? (dir > 0 ? 0 : items.length - 1) : (i + dir + items.length) % items.length
    this.focus(items[next]!.id)
  }

  /** Give a key to whatever has the keyboard: Tab moves on, the rest go to it. True if it was used. */
  handleKey(key: KeyEvent): boolean {
    if (key.name === "tab") {
      this.cycle(key.shift ? -1 : 1)
      key.preventDefault()
      return true
    }
    const f = this.current
    if (f && f.scope !== this.scope) return false
    return Boolean(f?.onKey?.(key))
  }
}

function isShown(n: Renderable): boolean {
  for (let p: Renderable | null = n; p; p = p.parent as Renderable | null) if (!p.visible) return false
  return true
}

export const FocusContext = createContext<FocusManager>(new FocusManager())
export const ScopeContext = createContext<string>("app")
export const ThemeContext = createContext<Theme>(DASH)

export function useTheme(): Theme {
  return useContext(ThemeContext)
}

export function useFocusManager(): FocusManager {
  return useContext(FocusContext)
}

/** Take part in Tab order as `id`: returns whether this has the keyboard, and a function that gives it the keyboard.
 * Put `ref` on the renderable that marks where it is. */
export function useFocus(
  id: string,
  opts: { onKey?: (key: KeyEvent) => boolean; input?: boolean; disabled?: boolean; autoFocus?: boolean } = {},
) {
  const fm = useFocusManager()
  const scope = useContext(ScopeContext)
  const ref = useRef<BoxRenderable | null>(null)
  const latest = useRef(opts)
  latest.current = opts
  useEffect(
    () =>
      fm.register({
        id,
        scope,
        node: () => ref.current,
        onKey: (key) => latest.current.onKey?.(key) ?? false,
        input: opts.input,
        disabled: () => Boolean(latest.current.disabled),
      }),
    [fm, id, scope, opts.input],
  )
  useEffect(() => {
    if (opts.autoFocus) fm.focus(id)
  }, [fm, id, opts.autoFocus])
  const focused = useSyncExternalStore(fm.subscribe, () => fm.focused === id && fm.scope === scope)
  return { ref, focused, focus: () => fm.focus(id) }
}

/** A dialog's own Tab order: while it's open, Tab stays inside it. */
export function FocusScope({ name, children }: { name: string; children: ReactNode }) {
  const fm = useFocusManager()
  useEffect(() => {
    const before = fm.focused
    fm.pushScope(name)
    return () => {
      fm.popScope(name)
      if (before && fm.has(before)) fm.focus(before)
    }
  }, [fm, name])
  return <ScopeContext.Provider value={name}>{children}</ScopeContext.Provider>
}
