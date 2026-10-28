// The Settings tab: this channel's answers from first-time setup and the FAQ side by side (one under the other in a
// narrow window), the order of the tabs along the top, what ReelForge set up on this computer, your profiles (Delete
// beside each one this window can delete, Restore beside each one deleted), and the danger zone across the bottom:
// factory reset and uninstall, each behind a dialog where you type the channel's name. None of them deletes anything:
// what they clear goes to a backup or the Recycle Bin (Trash). dashboard/settings_tab.py sends the "settings" view and
// does the work (with studio/reset.py, and dashboard/service.py and studio/profiles.py for the profiles);
// dashboard/faq.py writes the FAQ, and dashboard/tabs.py keeps the tab order.

import { TextAttributes, type KeyEvent, type Renderable } from "@opentui/core"
import { useEffect, useRef, useState } from "react"
import { useView } from "../bridge"
import { useFocus } from "../lib/focus"
import { lines, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Button } from "../ui/Button"
import { Switch, TextField } from "../ui/Fields"
import { Markdown, Modal, Panel, Scroll, Wrapped } from "../ui/Panels"
import { PUBLISH_KEY, TAB_NAMES, useDash, type Tab } from "./state"

export interface ComputerRow {
  key: string
  label: string
  on: boolean
  value: string
  button: string
}

/** A question and its answer (a little Markdown). */
export interface FaqItem {
  q: string
  a: string
}

export interface SettingsView {
  name: string
  onboarded: boolean
  rows: [string, string][]
  faq: FaqItem[]
  computer: ComputerRow[] | null // null while it's being looked up
  demo: boolean
  bin: string
  several: boolean
  profiles: ProfilesSettings
}

/** The Profiles panel (dashboard/service.py profiles_settings): every profile, then the deleted ones kept in backups. */
export interface ProfilesSettings {
  rows: { key: string; number: number; name: string; current: boolean; main: boolean; deletable: boolean; note: string }[]
  deleted: DeletedProfile[]
}

export interface DeletedProfile {
  id: string // its backup's folder name
  name: string
  when: string // "deleted today at 4:05 PM"
  size: string // "" until it's added up
  where: string // its backup, from the ReelForge folder
}

/** Narrower than this, the FAQ goes under the channel's answers instead of beside them. */
const SIDE_BY_SIDE = 110

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
  const [width, setWidth] = useState(0)
  if (!v) {
    return (
      <text fg={DASH.muted} marginTop={1}>
        Reading your settings…
      </text>
    )
  }
  const side = width === 0 || width >= SIDE_BY_SIDE
  return (
    <Scroll flexGrow={1} scrollY>
      <box height={1} flexShrink={0} />
      <box
        flexDirection={side ? "row" : "column"}
        gap={side ? 2 : 1}
        flexShrink={0}
        onSizeChange={function (this: Renderable) {
          setWidth(this.width)
        }}
      >
        <Channel v={v} grow={side} />
        <Faq items={v.faq} grow={side} />
      </box>
      <box height={1} flexShrink={0} />
      <TabOrder />
      <box height={1} flexShrink={0} />
      <Computer v={v} />
      <box height={1} flexShrink={0} />
      <ProfilesPanel v={v} />
      <box height={1} flexShrink={0} />
      <DangerZone v={v} />
    </Scroll>
  )
}

/** This channel's answers, and the button that asks first-time setup's questions again. grow: half the row (beside
 * the FAQ), else as tall as its rows (over it). */
function Channel({ v, grow }: { v: SettingsView; grow: boolean }) {
  const s = useDash()
  const width = Math.max(...v.rows.map(([label]) => label.length), 8) + 3
  const change = () => {
    if (v.demo) return s.bridge.emit("toast", { title: "Demo mode", body: "Nothing is changed in the demo.", severity: "information", timeout: 5 })
    s.nav.onboard("settings", "settings")
  }
  return (
    <Panel title={`THIS CHANNEL: ${v.name.toUpperCase()}`} flexGrow={grow ? 1 : undefined} flexShrink={grow ? 1 : 0}>
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

/** The FAQ: a question a row, its answer opening under it (one at a time). A click opens or closes one; with the
 * keyboard (Tab), the arrows move and Enter or Space opens. grow: half the row, beside the channel's answers. */
function Faq({ items, grow }: { items: FaqItem[]; grow: boolean }) {
  const [open, setOpen] = useState<number | null>(null)
  const [cursor, setCursor] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  const toggle = (i: number) => setOpen((o) => (o === i ? null : i))
  const { ref, focused, focus } = useFocus("settings-faq", {
    disabled: !items.length,
    onKey: (key: KeyEvent) => {
      const n = items.length
      if (key.name === "up") setCursor((c) => (c - 1 + n) % n)
      else if (key.name === "down") setCursor((c) => (c + 1) % n)
      else if (key.name === "return" || key.name === "enter" || key.name === "space") toggle(cursor)
      else return false
      key.preventDefault()
      return true
    },
  })
  return (
    <Panel title="FAQ" sub={<text fg={DASH.faint} wrapMode="none">click a question for its answer</text>} flexGrow={grow ? 1 : undefined} flexShrink={grow ? 1 : 0}>
      <box ref={ref} flexDirection="column" flexShrink={0}>
        {items.map((item, i) => {
          const shown = open === i
          const here = focused && cursor === i
          return (
            <box key={item.q} flexDirection="column" flexShrink={0}>
              <box
                flexDirection="row"
                flexShrink={0}
                backgroundColor={here ? DASH.cursor : hover === i ? DASH.raised : undefined}
                onMouseOver={() => setHover(i)}
                onMouseOut={() => setHover((h) => (h === i ? null : h))}
                onMouseDown={(e) => {
                  if (e.button !== 0) return
                  e.stopPropagation()
                  focus()
                  setCursor(i)
                  toggle(i)
                }}
              >
                <text fg={shown ? DASH.text : DASH.faint} width={2} flexShrink={0}>
                  {shown ? "▾" : "▸"}
                </text>
                <text fg={shown || here || hover === i ? DASH.text : DASH.muted} attributes={shown ? TextAttributes.BOLD : undefined} wrapMode="word" flexGrow={1} flexShrink={1}>
                  {item.q}
                </text>
              </box>
              {shown ? (
                <box paddingLeft={2} marginTop={1} marginBottom={1} flexShrink={0}>
                  <Markdown text={item.a} />
                </box>
              ) : null}
            </box>
          )
        })}
      </box>
    </Panel>
  )
}

/** The tabs along the top, in their order, each with the number that opens it. Drag one to another place, or pick one
 * (click it, or ← → while the row has the keyboard) and move it with the arrows (the buttons, or Shift+← →). Each move
 * is kept at once, for every profile; Reset to default puts them back in the default order (Overview first, Settings
 * and Updates last). Publish isn't one of them: under them, a line says where its button is. */
function TabOrder() {
  const s = useDash()
  const [picked, setPicked] = useState<Tab | null>(null)
  const [hover, setHover] = useState<Tab | null>(null)
  const [held, setHeld] = useState<Tab | null>(null) // the tab being dragged
  const nodes = useRef(new Map<Tab, Renderable>())
  const before = useRef("") // the order when the drag started
  const pickedNow = useRef<Tab | null>(null) // the picked tab for keys that come before the next draw
  const pick = (tab: Tab) => {
    pickedNow.current = tab
    setPicked(tab)
  }
  const at = picked ? s.order.indexOf(picked) : -1
  /** Put a tab in this place (0 is the far left); keep: false while it's being dragged. */
  const place = (tab: Tab, to: number, keep = true) => {
    const rest = s.order.filter((t) => t !== tab)
    const next = [...rest.slice(0, to), tab, ...rest.slice(to)]
    if (next.join() !== s.order.join()) s.setOrder(next, keep)
  }
  const nudge = (by: -1 | 1) => {
    const tab = pickedNow.current
    const i = tab ? s.order.indexOf(tab) : -1
    if (tab && i + by >= 0 && i + by < s.order.length) place(tab, i + by)
  }
  /** Where a dragged tab goes: after every other tab whose middle the pointer is past, on its row or a row below it
   * (above or below the tabs counts as their first or last row). */
  const dropAt = (tab: Tab, x: number, y: number) => {
    const rows = [...nodes.current.values()].map((n) => n.y)
    const row = Math.min(Math.max(y, Math.min(...rows)), Math.max(...rows))
    return s.order.filter((t) => {
      const n = t !== tab && nodes.current.get(t)
      return n && (n.y < row || (n.y === row && n.x + n.width / 2 <= x))
    }).length
  }
  const { ref, focused, focus } = useFocus("settings-tab-order", {
    onKey: (key: KeyEvent) => {
      const by = key.name === "left" ? -1 : key.name === "right" ? 1 : 0
      if (!by) return false
      const i = pickedNow.current ? s.order.indexOf(pickedNow.current) : -1
      if (key.shift) nudge(by)
      else pick(s.order[Math.min(Math.max(i + by, 0), s.order.length - 1)]!)
      key.preventDefault()
      return true
    },
  })
  useEffect(() => {
    if (focused && !pickedNow.current) pick(s.order[0]!) // the row has the keyboard: show where it is
  }, [focused])
  const reset = <Button id="settings-tab-reset" label="Reset to default" disabled={s.order.join() === s.defaultOrder.join()} onPress={() => s.setOrder(s.defaultOrder)} />
  const tabs = s.order.map((tab, k) => {
    const lit = tab === held || tab === picked
    const bg = tab === held ? mix(DASH.raised, "#ffffff", 0.1) : tab === picked ? (focused ? DASH.cursor : DASH.raised) : tab === hover ? DASH.raised : undefined
    return (
      <box
        key={tab}
        ref={(n: Renderable | null) => void (n ? nodes.current.set(tab, n) : nodes.current.delete(tab))}
        flexDirection="row"
        height={1}
        flexShrink={0}
        paddingLeft={1}
        paddingRight={1}
        backgroundColor={bg}
        onMouseOver={() => setHover(tab)}
        onMouseOut={() => setHover((h) => (h === tab ? null : h))}
        onMouseDown={(e) => {
          if (e.button !== 0) return
          e.stopPropagation()
          focus()
          pick(tab)
          before.current = s.order.join()
        }}
        onMouseDrag={(e) => {
          setHeld(tab)
          place(tab, dropAt(tab, e.x, e.y), false)
        }}
        onMouseDragEnd={() => {
          setHeld(null)
          if (s.order.join() !== before.current) s.setOrder(s.order)
        }}
      >
        <text wrapMode="none" selectable={false /* a press here starts a drag, not a text selection */}>
          <span fg={DASH.faint}>{`${k + 1} `}</span>
          <span fg={lit || tab === hover ? DASH.text : DASH.muted} attributes={lit ? TextAttributes.BOLD : undefined}>
            {TAB_NAMES[tab]}
          </span>
        </text>
      </box>
    )
  })
  return (
    <Panel title="TAB ORDER" sub={<text fg={DASH.faint} wrapMode="none">drag a tab, or click one and use the arrows</text>} right={reset} flexShrink={0}>
      {/* the tabs, with the arrows beside them (under them in a narrow window) */}
      <box flexDirection="row" flexWrap="wrap" columnGap={4} rowGap={1} flexShrink={0}>
        <box ref={ref} flexDirection="row" flexWrap="wrap" columnGap={2} flexShrink={1} minWidth={0}>
          {tabs}
        </box>
        <box flexDirection="row" columnGap={1} flexShrink={0}>
          <Button id="settings-tab-left" label="← Move left" disabled={at <= 0} onPress={() => nudge(-1)} />
          <Button id="settings-tab-right" label="Move right →" disabled={at < 0 || at >= s.order.length - 1} onPress={() => nudge(1)} />
        </box>
      </box>
      <text fg={DASH.faint} wrapMode="word" marginTop={1} flexShrink={0}>
        {`Publish has its own green button at the top right, and ${PUBLISH_KEY} opens it.`}
      </text>
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

/** Every profile, with Delete… beside each one this window can delete (and why not beside the others) and New profile
 * under them, then the deleted ones kept in backups, each with Restore and Move to the Recycle Bin. */
function ProfilesPanel({ v }: { v: SettingsView }) {
  const s = useDash()
  const p = v.profiles
  const demo = () => s.bridge.emit("toast", { title: "Demo mode", body: "Profiles can't be added, deleted or restored in the demo.", severity: "information", timeout: 5 })
  const discard = `Move to the ${v.bin}`
  return (
    <Panel title="PROFILES" sub={<text fg={DASH.faint} wrapMode="none">one for each channel: its own accounts, stats and log-ins</text>} flexShrink={0}>
      {p.rows.map((row) => (
        <box key={row.key} flexDirection="row" height={3} flexShrink={0} alignItems="center" gap={1}>
          <box flexDirection="column" flexGrow={1} flexShrink={1} justifyContent="center">
            <text wrapMode="none">
              <span fg={DASH.good} attributes={TextAttributes.BOLD}>{row.current ? "● " : "  "}</span>
              <span fg={DASH.faint}>{`${row.number}  `}</span>
              <span fg={DASH.text} attributes={TextAttributes.BOLD}>
                {row.name}
              </span>
            </text>
            <text fg={DASH.muted} wrapMode="none">{`     ${row.note}`}</text>
          </box>
          {row.deletable ? (
            <Button
              id={`settings-delete-${row.number}`}
              label="Delete…"
              variant="error"
              minWidth={18}
              flexShrink={0}
              onPress={() => (v.demo ? demo() : void s.openDialog("delete_profile", s.bridge.call("delete_profile_info", row.key)))}
            />
          ) : null}
        </box>
      ))}
      <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
        <Button id="settings-new-profile" label="+ New profile" onPress={() => (v.demo ? demo() : s.nav.onboard("new", "settings"))} />
      </box>
      {p.deleted.length ? (
        <text wrapMode="none" marginTop={2} flexShrink={0}>
          <span fg={DASH.text} attributes={TextAttributes.BOLD}>
            DELETED
          </span>
          <span fg={DASH.faint}>{"   kept whole in backups until you restore them"}</span>
        </text>
      ) : null}
      {p.deleted.map((d, i) => (
        <box key={d.id} flexDirection="row" height={3} flexShrink={0} alignItems="center" gap={1}>
          <box flexDirection="column" flexGrow={1} flexShrink={1} justifyContent="center">
            <text fg={DASH.text} attributes={TextAttributes.BOLD} wrapMode="none">
              {`     ${d.name}`}
            </text>
            <text fg={DASH.muted} wrapMode="none">{`     ${[d.when, d.size, d.where].filter(Boolean).join(" · ")}`}</text>
          </box>
          <Button id={`settings-restore-${i}`} label="Restore" variant="primary" flexShrink={0} onPress={() => (v.demo ? demo() : s.bridge.send("restore_profile", d.id))} />
          <Button
            id={`settings-discard-${i}`}
            label={discard}
            flexShrink={0}
            onPress={() => (v.demo ? demo() : s.set({ dialog: { kind: "discard_profile", data: { ...d, bin: v.bin } } }))}
          />
        </box>
      ))}
    </Panel>
  )
}

/** Are you sure? A deleted profile's backup goes to the Recycle Bin (Trash) to free its space: Restore can't bring it
 * back after that. */
export function DiscardProfile({ data, close }: { data: DeletedProfile & { bin: string }; close: () => void }) {
  const s = useDash()
  return (
    <Modal name="discard-profile" title={`MOVE ${data.name.toUpperCase()} TO THE ${data.bin.toUpperCase()}`}>
      <text fg={DASH.muted} wrapMode="word" flexShrink={0}>
        <span fg={DASH.text} attributes={TextAttributes.BOLD}>
          {data.name}
        </span>
        {`'s backup (${[data.size, data.where].filter(Boolean).join(", in ")}) goes to the ${data.bin} to free its space. Restore can't bring it back after that.`}
      </text>
      <box flexDirection="row" justifyContent="flex-end" height={1} marginTop={2} flexShrink={0} gap={1}>
        <Button id="db-cancel" label="Cancel" autoFocus onPress={close} />
        <Button
          id="db-discard"
          label={`Move to the ${data.bin}`}
          variant="error"
          onPress={() => {
            close()
            s.bridge.send("discard_profile", data.id)
          }}
        />
      </box>
    </Modal>
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

/** The box for the channel's name, under its instruction (here, and before deleting a profile: Profiles.tsx). */
export function Confirm({ id, word, typed, setTyped, onSubmit }: { id: string; word: string; typed: string; setTyped: (t: string) => void; onSubmit: () => void }) {
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
