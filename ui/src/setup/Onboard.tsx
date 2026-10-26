// The onboarding interview, step by step, then a review: Create my studio writes everything. Mouse and keyboard both
// work: Tab moves between fields, Enter presses a button, Esc offers to leave. The questions, their defaults and when
// each shows come from studio/questions.py, through studio/setup_service.py. Your accounts has a sign-up guide for
// each platform (and the channel's Gmail) for someone without the accounts yet. In a big enough window the mascot
// stands under the list of steps.

import { TextAttributes, type KeyEvent, type ScrollBoxRenderable } from "@opentui/core"
import { useKeyboard, useTerminalDimensions } from "@opentui/react"
import { useEffect, useRef, useState } from "react"
import { useFocusManager, useTheme } from "../lib/focus"
import { mix } from "../theme"
import { Button } from "../ui/Button"
import { CheckList, RadioSet, Switch, TextBox, TextField } from "../ui/Fields"
import { Mascot, MASCOT_BODY } from "../ui/Mascot"
import { Markdown, Modal, Scroll } from "../ui/Panels"
import type { SetupProps } from "./App"
import { Frame, frameLayout } from "./Frame"

/** The full logo needs this many rows here, where the questions want the room. */
const BIG_MIN_HEIGHT = 48

interface Field {
  key: string
  prompt: string
  required: boolean
  help: string
  kind: "text" | "number" | "long" | "choice" | "multi" | "yesno" | "handle"
  options: [string, string][]
  value: unknown
  placeholder: string
  visible: boolean
  platform?: string // a handle's platform, for its sign-up guide
}

/** How to make one account, or the channel's Gmail (setup_service.signup_guide). */
interface Guide {
  key: string
  title: string
  why: string
  steps: string[]
  button: string
  account: boolean
}

interface Step {
  index: number
  key: string
  title: string
  blurb: string
  fields?: Field[]
  review?: string
  gmail?: { title: string; why: string; button: string } // Your accounts: a Gmail for the channel first
}

export function Onboard({ bridge, init, quit, onDone }: SetupProps & { onDone: () => void }) {
  const theme = useTheme()
  const focus = useFocusManager()
  const [steps, setSteps] = useState<[string, string][]>([])
  const [labels, setLabels] = useState({ side: "Set up your channel", create: "Create my studio" })
  const [step, setStep] = useState<Step | null>(null)
  const [raws, setRaws] = useState<Record<string, unknown>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [status, setStatus] = useState("")
  const [detail, setDetail] = useState("")
  const [leaving, setLeaving] = useState(false)
  const [guide, setGuide] = useState<Guide | null>(null)
  const scroll = useRef<ScrollBoxRenderable | null>(null)
  const { width, height } = useTerminalDimensions()
  const roomy = width >= 100 // room for the list of steps beside the questions (each step's title says n/8 anyway)
  // the mascot under the steps, when the column has his rows and a gap below them (and their 3 rows of heading)
  const mascot =
    roomy && width >= 110 && steps.length > 0 &&
    frameLayout(init, width, height, BIG_MIN_HEIGHT, false).rows >= 3 + steps.length + 1 + MASCOT_BODY.height

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
      const start = await bridge.call<{ steps: [string, string][]; side?: string; create?: string }>("onboard_start")
      setSteps(start.steps)
      setLabels((l) => ({ side: start.side ?? l.side, create: start.create ?? l.create }))
      show(await bridge.call<Step>("onboard_step", 0))
    })()
  }, [bridge])

  // Esc (or Ctrl+Q) offers to leave, from a text field too: onboarding has no one-key shortcuts to get back to.
  useKeyboard((key: KeyEvent) => {
    if (leaving || guide) return
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

  /** A platform's sign-up guide (or the Gmail one, "gmail"); the handle you type there goes into its box here. */
  const signUp = async (key: string) => setGuide(await bridge.call<Guide>("signup_guide", key))
  const signedUp = (handle: string | null) => {
    const key = guide?.key
    setGuide(null)
    if (key && key !== "gmail" && handle !== null) void change(`handle_${key}`, handle) // counts as typed: your answer
    setTimeout(() => focus.focus(key && key !== "gmail" ? `w-handle_${key}` : "next"), 30)
  }

  const i = step?.index ?? 0
  return (
    <Frame init={init} step="channel" bigMinHeight={BIG_MIN_HEIGHT}>
      <box flexDirection="row" flexGrow={1}>
        {roomy ? (
          <box
            flexDirection="column"
            width={mascot ? MASCOT_BODY.width + 3 : 30}
            flexShrink={0}
            paddingTop={1}
            paddingRight={2}
            border={["right"]}
            borderStyle="single"
            borderColor={theme.panel}
          >
            <text fg={theme.muted} marginBottom={1}>
              {labels.side}
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
            {mascot ? (
              <box flexGrow={1} justifyContent="flex-end">
                {/* hello on the first step, then a glance round at each new one */}
                <Mascot fit="animation" once={i === 0 ? "wink" : "look"} cue={i} animation="idle" />
              </box>
            ) : null}
          </box>
        ) : null}
        <box flexDirection="column" flexGrow={1} paddingTop={1} paddingLeft={roomy ? 3 : 0}>
          <text fg="#ffffff" attributes={TextAttributes.BOLD} flexShrink={0}>
            {step?.title ?? ""}
          </text>
          <Scroll ref={scroll} flexGrow={1} scrollY>
            <text fg={theme.muted} wrapMode="word" marginBottom={1} paddingRight={1} flexShrink={0}>
              {step?.blurb ?? ""}
            </text>
            {step?.gmail ? <GmailOffer offer={step.gmail} onPress={() => void signUp("gmail")} /> : null}
            {step?.review !== undefined ? (
              <Markdown text={step.review} heading="#ffffff" />
            ) : (
              (step?.fields ?? [])
                .filter((f) => f.visible)
                .map((f) => (
                  <Question
                    key={f.key}
                    f={f}
                    value={raws[f.key]}
                    error={errors[f.key]}
                    check={init.check}
                    onChange={(v) => void change(f.key, v)}
                    onSignUp={f.platform ? () => void signUp(f.platform!) : undefined}
                  />
                ))
            )}
            {detail ? (
              <text fg={theme.bad} wrapMode="char" flexShrink={0}>
                {detail}
              </text>
            ) : null}
          </Scroll>
          <box flexDirection="row" height={3} flexShrink={0} marginTop={1} marginBottom={1} alignItems="center">
            <Button id="back" label="Back" minWidth={roomy ? 22 : 12} marginRight={2} disabled={i === 0} onPress={() => void back()} />
            <Button
              id="next"
              label={step?.key === "review" ? labels.create : "Next"}
              variant="primary"
              minWidth={roomy ? 22 : 12}
              marginRight={2}
              onPress={() => void next()}
            />
            <text fg={theme.muted} paddingLeft={2} wrapMode="word" flexGrow={1}>
              {status}
            </text>
          </box>
        </box>
      </box>
      {guide ? (
        <SignupGuide
          guide={guide}
          handle={String(raws[`handle_${guide.key}`] ?? "")}
          check={init.check}
          bridge={bridge}
          onDone={signedUp}
        />
      ) : null}
      {leaving ? (
        <Modal name="quit" title="Leave without saving?" width={60}>
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
  onSignUp,
}: {
  f: Field
  value: unknown
  error?: string
  check: string
  onChange: (v: unknown) => void
  onSignUp?: () => void
}) {
  const theme = useTheme()
  const id = `w-${f.key}`
  const bad = Boolean(error)
  let field
  if (f.kind === "text" || f.kind === "number")
    field = <TextField id={id} value={String(value ?? "")} placeholder={f.placeholder} bad={bad} onChange={onChange} />
  else if (f.kind === "handle")
    field = (
      <box flexDirection="row" height={3} flexShrink={0}>
        <box flexGrow={1} maxWidth={44} marginRight={2}>
          <TextField id={id} value={String(value ?? "")} placeholder={f.placeholder} bad={bad} flexGrow={1} onChange={onChange} />
        </box>
        {onSignUp ? <Button id={`signup-${f.platform}`} label="No account? Sign up →" minWidth={26} onPress={onSignUp} /> : null}
      </box>
    )
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

/** The box at the top of Your accounts: a Gmail just for the channel first, for someone starting from scratch. */
function GmailOffer({ offer, onPress }: { offer: { title: string; why: string; button: string }; onPress: () => void }) {
  const theme = useTheme()
  return (
    <box border borderStyle="rounded" borderColor={theme.border} paddingLeft={1} paddingRight={1} marginBottom={1} flexDirection="column" flexShrink={0}>
      <text attributes={TextAttributes.BOLD} wrapMode="word">
        {offer.title}
      </text>
      <text fg={theme.muted} wrapMode="word">
        {offer.why}
      </text>
      <box flexDirection="row" height={3} marginTop={1} flexShrink={0}>
        <Button id="gmail" label={offer.button} onPress={onPress} />
      </box>
    </box>
  )
}

/** How to make one account (or the channel's Gmail): the steps, a button that opens the official sign-up page in your
 * own browser (a private window of it for a second channel, so the other one stays logged in), and for an account a
 * box for the @handle you end up with. Done hands that handle back (maybe ""), Back hands back null. ReelForge never
 * makes the account or sees a password. */
function SignupGuide({
  guide,
  handle: start,
  check,
  bridge,
  onDone,
}: {
  guide: Guide
  handle: string
  check: string
  bridge: SetupProps["bridge"]
  onDone: (handle: string | null) => void
}) {
  const theme = useTheme()
  const focus = useFocusManager()
  const [opened, setOpened] = useState("") // what opened, said under the button: a private window, for a second channel
  const [handle, setHandle] = useState(start)
  const [problem, setProblem] = useState("")
  useKeyboard((key: KeyEvent) => {
    if (key.name === "escape") {
      key.preventDefault()
      onDone(null)
    }
  })
  const open = async () => {
    const said = await bridge.call<string | null>("open_signup", guide.key)
    setOpened(said || "Opened in your browser. Come back here when you're done.")
    setTimeout(() => focus.focus(guide.account ? "guide-handle" : "guide-done"), 30)
  }
  const done = async (typed = handle) => {
    if (!guide.account) return onDone(null)
    const res = await bridge.call<{ handle?: string; error?: string }>("signup_handle", typed)
    if (res.error) setProblem(res.error)
    else onDone(res.handle ?? "")
  }
  return (
    <Modal name="guide" title={guide.title} width={84}>
      <text fg={theme.muted} wrapMode="word" flexShrink={0}>
        {guide.why}
      </text>
      <box flexDirection="column" marginTop={1} flexShrink={0}>
        {guide.steps.map((step, i) => (
          <box key={i} flexDirection="row" flexShrink={0}>
            <text attributes={TextAttributes.BOLD} width={4} flexShrink={0}>
              {`${i + 1}.`.padStart(3)}
            </text>
            <text wrapMode="word" flexGrow={1} flexShrink={1}>
              {step}
            </text>
          </box>
        ))}
      </box>
      <box flexDirection="row" height={3} marginTop={1} marginLeft={4} flexShrink={0}>
        <Button id="guide-open" label={guide.button} variant="primary" autoFocus onPress={() => void open()} />
      </box>
      {opened ? (
        <text fg={theme.good} marginLeft={4} wrapMode="word" flexShrink={0}>
          {`${check} ${opened}`}
        </text>
      ) : null}
      {guide.account ? (
        <>
          <text attributes={TextAttributes.BOLD} marginTop={1} flexShrink={0}>
            Your @handle
          </text>
          <TextField id="guide-handle" value={handle} placeholder="@yourname" bad={!!problem} onChange={setHandle} onSubmit={(v) => void done(v)} />
          {problem ? (
            <text fg={theme.bad} wrapMode="word" flexShrink={0}>
              {problem}
            </text>
          ) : null}
        </>
      ) : null}
      <box flexDirection="row" height={3} marginTop={1} gap={2} flexShrink={0}>
        <Button id="guide-done" label="Done" variant="primary" onPress={() => void done()} />
        <Button id="guide-back" label="Back" onPress={() => onDone(null)} />
      </box>
    </Modal>
  )
}
