// The Publish tab: every finished video with its post already written. Each platform's button opens its upload page,
// copies exactly the text it needs and shows the file, so you drag it in and press Post; ReelForge spots the post by
// itself. Under the list, the best time to post on each platform.

import { TextAttributes } from "@opentui/core"
import { useEffect } from "react"
import { useView } from "../bridge"
import type { Parts, Segs } from "../lib/styled"
import { DASH } from "../theme"
import { Button } from "../ui/Button"
import { TextField } from "../ui/Fields"
import { Fitted, Line } from "../ui/Line"
import { OptionList, Table } from "../ui/Lists"
import { Panel, Scroll } from "../ui/Panels"
import { useDash } from "./state"
import type { FilesView, PlatformInfo, PreviewView, TableView } from "./types"

export function Publish() {
  return (
    <box flexDirection="row" flexGrow={1} marginTop={1}>
      {/* A third of the width for the videos (a min width would count towards Yoga's share of the rest). */}
      <box flexDirection="column" width="33%" minWidth={40} flexShrink={0}>
        <Files />
        <Best />
      </box>
      <Form />
    </box>
  )
}

function Files() {
  const s = useDash()
  const files = useView<FilesView>(s.bridge, "files")
  return (
    <Panel flexGrow={1}>
      <Line segs={files?.heading} base={DASH.muted} />
      <OptionList
        id="file-list"
        items={files?.items ?? []}
        selected={files?.selected}
        onSelect={(id) => {
          s.bridge.emit("files", { ...files!, selected: id })
          s.bridge.send("pick_file", id)
        }}
        onMenu={(id) => void s.openDialog("remove", s.bridge.call("remove_menu", id))}
        empty={
          <box flexDirection="column">
            {(files?.empty ?? []).map((l, i) => (
              <Line key={i} segs={l} />
            ))}
          </box>
        }
      />
    </Panel>
  )
}

function Best() {
  const s = useDash()
  const best = useView<{ title: Parts; lines: Parts[] }>(s.bridge, "best")
  return (
    <Panel flexShrink={0}>
      <Fitted parts={best?.title} base={DASH.muted} flexGrow={0} />
      {(best?.lines ?? []).map((l, i) => (
        <Fitted key={i} parts={l} flexGrow={0} />
      ))}
    </Panel>
  )
}

function Form() {
  const s = useDash()
  const { init } = s
  const preview = useView<PreviewView>(s.bridge, "preview")
  const posted = useView<{ line: Segs; done: Record<string, boolean> }>(s.bridge, "posted")
  const uploads = useView<TableView>(s.bridge, "uploads")
  const connected = useView<{ platforms: PlatformInfo[] }>(s.bridge, "platforms")
  useEffect(() => {
    // the preview of the form as it is (another tab and back, or nothing picked yet)
    s.bridge.send("form_changed", s.caption, s.tags)
  }, [])
  const changed = (caption: string, tags: string) => {
    s.set({ caption, tags })
    s.bridge.send("form_changed", caption, tags)
  }
  const ps = connected?.platforms ?? init.platforms // only the connected platforms have buttons
  const copies = init.copies
  // Each copy button sits under its platform's button, both as wide as the wider label.
  const widths: Record<string, number> = Object.fromEntries(
    ps.map((p) => [p.key, Math.max(`${p.name} →`.length, (copies[p.key]?.[1] ?? "").length) + 4]),
  )
  const openAll = ps.length > 1 ? `Open all ${ps.length} →` : null
  return (
    <Panel flexGrow={1}>
      <Scroll flexGrow={1} scrollY>
        <box marginTop={1} flexShrink={0}>
          <Line segs={preview?.caption ?? [["Caption", ""]]} base={DASH.muted} />
        </box>
        <TextField
          id="f-caption"
          value={s.caption}
          maxLength={200}
          placeholder={init.caption_placeholder}
          onChange={(v) => changed(v, s.tags)}
        />
        <box marginTop={1} flexShrink={0}>
          <Line segs={preview?.tags ?? [["Hashtags", ""]]} base={DASH.muted} />
        </box>
        <TextField id="f-tags" value={s.tags} placeholder={init.tags_placeholder} onChange={(v) => changed(s.caption, v)} />
        <box border borderStyle="rounded" borderColor={DASH.border} marginTop={1} paddingLeft={1} paddingRight={1} flexDirection="column" flexShrink={0}>
          <text fg={DASH.muted} attributes={TextAttributes.BOLD} flexShrink={0}>
            PREVIEW
          </text>
          {(preview?.rows ?? []).map((r) => (
            <box key={r.name} flexDirection="row" flexShrink={0}>
              <text fg={r.color} attributes={TextAttributes.BOLD} width={10} flexShrink={0}>
                {r.name}
              </text>
              <text fg={DASH.text} wrapMode="word" flexGrow={1}>
                {r.text}
              </text>
            </box>
          ))}
        </box>
        <box marginTop={1} paddingLeft={1} paddingRight={1} flexShrink={0}>
          <Line segs={posted?.line} />
        </box>
        <box marginTop={1} flexShrink={0}>
          <Line segs={[["UPLOAD  ", "bold"], ["each button opens the upload page, copies that platform's text and shows the file", DASH.muted]]} />
        </box>
        <Scroll scrollX scrollY={false} height={6} flexShrink={0}>
          <box flexDirection="row" height={3} flexShrink={0}>
            {openAll ? (
              <Button
                id="open-all"
                label={openAll}
                variant="primary"
                marginRight={1}
                onPress={() => s.bridge.send("open_all", s.caption, s.tags)}
              />
            ) : null}
            {ps.map((p) => (
              <Button
                key={p.key}
                id={`open-${p.key}`}
                label={`${p.name} ${posted?.done?.[p.key] ? "✓" : "→"}`}
                width={widths[p.key]}
                marginRight={1}
                onPress={() => s.bridge.send("open_upload", p.key, s.caption, s.tags)}
              />
            ))}
            <Button id="reveal" label="Show file" marginRight={1} onPress={() => s.bridge.send("reveal_file")} />
          </box>
          <box flexDirection="row" height={3} flexShrink={0}>
            {openAll ? <box width={openAll.length + 4} marginRight={1} flexShrink={0} /> : null}
            {ps.map((p) =>
              copies[p.key] ? (
                <Button
                  key={p.key}
                  id={copies[p.key]![0]}
                  label={copies[p.key]![1]}
                  width={widths[p.key]}
                  marginRight={1}
                  onPress={() => s.bridge.send("copy_field", copies[p.key]![0], s.caption, s.tags)}
                />
              ) : null,
            )}
            {ps.length && !ps.some((p) => p.key === "x") ? (
              // the caption on its own, for when X (whose post it is) isn't connected
              <Button
                id="copy-caption-alone"
                label="Copy caption"
                marginRight={1}
                onPress={() => s.bridge.send("copy_field", "copy-caption-alone", s.caption, s.tags)}
              />
            ) : null}
          </box>
        </Scroll>
        <box marginTop={1} flexShrink={0}>
          <Line segs={uploads?.heading} />
        </box>
        <Table id="uploads-table" data={uploads} cursor={false} rowsShown={Math.min(Math.max(uploads?.rows.length ?? 0, 1), 11)} />
      </Scroll>
    </Panel>
  )
}
