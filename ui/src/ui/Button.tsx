// A button three rows tall, like the old window's: a thin light edge on top and a dark one underneath. Click it, or
// give it the keyboard (Tab) and press Enter or Space.

import { TextAttributes, type KeyEvent } from "@opentui/core"
import { useState } from "react"
import { useFocus, useTheme } from "../lib/focus"
import { cellLen } from "../lib/styled"
import { mix } from "../theme"

export interface ButtonProps {
  id: string
  label: string
  onPress: () => void
  variant?: "primary" | "default" | "error"
  disabled?: boolean
  /** Columns wide; by default the label and two spaces either side. */
  width?: number
  minWidth?: number
  marginRight?: number
  marginLeft?: number
  autoFocus?: boolean
  flexShrink?: number
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
  const base = variant === "primary" ? theme.primary : variant === "error" ? theme.bad : theme.button
  const fg = variant === "default" ? theme.buttonText : variant === "primary" ? theme.primaryText : "#ffffff"
  let bg = base
  if (disabled) bg = mix(base, theme.bg, 0.5)
  else if (down) bg = mix(base, "#000000", 0.2)
  else if (hover || focused) bg = mix(base, "#ffffff", variant === "default" ? 0.08 : 0.15)
  const textFg = disabled ? mix(fg, bg, 0.55) : fg
  const width = props.width ?? Math.max(cellLen(label) + 4, props.minWidth ?? 0)
  const attributes = TextAttributes.BOLD | (focused && !disabled ? TextAttributes.UNDERLINE : 0)
  return (
    <box
      ref={ref}
      flexDirection="column"
      width={width}
      height={3}
      flexShrink={props.flexShrink ?? 0}
      marginRight={props.marginRight}
      marginLeft={props.marginLeft}
      backgroundColor={bg}
      onMouseDown={(e) => {
        if (e.button !== 0 || disabled) return
        e.stopPropagation()
        focus()
        setDown(true)
      }}
      onMouseUp={(e) => {
        if (!down) return
        setDown(false)
        if (e.button === 0) press()
      }}
      onMouseOver={() => setHover(true)}
      onMouseOut={() => {
        setHover(false)
        setDown(false)
      }}
    >
      <text fg={mix(bg, "#ffffff", 0.25)} wrapMode="none">
        {"▔".repeat(width)}
      </text>
      <box height={1} justifyContent="center" flexDirection="row">
        <text fg={textFg} attributes={attributes} wrapMode="none">
          {label}
        </text>
      </box>
      <text fg={mix(bg, "#000000", 0.45)} wrapMode="none">
        {"▁".repeat(width)}
      </text>
    </box>
  )
}
