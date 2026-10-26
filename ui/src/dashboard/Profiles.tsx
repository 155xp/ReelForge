// Profiles: one for each channel (studio/profiles.py). The button at the top left shows this window's profile (with a
// red dot when another one has unread notifications); its menu lists every profile, with the platforms each has
// connected and its unread notifications, and offers a new profile, this one's settings, and removing another one.
// Picking a profile shows it in this window: ui/src/root.tsx starts the Python side again on it.

import type { KeyEvent, Renderable } from "@opentui/core"
import { useState } from "react"
import { useView } from "../bridge"
import { useFocus, FocusScope } from "../lib/focus"
import { cellLen, lines, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Button } from "../ui/Button"
import { Line } from "../ui/Line"
import { Modal, Wrapped } from "../ui/Panels"
import { useDash } from "./state"
import type { ProfileRow, ProfilesMenu, ProfileView } from "./types"

export const MENU_WIDTH = 64

/** The button: the profile's name with ▾, and a red dot while another profile has something unread. */
export function profileButton(p: ProfileView, open: boolean): Segs {
  const bg = open ? mix(DASH.chip, "#ffffff", 0.12) : DASH.chip
  const out: Segs = [[` ${p.name} `, `bold #ffffff on ${bg}`, ["profiles"]], ["▾ ", `${DASH.muted} on ${bg}`, ["profiles"]]]
  if (p.elsewhere > 0) out.push(["●", `bold ${DASH.bad}`, ["profiles"]])
  return out
}

export function ProfileButton() {
  const s = useDash()
  const view = useView<ProfileView>(s.bridge, "profile") ?? s.init.profile
  return (
    <box flexDirection="row" height={3} alignItems="center" flexShrink={0} paddingLeft={2}>
      <Line segs={profileButton(view, s.dialog?.kind === "profiles")} />
    </box>
  )
}

type Item = { kind: "profile"; row: ProfileRow } | { kind: "new" } | { kind: "settings" }

/** One row of the menu, as styled text fitted to the menu's width. */
function rowSegs(row: ProfileRow, width: number, highlighted: boolean): Segs {
  const out: Segs = []
  out.push([row.current ? " ● " : "   ", `bold ${DASH.good}`])
  out.push([`${row.number}  `, DASH.muted])
  const tags: Segs = []
  for (const p of row.platforms) tags.push([`${p.short} `, `bold ${p.color}`])
  if (!row.platforms.length) tags.push(["nothing connected ", DASH.muted])
  const unread: Segs = row.unread ? [[`${row.unread} new `, `bold ${DASH.bad}`]] : []
  const remove: Segs = !row.current && !row.main ? [[" Remove ", `${highlighted ? "#ffffff" : DASH.muted} on ${DASH.chip}`]] : []
  const right = [...tags, ...unread, ...(remove.length ? [[" ", ""] as [string, string]] : []), ...remove]
  const used = cellLen(out.map((x) => x[0]).join("")) + cellLen(right.map((x) => x[0]).join("")) + 2
  let name = row.name
  const room = Math.max(width - used, 8)
  if (cellLen(name) > room) name = name.slice(0, Math.max(room - 1, 1)) + "…"
  out.push([name, row.current ? "bold #ffffff" : "bold"])
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
    if (!item) return
    if (data.demo) {
      close()
      s.bridge.emit("toast", { title: "Demo mode", body: "Profiles can't be switched, added or removed in the demo.", severity: "information", timeout: 5 })
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
    if (remove) {
      if (item.row.current || item.row.main) return
      return void s.openDialog("remove_profile", s.bridge.call("remove_profile_info", item.row.key))
    }
    s.showProfile(item.row.key)
  }
  const { ref } = useFocus("profile-menu", {
    autoFocus: true,
    onKey: (key: KeyEvent) => {
      if (key.name === "up") setIndex((i) => (i - 1 + items.length) % items.length)
      else if (key.name === "down") setIndex((i) => (i + 1) % items.length)
      else if (key.name === "return" || key.name === "enter" || key.name === "space") run(items[index])
      else if (key.name === "delete") run(items[index], true)
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
        <text wrapMode="none" fg={on ? "#ffffff" : DASH.text}>
          {label}
        </text>
      </box>
    )
  }
  return (
    <box
      ref={ref}
      position="absolute"
      left={s.init.anvil.length ? 10 : 2}
      top={3}
      width={MENU_WIDTH}
      border
      borderStyle="rounded"
      borderColor={mix(DASH.border, "#ffffff", 0.15)}
      title=" PROFILES "
      titleColor={DASH.muted}
      backgroundColor={DASH.surface}
      flexDirection="column"
      paddingLeft={1}
      paddingRight={1}
      onMouseDown={(e) => e.stopPropagation()}
    >
      <text fg={DASH.muted} wrapMode="none" flexShrink={0}>
        {" One for each channel: its own accounts, stats and log-ins"}
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
      <text fg={DASH.muted} wrapMode="none" flexShrink={0} marginTop={1}>
        {" ↑↓ pick  ·  Enter opens  ·  Esc closes"}
      </text>
    </box>
  )
}

/** Are you sure? Removing a profile moves its folder to the Recycle Bin (or the Trash): you can put it back. */
export function RemoveProfile({ data, close }: { data: { key: string; name: string; note: Segs; bin: string }; close: () => void }) {
  const s = useDash()
  return (
    <Modal name="remove-profile" title={`REMOVE ${data.name.toUpperCase()}`}>
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      <box flexDirection="row" justifyContent="flex-end" height={3} marginTop={1} flexShrink={0} gap={1}>
        <Button id="rp-cancel" label="Cancel" autoFocus onPress={close} />
        <Button
          id="rp-remove"
          label={`Move to ${data.bin}`}
          variant="error"
          onPress={() => {
            close()
            void s.bridge.call<boolean>("remove_profile", data.key)
          }}
        />
      </box>
    </Modal>
  )
}
