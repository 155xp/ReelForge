// The Videos tab: every video on every platform, scored against your typical video; the highlighted one's badges, and
// its views since it went up against your typical video's.

import { useCallback, useEffect } from "react"
import { useView } from "../bridge"
import { ageLabels, lines as drawLines, type Drawn } from "../lib/chart"
import { useFocusManager } from "../lib/focus"
import type { Parts, Segs } from "../lib/styled"
import { Chart } from "../ui/Chart"
import { BadgeLine, Fitted } from "../ui/Line"
import { DASH } from "../theme"
import { Table } from "../ui/Lists"
import { Panel } from "../ui/Panels"
import { useDash } from "./state"
import { hoursTitle } from "./titles"
import type { DetailView, TableView } from "./types"

export function Videos() {
  const s = useDash()
  const focus = useFocusManager()
  const videos = useView<TableView>(s.bridge, "videos")
  const badges = useView<{ line: Parts }>(s.bridge, "video_badges")
  useEffect(() => {
    if (!videos) return
    if (videos.select !== undefined && videos.select !== s.video) s.set({ video: videos.select ?? null })
    if (videos.focus) setTimeout(() => focus.focus("videos-table"), 30)
  }, [videos])
  const select = (key: string | null) => {
    s.set({ video: key })
    s.bridge.send("video_highlighted", key)
  }
  return (
    <box flexDirection="column" flexGrow={1} marginTop={1} gap={1}>
      <Panel flexGrow={1} minHeight={8}>
        <box height={1} marginBottom={1} flexShrink={0}>
          <Fitted parts={videos?.hint} base={DASH.faint} />
        </box>
        <Table
          id="videos-table"
          data={videos}
          selected={s.video}
          zebra
          onSelect={select}
          onActivate={(key) => s.bridge.send("open_row", key)}
          onSort={(col) => s.bridge.send("sort_videos", col)}
        />
      </Panel>
      {badges?.line?.length ? <BadgeLine parts={badges.line} how={s.init.badges_how} bg={DASH.surface} fg={DASH.muted} /> : null}
      <Detail />
    </box>
  )
}

const HEAD: Segs = [["VIEWS SINCE POSTING  ", "bold"]]

/** The highlighted video's views hour by hour since it went up, the line drawing in from the left whenever another
 * video is picked. */
function Detail() {
  const s = useDash()
  const detail = useView<DetailView>(s.bridge, "detail")
  const series = detail?.series
  const span = detail?.span ?? 1
  const draw = useCallback(
    (w: number, h: number, hover: number | null, grow: number): Drawn =>
      drawLines(series ?? [], span, w, h, (pw) => ageLabels(span, pw), [], hover, true, true, true, { grow, fade: true }),
    [series, span],
  )
  return (
    <Chart
      title={(hover) => (hover === null || !series ? (detail?.title ?? HEAD) : hoursTitle(HEAD, series, hover, true))}
      draw={series && !detail?.empty ? draw : null}
      empty={detail?.empty}
      animate={detail?.key}
      height="40%"
      minHeight={9}
    />
  )
}
