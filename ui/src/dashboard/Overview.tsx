// The Overview tab: a tile per platform and one for them all (followers in big numbers that count up, the day's change,
// views and likes, and the views per hour as a sparkline), today's badges, views / followers / likes gained per hour
// (or 6 hours, or day) stacked by platform with a pin where each video went up, Top performers, and how the latest
// video is doing.

import { TextAttributes, type Renderable } from "@opentui/core"
import { useCallback, useEffect, useState, type ReactNode } from "react"
import { useView } from "../bridge"
import { bars, clockLabels, type Drawn } from "../lib/chart"
import { fmtDelta, fmtNum, shortNum, sigNum } from "../lib/format"
import { cellLen, lines, segsLen, type Parts, type Segs } from "../lib/styled"
import { DASH, mix } from "../theme"
import { Chart } from "../ui/Chart"
import { BigNumber, faceWidth, Sparkline, StackedSparkline } from "../ui/Graphics"
import { BadgeLine, Fitted, Line, Lines } from "../ui/Line"
import { Table } from "../ui/Lists"
import { useTween } from "../ui/Motion"
import { Panel, Scroll } from "../ui/Panels"
import { cardLines, wrapLines } from "./cards"
import { useDash } from "./state"
import { metricTitle, pickVariant } from "./titles"
import type { CardView, MetricView, TableView, TrendsView, Variant } from "./types"

/** Rows a tile takes: its padding, the name, three for the big number, a space, views and likes, the sparkline. */
export const TILE_ROWS = 9
/** The big numbers' shading, white at the top to grey at the foot. */
const FACE = ["#ffffff", "#dde1e6", "#a9b0ba"]
/** Narrower than this, Top performers goes under the charts instead of beside them. */
const SIDE_BY_SIDE = 140

export function Overview() {
  const s = useDash()
  const cards = useView<{ cards: CardView[] }>(s.bridge, "cards")
  const badges = useView<{ line: Parts }>(s.bridge, "badges")
  const [width, setWidth] = useState(0)
  const all = cards?.cards ?? []
  const side = width >= SIDE_BY_SIDE
  // Every tile fits its numbers to the narrowest one, so they all show the big numbers or none do.
  const tileW = all.length ? Math.floor((width - (side ? 0 : 1) - (all.length - 1)) / all.length) : 0 // 1: the scrollbar
  const pad = tileW < 24 ? 1 : 2
  const room = Math.max(tileW - 2 * pad, 0) // the left edge and the padding
  const tiles = (
    <box flexDirection="row" height={TILE_ROWS} marginTop={1} flexShrink={0} gap={1}>
      {all.map((c) => (
        <Tile key={c.id} card={c} picked={s.picked === `card-${c.id}`} others={all} room={room} pad={pad} />
      ))}
    </box>
  )
  const badge = badges?.line?.length ? <BadgeLine parts={badges.line} how={s.init.badges_how} bg={DASH.surface} fg={DASH.muted} marginTop={1} /> : null
  return (
    <box
      flexDirection="column"
      flexGrow={1}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      {side ? (
        <>
          {tiles}
          {badge}
          <box flexDirection="row" flexGrow={1} flexBasis={0} marginTop={1} gap={1}>
            <Trends />
            <box flexDirection="column" gap={1} width={74} flexShrink={0}>
              <Top />
              <Latest />
            </box>
          </box>
        </>
      ) : (
        // A narrow window: the same pieces one under another, scrolling.
        <Scroll flexGrow={1} scrollY>
          {tiles}
          {badge}
          <box flexDirection="column" flexShrink={0} marginTop={1} gap={1}>
            <box height={18} flexShrink={0} flexDirection="column">
              <Trends only="views" />
            </box>
            <box height={14} flexShrink={0} flexDirection="row" gap={1}>
              <Trends only="followers" />
            </box>
            <box height={16} flexShrink={0} flexDirection="column">
              <Top />
            </box>
            <Latest />
          </box>
        </Scroll>
      )}
    </box>
  )
}

// ---------------------------------------------------------------- the tiles

/** A tile: the platform's name and its followers' change today; followers in the big numbers (counting up to them);
 * views and likes with their changes; views per hour as a sparkline (the platforms stacked on All platforms). Too
 * narrow for the big numbers, it shows the three lines the old cards did, shortened to fit (cards.ts). Nothing on a tile
 * is ever cut off. */
function Tile({ card, picked, others, room, pad }: { card: CardView; picked: boolean; others: CardView[]; room: number; pad: number }) {
  const [measured, setInner] = useState(0)
  const inner = Math.min(measured || room, room || measured)
  const total = card.id === "total"
  const color = total ? DASH.text : card.color
  const values = card.values
  const changes = card.changes ?? {}
  const followers = useTween(values?.followers ?? NaN, { from: 0, ms: 900 })
  const views = useTween(values?.views ?? NaN, { from: 0, ms: 900, delay: 60 })
  const likes = useTween(values?.likes ?? NaN, { from: 0, ms: 900, delay: 120 })
  const shown = { followers: values?.followers == null ? null : followers, views: values?.views == null ? null : views, likes: values?.likes == null ? null : likes }
  const big = values ? [sigNum(shown.followers), fmtNum(shown.followers)].find((t) => faceWidth(t) <= inner) : undefined
  const delta = changes.followers ? `${changes.followers > 0 ? "▲" : "▼"} ${fmtDelta(changes.followers)}` : ""
  const name = card.titles.find((t) => cellLen(t) + 2 + (delta ? cellLen(delta) + 2 : 0) <= inner) ?? card.titles[card.titles.length - 1] ?? ""
  const spark = card.gains.some(Boolean)
  const stacks = others.filter((c) => c.id !== "total" && c.gains.some(Boolean)).map((c) => ({ color: c.color, values: c.gains.map((g) => g ?? 0) }))
  const grow = useTween(spark ? 1 : 0, { from: 0, ms: 800, delay: 150, ease: "outCirc" })
  let body: Segs[]
  if (!values) body = wrapLines(lines(card.message), inner).slice(0, 5)
  else if (big) body = [subLine(shown, changes, inner)]
  else body = cardLines(shown, changes, inner)
  return (
    <Panel flexGrow={1} height={TILE_ROWS} paddingX={pad} picked={picked}>
      <box
        flexDirection="column"
        flexGrow={1}
        onSizeChange={function (this: Renderable) {
          setInner(this.width)
        }}
      >
        <box flexDirection="row" height={1} flexShrink={0}>
          <text wrapMode="none" flexShrink={0}>
            <span fg={total ? DASH.muted : color}>{total ? "◆ " : "● "}</span>
            <span fg={color} attributes={TextAttributes.BOLD}>
              {name}
            </span>
          </text>
          <box flexGrow={1} />
          {delta && values ? (
            <text fg={(changes.followers ?? 0) > 0 ? DASH.good : DASH.bad} wrapMode="none" flexShrink={0}>
              {delta}
            </text>
          ) : null}
        </box>
        {big ? (
          <box flexDirection="row" height={3} flexShrink={0} alignItems="flex-end">
            <BigNumber text={big} stops={FACE} />
            {inner - faceWidth(big) >= 11 ? (
              <text fg={DASH.faint} wrapMode="none" marginLeft={1}>
                followers
              </text>
            ) : null}
          </box>
        ) : null}
        <box flexDirection="column" flexShrink={0} marginTop={big ? 1 : 0} height={big ? 1 : 4}>
          {body.map((l, i) => (
            <Line key={i} segs={l} />
          ))}
        </box>
        <box flexGrow={1} />
        {spark ? (
          total && stacks.length > 1 ? (
            <StackedSparkline stacks={stacks} background={DASH.surface} grow={grow} />
          ) : (
            <Sparkline data={card.gains.map((g) => g ?? 0)} color={color} background={DASH.surface} grow={grow} />
          )
        ) : null}
      </box>
    </Panel>
  )
}

/** Views and likes under the big number, each with its change, shortened to fit `width`: the numbers get shorter,
 * then the likes go, then the views' change. */
function subLine(values: Record<string, number | null>, changes: Record<string, number | null | undefined>, width: number): Segs {
  const part = (k: "views" | "likes", short: boolean, change = true): Segs => {
    const n = changes[k]
    const out: Segs = [[short ? sigNum(values[k]) : fmtNum(values[k]), `bold ${DASH.text}`], [` ${k}`, DASH.faint]]
    if (n && change) out.push([` ${n > 0 ? "+" : "−"}${short ? shortNum(Math.abs(n)) : fmtNum(Math.abs(n))}`, n > 0 ? DASH.good : DASH.bad])
    return out
  }
  const options: Segs[] = [
    [...part("views", false), ["   ", ""], ...part("likes", false)],
    [...part("views", true), ["   ", ""], ...part("likes", true)],
    part("views", false),
    part("views", true),
    part("views", true, false),
  ]
  return options.find((o) => segsLen(o) <= width) ?? [[sigNum(values.views), `bold ${DASH.text}`]]
}

// ---------------------------------------------------------------- the charts

/** The views chart, with the range at the right of its title and the platforms' key under it (click one to hide it),
 * and followers and likes side by side under it. */
function Trends({ only }: { only?: "views" | "followers" }) {
  const s = useDash()
  const trends = useView<TrendsView>(s.bridge, "trends")
  const [width, setWidth] = useState(0)
  // the chosen range filled, the others plain words
  const ranges: Segs = (trends?.ranges ?? [])
    .filter((seg) => seg[0].trim())
    .flatMap((seg, i): Segs => {
      const gap: Segs = i ? [["  ", ""]] : []
      return seg[2] ? [...gap, [seg[0], DASH.muted, seg[2]]] : [...gap, [seg[0], `bold ${DASH.text} on ${mix(DASH.raised, "#ffffff", 0.05)}`]]
    })
  const short = segsLen(trends?.legend) + 20 > width - 4
  const key = (short ? trends?.legend_short : trends?.legend) ?? []
  const legend: Segs = key.length ? [...key, ["  ▼ video posted", DASH.warn]] : [] // no platforms shown: no key at all
  const views = <Metric metric="views" view={trends?.metrics.views} range={trends?.range} flexGrow={1} right={<Line segs={ranges} />} sub={<Line segs={legend} />} />
  const small = (
    <>
      <Metric metric="followers" view={trends?.metrics.followers} range={trends?.range} flexGrow={1} />
      <Metric metric="likes" view={trends?.metrics.likes} range={trends?.range} flexGrow={1} />
    </>
  )
  if (only === "followers") return small
  return (
    <box
      flexDirection="column"
      flexGrow={1}
      flexBasis={0}
      gap={1}
      onSizeChange={function (this: Renderable) {
        setWidth(this.width)
      }}
    >
      {views}
      {only ? null : (
        <box flexDirection="row" height={14} flexShrink={0} gap={1}>
          {small}
        </box>
      )}
    </box>
  )
}

/** Bars of what each platform gained per bucket, stacked; the title carries the numbers, or the hovered bar's. A
 * chart too narrow for a bar per bucket draws combined buckets, so every bar keeps its columns and a gap. */
function Metric({
  metric,
  view,
  range,
  flexGrow,
  right,
  sub,
}: {
  metric: string
  view: MetricView | undefined
  range: string | undefined
  flexGrow: number
  right?: ReactNode
  sub?: ReactNode
}) {
  const variants = view?.variants
  const draw = useCallback(
    (w: number, h: number, hover: number | null, grow: number): Drawn => {
      const v = pickVariant(variants!, w - 8) // 8: room for the y labels
      return { ...bars(v.series, v.n, w, h, (pw) => clockLabels(v.slots, pw, v.step_h), v.marks, hover, true, { grow, fade: true }), meta: v }
    },
    [variants],
  )
  const title = (hover: number | null, drawn: Drawn | null): Parts => {
    if (!view?.variants) return [[[[metric.toUpperCase(), "bold"]], 0]]
    const v = (drawn?.meta as Variant | undefined) ?? view.variants[0]!
    return metricTitle(metric, view, v, hover)
  }
  return <Chart title={title} draw={variants?.length ? draw : null} empty={view?.empty} flexGrow={flexGrow} right={right} sub={sub} animate={range} />
}

// ---------------------------------------------------------------- the tables

function Top() {
  const s = useDash()
  const top = useView<TableView>(s.bridge, "top")
  useEffect(() => {
    const keys = (top?.rows ?? []).map((r) => r.key)
    if (keys.length && !keys.includes(s.top)) s.set({ top: keys[0] })
  }, [top])
  return (
    <Panel flexGrow={1} minHeight={6}>
      <box height={1} marginBottom={1} flexShrink={0}>
        <Fitted parts={top?.title} base={DASH.faint} flexGrow={0} />
      </box>
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
    <Panel maxHeight={11} flexShrink={0} paddingBottom={1}>
      <box height={1} marginBottom={1} flexShrink={0}>
        <Line segs={latest?.heading} base={DASH.faint} />
      </box>
      <Lines segs={latest?.body} />
    </Panel>
  )
}
