// ReelForge's first run, all inside one box round the terminal with the logo on top: the tools it needs (one list,
// one yes), the downloads with their progress, a health check, onboarding, then what to do next. The Python side is
// studio/setup_service.py.

import { TextAttributes, type KeyEvent } from "@opentui/core"
import { useKeyboard, useTerminalDimensions } from "@opentui/react"
import { useEffect, useMemo, useState } from "react"
import { useView, type Bridge } from "../bridge"
import { FocusContext, FocusManager, ThemeContext, useFocus, useTheme } from "../lib/focus"
import type { Segs } from "../lib/styled"
import { SETUP } from "../theme"
import { Button } from "../ui/Button"
import { ProgressBar } from "../ui/Graphics"
import { Line } from "../ui/Line"
import { Scroll, ToastStack, toasts, useTick, Wrapped } from "../ui/Panels"
import { Frame } from "./Frame"
import { Onboard } from "./Onboard"

export interface SetupInit {
  start: string
  kit: string
  test: boolean
  root: string
  big: [string, string | null, string | null][][]
  anvil: [string, string | null, string | null][][]
  quadrants: boolean
  steps: [string, string][]
  check: string
  cross: string
  fancy: boolean
  onboarded: boolean
  new?: boolean // making a new profile (one for each channel)
  embedded?: boolean // inside the ReelForge window: the last screen goes back to it
  profile?: string // the profile it's for (or, for a new one, opened from)
  several?: boolean
}

type Screen = "tools" | "work" | "onboard" | "done"

export interface SetupProps {
  bridge: Bridge
  init: SetupInit
  quit: (code?: number, result?: object) => void
  options: Record<string, unknown>
}

export function SetupApp(props: SetupProps) {
  const focus = useMemo(() => new FocusManager(), [])
  const [screen, setScreen] = useState<Screen>(
    props.init.start === "onboard" ? "onboard" : props.init.start === "done" ? "done" : "tools",
  )
  const [chosen, setChosen] = useState<string[]>([])
  useEffect(() => props.bridge.on("toast", (t) => toasts.add(t)), [props.bridge])
  const go = (next: Screen) => {
    focus.blur()
    setScreen(next)
  }
  return (
    <ThemeContext.Provider value={SETUP}>
      <FocusContext.Provider value={focus}>
        <Keys focus={focus} />
        {screen === "tools" && (
          <Tools
            {...props}
            onGo={(keys) => {
              setChosen(keys)
              go("work")
            }}
          />
        )}
        {screen === "work" && (
          <Work
            {...props}
            keys={chosen}
            onNext={async () => go((await props.bridge.call<string>("after_tools")) === "done" ? "done" : "onboard")}
            onAgain={() => go("tools")}
          />
        )}
        {screen === "onboard" && <Onboard {...props} onDone={() => go("done")} />}
        {screen === "done" && <Done {...props} />}
        <ToastStack />
      </FocusContext.Provider>
    </ThemeContext.Provider>
  )
}

/** Tab moves, Enter presses (whatever has the keyboard handles the rest; each screen adds Esc). */
function Keys({ focus }: { focus: FocusManager }) {
  useKeyboard((key: KeyEvent) => {
    focus.handleKey(key)
  })
  return null
}

function useEscape(fn: () => void) {
  useKeyboard((key: KeyEvent) => {
    if (key.name === "escape" || (key.ctrl && (key.name === "q" || key.name === "c"))) fn()
  })
}

interface Item {
  key: string
  name: string
  why: string
  ready: boolean
  detail: string
  size_mb: number
  can_install: boolean
  default: boolean
}

/** A tick that can be turned off: the same green tick as the ready rows while on, a grey circle while off. */
function Tick({ id, on, onChange, check }: { id: string; on: boolean; onChange: (on: boolean) => void; check: string }) {
  const theme = useTheme()
  const { ref, focused, focus } = useFocus(id, {
    onKey: (key) => {
      if (key.name !== "space" && key.name !== "return" && key.name !== "enter") return false
      onChange(!on)
      return true
    },
  })
  return (
    <box
      ref={ref}
      width={3}
      marginRight={3}
      flexShrink={0}
      backgroundColor={focused ? theme.cursor : undefined}
      onMouseDown={() => {
        focus()
        onChange(!on)
      }}
    >
      <text fg={on ? theme.good : theme.muted} attributes={on ? TextAttributes.BOLD : undefined}>
        {` ${on ? check : "○"}`}
      </text>
    </box>
  )
}

/** Step 1: what ReelForge needs, ticked, and one button to set it all up. */
function Tools({ bridge, init, quit, onGo }: SetupProps & { onGo: (keys: string[]) => void }) {
  const theme = useTheme()
  const view = useView<{ intro: Segs; items: Item[]; todo: string[]; note: string }>(bridge, "items")
  const [ticked, setTicked] = useState<Record<string, boolean>>({})
  useEffect(() => {
    bridge.send("plan")
  }, [bridge])
  useEffect(() => {
    if (view) setTicked(Object.fromEntries(view.items.map((i) => [i.key, i.default])))
  }, [view])
  useEscape(() => quit(0))
  const picked = (view?.items ?? []).filter((i) => view?.todo.includes(i.key) && ticked[i.key])
  let label = "Checking…"
  if (view) {
    if (!view.todo.length) label = "Continue"
    else if (picked.length) {
      const mb = picked.reduce((n, i) => n + i.size_mb, 0)
      label = mb ? `Set up (about ${mb} MB)` : "Set up"
    } else label = "Continue without these"
  }
  return (
    <Frame init={init} step="tools" bigMinHeight={30}>
      <box flexDirection="column" flexGrow={1}>
        <Scroll flexGrow={1} scrollY>
          <box flexDirection="column" paddingRight={1} flexShrink={0}>
            {view ? (
              <Wrapped segs={view.intro} flexGrow={0} />
            ) : (
              <Line segs={[["Let's get ReelForge ready. ", "bold"], ["Checking what's already on this computer…", ""]]} />
            )}
            <box flexDirection="column" paddingTop={1} flexShrink={0}>
              {(view?.items ?? []).map((i) => (
                <box key={i.key} flexDirection="row" flexShrink={0}>
                  {!i.ready && i.can_install ? (
                    <Tick id={`cb-${i.key}`} on={Boolean(ticked[i.key])} check={init.check} onChange={(on) => setTicked((t) => ({ ...t, [i.key]: on }))} />
                  ) : (
                    <text width={6} flexShrink={0} fg={i.ready ? theme.good : theme.warn} attributes={TextAttributes.BOLD}>
                      {i.ready ? ` ${init.check}` : " !"}
                    </text>
                  )}
                  <text width={26} flexShrink={0} attributes={TextAttributes.BOLD} wrapMode="none">
                    {i.name}
                  </text>
                  <text flexGrow={1} flexShrink={1} wrapMode="word">
                    <span fg={theme.muted}>{i.why + "  ·  "}</span>
                    <span fg={i.ready ? theme.good : !i.can_install ? theme.warn : theme.muted}>{i.detail}</span>
                  </text>
                </box>
              ))}
            </box>
            {view ? (
              <box paddingTop={1} flexShrink={0}>
                <text fg={theme.muted} wrapMode="word">
                  {view.note}
                </text>
              </box>
            ) : null}
          </box>
        </Scroll>
        <box flexDirection="row" height={3} flexShrink={0} marginTop={1} marginBottom={1}>
          <Button
            id="go"
            label={label}
            variant="primary"
            minWidth={28}
            marginRight={2}
            disabled={!view}
            autoFocus={Boolean(view)}
            onPress={() => onGo(picked.map((i) => i.key))}
          />
          {view?.todo.length ? <Button id="skip" label="Skip for now" minWidth={20} onPress={() => onGo([])} /> : null}
        </box>
      </box>
    </Frame>
  )
}

interface Job {
  key: string
  name: string
  percent?: boolean
}

/** Step 1, continued: each download with its progress, then the health check. */
function Work({ bridge, init, keys, onNext, onAgain }: SetupProps & { keys: string[]; onNext: () => void; onAgain: () => void }) {
  const theme = useTheme()
  const jobs = useView<{ jobs: Job[] }>(bridge, "jobs")
  const checks = useView<{ rows?: Segs[]; bad?: boolean; warning?: string; next?: string; checking?: boolean }>(bridge, "checks")
  const [state, setState] = useState<Record<string, { text: string; done: number; total: number; state: string }>>({})
  useEffect(() => {
    bridge.emit("checks", undefined)
    const off = bridge.on("job", (j) => setState((s) => ({ ...s, [j.key]: j })))
    bridge.send("run_setup", keys)
    return off
  }, [bridge])
  const working = Object.values(state).some((j) => j.state === "busy")
  const tick = useTick(working || !checks?.rows, 120)
  const spin = init.fancy ? "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" : "-\\|/"
  const finished = Boolean(checks?.rows)
  // The bars get what the window has left after the names and some room for each one's status, up to 44 cells.
  const bar = Math.min(Math.max(useTerminalDimensions().width - 56, 10), 44)
  return (
    <Frame init={init} step="tools" bigMinHeight={30}>
      <box flexDirection="column" flexGrow={1}>
        <Scroll flexGrow={1} scrollY>
          {(jobs?.jobs ?? []).map((j) => {
            const st = state[j.key]
            const mark =
              !st ? "·" : st.state === "ok" ? init.check : st.state === "failed" ? init.cross : spin[tick % spin.length]!
            const color = !st ? theme.muted : st.state === "ok" ? theme.good : st.state === "failed" ? theme.bad : theme.text
            return (
              <box key={j.key} flexDirection="row" height={2} flexShrink={0}>
                <text width={4} paddingLeft={1} flexShrink={0} fg={color} attributes={TextAttributes.BOLD}>
                  {mark}
                </text>
                <text width={24} flexShrink={0} attributes={TextAttributes.BOLD} wrapMode="none">
                  {j.name}
                </text>
                <box width={bar + 6} flexShrink={0} flexDirection="row">
                  <ProgressBar
                    width={bar}
                    done={st?.state === "ok" ? 1 : (st?.done ?? 0)}
                    total={st?.state === "ok" || st?.state === "failed" ? 1 : st?.total || null}
                    color={st?.state === "failed" ? theme.bad : st?.state === "ok" ? theme.good : theme.primary}
                    track="#2a2e35"
                    tick={st ? tick : 0}
                  />
                  {j.percent !== false && st?.total && st.state === "busy" ? (
                    <text fg={theme.muted} marginLeft={1} width={4}>{`${Math.floor((100 * st.done) / st.total)}%`}</text>
                  ) : null}
                </box>
                <text flexGrow={1} wrapMode="none" fg={st?.state === "ok" ? theme.good : st?.state === "failed" ? theme.bad : theme.muted}>
                  {st?.text ?? "waiting"}
                </text>
              </box>
            )
          })}
          {checks?.checking ? (
            <text fg={theme.muted} marginTop={1}>
              Checking everything…
            </text>
          ) : null}
          {checks?.rows ? (
            <box flexDirection="column" paddingTop={1} flexShrink={0}>
              <text attributes={TextAttributes.BOLD}>Health check</text>
              {checks.rows.map((r, i) => (
                <Line key={i} segs={r} />
              ))}
              {checks.warning ? (
                <box marginTop={1}>
                  <text fg={theme.warn} wrapMode="word">
                    {checks.warning}
                  </text>
                </box>
              ) : null}
            </box>
          ) : null}
        </Scroll>
        <box flexDirection="row" height={3} flexShrink={0} marginBottom={1} marginTop={1}>
          <Button
            id="next"
            label={finished ? (checks!.next ?? "Continue") : "Working…"}
            variant="primary"
            minWidth={20}
            marginRight={2}
            disabled={!finished}
            autoFocus={finished}
            onPress={onNext}
          />
          {checks?.bad ? <Button id="again" label="Check again" minWidth={20} onPress={onAgain} /> : null}
        </box>
      </box>
    </Frame>
  )
}

/** Step 3: what was made, what runs in the background, and what to do next. */
function Done({ bridge, init, quit }: SetupProps) {
  const theme = useTheme()
  const [info, setInfo] = useState<{
    head: Segs[]
    written: string
    steps: Segs[]
    login: string
    open: string
    tab: string
    profile?: string
    back?: string
  } | null>(null)
  const system = useView<{ rows: Segs[] }>(bridge, "system")
  useEffect(() => {
    bridge.call("done_info").then(setInfo)
  }, [bridge])
  useEscape(() => quit(0))
  return (
    <Frame init={init} step="ready" bigMinHeight={32}>
      <box flexDirection="column" flexGrow={1}>
        <Scroll flexGrow={1} scrollY>
          {info ? (
            <box flexDirection="column" flexShrink={0}>
              {info.head.map((l, i) => (
                <Wrapped key={i} segs={l} flexGrow={0} />
              ))}
              {info.written ? (
                <text fg={theme.muted} marginTop={1}>{`Written:  ${info.written}`}</text>
              ) : null}
              <box flexDirection="column" marginTop={1} flexShrink={0}>
                {(system?.rows ?? [[["  Setting up your background stats…", theme.muted]]]).map((l, i) => (
                  <Wrapped key={i} segs={l} flexGrow={0} />
                ))}
              </box>
              <text attributes={TextAttributes.BOLD} marginTop={1}>
                What's next
              </text>
              {info.steps.map((l, i) => (
                <Wrapped key={i} segs={l} flexGrow={0} />
              ))}
              {info.login ? (
                <box marginTop={1}>
                  <text fg={theme.warn} wrapMode="word">
                    {info.login}
                  </text>
                </box>
              ) : null}
            </box>
          ) : null}
        </Scroll>
        <box flexDirection="row" height={3} flexShrink={0} marginBottom={1} gap={2}>
          <Button
            id="open"
            label={info?.open ?? "Open ReelForge"}
            variant="primary"
            minWidth={20}
            autoFocus={Boolean(info)}
            onPress={() => quit(0, { open: "dashboard", tab: info?.tab ?? "overview", ...(info?.profile ? { profile: info.profile } : {}) })}
          />
          <Button id="folder" label={init.new ? "Show its folder" : "Show this folder"} minWidth={20} onPress={() => bridge.send("show_folder")} />
          <Button id="close" label={info?.back || "Close"} minWidth={20} onPress={() => quit(0)} />
        </box>
      </box>
    </Frame>
  )
}
