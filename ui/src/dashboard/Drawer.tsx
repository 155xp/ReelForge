// The notifications drawer: it slides in from the right over the tab, under the bell. Newest first, each with its
// unread dot and icon, its title, the start of its body and how long ago, and a small × on its right that deletes it
// (red under the mouse). Click one to go to what it's about; Delete deletes the highlighted one; Mark all read and
// Clear all are at the top.

import { TextAttributes, type Renderable } from "@opentui/core"
import { useState } from "react"
import { useView } from "../bridge"
import { segsLen, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Line } from "../ui/Line"
import { OptionList, type Option } from "../ui/Lists"
import { Asleep } from "../ui/Mascot"
import { MOTION, useTween } from "../ui/Motion"
import { TOP_ROWS, useDash } from "./state"
import type { NotesView } from "./types"

export const DRAWER_WIDTH = 52
const BODY_LINES = 3 // a notification shows at most this many lines of its body
const X = 3 // the ×'s column, and a space either side

/** Plain text wrapped at spaces to `width` columns (a word longer than that is cut). */
export function wrap(text: string, width: number): string[] {
  const out: string[] = []
  for (const para of text.split("\n")) {
    let line = ""
    for (const word of para.split(/\s+/).filter(Boolean)) {
      if (!line) line = word
      else if (line.length + 1 + word.length <= width) line += " " + word
      else {
        out.push(line)
        line = word
      }
      while (line.length > width) {
        out.push(line.slice(0, width))
        line = line.slice(width)
      }
    }
    out.push(line)
  }
  return out
}

/** The drawer, sliding in while it's open and out when it closes. */
export function Drawer() {
  const s = useDash()
  const shown = useTween(s.drawer ? 1 : 0, { ms: s.drawer ? 220 : 160, ease: "outCirc" })
  if (!s.drawer && (shown <= 0.01 || !MOTION)) return null
  return (
    <box position="absolute" top={TOP_ROWS} bottom={1} right={Math.round((shown - 1) * (DRAWER_WIDTH + 2))} width={DRAWER_WIDTH + 2} zIndex={30} flexDirection="row">
      <Shadow />
      <Notes />
    </box>
  )
}

/** A soft shadow down the drawer's left edge, two columns fading into the window. */
function Shadow() {
  const near = mix(DASH.bg, "#000000", 0.55)
  const far = mix(DASH.bg, "#000000", 0.25)
  return (
    <box width={2} flexShrink={0} flexDirection="row">
      <box width={1} backgroundColor={far} />
      <box width={1} backgroundColor={near} />
    </box>
  )
}

function Notes() {
  const s = useDash()
  const notes = useView<NotesView>(s.bridge, "notes")
  const [width, setWidth] = useState(DRAWER_WIDTH - 4)
  const bg = DASH.surface
  const markW = 4
  const textW = Math.max(width - 2 - markW - X, 8) // 2: the highlighted one's edge
  const items: Option[] = (notes?.items ?? []).map((n) => {
    const title = wrap(n.title.map((t) => t[0]).join(""), textW)
    const body = n.body ? wrap(n.body, textW).slice(0, BODY_LINES) : []
    const indent: Segs[number] = [" ".repeat(segsLen(n.mark)), ""]
    const titleStyle = `bold ${n.read ? DASH.muted : DASH.text}`
    const lines: Segs[] = [
      [...n.mark, [title[0] ?? "", titleStyle]],
      ...title.slice(1).map((t): Segs => [indent, [t, titleStyle]]),
      ...body.map((b): Segs => [indent, [b, n.read ? DASH.faint : DASH.muted]]),
      [indent, [n.ago, DASH.faint]],
    ]
    return { id: String(n.id), lines }
  })
  const del = (id: string) => s.bridge.send("delete_note", Number(id))
  return (
    <box
      flexDirection="column"
      flexGrow={1}
      backgroundColor={bg}
      paddingLeft={2}
      paddingRight={1}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width - 3)
      }}
    >
      <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
        <box flexGrow={1}>
          <Line segs={notes?.head} />
        </box>
        <Line segs={notes?.close} />
      </box>
      <box height={1} marginTop={1} marginBottom={1} flexShrink={0}>
        <Line segs={notes?.tools} />
      </box>
      <OptionList
        id="notes"
        items={items}
        spaced
        selected={s.note}
        bg={bg}
        onSelect={(id) => s.set({ note: id })}
        onActivate={(id) => s.bridge.send("open_note", Number(id))}
        onDelete={del}
        aside={(it, lines) => <Cross id={it.id} lines={lines} onPress={() => del(it.id)} />}
        empty={
          <Asleep>
            <text fg={DASH.muted} wrapMode="word">
              {notes?.empty ?? ""}
            </text>
          </Asleep>
        }
      />
    </box>
  )
}

/** A notification's ×, beside its title: faint, red under the mouse. */
function Cross({ id, lines, onPress }: { id: string; lines: number; onPress: () => void }) {
  const [hover, setHover] = useState(false)
  return (
    <box
      key={id}
      width={X}
      height={lines}
      flexShrink={0}
      alignItems="center"
      backgroundColor={hover ? mix(DASH.surface, DASH.bad, 0.18) : undefined}
      onMouseOver={() => setHover(true)}
      onMouseOut={() => setHover(false)}
      onMouseDown={(e) => {
        e.stopPropagation()
        if (e.button === 0) onPress()
      }}
    >
      <text fg={hover ? DASH.bad : DASH.faint} attributes={hover ? TextAttributes.BOLD : undefined}>
        ×
      </text>
    </box>
  )
}
