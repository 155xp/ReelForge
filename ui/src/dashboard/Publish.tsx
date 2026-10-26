// The Publish tab: every finished video with its post already written. Each platform's button opens its upload page,
// copies exactly the text it needs and shows the file, so you drag it in and press Post; ReelForge spots the post by
// itself. Under the list, the best time to post on each platform.

import { TextAttributes } from "@opentui/core"
import { useEffect } from "react"
import { useView } from "../bridge"
import type { Parts, Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Button } from "../ui/Button"
import { TextField } from "../ui/Fields"
import { Fitted, Line } from "../ui/Line"
import { OptionList, Table } from "../ui/Lists"
import { Asleep } from "../ui/Mascot"
import { Panel, Scroll } from "../ui/Panels"
import { useDash } from "./state"
import type { FilesView, PlatformInfo, PreviewView, TableView } from "./types"

export function Publish() {
  return (
    <box flexDirection="row" flexGrow={1} marginTop={1} gap={1}>
      {/* A third of the width for the videos (a min width would count towards Yoga's share of the rest). */}
      <box flexDirection="column" width="33%" minWidth={44} flexShrink={0} gap={1}>
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
    <Panel flexGrow={1} paddingX={1}>
      <box height={1} marginBottom={1} paddingLeft={1} flexShrink={0}>
        <Line segs={files?.heading} base={DASH.faint} />
      </box>
      <OptionList
        id="file-list"
        items={files?.items ?? []}
        selected={files?.selected}
        spaced
        onSelect={(id) => {
          s.bridge.emit("files", { ...files!, selected: id })
          s.bridge.send("pick_file", id)
        }}
        onMenu={(id) => void s.openDialog("remove", s.bridge.call("remove_menu", id))}
        empty={
          <Asleep>
            <box flexDirection="column">
              {(files?.empty ?? []).map((l, i) => (
                <Line key={i} segs={l} />
              ))}
            </box>
          </Asleep>
        }
      />
    </Panel>
  )
}

function Best() {
  const s = useDash()
  const best = useView<{ title: Parts; lines: Parts[] }>(s.bridge, "best")
  return (
    <Panel flexShrink={0} paddingBottom={1}>
      <box height={1} marginBottom={1} flexShrink={0}>
        <Fitted parts={best?.title} base={DASH.faint} flexGrow={0} />
      </box>
      {(best?.lines ?? []).map((l, i) => (
        <Fitted key={i} parts={l} flexGrow={0} />
      ))}
    </Panel>
  )
}

function Label({ segs, fallback }: { segs: Segs | undefined; fallback: string }) {
  return (
    <box marginTop={1} marginBottom={1} flexShrink={0}>
      <Line segs={segs ?? [[fallback, ""]]} base={DASH.muted} />
    </box>
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
    <Panel flexGrow={1} paddingTop={0}>
      <Scroll flexGrow={1} scrollY>
        <Label segs={preview?.caption} fallback="Caption" />
        <TextField
          id="f-caption"
          value={s.caption}
          maxLength={200}
          placeholder={init.caption_placeholder}
          onChange={(v) => changed(v, s.tags)}
        />
        <Label segs={preview?.tags} fallback="Hashtags" />
        <TextField id="f-tags" value={s.tags} placeholder={init.tags_placeholder} onChange={(v) => changed(s.caption, v)} />
        <box backgroundColor={mix(DASH.surface, DASH.bg, 0.5)} marginTop={2} paddingLeft={2} paddingRight={2} paddingTop={1} paddingBottom={1} flexDirection="column" flexShrink={0}>
          <text fg={DASH.faint} attributes={TextAttributes.BOLD} flexShrink={0} marginBottom={1}>
            PREVIEW
          </text>
          {(preview?.rows ?? []).map((r) => (
            <box key={r.name} flexDirection="row" flexShrink={0}>
              <text fg={r.color} attributes={TextAttributes.BOLD} width={12} flexShrink={0}>
                {r.name}
              </text>
              <text fg={DASH.text} wrapMode="word" flexGrow={1}>
                {r.text}
              </text>
            </box>
          ))}
        </box>
        <box marginTop={1} flexShrink={0}>
          <Line segs={posted?.line} />
        </box>
        <box marginTop={2} marginBottom={1} flexShrink={0}>
          <Line segs={[["UPLOAD  ", "bold"], ["each button opens the upload page, copies that platform's text and shows the file", DASH.faint]]} />
        </box>
        <Scroll scrollX scrollY={false} height={4} flexShrink={0}>
          <box flexDirection="row" height={1} flexShrink={0}>
            {openAll ? (
              <Button
                id="open-all"
                label={openAll}
                variant="primary"
                marginRight={2}
                onPress={() => s.bridge.send("open_all", s.caption, s.tags)}
              />
            ) : null}
            {ps.map((p) => (
              <Button
                key={p.key}
                id={`open-${p.key}`}
                label={`${p.name} ${posted?.done?.[p.key] ? "✓" : "→"}`}
                width={widths[p.key]}
                accent={p.color}
                marginRight={1}
                onPress={() => s.bridge.send("open_upload", p.key, s.caption, s.tags)}
              />
            ))}
            <Button id="reveal" label="Show file" variant="ghost" marginLeft={1} onPress={() => s.bridge.send("reveal_file")} />
          </box>
          <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
            {openAll ? <box width={openAll.length + 4} marginRight={2} flexShrink={0} /> : null}
            {ps.map((p) =>
              copies[p.key] ? (
                <Button
                  key={p.key}
                  id={copies[p.key]![0]}
                  label={copies[p.key]![1]}
                  width={widths[p.key]}
                  variant="ghost"
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
                variant="ghost"
                marginRight={1}
                onPress={() => s.bridge.send("copy_field", "copy-caption-alone", s.caption, s.tags)}
              />
            ) : null}
          </box>
        </Scroll>
        <box marginTop={1} marginBottom={1} flexShrink={0}>
          <Line segs={uploads?.heading} />
        </box>
        <Table id="uploads-table" data={uploads} cursor={false} rowsShown={Math.min(Math.max(uploads?.rows.length ?? 0, 1), 11)} />
      </Scroll>
    </Panel>
  )
}
