// Dialogs over the window: how ReelForge works, typing in stats, removing a video, and which video a post is.

import { TextAttributes } from "@opentui/core"
import { useState } from "react"
import { lines } from "../lib/styled"
import { DASH } from "../theme"
import { Button } from "../ui/Button"
import { RadioSet, TextField } from "../ui/Fields"
import { OptionList } from "../ui/Lists"
import { Modal, Scroll, Wrapped } from "../ui/Panels"
import { useDash, type EpisodeData, type LogData } from "./state"

export function Dialogs() {
  const s = useDash()
  const d = s.dialog
  if (!d) return null
  const close = () => s.set({ dialog: null })
  if (d.kind === "help") return <Help close={close} />
  if (d.kind === "log") return <LogStats data={d.data} close={close} />
  if (d.kind === "remove") return <Remove data={d.data} close={close} />
  return <EpisodePicker data={d.data} close={close} />
}

function Buttons({ children }: { children: React.ReactNode }) {
  return (
    <box flexDirection="row" justifyContent="flex-end" height={3} marginTop={1} flexShrink={0} gap={1}>
      {children}
    </box>
  )
}

function Help({ close }: { close: () => void }) {
  const s = useDash()
  return (
    <Modal name="help" title="HOW REELFORGE WORKS">
      <Scroll maxHeight={30} flexShrink={1} scrollY>
        {s.init.help.map(([tab, text]) => (
          <box key={tab} flexDirection="column" marginBottom={1} flexShrink={0}>
            <text fg={DASH.good} attributes={TextAttributes.BOLD}>
              {tab}
            </text>
            <text fg={DASH.text} wrapMode="word">
              {text}
            </text>
          </box>
        ))}
        <text fg={DASH.good} attributes={TextAttributes.BOLD} flexShrink={0}>
          Keys
        </text>
        {s.init.keys.map(([key, what]) => (
          <text key={key} flexShrink={0}>
            <span attributes={TextAttributes.BOLD}>{`  ${key.padEnd(8)}`}</span>
            <span fg={DASH.muted}>{what}</span>
          </text>
        ))}
        <text fg={DASH.muted} flexShrink={0}>
          Everything else is a button on the page it applies to.
        </text>
      </Scroll>
      <Buttons>
        <Button id="help-close" label="Close" variant="primary" autoFocus onPress={close} />
      </Buttons>
    </Modal>
  )
}

/** Type in numbers for platforms ReelForge can't read itself (Instagram and X before logging in). */
function LogStats({ data, close }: { data: LogData; close: () => void }) {
  const s = useDash()
  const fill = (key: string) => {
    const last = data.last[key]
    return {
      followers: last?.followers === null || last?.followers === undefined ? "" : String(last.followers),
      views: Object.fromEntries(data.episodes.map((e) => [String(e.id), last?.views[String(e.id)] !== undefined ? String(last.views[String(e.id)]) : ""])),
    }
  }
  const [platform, setPlatform] = useState(data.start)
  const [values, setValues] = useState(() => fill(data.start))
  const [problem, setProblem] = useState("")
  const save = async () => {
    const error = await s.bridge.call<string | null>("save_logged_stats", platform, values.followers, values.views)
    if (error) setProblem(error)
    else close()
  }
  return (
    <Modal name="log" title="LOG STATS">
      <RadioSet
        id="ls-platform"
        options={data.platforms.map((p) => [p.key, p.name])}
        value={platform}
        onChange={(key) => {
          setPlatform(key)
          setValues(fill(key))
        }}
      />
      <box marginTop={1} marginBottom={1} flexShrink={0}>
        <text fg={DASH.muted} wrapMode="word">
          Copy the numbers from the app. Blank fields are skipped; 1.2K and 3,400 both work. Enter saves.
        </text>
      </box>
      <box flexDirection="row" height={3} flexShrink={0}>
        <box flexGrow={1} justifyContent="center">
          <text attributes={TextAttributes.BOLD}>Followers</text>
        </box>
        <TextField
          id="ls-followers"
          width={18}
          autoFocus
          value={values.followers}
          placeholder="followers"
          onChange={(v) => setValues((x) => ({ ...x, followers: v }))}
          onSubmit={() => void save()}
        />
      </box>
      {data.episodes.length ? (
        <text fg={DASH.muted} attributes={TextAttributes.BOLD} marginTop={1} flexShrink={0}>
          VIEWS PER VIDEO
        </text>
      ) : (
        <text fg={DASH.muted} flexShrink={0}>
          Videos show up here once you've uploaded them from the Publish tab.
        </text>
      )}
      <Scroll maxHeight={15} flexShrink={1} scrollY>
        {data.episodes.map((e) => (
          <box key={e.id} flexDirection="row" height={3} flexShrink={0}>
            <box flexGrow={1} justifyContent="center">
              <text wrapMode="none">{e.title}</text>
            </box>
            <TextField
              id={`ls-ep-${e.id}`}
              width={18}
              value={values.views[String(e.id)] ?? ""}
              placeholder="views"
              onChange={(v) => setValues((x) => ({ ...x, views: { ...x.views, [String(e.id)]: v } }))}
              onSubmit={() => void save()}
            />
          </box>
        ))}
      </Scroll>
      {problem ? (
        <text fg={DASH.warn} marginTop={1} flexShrink={0}>
          {problem}
        </text>
      ) : null}
      <Buttons>
        <Button id="ls-cancel" label="Cancel" onPress={close} />
        <Button id="ls-save" label="Save" variant="primary" onPress={() => void save()} />
      </Buttons>
    </Modal>
  )
}

/** What to do with a video in the Publish list: move it to the Recycle Bin (or Trash), or hide it from the list. */
function Remove({ data, close }: { data: { path: string; note: import("../lib/styled").Segs; bin: string }; close: () => void }) {
  const s = useDash()
  const choose = (choice: string) => {
    close()
    s.bridge.send("remove_video", data.path, choice)
  }
  return (
    <Modal name="remove" title="REMOVE VIDEO">
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      <Buttons>
        <Button id="rm-cancel" label="Cancel" autoFocus onPress={close} />
        <Button id="rm-hide" label="Hide from list" onPress={() => choose("hide")} />
        <Button id="rm-recycle" label={`Move to ${data.bin}`} variant="error" onPress={() => choose("recycle")} />
      </Buttons>
    </Modal>
  )
}

/** Which video a post is: one of your episodes, or not one of your videos. */
function EpisodePicker({ data, close }: { data: EpisodeData; close: () => void }) {
  const s = useDash()
  const [selected, setSelected] = useState(data.current ?? data.options[0]?.id ?? null)
  const choose = (id: string) => {
    close()
    s.bridge.send("set_episode", data.key, id)
  }
  return (
    <Modal name="episode" title="WHICH VIDEO IS THIS?">
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l} flexGrow={0} />
      ))}
      <box marginTop={1} flexShrink={0} flexDirection="column">
        <OptionList
          id="episode-choices"
          items={data.options}
          selected={selected}
          maxLines={16}
          onSelect={setSelected}
          onActivate={choose}
        />
      </box>
      <Buttons>
        <Button id="ep-cancel" label="Cancel" onPress={close} />
        <Button id="ep-pick" label="This one" variant="primary" disabled={!selected} onPress={() => selected && choose(selected)} />
      </Buttons>
    </Modal>
  )
}
