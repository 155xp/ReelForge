// The onboarding interview, step by step, then a review: Create my studio writes everything. Mouse and keyboard both
// work: Tab moves between fields, Enter presses a button, Esc offers to leave. The questions, their defaults and when
// each shows come from studio/questions.py, through studio/setup_service.py.

import { TextAttributes, type KeyEvent, type ScrollBoxRenderable } from "@opentui/core"
import { useKeyboard } from "@opentui/react"
import { useEffect, useRef, useState } from "react"
import { useFocusManager, useTheme } from "../lib/focus"
import { mix } from "../theme"
import { Button } from "../ui/Button"
import { CheckList, RadioSet, Switch, TextBox, TextField } from "../ui/Fields"
import { Markdown, Modal, Scroll } from "../ui/Panels"
import type { SetupProps } from "./App"
import { Frame } from "./Frame"

interface Field {
  key: string
  prompt: string
  required: boolean
  help: string
  kind: "text" | "number" | "long" | "choice" | "multi" | "yesno"
  options: [string, string][]
  value: unknown
  placeholder: string
  visible: boolean
}

interface Step {
  index: number
  key: string
  title: string
  blurb: string
  fields?: Field[]
  review?: string
}

export function Onboard({ bridge, init, quit, onDone }: SetupProps & { onDone: () => void }) {
  const theme = useTheme()
  const focus = useFocusManager()
  const [steps, setSteps] = useState<[string, string][]>([])
  const [step, setStep] = useState<Step | null>(null)
  const [raws, setRaws] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [status, setStatus] = useState("")
  const [detail, setDetail] = useState("")
  const [leaving, setLeaving] = useState(false)
  const scroll = useRef<ScrollBoxRenderable | null>(null)

  const show = (s: Step) => {
    setStep(s)
    setRaws(Object.fromEntries((s.fields ?? []).map((f) => [f.key, f.value])))
    setErrors({})
    setStatus("")
    setDetail("")
    scroll.current?.scrollTo(0)
    focus.blur()
    const first = s.fields?.find((f) => f.visible)
    setTimeout(() => focus.focus(first ? `w-${first.key}` : "next"), 30)
  }

  useEffect(() => {
    void (async () => {
      const start = await bridge.call<{ steps: [string, string][] }>("onboard_start")
      setSteps(start.steps)
      show(await bridge.call<Step>("onboard_step", 0))
    })()
  }, [bridge])

  // Esc (or Ctrl+Q) offers to leave, from a text field too: onboarding has no one-key shortcuts to get back to.
  useKeyboard((key: KeyEvent) => {
    if (leaving) return
    if (key.name === "escape" || (key.ctrl && (key.name === "q" || key.name === "c"))) {
      key.preventDefault()
      setLeaving(true)
    }
  })

  const change = async (key: string, value: unknown) => {
    setRaws((r) => ({ ...r, [key]: value }))
    setErrors((e) => ({ ...e, [key]: "" }))
    const res = await bridge.call<{ fields: Field[] } | null>("onboard_change", key, value)
    if (!res) return
    setStep((s) => (s ? { ...s, fields: res.fields } : s))
    // A new format brings its own suggestions for the questions you haven't typed in.
    if (key === "format")
      setRaws((r) => {
        const out = { ...r }
        for (const f of res.fields) if (f.key === "series" || f.key === "twist") out[f.key] = f.value
        return out
      })
  }

  const next = async () => {
    if (!step) return
    if (step.key === "review") {
      setStatus("Writing your studio…")
      const res = await bridge.call<{ ok: boolean; status?: string; review?: string; detail?: string }>("onboard_create")
      if (res.ok) return onDone()
      setStatus(res.status ?? "")
      if (res.review) setStep({ ...step, review: res.review })
      if (res.detail) setDetail(res.detail)
      return
    }
    const res = await bridge.call<{ ok: boolean; step?: Step; errors?: Record<string, string>; first?: string; status?: string }>(
      "onboard_next",
      raws,
    )
    if (res.ok && res.step) return show(res.step)
    setErrors(res.errors ?? {})
    setStatus(res.status ?? "")
    if (res.first) {
      scroll.current?.scrollChildIntoView(`f-${res.first}`)
      focus.focus(`w-${res.first}`)
    }
  }

  const back = async () => {
    const s = await bridge.call<Step | null>("onboard_back", raws)
    if (s) show(s)
  }

  const i = step?.index ?? 0
  return (
    <Frame init={init} step="channel" hint=" Tab moves  ·  Enter presses  ·  Esc to leave " bigMinHeight={48}>
      <box flexDirection="row" flexGrow={1}>
        <box
          flexDirection="column"
          width={30}
          flexShrink={0}
          paddingTop={1}
          paddingRight={2}
          border={["right"]}
          borderStyle="single"
          borderColor={theme.panel}
        >
          <text fg={theme.muted} marginBottom={1}>
            Set up your channel
          </text>
          {steps.map(([key, label], n) => (
            <text
              key={key}
              paddingLeft={1}
              fg={n === i ? theme.text : n < i ? theme.good : theme.muted}
              bg={n === i ? mix(theme.primary, theme.bg, 0.75) : undefined}
              attributes={n === i ? TextAttributes.BOLD : undefined}
              wrapMode="none"
            >
              {(n < i ? `${init.check} ` : n === i ? "› " : "  ") + label}
            </text>
          ))}
        </box>
        <box flexDirection="column" flexGrow={1} paddingTop={1} paddingLeft={3}>
          <text fg="#ffffff" attributes={TextAttributes.BOLD} flexShrink={0}>
            {step?.title ?? ""}
          </text>
          <text fg={theme.muted} wrapMode="word" marginBottom={1} flexShrink={0}>
            {step?.blurb ?? ""}
          </text>
          <Scroll ref={scroll} flexGrow={1} scrollY>
            {step?.review !== undefined ? (
              <Markdown text={step.review} heading="#ffffff" />
            ) : (
              (step?.fields ?? [])
                .filter((f) => f.visible)
                .map((f) => <Question key={f.key} f={f} value={raws[f.key]} error={errors[f.key]} check={init.check} onChange={(v) => void change(f.key, v)} />)
            )}
            {detail ? (
              <text fg={theme.bad} wrapMode="char" flexShrink={0}>
                {detail}
              </text>
            ) : null}
          </Scroll>
          <box flexDirection="row" height={3} flexShrink={0} marginTop={1} marginBottom={1} alignItems="center">
            <Button id="back" label="Back" minWidth={22} marginRight={2} disabled={i === 0} onPress={() => void back()} />
            <Button
              id="next"
              label={step?.key === "review" ? "Create my studio" : "Next"}
              variant="primary"
              minWidth={22}
              marginRight={2}
              onPress={() => void next()}
            />
            <text fg={theme.muted} paddingLeft={2} wrapMode="word" flexGrow={1}>
              {status}
            </text>
          </box>
        </box>
      </box>
      {leaving ? (
        <Modal name="quit" title="Leave onboarding?" width={60}>
          <text flexShrink={0}>Your answers so far won't be saved.</text>
          <box flexDirection="row" height={3} marginTop={1} gap={2} flexShrink={0}>
            <Button id="stay" label="Keep going" variant="primary" autoFocus onPress={() => setLeaving(false)} />
            <Button id="leave" label="Leave" variant="error" onPress={() => quit(0)} />
          </box>
        </Modal>
      ) : null}
    </Frame>
  )
}

/** One question: its prompt, help line, the field, and a line for what's wrong with the answer. */
function Question({
  f,
  value,
  error,
  check,
  onChange,
}: {
  f: Field
  value: unknown
  error?: string
  check: string
  onChange: (v: unknown) => void
}) {
  const theme = useTheme()
  const id = `w-${f.key}`
  const bad = Boolean(error)
  let field
  if (f.kind === "text" || f.kind === "number")
    field = <TextField id={id} value={String(value ?? "")} placeholder={f.placeholder} bad={bad} onChange={onChange} />
  else if (f.kind === "long")
    field = (
      <TextBox
        id={id}
        value={Array.isArray(value) ? value.join("\n") : String(value ?? "")}
        placeholder={f.placeholder}
        bad={bad}
        onChange={onChange}
      />
    )
  else if (f.kind === "choice") field = <RadioSet id={id} options={f.options} value={(value as string) ?? null} bad={bad} onChange={onChange} />
  else if (f.kind === "multi")
    field = <CheckList id={id} options={f.options} value={Array.isArray(value) ? (value as string[]) : []} bad={bad} check={check} onChange={onChange} />
  else field = <Switch id={id} value={Boolean(value)} onChange={onChange} />
  return (
    <box id={`f-${f.key}`} flexDirection="column" paddingBottom={1} flexShrink={0}>
      <text attributes={TextAttributes.BOLD} wrapMode="word">
        {f.prompt + (f.required ? " *" : "")}
      </text>
      {f.help ? (
        <text fg={theme.muted} wrapMode="word">
          {f.help}
        </text>
      ) : null}
      {field}
      {error ? <text fg={theme.bad}>{error}</text> : null}
    </box>
  )
}
