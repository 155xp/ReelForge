// The Settings tab (7): this channel's answers from first-time setup and how hard your AI reasons side by side, what
// ReelForge set up on this computer under them, and the danger zone across the bottom: factory reset and uninstall,
// each behind a dialog where you type the channel's name. Neither deletes anything: what they clear goes to a backup
// or the Recycle Bin (Trash). dashboard/settings_tab.py sends the "settings" view and does the work (with
// studio/reset.py).

import { TextAttributes } from "@opentui/core"
import { useEffect, useState } from "react"
import { useView } from "../bridge"
import { lines, type Segs } from "../lib/styled"
import { DASH } from "../theme"
import { Button } from "../ui/Button"
import { RadioSet, Switch, TextField } from "../ui/Fields"
import { Modal, Panel, Scroll, Wrapped } from "../ui/Panels"
import { useDash, type AdvancedData } from "./state"

export interface ComputerRow {
  key: string
  label: string
  on: boolean
  value: string
  button: string
}

export interface SettingsView {
  name: string
  onboarded: boolean
  rows: [string, string][]
  ai: (AdvancedData & { about: Record<string, string> }) | null
  computer: ComputerRow[] | null // null while it's being looked up
  demo: boolean
  bin: string
  several: boolean
}

export interface ResetData {
  note: Segs
  word: string
}

export interface UninstallData {
  note: Segs
  word: string
  bin: string
  keep_to: string
  videos: number
  videos_size: string
  channels: string[]
}

const DANGER = DASH.bad

/** What's typed matches the name to type: any case, spaces squeezed (studio/reset.py matches). */
export function typedMatches(typed: string, word: string): boolean {
  const norm = (t: string) => t.split(/\s+/).filter(Boolean).join(" ").toLowerCase()
  return norm(typed) !== "" && norm(typed) === norm(word)
}

export function Settings() {
  const s = useDash()
  const v = useView<SettingsView>(s.bridge, "settings")
  if (!v) {
    return (
      <text fg={DASH.muted} marginTop={1}>
        Reading your settings…
      </text>
    )
  }
  return (
    <Scroll flexGrow={1} scrollY>
      <box height={1} flexShrink={0} />
      <box flexDirection="row" gap={2} flexShrink={0}>
        <Channel v={v} />
        <Reasoning v={v} />
      </box>
      <box height={1} flexShrink={0} />
      <Computer v={v} />
      <box height={1} flexShrink={0} />
      <DangerZone v={v} />
    </Scroll>
  )
}

/** This channel's answers, and the button that asks first-time setup's questions again. */
function Channel({ v }: { v: SettingsView }) {
  const s = useDash()
  const width = Math.max(...v.rows.map(([label]) => label.length), 8) + 3
  const change = () => {
    if (v.demo) return s.bridge.emit("toast", { title: "Demo mode", body: "Nothing is changed in the demo.", severity: "information", timeout: 5 })
    s.nav.onboard("settings", "settings")
  }
  return (
    <Panel title={`THIS CHANNEL: ${v.name.toUpperCase()}`} flexGrow={1} flexShrink={1}>
      {v.onboarded ? (
        v.rows.map(([label, value]) => (
          <text key={label} wrapMode="none" flexShrink={0}>
            <span fg={DASH.muted}>{label.padEnd(width)}</span>
            <span fg={DASH.text}>{value}</span>
          </text>
        ))
      ) : (
        <text fg={DASH.muted} wrapMode="word" flexShrink={0}>
          This channel isn't set up yet: first-time setup asks a few questions about it and writes your AI's notes.
        </text>
      )}
      <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
        <Button id="settings-change" label={v.onboarded ? "Change your answers" : "Set it up"} variant="primary" marginRight={1} onPress={change} />
      </box>
    </Panel>
  )
}

/** How hard your AI reasons on each video (the profile menu's Advanced settings opens this tab). */
function Reasoning({ v }: { v: SettingsView }) {
  const s = useDash()
  const [level, setLevel] = useState(v.ai?.current ?? "high")
  useEffect(() => setLevel(v.ai?.current ?? "high"), [v.ai?.current])
  return (
    <Panel title="YOUR AI'S REASONING" flexGrow={1} flexShrink={1}>
      {v.ai ? (
        <>
          <text fg={DASH.muted} wrapMode="word" flexShrink={0}>
            {`How hard your AI thinks on each of ${v.ai.channel}'s videos. High suits almost every channel.`}
          </text>
          <box marginTop={1} flexShrink={0}>
            <RadioSet id="settings-reasoning" options={v.ai.options} value={level} onChange={setLevel} />
          </box>
          <text fg={DASH.text} wrapMode="word" marginTop={1} flexShrink={0}>
            {v.ai.about[level] ?? ""}
          </text>
          <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
            <Button
              id="settings-reasoning-save"
              label="Save"
              disabled={level === v.ai.current}
              onPress={() => {
                void s.bridge.call<boolean>("set_reasoning", level).then(() => s.bridge.send("tab_opened", "settings"))
              }}
            />
          </box>
        </>
      ) : (
        <text fg={DASH.muted} wrapMode="word" flexShrink={0}>
          Set up the channel first: first-time setup asks how hard your AI should work on its videos.
        </text>
      )}
    </Panel>
  )
}

/** What ReelForge set up on this computer, each with its button (all as wide as the widest, lined up on the right). */
function Computer({ v }: { v: SettingsView }) {
  const s = useDash()
  const width = Math.max(0, ...(v.computer ?? []).map((row) => row.button.length)) + 4
  return (
    <Panel title="ON THIS COMPUTER" flexShrink={0}>
      {v.computer === null ? (
        <text fg={DASH.muted} flexShrink={0}>
          Looking…
        </text>
      ) : (
        v.computer.map((row) => (
          <box key={row.key} flexDirection="row" height={3} flexShrink={0} alignItems="center" gap={1}>
            <box flexDirection="column" flexGrow={1} flexShrink={1} justifyContent="center">
              <text attributes={TextAttributes.BOLD} wrapMode="none">
                {row.label}
              </text>
              <text fg={row.on ? DASH.good : DASH.muted} wrapMode="none">
                {row.value}
              </text>
            </box>
            {row.button ? <Button id={`settings-${row.key}`} label={row.button} minWidth={width} flexShrink={0} onPress={() => s.bridge.send("settings_toggle", row.key)} /> : null}
          </box>
        ))
      )}
    </Panel>
  )
}

/** Factory reset and uninstall: red, across the bottom, each opening a dialog that asks for the channel's name. */
function DangerZone({ v }: { v: SettingsView }) {
  const s = useDash()
  const item = (id: string, title: string, what: string, label: string, onPress: () => void) => (
    <box key={id} flexDirection="row" minHeight={3} flexShrink={0} alignItems="center" gap={1}>
      <box flexDirection="column" flexGrow={1} flexShrink={1}>
        <text fg={DANGER} attributes={TextAttributes.BOLD} wrapMode="none">
          {title}
        </text>
        <text fg={DASH.muted} wrapMode="word">
          {what}
        </text>
      </box>
      <Button id={id} label={label} variant="error" minWidth={18} flexShrink={0} onPress={onPress} />
    </box>
  )
  return (
    <Panel title="DANGER ZONE" titleColor={DANGER} flexShrink={0}>
      {item(
        "settings-reset",
        "Factory reset",
        v.several
          ? "Every channel goes to a backup (your first channel's videos stay), then first-time setup starts again."
          : "Your settings, log-ins and stats go to a backup, then first-time setup starts again. Your videos stay.",
        "Factory reset…",
        () => void s.openDialog("factory_reset", s.bridge.call("reset_info")),
      )}
      <box height={1} flexShrink={0} />
      {item(
        "settings-uninstall",
        "Uninstall ReelForge",
        `Removes ReelForge from this computer (to the ${v.bin}). Your videos and channels can be kept in a folder beside it.`,
        "Uninstall…",
        () => void s.openDialog("uninstall", s.bridge.call("uninstall_info")),
      )}
    </Panel>
  )
}

/** The box for the channel's name, under its instruction. */
function Confirm({ id, word, typed, setTyped, onSubmit }: { id: string; word: string; typed: string; setTyped: (t: string) => void; onSubmit: () => void }) {
  return (
    <>
      <text marginTop={1} flexShrink={0} wrapMode="word">
        <span fg={DASH.text}>Type </span>
        <span fg={DASH.text} attributes={TextAttributes.BOLD}>
          {word}
        </span>
        <span fg={DASH.text}> to confirm:</span>
      </text>
      <TextField id={id} value={typed} placeholder={word} autoFocus onChange={setTyped} onSubmit={onSubmit} />
    </>
  )
}

export function FactoryReset({ data, close }: { data: ResetData; close: () => void }) {
  const s = useDash()
  const [typed, setTyped] = useState("")
  const ok = typedMatches(typed, data.word)
  const go = () => {
    if (!ok) return
    close()
    void s.bridge.call<boolean>("factory_reset", typed)
  }
  return (
    <Modal name="factory-reset" title="FACTORY RESET" width={90}>
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      <Confirm id="reset-word" word={data.word} typed={typed} setTyped={setTyped} onSubmit={go} />
      <box flexDirection="row" justifyContent="flex-end" height={1} marginTop={2} flexShrink={0} gap={1}>
        <Button id="reset-cancel" label="Cancel" onPress={close} />
        <Button id="reset-go" label="Reset ReelForge" variant="error" disabled={!ok} onPress={go} />
      </box>
    </Modal>
  )
}

export function Uninstall({ data, close }: { data: UninstallData; close: () => void }) {
  const s = useDash()
  const [typed, setTyped] = useState("")
  const [keep, setKeep] = useState(true)
  const ok = typedMatches(typed, data.word)
  const go = () => {
    if (!ok) return
    close()
    void s.bridge.call<boolean>("uninstall", typed, keep)
  }
  const what = data.channels.length ? `${data.videos} files, ${data.videos_size}` : ""
  return (
    <Modal name="uninstall" title="UNINSTALL REELFORGE" width={90}>
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      <text marginTop={1} fg={DASH.text} attributes={TextAttributes.BOLD} flexShrink={0}>
        Your videos and channels
      </text>
      {data.channels.length ? (
        <>
          <box flexDirection="row" gap={2} height={1} flexShrink={0}>
            <text fg={DASH.text} wrapMode="none">
              Keep them
            </text>
            <Switch id="uninstall-keep" value={keep} onChange={setKeep} />
          </box>
          <text fg={keep ? DASH.good : DASH.warn} wrapMode="word" flexShrink={0}>
            {keep
              ? `Moved first to ${data.keep_to} (${what}): a folder for each channel, with its videos and its answers from first-time setup.`
              : `They go to the ${data.bin} with the rest of ReelForge (${what}).`}
          </text>
        </>
      ) : (
        <text fg={DASH.muted} wrapMode="word" flexShrink={0}>
          There are no videos or channel answers in the ReelForge folder, so there's nothing to keep.
        </text>
      )}
      <Confirm id="uninstall-word" word={data.word} typed={typed} setTyped={setTyped} onSubmit={go} />
      <box flexDirection="row" justifyContent="flex-end" height={1} marginTop={2} flexShrink={0} gap={1}>
        <Button id="uninstall-cancel" label="Cancel" onPress={close} />
        <Button id="uninstall-go" label="Uninstall ReelForge" variant="error" disabled={!ok} onPress={go} />
      </box>
    </Modal>
  )
}
