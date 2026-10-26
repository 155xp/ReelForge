// The Overview tab: a card per platform and one for them all, today's badges, views / followers / likes gained per
// hour (or 6 hours, or day) stacked by platform with a mark where each video went up, Top performers, and how the
// latest video is doing.

import type { Renderable } from "@opentui/core"
import { useCallback, useEffect, useState } from "react"
import { useView } from "../bridge"
import { bars, clockLabels, type Drawn } from "../lib/chart"
import { fit } from "../lib/fit"
import { cellLen, lines, segsLen, type Parts, type Segs } from "../lib/styled"
import { DASH, PICKED } from "../theme"
import { Chart } from "../ui/Chart"
import { Sparkline } from "../ui/Graphics"
import { BadgeLine, Fitted, Line, Lines } from "../ui/Line"
import { Table } from "../ui/Lists"
import { Panel } from "../ui/Panels"
import { cardLines, wrapLines } from "./cards"
import { useDash } from "./state"
import { metricTitle, pickVariant } from "./titles"
import type { CardView, MetricView, TableView, TrendsView, Variant } from "./types"

export function Overview() {
  const s = useDash()
  const cards = useView<{ cards: CardView[] }>(s.bridge, "cards")
  const badges = useView<{ line: Parts }>(s.bridge, "badges")
  return (
    <box flexDirection="column" flexGrow={1}>
      <box flexDirection="row" height={8} marginTop={1} flexShrink={0}>
        {(cards?.cards ?? []).map((c, i, all) => (
          <Card key={c.id} card={c} last={i === all.length - 1} picked={s.picked === `card-${c.id}`} />
        ))}
      </box>
      {badges?.line?.length ? <BadgeLine parts={badges.line} how={s.init.badges_how} bg={DASH.surface} fg={DASH.muted} /> : null}
      <box flexDirection="row" flexGrow={1} flexBasis={0}>
        <Trends />
        <box flexDirection="column" flexGrow={1} minWidth={68} maxWidth={72}>
          <Top />
          <Latest />
        </box>
      </box>
    </box>
  )
}

/** Followers, views and likes with their 24-hour change, and views per hour underneath. Nothing on a card is ever cut
 * off: its lines get shorter as the card narrows. */
function Card({ card, last, picked }: { card: CardView; last: boolean; picked: boolean }) {
  const [width, setWidth] = useState(0) // the whole card, border and all
  const pad = width < 18 ? 0 : 1 // a narrow card gives its padding to the numbers
  const inner = Math.max(width - 2 - 2 * pad, 0)
  const title = card.titles.find((t) => t.length + 6 <= width) ?? card.titles[card.titles.length - 1]
  const body: Segs[] = width
    ? card.values
      ? cardLines(card.values, card.changes ?? {}, inner)
      : wrapLines(lines(card.message), inner)
    : []
  // A sparkline of all zeros draws as solid blocks, so it only shows once views are coming in.
  const spark = card.gains.some(Boolean)
  const caption = spark ? (card.captions.find((c) => cellLen(c) <= inner) ?? "") : ""
  return (
    <box
      border
      borderStyle={picked ? "heavy" : "rounded"}
      borderColor={picked ? PICKED : card.color}
      title={` ${title} `}
      titleColor={card.color}
      flexDirection="column"
      flexGrow={1}
      flexBasis={0}
      height={8}
      marginRight={last ? 0 : 1}
      paddingLeft={pad}
      paddingRight={pad}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      <box height={3} flexDirection="column" flexShrink={0}>
        {body.slice(0, 3).map((l, i) => (
          <Line key={i} segs={l} />
        ))}
      </box>
      {spark ? <Sparkline data={card.gains} color={card.color} background={DASH.bg} /> : <box height={2} />}
      <text fg={DASH.muted} wrapMode="none" height={1}>
        {caption}
      </text>
    </box>
  )
}

/** The three charts and the bar over them: the range, the platforms (click one to hide it), and the marks' key. */
function Trends() {
  const s = useDash()
  const trends = useView<TrendsView>(s.bridge, "trends")
  const [width, setWidth] = useState(0)
  const ranges = trends?.ranges ?? []
  const short = segsLen(ranges) + segsLen(trends?.legend) + 8 > width - 2 // TT YT IG X when the full names don't fit
  const bar: Parts = [
    [ranges, 0],
    [(short ? trends?.legend_short : trends?.legend) ?? [], 0],
    [[["   ▼ video posted", DASH.warn]], 1],
  ]
  return (
    <box
      flexDirection="column"
      flexGrow={2}
      flexBasis={0}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      <box height={1} paddingLeft={1} paddingRight={1} flexShrink={0}>
        <Line segs={fit(bar, Math.max(width - 2, 1))} />
      </box>
      <Metric metric="views" view={trends?.metrics.views} flexGrow={1} />
      <box flexDirection="row" flexGrow={1} flexBasis={0}>
        <Metric metric="followers" view={trends?.metrics.followers} flexGrow={1} />
        <Metric metric="likes" view={trends?.metrics.likes} flexGrow={1} />
      </box>
    </box>
  )
}

/** Bars of what each platform gained per bucket, stacked; the title carries the numbers, or the hovered bar's. A
 * chart too narrow for a bar per bucket draws combined buckets, so every bar keeps its columns and a gap. */
function Metric({ metric, view, flexGrow }: { metric: string; view: MetricView | undefined; flexGrow: number }) {
  const variants = view?.variants
  const draw = useCallback(
    (w: number, h: number, hover: number | null): Drawn => {
      const v = pickVariant(variants!, w - 8) // 8: room for the y labels and axis
      return { ...bars(v.series, v.n, w, h, (pw) => clockLabels(v.slots, pw, v.step_h), v.marks, hover), meta: v }
    },
    [variants],
  )
  const title = (hover: number | null, drawn: Drawn | null): Parts => {
    if (!view?.variants) return [[[[metric.toUpperCase(), "bold"]], 0]]
    const v = (drawn?.meta as Variant | undefined) ?? view.variants[0]!
    return metricTitle(metric, view, v, hover)
  }
  return (
    <Chart
      title={title}
      draw={variants?.length ? draw : null}
      empty={view?.empty}
      flexGrow={flexGrow}
    />
  )
}

function Top() {
  const s = useDash()
  const top = useView<TableView>(s.bridge, "top")
  useEffect(() => {
    const keys = (top?.rows ?? []).map((r) => r.key)
    if (keys.length && !keys.includes(s.top)) s.set({ top: keys[0] })
  }, [top])
  return (
    <Panel flexGrow={1}>
      <Fitted parts={top?.title} base={DASH.muted} flexGrow={0} />
      <Table
        id="top-table"
        data={top}
        selected={s.top}
        onSelect={(key) => s.set({ top: key })}
        onActivate={(key) => s.bridge.send("open_row", key)}
        onSort={(col) => s.bridge.send("sort_top", col)}
      />
    </Panel>
  )
}

function Latest() {
  const s = useDash()
  const latest = useView<{ heading: Segs; body: Segs }>(s.bridge, "latest")
  return (
    <Panel maxHeight={11} flexShrink={0}>
      <Line segs={latest?.heading} base={DASH.muted} />
      <Lines segs={latest?.body} />
    </Panel>
  )
}
