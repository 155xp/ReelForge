// Dialogs over the window: how ReelForge works, typing in stats, removing a video, which video a post is, making an
// account (or the channel's Gmail), and disconnecting one.

import { TextAttributes } from "@opentui/core"
import { useState } from "react"
import { lines } from "../lib/styled"
import { DASH } from "../theme"
import { Button } from "../ui/Button"
import { RadioSet, TextField } from "../ui/Fields"
import { OptionList } from "../ui/Lists"
import { Modal, Scroll, Wrapped } from "../ui/Panels"
import { useFocusManager } from "../lib/focus"
import { useDash, type EpisodeData, type LogData, type SignupData } from "./state"

export function Dialogs() {
  const s = useDash()
  const d = s.dialog
  if (!d) return null
  const close = () => s.set({ dialog: null })
  if (d.kind === "help") return <Help close={close} />
  if (d.kind === "log") return <LogStats data={d.data} close={close} />
  if (d.kind === "remove") return <Remove data={d.data} close={close} />
  if (d.kind === "signup") return <SignUp data={d.data} close={close} />
  if (d.kind === "disconnect") return <Disconnect data={d.data} close={close} />
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

/** Making an account you don't have yet (or the channel's Gmail): a few steps, a button that opens the platform's own
 * sign-up page in your usual browser, and a box for the @handle you end up with, which Connect connects. ReelForge
 * never makes the account, fills in a form or sees a password. */
function SignUp({ data, close }: { data: SignupData; close: () => void }) {
  const s = useDash()
  const focus = useFocusManager()
  const [opened, setOpened] = useState(false)
  const [handle, setHandle] = useState(s.handles[data.key] ?? "")
  const [problem, setProblem] = useState("")
  const open = () => {
    s.bridge.send("open_signup", data.key)
    setOpened(true)
    setTimeout(() => focus.focus(data.account ? "su-handle" : "su-done"), 30)
  }
  const done = (typed = handle) => {
    if (!data.account) return close()
    if (!typed.trim()) return setProblem("Type your new @handle first.")
    close()
    void s.connect(data.key, typed)
  }
  return (
    <Modal name="signup" title={data.title} width={84}>
      <text fg={DASH.muted} wrapMode="word" flexShrink={0}>
        {data.why}
      </text>
      <box flexDirection="column" marginTop={1} flexShrink={0}>
        {data.steps.map((step, i) => (
          <box key={i} flexDirection="row" flexShrink={0}>
            <text attributes={TextAttributes.BOLD} width={4} flexShrink={0}>
              {`${i + 1}.`.padStart(3)}
            </text>
            <text wrapMode="word" flexGrow={1} flexShrink={1}>
              {step}
            </text>
          </box>
        ))}
      </box>
      <box flexDirection="row" height={3} marginTop={1} marginLeft={4} flexShrink={0}>
        <Button id="su-open" label={data.button} variant="primary" autoFocus onPress={open} />
      </box>
      {opened ? (
        <text fg={DASH.good} marginLeft={4} flexShrink={0}>
          ✓ Opened in your browser. Come back here when you're done.
        </text>
      ) : null}
      {data.account ? (
        <>
          <text attributes={TextAttributes.BOLD} marginTop={1} flexShrink={0}>
            Your @handle
          </text>
          <TextField id="su-handle" value={handle} placeholder="@yourname" bad={!!problem} onChange={setHandle} onSubmit={(v) => done(v)} />
          {problem ? (
            <text fg={DASH.bad} flexShrink={0}>
              {problem}
            </text>
          ) : null}
        </>
      ) : null}
      <Buttons>
        <Button id="su-cancel" label="Cancel" onPress={close} />
        <Button id="su-done" label={data.account ? "Connect" : "Done"} variant={data.account ? "primary" : "default"} onPress={() => done()} />
      </Buttons>
    </Modal>
  )
}

/** Are you sure? Disconnecting a platform hides it everywhere in ReelForge and stops its reads; its stats stay. */
function Disconnect({ data, close }: { data: { key: string; title: string; note: import("../lib/styled").Segs }; close: () => void }) {
  const s = useDash()
  return (
    <Modal name="disconnect" title={data.title}>
      {lines(data.note).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      <Buttons>
        <Button id="dc-cancel" label="Cancel" autoFocus onPress={close} />
        <Button
          id="disconnect"
          label="Disconnect"
          variant="error"
          onPress={() => {
            close()
            s.bridge.send("disconnect", data.key)
          }}
        />
      </Buttons>
    </Modal>
  )
}
