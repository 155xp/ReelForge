// The Compare tab: the platform scoreboard (which platform is working: views per video, like rate, followers gained,
// and how a typical video grows on each), or one episode on every platform against each one's typical video.

import { useCallback } from "react"
import { useView } from "../bridge"
import { ageLabels, lines as drawLines, type Drawn } from "../lib/chart"
import { DASH } from "../theme"
import { Chart } from "../ui/Chart"
import { HBars } from "../ui/Graphics"
import { Line } from "../ui/Line"
import { OptionList, Table, type Option } from "../ui/Lists"
import { Panel, Scroll } from "../ui/Panels"
import { useDash } from "./state"
import { hoursTitle } from "./titles"
import type { CompareChart, CompareView } from "./types"

export function Compare() {
  const s = useDash()
  const episodes = useView<{ items: Option[]; selected: string }>(s.bridge, "episodes")
  const compare = useView<CompareView>(s.bridge, "compare")
  const charts = compare?.charts ?? []
  const rows = [charts.slice(0, 2), charts.slice(2, 4)].filter((r) => r.length)
  return (
    <box flexDirection="row" flexGrow={1}>
      <Panel title="EPISODES" titleColor={DASH.muted} width={42} flexShrink={0}>
        <OptionList
          id="episode-list"
          items={episodes?.items ?? []}
          selected={episodes?.selected}
          onSelect={(id) => {
            s.bridge.emit("episodes", { ...episodes!, selected: id })
            s.bridge.send("pick_episode", id)
          }}
        />
      </Panel>
      <Scroll flexGrow={1} scrollY>
        <Panel flexShrink={0}>
          <Line segs={compare?.heading} base={DASH.muted} />
          <HBars sections={compare?.bars ?? []} muted={DASH.muted} />
        </Panel>
        <box flexDirection="column" height={26} flexShrink={0}>
          {rows.map((row, i) => (
            <box key={i} flexDirection="row" flexGrow={1} flexBasis={0}>
              {row.map((c, j) => (
                <PlatformChart key={c.key} chart={c} last={j === row.length - 1} />
              ))}
            </box>
          ))}
        </box>
        <Table
          id="compare-table"
          data={compare?.table}
          selected={s.compareRow}
          rowsShown={Math.min(Math.max(compare?.table.rows.length ?? 1, 1), 6)}
          onSelect={(key) => s.set({ compareRow: key })}
          onActivate={(key) => s.bridge.send("open_row", key)}
        />
      </Scroll>
    </box>
  )
}

function PlatformChart({ chart, last }: { chart: CompareChart; last: boolean }) {
  const series = chart.series
  const span = chart.span ?? 1
  const draw = useCallback(
    (w: number, h: number, hover: number | null): Drawn =>
      drawLines(series ?? [], span, w, h, (pw) => ageLabels(span, pw), [], hover, true),
    [series, span],
  )
  return (
    <Chart
      title={(hover) => (hover === null || !series ? chart.heading : hoursTitle([], series, hover, false))}
      draw={series && !chart.empty ? draw : null}
      empty={chart.empty}
      flexGrow={1}
      marginRight={last ? 0 : 1}
    />
  )
}
