// A button: a one-row pill, a raised block with half-block ends, the main one in the forge's red to ember gradient.
// Click it, or give it the keyboard (Tab) and press Enter or Space.

import { TextAttributes, type KeyEvent } from "@opentui/core"
import { useState } from "react"
import { useFocus, useTheme } from "../lib/focus"
import { cellLen } from "../lib/styled"
import { along, mix } from "../theme"

export interface ButtonProps {
  id: string
  label: string
  onPress: () => void
  variant?: "primary" | "default" | "error" | "ghost"
  disabled?: boolean
  /** Columns wide; by default the label and two spaces either side. */
  width?: number
  minWidth?: number
  marginRight?: number
  marginLeft?: number
  autoFocus?: boolean
  flexShrink?: number
  /** A colour for the pill's left end: the platform a button is for. */
  accent?: string
}

export function Button(props: ButtonProps) {
  const theme = useTheme()
  const { id, label, onPress, variant = "default", disabled = false } = props
  const [hover, setHover] = useState(false)
  const [down, setDown] = useState(false)
  const press = () => {
    if (!disabled) onPress()
  }
  const { ref, focused, focus } = useFocus(id, {
    disabled,
    autoFocus: props.autoFocus,
    onKey: (key: KeyEvent) => {
      if (key.name === "return" || key.name === "enter" || key.name === "space") {
        press()
        key.preventDefault()
        return true
      }
      return false
    },
  })
  const width = props.width ?? Math.max(cellLen(label) + 4, props.minWidth ?? 0)
  // the fill: a gradient for the main button, one colour for the others
  const stops: string[] =
    variant === "primary" ? [...theme.accent] : variant === "error" ? [theme.bad, theme.bad] : variant === "ghost" ? [theme.bg, theme.bg] : [theme.button, theme.button]
  const lift = (c: string) => {
    if (disabled) return mix(c, theme.bg, 0.55)
    if (down) return mix(c, "#000000", 0.2)
    if (hover || focused) return mix(c, "#ffffff", variant === "default" || variant === "ghost" ? 0.08 : 0.14)
    return c
  }
  const fill = stops.map(lift)
  const fg = variant === "default" ? theme.buttonText : variant === "ghost" ? (hover || focused ? theme.text : theme.muted) : variant === "primary" ? theme.primaryText : "#ffffff"
  const textFg = disabled ? mix(fg, fill[0]!, 0.55) : fg
  const attributes = TextAttributes.BOLD | (focused && !disabled ? TextAttributes.UNDERLINE : 0)
  const events = {
    onMouseDown: (e: { button: number; stopPropagation: () => void }) => {
      if (e.button !== 0 || disabled) return
      e.stopPropagation()
      focus()
      setDown(true)
    },
    onMouseUp: (e: { button: number }) => {
      if (!down) return
      setDown(false)
      if (e.button === 0) press()
    },
    onMouseOver: () => setHover(true),
    onMouseOut: () => {
      setHover(false)
      setDown(false)
    },
  }
  // One row: the half-block ends in the fill's colour round the label, centred in the width.
  const inner = Math.max(width - 2, cellLen(label))
  const before = Math.floor((inner - cellLen(label)) / 2)
  const text = " ".repeat(before) + label + " ".repeat(inner - before - cellLen(label))
  const chars = [...text]
  const ghost = variant === "ghost"
  return (
    <box ref={ref} height={1} width={inner + 2} flexShrink={props.flexShrink ?? 0} marginRight={props.marginRight} marginLeft={props.marginLeft} {...events}>
      <text wrapMode="none">
        {props.accent && !ghost ? (
          <span fg={disabled ? mix(props.accent, theme.bg, 0.55) : props.accent} bg={fill[0]}>
            ▎
          </span>
        ) : (
          <span fg={ghost ? undefined : fill[0]}>{ghost ? " " : "▐"}</span>
        )}
        {chars.map((ch, i) => (
          <span key={i} fg={textFg} bg={ghost && !(hover || focused) ? undefined : along(fill, chars.length > 1 ? i / (chars.length - 1) : 0)} attributes={attributes}>
            {ch}
          </span>
        ))}
        <span fg={ghost ? undefined : fill[fill.length - 1]}>{ghost ? " " : "▌"}</span>
      </text>
    </box>
  )
}
