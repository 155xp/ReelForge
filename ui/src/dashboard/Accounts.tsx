// The Accounts tab: connect the platforms you post to (ReelForge shows only the connected ones everywhere else), and
// for each connected one where its stats come from, how fresh they are, its log-in / profile / refresh buttons, and
// its followers over the time ReelForge has been reading them.

import { TextAttributes, type Renderable } from "@opentui/core"
import { useCallback, useState } from "react"
import { useView } from "../bridge"
import { clockLabels, lines as drawLines, MARK, type Drawn } from "../lib/chart"
import { fmtNum } from "../lib/format"
import { lines, segsLen, type Segs } from "../lib/styled"
import { DASH } from "../theme"
import { Button } from "../ui/Button"
import { Chart } from "../ui/Chart"
import { TextField } from "../ui/Fields"
import { Fitted, Line } from "../ui/Line"
import { Panel, Wrapped } from "../ui/Panels"
import { useDash } from "./state"
import type { AccountPanelView, AccountsView } from "./types"

export function Accounts() {
  const s = useDash()
  const accounts = useView<AccountsView>(s.bridge, "accounts")
  const panels = accounts?.panels ?? []
  const rows = [panels.slice(0, 2), panels.slice(2, 4)].filter((r) => r.length)
  return (
    <box flexDirection="column" flexGrow={1} paddingTop={1} gap={1}>
      {accounts?.hint ? (
        <box paddingLeft={1} flexShrink={0}>
          <Fitted parts={accounts.hint} />
        </box>
      ) : null}
      {rows.map((row, i) => (
        <box key={i} flexDirection="row" flexGrow={1} flexBasis={0} gap={1}>
          {row.map((p) => (
            <Account key={p.key} panel={p} picked={s.picked === `acct-${p.key}`} />
          ))}
          {row.length === 1 ? <box flexGrow={1} flexBasis={0} /> : null}
        </box>
      ))}
    </box>
  )
}

function Account({ panel: p, picked }: { panel: AccountPanelView; picked: boolean }) {
  return (
    <Panel flexGrow={1} picked={picked} paddingBottom={1}>
      <text wrapMode="none" flexShrink={0} marginBottom={1}>
        <span fg={p.color} attributes={TextAttributes.BOLD}>
          {p.name}
        </span>
      </text>
      <Status panel={p} />
      {lines(p.body).map((l, i) => (
        <Wrapped key={i} segs={l.length ? l : [[" ", ""]]} flexGrow={0} />
      ))}
      {p.state === "off" ? <Connect panel={p} /> : <Connected panel={p} />}
    </Panel>
  )
}

/** The first line: where the stats come from, and Disconnect at its right end while there's room. */
function Status({ panel: p }: { panel: AccountPanelView }) {
  const [width, setWidth] = useState(0)
  const out = p.disconnect
  const fits = (t: Segs) => out && segsLen(t) + 2 + segsLen(out) <= width
  const line = fits(p.status) ? p.status : p.status_short && fits(p.status_short) ? p.status_short : null
  return (
    <box
      flexDirection="row"
      height={1}
      flexShrink={0}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      <Line segs={line ?? p.status_short ?? p.status} flexGrow={1} />
      {line && out ? <Line segs={out} /> : null}
    </box>
  )
}

/** Not connected: a box for the @handle (a link to the profile works too), Connect, and Sign up for someone without
 * the account yet. One row, so even a short window shows all three. */
function Connect({ panel: p }: { panel: AccountPanelView }) {
  const s = useDash()
  const typed = s.handles[p.key] ?? ""
  const error = s.handleErrors[p.key]
  const signUp = () => void s.openDialog("signup", s.bridge.call("signup_guide", p.key))
  return (
    <>
      <box flexDirection="row" height={3} marginTop={1} flexShrink={0} alignItems="center">
        <box flexGrow={1} maxWidth={40} marginRight={2}>
          <TextField
            id={`handle-${p.key}`}
            value={typed}
            placeholder="@yourname"
            bad={!!error}
            flexGrow={1}
            onChange={(v) => s.set({ handles: { ...s.handles, [p.key]: v } })}
            onSubmit={(v) => void s.connect(p.key, v)}
          />
        </box>
        <Button id={`connect-${p.key}`} label="Connect" variant="primary" marginRight={1} onPress={() => void s.connect(p.key, s.handles[p.key] ?? "")} />
        {p.signup ? <Button id={`signup-${p.key}`} label="Sign up →" marginRight={1} onPress={signUp} /> : null}
      </box>
      {error ? (
        <text fg={DASH.bad} wrapMode="word" flexShrink={0}>
          {error}
        </text>
      ) : null}
      <box marginTop={1} flexShrink={0}>
        <Wrapped segs={p.note} />
      </box>
    </>
  )
}

/** Connected (or waiting for its one log-in): its buttons, then its followers chart taking whatever room is left. The
 * buttons come right after the status lines, so a short window never pushes them out of sight. */
function Connected({ panel: p }: { panel: AccountPanelView }) {
  const s = useDash()
  const chart = p.chart
  const draw = useCallback(
    (w: number, h: number, hover: number | null, grow: number): Drawn =>
      drawLines(chart!.series, chart!.n, w, h, (pw) => clockLabels(chart!.slots, pw, chart!.step_h), [], hover, false, true, true, { grow, fade: true }),
    [chart],
  )
  const title = (hover: number | null): Segs => {
    if (!chart) return []
    if (hover === null || hover < 0 || hover >= chart.n) return chart.heading
    const value = chart.values[hover]
    return [
      ["FOLLOWERS  ", "bold"],
      [chart.slots[hover]!.label + "  ", `bold ${MARK}`],
      value !== null && value !== undefined ? [fmtNum(value), "bold"] : ["no reading yet", DASH.muted],
    ]
  }
  return (
    <>
      <box flexDirection="row" height={1} marginTop={1} flexShrink={0}>
        {p.logs_in ? (
          <Button id={`login-${p.key}`} label={p.login_label ?? "Log in"} variant="primary" marginRight={1} onPress={() => s.bridge.send("login", p.key)} />
        ) : null}
        {p.state === "on" ? (
          <>
            <Button id={`profile-${p.key}`} label="Open profile" disabled={p.profile_disabled} marginRight={1} onPress={() => s.bridge.send("profile", p.key)} />
            <Button
              id={`refresh-${p.key}`}
              label="Refresh now"
              disabled={p.refresh_disabled}
              marginRight={1}
              onPress={() => s.bridge.send("refresh_platform", p.key)}
            />
          </>
        ) : null}
        {p.show_log ? (
          <Button
            id={`log-${p.key}`}
            label="Type in stats"
            marginRight={1}
            onPress={() => void s.openDialog("log", s.bridge.call("log_stats", p.key))}
          />
        ) : null}
      </box>
      <box marginTop={1} flexShrink={0}>
        <Wrapped segs={p.note} />
      </box>
      {chart ? (
        <box marginTop={1} flexGrow={1} flexDirection="column">
          <Chart title={title} draw={draw} flexGrow={1} bare />
        </box>
      ) : null}
    </>
  )
}
