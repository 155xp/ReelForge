// Profiles: one for each channel (studio/profiles.py). The button at the top left shows this window's profile (with a
// red dot when another one has unread notifications); its menu lists every profile, with the platforms each has
// connected and its unread notifications, and offers a new profile, this one's settings, and deleting another one
// (the Settings tab's Profiles panel deletes them too, and restores them). Picking a profile shows it in this window:
// ui/src/root.tsx starts the Python side again on it.

import { TextAttributes, type KeyEvent, type Renderable } from "@opentui/core"
import { useState } from "react"
import { useView } from "../bridge"
import { useFocus, FocusScope } from "../lib/focus"
import { cellLen, lines, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Button } from "../ui/Button"
import { Line } from "../ui/Line"
import { Modal, Wrapped } from "../ui/Panels"
import { Confirm, typedMatches } from "./Settings"
import { useDash } from "./state"
import type { ProfileRow, ProfilesMenu, ProfileView } from "./types"

export const MENU_WIDTH = 64

/** The button: a pill with the profile's name (cut short to `room` columns) and ▾, and a red dot while another
 * profile has something unread. */
export function profileButton(p: ProfileView, open: boolean, hover = false, room = 40): Segs {
  const bg = open ? mix(DASH.raised, "#ffffff", 0.1) : hover ? mix(DASH.raised, "#ffffff", 0.05) : DASH.raised
  const name = cellLen(p.name) > room ? p.name.slice(0, Math.max(room - 1, 1)) + "…" : p.name
  const out: Segs = [
    ["▐", bg, ["profiles"]],
    [` ${name} `, `bold ${DASH.text} on ${bg}`, ["profiles"]],
    ["▾", `${DASH.muted} on ${bg}`, ["profiles"]],
    [" ", `on ${bg}`, ["profiles"]],
    ["▌", bg, ["profiles"]],
  ]
  if (p.elsewhere > 0) out.push([" ●", `bold ${DASH.bad}`, ["profiles"]])
  return out
}

export function ProfileButton({ room = 40 }: { room?: number }) {
  const s = useDash()
  const view = useView<ProfileView>(s.bridge, "profile") ?? s.init.profile
  const [hover, setHover] = useState(false)
  return (
    <box flexDirection="row" height={3} alignItems="center" flexShrink={0} onMouseOver={() => setHover(true)} onMouseOut={() => setHover(false)}>
      <Line segs={profileButton(view, s.dialog?.kind === "profiles", hover, room)} />
    </box>
  )
}

type Item = { kind: "profile"; row: ProfileRow } | { kind: "new" } | { kind: "settings" }

/** One row of the menu, as styled text fitted to the menu's width. */
function rowSegs(row: ProfileRow, width: number, highlighted: boolean): Segs {
  const out: Segs = []
  out.push([highlighted ? "▌" : " ", DASH.focus])
  out.push([row.current ? " ● " : "   ", `bold ${DASH.good}`])
  out.push([`${row.number}  `, DASH.faint])
  const tags: Segs = []
  for (const p of row.platforms) tags.push([`${p.short} `, `bold ${p.color}`])
  if (!row.platforms.length) tags.push(["nothing connected ", DASH.muted])
  const unread: Segs = row.unread ? [[`${row.unread} new `, `bold ${DASH.bad}`]] : []
  const remove: Segs = !row.current && !row.main ? [[" Delete ", highlighted ? `${DASH.text} on ${mix(DASH.bad, DASH.cursor, 0.55)}` : DASH.faint]] : []
  const right = [...tags, ...unread, ...(remove.length ? [[" ", ""] as [string, string]] : []), ...remove]
  const used = cellLen(out.map((x) => x[0]).join("")) + cellLen(right.map((x) => x[0]).join("")) + 2
  let name = row.name
  const room = Math.max(width - used, 8)
  if (cellLen(name) > room) name = name.slice(0, Math.max(room - 1, 1)) + "…"
  out.push([name, row.current ? `bold ${DASH.text}` : highlighted ? DASH.text : DASH.muted])
  out.push([" ".repeat(Math.max(width - used - cellLen(name) + 2, 1)), ""])
  return [...out, ...right]
}

/** The menu, under the button: its own Tab order (FocusScope), so the arrows, Enter and the numbers go to it. */
export function ProfileMenu({ data, close }: { data: ProfilesMenu; close: () => void }) {
  return (
    <box position="absolute" left={0} top={0} width="100%" height="100%" zIndex={50} onMouseDown={() => close()}>
      <FocusScope name="profiles">
        <MenuBox data={data} close={close} />
      </FocusScope>
    </box>
  )
}

function MenuBox({ data, close }: { data: ProfilesMenu; close: () => void }) {
  const s = useDash()
  const current = data.rows.find((r) => r.current)
  const items: Item[] = [...data.rows.map((row) => ({ kind: "profile", row }) as Item), { kind: "new" }]
  if (current) items.push({ kind: "settings" })
  const [index, setIndex] = useState(Math.max(data.rows.findIndex((r) => r.current), 0))
  const width = MENU_WIDTH - 4
  const run = (item: Item | undefined, remove = false) => {
    if (!item || (remove && item.kind !== "profile")) return
    if (remove && item.kind === "profile" && item.row.why) {
      // this window's own profile, the first one, or one open in another window: say why, and stay in the menu
      s.bridge.emit("toast", { title: "Can't delete it", body: item.row.why, severity: "warning", timeout: 10 })
      return
    }
    if (data.demo) {
      close()
      s.bridge.emit("toast", { title: "Demo mode", body: "Profiles can't be switched, added or deleted in the demo.", severity: "information", timeout: 5 })
      return
    }
    if (item.kind === "new") {
      close()
      return s.nav.onboard("new", s.tab)
    }
    if (item.kind === "settings") {
      close()
      return s.nav.onboard("settings", s.tab)
    }
    if (remove) return void s.openDialog("delete_profile", s.bridge.call("delete_profile_info", item.row.key))
    s.showProfile(item.row.key)
  }
  const { ref } = useFocus("profile-menu", {
    autoFocus: true,
    onKey: (key: KeyEvent) => {
      if (key.name === "up") setIndex((i) => (i - 1 + items.length) % items.length)
      else if (key.name === "down") setIndex((i) => (i + 1) % items.length)
      else if (key.name === "return" || key.name === "enter" || key.name === "space") run(items[index])
      else if (key.name === "delete" || key.name === "backspace") run(items[index], true) // a Mac's delete is backspace
      else if (/^[1-9]$/.test(key.name) && Number(key.name) <= data.rows.length) run(items[Number(key.name) - 1])
      else if (key.name === "p") close()
      else return false
      key.preventDefault()
      return true
    },
  })
  const action = (label: string, i: number) => {
    const on = i === index
    return (
      <box
        key={label}
        height={1}
        flexShrink={0}
        backgroundColor={on ? DASH.cursor : undefined}
        onMouseOver={() => setIndex(i)}
        onMouseDown={(e) => {
          if (e.button !== 0) return
          e.stopPropagation()
          run(items[i])
        }}
      >
        <text wrapMode="none" fg={on ? DASH.text : DASH.muted}>
          <span fg={DASH.focus}>{on ? "▌" : " "}</span>
          {label}
        </text>
      </box>
    )
  }
  return (
    <box
      ref={ref}
      position="absolute"
      left={s.init.anvil.length ? 12 : 1}
      top={3}
      width={MENU_WIDTH}
      border
      borderStyle="rounded"
      borderColor={mix(DASH.border, "#ffffff", 0.08)}
      backgroundColor={DASH.surface}
      flexDirection="column"
      paddingLeft={1}
      paddingRight={1}
      paddingTop={1}
      paddingBottom={1}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <text wrapMode="none" flexShrink={0}>
        <span fg={DASH.text} attributes={TextAttributes.BOLD}>{" PROFILES"}</span>
        <span fg={DASH.faint}>{"   one for each channel: its own accounts, stats and log-ins"}</span>
      </text>
      <box height={1} flexShrink={0} />
      {data.rows.map((row, i) => {
        const on = i === index
        const segs = rowSegs(row, width, on)
        const removeAt = !row.current && !row.main ? width - 6 : -1
        return (
          <box
            key={row.key}
            height={1}
            flexShrink={0}
            backgroundColor={on ? DASH.cursor : undefined}
            onMouseOver={() => setIndex(i)}
            onMouseDown={function (this: Renderable, e) {
              if (e.button !== 0) return
              e.stopPropagation()
              const x = e.x - this.x
              run(items[i], removeAt >= 0 && x >= removeAt)
            }}
          >
            <Line segs={segs} base={DASH.text} />
          </box>
        )
      })}
      <text fg={DASH.border} wrapMode="none" flexShrink={0} marginTop={1}>
        {"─".repeat(width)}
      </text>
      {action(" +  New profile", data.rows.length)}
      {current ? action(` ›  ${data.onboarded ? "Settings for" : "Set up"} ${current.name}`, data.rows.length + 1) : null}
      <text fg={DASH.faint} wrapMode="none" flexShrink={0} marginTop={1}>
        {"  ↑↓ pick   Enter opens   Del deletes   Esc closes"}
      </text>
    </box>
  )
}

/** What the dialog before deleting a profile shows (dashboard/service.py delete_profile_info). */
export interface DeleteProfileData {
  key: string
  name: string
  note: Segs
  word: string // what to type: its name
}

/** Are you sure? Deleting a profile takes it out of ReelForge once you type its name: its folder moves whole into
 * backups, and Restore on the Settings tab puts it back. */
export function DeleteProfile({ data, close }: { data: DeleteProfileData; close: () => void }) {
  const s = useDash()
  const [typed, setTyped] = useState("")
  const ok = typedMatches(typed, data.word)
  const go = () => {
    if (!ok) return
    close()
    void s.bridge.call<boolean>("delete_profile", data.key, typed)
  }
  return (
    <Modal name="delete-profile" title={`DELETE ${data.name.toUpperCase()}`} width={84}>
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      <Confirm id="dp-word" word={data.word} typed={typed} setTyped={setTyped} onSubmit={go} />
      <box flexDirection="row" justifyContent="flex-end" height={1} marginTop={2} flexShrink={0} gap={1}>
        <Button id="dp-cancel" label="Cancel" onPress={close} />
        <Button id="dp-delete" label={`Delete ${data.name}`} variant="error" disabled={!ok} onPress={go} />
      </box>
    </Modal>
  )
}
