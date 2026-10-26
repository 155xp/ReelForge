// Fields for forms: a text field, a longer text box, one-of-several, several-of-several, and a yes/no switch. Each
// takes part in Tab order, shows when it has the keyboard, and turns red with a problem.

import { TextAttributes, type InputRenderable, type KeyEvent, type TextareaRenderable } from "@opentui/core"
import { useEffect, useRef, useState } from "react"
import { useFocus, useTheme } from "../lib/focus"
import { mix } from "../theme"

interface FieldBase {
  id: string
  bad?: boolean
  width?: number | `${number}%`
  flexGrow?: number
  autoFocus?: boolean
}

/** A one-line text field. `value` sets what it shows (when it changes from outside); onChange hears typing. */
export function TextField(
  p: FieldBase & {
    value: string
    placeholder?: string
    maxLength?: number
    onChange?: (value: string) => void
    onSubmit?: (value: string) => void
  },
) {
  const theme = useTheme()
  const input = useRef<InputRenderable | null>(null)
  const { ref, focused, focus } = useFocus(p.id, { input: true, autoFocus: p.autoFocus })
  useEffect(() => {
    if (input.current && input.current.value !== p.value) input.current.value = p.value
  }, [p.value])
  const bg = p.bad && theme.buttons === "row" ? mix(theme.input, theme.bad, 0.07) : focused ? theme.inputFocus : theme.input
  return (
    <box
      ref={ref}
      height={3}
      width={p.width}
      flexGrow={p.flexGrow}
      flexShrink={0}
      flexDirection="row"
      backgroundColor={bg}
      border={theme.buttons === "tall" && p.bad ? true : ["left"]}
      borderStyle="heavy"
      borderColor={p.bad ? theme.bad : focused ? theme.focus : bg}
      paddingLeft={1}
      paddingRight={1}
      alignItems="center"
      onMouseDown={() => focus()}
    >
      <input
        ref={input}
        flexGrow={1}
        value={p.value}
        placeholder={p.placeholder}
        maxLength={p.maxLength}
        focused={focused}
        backgroundColor={bg}
        focusedBackgroundColor={bg}
        textColor={theme.text}
        focusedTextColor={theme.text}
        placeholderColor={mix(theme.muted, bg, 0.35)}
        cursorColor={theme.text}
        onInput={(v: string) => p.onChange?.(v)}
        onSubmit={() => p.onSubmit?.(input.current?.value ?? "")}
      />
    </box>
  )
}

/** Several lines of text (one answer a line, or a sentence or two). */
export function TextBox(
  p: FieldBase & { value: string; placeholder?: string; onChange?: (value: string) => void; height?: number },
) {
  const theme = useTheme()
  const area = useRef<TextareaRenderable | null>(null)
  const { ref, focused, focus } = useFocus(p.id, { input: true, autoFocus: p.autoFocus })
  useEffect(() => {
    if (area.current && area.current.plainText !== p.value) area.current.setText(p.value)
  }, [p.value])
  const bg = p.bad && theme.buttons === "row" ? mix(theme.input, theme.bad, 0.07) : focused ? theme.inputFocus : theme.input
  return (
    <box
      ref={ref}
      height={p.height ?? 5}
      flexShrink={0}
      backgroundColor={bg}
      border={theme.buttons === "tall" && p.bad ? true : ["left"]}
      borderStyle="heavy"
      borderColor={p.bad ? theme.bad : focused ? theme.focus : bg}
      paddingLeft={1}
      paddingRight={1}
      paddingTop={1}
      onMouseDown={() => focus()}
    >
      <textarea
        ref={area}
        flexGrow={1}
        initialValue={p.value}
        placeholder={p.placeholder}
        focused={focused}
        wrapMode="word"
        backgroundColor={bg}
        focusedBackgroundColor={bg}
        textColor={theme.text}
        focusedTextColor={theme.text}
        placeholderColor={mix(theme.muted, bg, 0.35)}
        cursorColor={theme.text}
        onContentChange={() => p.onChange?.(area.current?.plainText ?? "")}
      />
    </box>
  )
}

function keyIs(key: KeyEvent, ...names: string[]) {
  return names.includes(key.name)
}

/** One of several: ● marks the one picked; the arrows move, Enter or Space picks. */
export function RadioSet(
  p: FieldBase & { options: [string, string][]; value: string | null; onChange: (value: string) => void },
) {
  const theme = useTheme()
  const [cursor, setCursor] = useState(Math.max(p.options.findIndex(([v]) => v === p.value), 0))
  const { ref, focused, focus } = useFocus(p.id, {
    autoFocus: p.autoFocus,
    onKey: (key) => {
      const n = p.options.length
      if (keyIs(key, "up", "left")) setCursor((cursor - 1 + n) % n)
      else if (keyIs(key, "down", "right")) setCursor((cursor + 1) % n)
      else if (keyIs(key, "return", "enter", "space")) p.onChange(p.options[cursor]![0])
      else return false
      return true
    },
  })
  return (
    <box
      ref={ref}
      flexDirection="column"
      flexShrink={0}
      border
      borderStyle="single"
      borderColor={p.bad ? theme.bad : focused ? theme.focus : theme.input}
      backgroundColor={theme.input}
      paddingLeft={1}
      paddingRight={1}
      onMouseDown={() => focus()}
    >
      {p.options.map(([value, label], i) => {
        const on = value === p.value
        const here = focused && i === cursor
        return (
          <box
            key={value}
            flexDirection="row"
            height={1}
            onMouseDown={() => {
              setCursor(i)
              p.onChange(value)
            }}
          >
            <text fg={on ? theme.good : mix(theme.muted, theme.input, 0.5)} width={2} flexShrink={0}>
              {on ? "● " : "○ "}
            </text>
            <text
              fg={on ? "#ffffff" : theme.text}
              bg={on ? theme.primary : here ? theme.cursor : undefined}
              attributes={on || here ? TextAttributes.BOLD : undefined}
              wrapMode="none"
            >
              {` ${label} `}
            </text>
          </box>
        )
      })}
    </box>
  )
}

/** Several of several: ✓ marks the ones picked; the arrows move, Space or Enter ticks. */
export function CheckList(
  p: FieldBase & { options: [string, string][]; value: string[]; onChange: (value: string[]) => void; check?: string },
) {
  const theme = useTheme()
  const [cursor, setCursor] = useState(0)
  const toggle = (v: string) =>
    p.onChange(p.options.map(([o]) => o).filter((o) => (o === v ? !p.value.includes(v) : p.value.includes(o))))
  const { ref, focused, focus } = useFocus(p.id, {
    autoFocus: p.autoFocus,
    onKey: (key) => {
      const n = p.options.length
      if (keyIs(key, "up")) setCursor((cursor - 1 + n) % n)
      else if (keyIs(key, "down")) setCursor((cursor + 1) % n)
      else if (keyIs(key, "return", "enter", "space")) toggle(p.options[cursor]![0])
      else return false
      return true
    },
  })
  return (
    <box
      ref={ref}
      flexDirection="column"
      flexShrink={0}
      border
      borderStyle="single"
      borderColor={p.bad ? theme.bad : focused ? theme.focus : theme.input}
      backgroundColor={theme.input}
      paddingLeft={1}
      paddingRight={1}
      onMouseDown={() => focus()}
    >
      {p.options.map(([value, label], i) => {
        const on = p.value.includes(value)
        const here = focused && i === cursor
        return (
          <box
            key={value}
            flexDirection="row"
            height={1}
            onMouseDown={() => {
              setCursor(i)
              toggle(value)
            }}
          >
            <text fg={on ? theme.good : mix(theme.muted, theme.input, 0.4)} width={3} flexShrink={0} attributes={TextAttributes.BOLD}>
              {on ? `${p.check ?? "✓"} ` : "○ "}
            </text>
            <text fg={on ? "#ffffff" : theme.text} bg={here ? theme.cursor : undefined} wrapMode="none">
              {` ${label} `}
            </text>
          </box>
        )
      })}
    </box>
  )
}

/** Yes or no: Space or Enter (or a click) flips it. */
export function Switch(p: FieldBase & { value: boolean; onChange: (value: boolean) => void }) {
  const theme = useTheme()
  const { ref, focused, focus } = useFocus(p.id, {
    autoFocus: p.autoFocus,
    onKey: (key) => {
      if (!keyIs(key, "return", "enter", "space")) return false
      p.onChange(!p.value)
      return true
    },
  })
  const track = p.value ? theme.good : mix(theme.muted, theme.input, 0.6)
  return (
    <box
      ref={ref}
      flexDirection="row"
      height={1}
      flexShrink={0}
      gap={1}
      onMouseDown={() => {
        focus()
        p.onChange(!p.value)
      }}
    >
      <text bg={focused ? mix(theme.input, "#ffffff", 0.08) : theme.input} wrapMode="none">
        <span fg={p.value ? theme.input : track}>{p.value ? "━━━" : "▐█▌"}</span>
        <span fg={p.value ? track : theme.input}>{p.value ? "▐█▌" : "━━━"}</span>
      </text>
      <text fg={p.value ? theme.good : theme.muted} attributes={focused ? TextAttributes.BOLD | TextAttributes.UNDERLINE : TextAttributes.BOLD}>
        {p.value ? "Yes" : "No"}
      </text>
    </box>
  )
}
