// What the Python side (dashboard/service.py) sends the window: the start-up facts, then one view per piece of the
// window, each sent again whenever it changes.

import type { Mark, Series, Slot } from "../lib/chart"
import type { Option, TableData } from "../ui/Lists"
import type { Parts, Segs } from "../lib/styled"

export interface PlatformInfo {
  key: string
  name: string
  color: string
  short: string
}

export interface Init {
  platforms: PlatformInfo[]
  tab: string
  drawer: boolean
  test: boolean
  demo: boolean
  screenshots: boolean
  title: string
  files: string
  files_window: string
  bin: string
  anvil: [string, string | null, string | null][][]
  quadrants: boolean
  help: [string, string][]
  keys: [string, string][]
  version: string
  max_tags: number
  first_tag: string
  default_tags: string
  caption_placeholder: string
  tags_placeholder: string
  copies: Record<string, [string, string]>
  badges_how: string
  ranges: Record<string, string>
  videos_dir: string
}

export interface CardView {
  id: string
  color: string
  titles: string[]
  gains: number[]
  captions: string[]
  values?: Record<string, number | null>
  changes?: Record<string, number | null>
  message?: Segs
}

export interface Variant {
  step_h: number
  n: number
  unit: string
  slots: Slot[]
  series: Series[]
  marks: Mark[]
}

export interface MetricView {
  empty?: string | null
  variants?: Variant[]
  span?: string
  hourly?: boolean
  summary?: { latest: number | null; gained: number | null; pace: number | null; change: number | null }
}

export interface TrendsView {
  range: string
  ranges: Segs
  legend: Segs
  legend_short: Segs
  metrics: Record<string, MetricView>
}

export type TableView = TableData & { title?: Parts; hint?: Parts; select?: string | null; focus?: boolean; heading?: Segs }

export interface DetailView {
  key: string | null
  title: Segs
  series?: Series[]
  span?: number
  empty?: string | null
}

export interface CompareChart {
  key: string
  heading: Segs
  series?: Series[]
  span?: number
  empty?: string | null
}

export interface CompareView {
  heading: Segs
  bars: [string, [string, number, string, string][]][]
  charts: CompareChart[]
  table: TableData
}

export interface FilesView {
  heading: Segs
  items: Option[]
  empty: Segs[] | null
  selected: string | null
}

export interface PreviewView {
  caption: Segs
  tags: Segs
  rows: { name: string; color: string; text: string }[]
}

export interface AccountPanelView {
  key: string
  name: string
  color: string
  body: Segs
  note: Segs
  logs_in: boolean
  login_label: string
  profile_disabled: boolean
  refresh_disabled: boolean
  show_log: boolean
  chart: null | {
    heading: Segs
    n: number
    step_h: number
    slots: Slot[]
    values: (number | null)[]
    series: Series[]
  }
}

export interface NoteView {
  id: number
  mark: Segs
  title: Segs
  body: string
  ago: string
  read: boolean
}

export interface NotesView {
  unread: number
  head: Segs
  close: Segs
  tools: Segs
  items: NoteView[]
  empty: string
}

export interface UpdateView {
  newer: boolean
  status: Segs
  apply: { show: boolean; disabled: boolean; label: string }
  check_disabled: boolean
  notes: string
  how: Segs
  updating: boolean
}

export interface UpdateStep {
  step?: Segs
  status?: Segs
  progress?: { done: number; total: number | null } | null
}
