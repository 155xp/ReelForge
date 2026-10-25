// The Accounts tab: where each platform's stats come from, how fresh they are, its log-in / profile / refresh buttons,
// and its followers over the time ReelForge has been reading them.

import { useCallback } from "react"
import { useView } from "../bridge"
import { clockLabels, lines as drawLines, MARK, type Drawn } from "../lib/chart"
import { fmtNum } from "../lib/format"
import { lines, type Segs } from "../lib/styled"
import { DASH, PICKED } from "../theme"
import { Button } from "../ui/Button"
import { Chart } from "../ui/Chart"
import { Wrapped } from "../ui/Panels"
import { useDash } from "./state"
import type { AccountPanelView } from "./types"

export function Accounts() {
  const s = useDash()
  const accounts = useView<{ panels: AccountPanelView[] }>(s.bridge, "accounts")
  const panels = accounts?.panels ?? []
  const rows = [panels.slice(0, 2), panels.slice(2, 4)].filter((r) => r.length)
  return (
    <box flexDirection="column" flexGrow={1} paddingTop={1} paddingBottom={1} gap={1}>
      {rows.map((row, i) => (
        <box key={i} flexDirection="row" flexGrow={1} flexBasis={0} gap={2}>
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
  const s = useDash()
  const chart = p.chart
  const draw = useCallback(
    (w: number, h: number, hover: number | null): Drawn =>
      drawLines(chart!.series, chart!.n, w, h, (pw) => clockLabels(chart!.slots, pw, chart!.step_h), [], hover),
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
  // The buttons come right after the status lines, so a short window never pushes them out of sight; the followers
  // chart at the bottom takes whatever room is left.
  return (
    <box
      border
      borderStyle={picked ? "heavy" : "rounded"}
      borderColor={picked ? PICKED : p.color}
      title={` ${p.name} `}
      titleColor={p.color}
      flexDirection="column"
      flexGrow={1}
      flexBasis={0}
      paddingLeft={1}
      paddingRight={1}
    >
      {lines(p.body).map((l, i) => (
        <Wrapped key={i} segs={l} flexGrow={0} />
      ))}
      <box flexDirection="row" height={3} marginTop={1} flexShrink={0}>
        {p.logs_in ? (
          <Button id={`login-${p.key}`} label={p.login_label} variant="primary" marginRight={1} onPress={() => s.bridge.send("login", p.key)} />
        ) : null}
        <Button id={`profile-${p.key}`} label="Open profile" disabled={p.profile_disabled} marginRight={1} onPress={() => s.bridge.send("profile", p.key)} />
        <Button
          id={`refresh-${p.key}`}
          label="Refresh now"
          disabled={p.refresh_disabled}
          marginRight={1}
          onPress={() => s.bridge.send("refresh_platform", p.key)}
        />
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
    </box>
  )
}
