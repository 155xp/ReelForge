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
  profile: ProfileView
}

/** The profile this window shows (one profile for each channel: studio/profiles.py), for the button at the top left.
 * elsewhere: the other profiles' unread notifications (a red dot on the button). */
export interface ProfileView {
  key: string
  name: string
  main: boolean
  several: boolean
  elsewhere: number
}

/** One profile in the profile button's menu. */
export interface ProfileRow {
  key: string
  number: number
  name: string
  current: boolean
  main: boolean
  unread: number
  where: string // its folder (profiles/<name>), or "" for the ReelForge folder's own
  why: string // why this window can't delete it (its own, the first one, open in another window), or ""
  platforms: { key: string; short: string; name: string; color: string }[]
}

export interface ProfilesMenu {
  rows: ProfileRow[]
  current: string
  demo: boolean
  onboarded: boolean
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

/** A platform at the top of the Stats tab: ticked (counted in the totals) or left out; has: it has stats to count. */
export interface TotalsToggle {
  key: string
  name: string
  short: string
  color: string
  counted: boolean
  has: boolean
}

/** A bucket on a Stats chart, for the hover read-out: the total at its end (or now), what it gained in the bucket, and
 * each counted platform's reading then. */
export interface TotalsHover {
  total: number
  gain: number | null
  each: Record<string, number | null>
}

/** A platform in a Stats chart's breakdown: its number now, its gain over the chart's span, its share of the total,
 * what it gained in each bucket, and when it was last read once that's a while ago. */
export interface TotalsRow {
  key: string
  name: string
  short: string
  color: string
  counted: boolean
  left_out: boolean
  value: number | null
  gained: number | null
  share: number | null
  gains: (number | null)[]
  stale: string | null // "last read 34h ago": a platform whose reads stopped a while ago
}

/** One of the Stats tab's charts (dashboard/stats_tab.py totals_metric): followers or likes added up. */
export interface TotalsMetric {
  name: string
  empty?: string | null
  n?: number
  step_h?: number
  slots?: Slot[]
  series?: Series[]
  hover?: (TotalsHover | null)[]
  marks?: Mark[]
  title?: Parts
  note?: Segs | null
  rows?: TotalsRow[]
  total?: { value: number | null; gained: number | null }
}

export interface TotalsView {
  range: string
  ranges: Segs
  toggles: TotalsToggle[]
  metrics: Record<string, TotalsMetric>
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

/** One platform on the Accounts tab: on (connected), login (its handle is in, waiting for the one log-in) or off
 * (not connected: a box for its @handle, Connect and Sign up). */
export interface AccountPanelView {
  key: string
  name: string
  color: string
  state: "on" | "login" | "off"
  status: Segs // the first line, with Disconnect at its right end while there's room
  status_short: Segs | null // ... for a narrow panel
  disconnect: Segs | null
  body: Segs
  note: Segs
  signup?: boolean
  logs_in?: boolean
  login_label?: string
  profile_disabled?: boolean
  refresh_disabled?: boolean
  show_log?: boolean
  chart?: null | {
    heading: Segs
    n: number
    step_h: number
    slots: Slot[]
    values: (number | null)[]
    series: Series[]
  }
}

export interface AccountsView {
  panels: AccountPanelView[]
  hint: Parts | null // "Connect the platforms you post to ..." while one isn't connected
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
  done?: boolean // the update is in; ReelForge restarts
  failed?: boolean // it didn't finish, and the version you have keeps working
}
