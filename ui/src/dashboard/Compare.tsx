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
import { useProgress } from "../ui/Motion"
import { Panel, Scroll } from "../ui/Panels"
import { useDash } from "./state"
import { hoursTitle } from "./titles"
import type { CompareChart, CompareView } from "./types"

export function Compare() {
  const s = useDash()
  const episodes = useView<{ items: Option[]; selected: string }>(s.bridge, "episodes")
  const compare = useView<CompareView>(s.bridge, "compare")
  const grow = useProgress(episodes?.selected, { ms: 700 })
  const charts = compare?.charts ?? []
  const rows = [charts.slice(0, 2), charts.slice(2, 4)].filter((r) => r.length)
  return (
    <box flexDirection="row" flexGrow={1} marginTop={1} gap={1}>
      <Panel title="EPISODES" width={44} flexShrink={0} paddingX={1}>
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
        <Panel flexShrink={0} paddingBottom={1}>
          <box height={1} marginBottom={1} flexShrink={0}>
            <Line segs={compare?.heading} base={DASH.faint} />
          </box>
          <HBars sections={compare?.bars ?? []} muted={DASH.faint} grow={grow} />
        </Panel>
        <box flexDirection="column" height={27} flexShrink={0} marginTop={1} gap={1}>
          {rows.map((row, i) => (
            <box key={i} flexDirection="row" flexGrow={1} flexBasis={0} gap={1}>
              {row.map((c) => (
                <PlatformChart key={c.key} chart={c} animate={episodes?.selected} />
              ))}
            </box>
          ))}
        </box>
        <Panel flexShrink={0} marginTop={1} paddingBottom={1}>
          <Table
            id="compare-table"
            data={compare?.table}
            selected={s.compareRow}
            rowsShown={Math.min(Math.max(compare?.table.rows.length ?? 1, 1), 6)}
            onSelect={(key) => s.set({ compareRow: key })}
            onActivate={(key) => s.bridge.send("open_row", key)}
          />
        </Panel>
      </Scroll>
    </box>
  )
}

function PlatformChart({ chart, animate }: { chart: CompareChart; animate: unknown }) {
  const series = chart.series
  const span = chart.span ?? 1
  const draw = useCallback(
    (w: number, h: number, hover: number | null, grow: number): Drawn =>
      drawLines(series ?? [], span, w, h, (pw) => ageLabels(span, pw), [], hover, true, true, true, { grow, fade: true }),
    [series, span],
  )
  return (
    <Chart
      title={(hover) => (hover === null || !series ? chart.heading : hoursTitle([], series, hover, false))}
      draw={series && !chart.empty ? draw : null}
      empty={chart.empty}
      animate={animate}
      flexGrow={1}
    />
  )
}
