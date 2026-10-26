// The Updates tab: your version, what's new in the next one, and Update and restart: one click downloads it, puts it
// in place (your channel, videos and stats stay as they are) and opens ReelForge again. Beside it, when the window has
// room, the mascot: he winks when a new version is out, hammers while it installs and hops once it's in.

import { TextAttributes, type Renderable } from "@opentui/core"
import { useState } from "react"
import { useView } from "../bridge"
import { DASH } from "../theme"
import { Button } from "../ui/Button"
import { ProgressBar } from "../ui/Graphics"
import { Lines } from "../ui/Line"
import { Mascot, MASCOT } from "../ui/Mascot"
import { Markdown, Panel, Scroll, useTick, Wrapped } from "../ui/Panels"
import { useDash } from "./state"
import type { UpdateStep, UpdateView } from "./types"

export function Updates() {
  const s = useDash()
  const u = useView<UpdateView>(s.bridge, "update")
  const step = useView<UpdateStep>(s.bridge, "update_step")
  const progress = u?.updating ? step?.progress : null
  const tick = useTick(Boolean(progress && !progress.total), 80)
  const status = step?.status && !u?.updating ? step.status : u?.status
  const [room, setRoom] = useState<[number, number]>([0, 0])
  // the mascot beside the panels when they keep 70 columns and he has his rows
  const mascot = room[0] - MASCOT.width - 2 >= 70 && room[1] >= MASCOT.height
  return (
    <box flexDirection="column" flexGrow={1}>
      <box
        flexDirection="row"
        flexGrow={1}
        onSizeChange={function (this: Renderable) {
          setRoom([this.width, this.height])
        }}
      >
        <box flexDirection="column" flexGrow={1}>
          <Panel marginTop={1} flexShrink={0} paddingBottom={1}>
            <Wrapped segs={status ?? []} flexGrow={0} />
            <box flexDirection="row" height={1} marginTop={2} flexShrink={0}>
              {u?.apply.show ? (
                <Button
                  id="update-apply"
                  label={u.apply.label}
                  variant="primary"
                  disabled={u.apply.disabled}
                  marginRight={1}
                  onPress={() => s.bridge.send("start_update")}
                />
              ) : null}
              <Button id="update-check" label="Check now" disabled={u?.check_disabled ?? true} marginRight={1} onPress={() => s.bridge.send("check_updates")} />
              <Button id="update-page" label="Release page" marginRight={1} onPress={() => s.bridge.send("release_page")} />
            </box>
            {progress ? (
              <box marginTop={1} flexShrink={0}>
                <ProgressBar done={progress.done} total={progress.total} color={DASH.primary} stops={DASH.accent} track={DASH.border} width={60} tick={tick} />
              </box>
            ) : null}
            {step?.step ? (
              <box marginTop={1} flexShrink={0}>
                <Lines segs={step.step} />
              </box>
            ) : null}
          </Panel>
          <Panel marginTop={1} flexGrow={1}>
            <text fg={DASH.faint} attributes={TextAttributes.BOLD} flexShrink={0} marginBottom={1}>
              WHAT'S NEW
            </text>
            <Scroll flexGrow={1} scrollY>
              <Markdown text={u?.notes ?? ""} spaced />
            </Scroll>
          </Panel>
        </box>
        {mascot ? (
          <box flexDirection="column" justifyContent="flex-end" flexShrink={0} marginLeft={2}>
            <UpdateMascot u={u} step={step} />
          </box>
        ) : null}
      </box>
      {u?.how?.length ? (
        <box marginTop={1} flexShrink={0}>
          <Wrapped segs={u.how} />
        </box>
      ) : null}
    </box>
  )
}

/** The mascot for where the update is: each change is a fresh one, so what he does once plays again next time. */
function UpdateMascot({ u, step }: { u: UpdateView | undefined; step: UpdateStep | undefined }) {
  if (u?.updating)
    return step?.done ? <Mascot key="done" once="success" animation="idle" /> : <Mascot key="updating" animation="forge" />
  if (step?.failed) return <Mascot key="failed" once="error" animation="idle" />
  return u?.newer ? <Mascot key="newer" once="wink" animation="idle" /> : <Mascot key="idle" animation="idle" />
}
