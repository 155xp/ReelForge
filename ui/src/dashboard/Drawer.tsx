// The notifications drawer, on the right under the bell: newest first, each with its unread dot and icon, its title,
// the start of its body and how long ago, and the big × on its right that deletes it. Click one to go to what it's
// about; Delete deletes the highlighted one; Mark all read and Clear all are at the top.

import type { Renderable } from "@opentui/core"
import { useState } from "react"
import { useView } from "../bridge"
import { segsLen, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Cells } from "../ui/Cells"
import { cross, X_WIDTH } from "../ui/Graphics"
import { Line } from "../ui/Line"
import { OptionList, type Option } from "../ui/Lists"
import { useDash } from "./state"
import type { NotesView } from "./types"

const BODY_LINES = 3 // a notification shows at most this many lines of its body

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

export function Drawer() {
  const s = useDash()
  const notes = useView<NotesView>(s.bridge, "notes")
  const [width, setWidth] = useState(46)
  const markW = 4
  const textW = Math.max(width - markW - 1 - X_WIDTH - 1, 8)
  const items: Option[] = (notes?.items ?? []).map((n) => {
    const title = wrap(n.title.map((t) => t[0]).join(""), textW)
    const body = n.body ? wrap(n.body, textW).slice(0, BODY_LINES) : []
    const indent: Segs[number] = [" ".repeat(segsLen(n.mark)), ""]
    const titleStyle = n.title[0]?.[1] ?? ""
    const lines: Segs[] = [
      [...n.mark, [title[0] ?? "", titleStyle]],
      ...title.slice(1).map((t): Segs => [indent, [t, titleStyle]]),
      ...body.map((b): Segs => [indent, [b, DASH.muted]]),
      [indent, [n.ago, "#5c6370"]],
    ]
    return { id: String(n.id), lines }
  })
  const del = (id: string) => s.bridge.send("delete_note", Number(id))
  return (
    <box
      width={48}
      flexShrink={0}
      flexDirection="column"
      backgroundColor={DASH.surface}
      border={["left"]}
      borderStyle="heavy"
      borderColor={DASH.border}
      paddingLeft={1}
      paddingRight={1}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width - 4)
      }}
    >
      <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
        <box flexGrow={1}>
          <Line segs={notes?.head} />
        </box>
        <Line segs={notes?.close} />
      </box>
      <box height={1} marginBottom={1} flexShrink={0}>
        <Line segs={notes?.tools} />
      </box>
      <OptionList
        id="notes"
        items={items}
        spaced
        selected={s.note}
        bg={DASH.surface}
        onSelect={(id) => s.set({ note: id })}
        onActivate={(id) => s.bridge.send("open_note", Number(id))}
        onDelete={del}
        aside={(it, lines) => <Cross id={it.id} lines={lines} onPress={() => del(it.id)} />}
        empty={<text fg={DASH.muted} wrapMode="word">{notes?.empty ?? ""}</text>}
      />
    </box>
  )
}

/** A notification's ×, in the middle of its height: grey, red under the mouse. */
function Cross({ id, lines, onPress }: { id: string; lines: number; onPress: () => void }) {
  const s = useDash()
  const [hover, setHover] = useState(false)
  const art = cross(lines, s.init.quadrants, hover ? DASH.bad : "#6e7681")
  return (
    <box
      key={id}
      width={X_WIDTH + 1}
      paddingLeft={1}
      flexShrink={0}
      justifyContent="center"
      backgroundColor={hover ? mix(DASH.surface, DASH.bad, 0.15) : undefined}
      onMouseOver={() => setHover(true)}
      onMouseOut={() => setHover(false)}
      onMouseDown={(e) => {
        e.stopPropagation()
        if (e.button === 0) onPress()
      }}
    >
      <Cells grid={art} />
    </box>
  )
}
