# ReelForge's window

Everything ReelForge shows in a terminal after setup's first box (the ReelForge window, the first-run screens and
first-time setup) is this [OpenTUI](https://github.com/anomalyco/opentui) app: TypeScript with React, run by
[Bun](https://bun.com). The numbers, the stats reads and every button's work stay in Python; the window starts
`python -m studio.bridge` and talks to it in lines of JSON over stdin and stdout.

```
reelforge ──▶ studio/ui.py ──▶ bun ui/src/main.tsx dashboard '{"tab": "publish"}'
                                        │   ▲
                         calls (JSON)   ▼   │   views (JSON): what to draw
                               python -m studio.bridge
                                 ├─ dashboard/service.py      the ReelForge window
                                 └─ studio/setup_service.py   the first-run screens and the channel's questions
```

The Python side sends each piece of the window as a view (`cards`, `trends`, `videos`, `notes`, …) whenever it
changes, as styled text (`dashboard/view.py`: segments of `[text, style, action]`) and plain numbers. The window
keeps the newest of each and draws it: the layout, the tables and lists, the charts (`src/lib/chart.ts`), fitting
titles and cards to the room they get, the mouse, the keys and the dialogs.

## Running it

Setup puts Bun in `tools/bun` and the packages in `node_modules` (`python -m studio.ui install`); `studio/ui.py`
checks both each time ReelForge opens. To work on the window, from this folder (with a Bun of your own, or
`../tools/bun/bun`):

```
bun install                                    the packages, dev ones included
bun src/main.tsx dashboard '{"demo": true}'    the window on made-up stats
bun src/main.tsx setup '{"start": "onboard"}'  the channel's questions (it writes your answers when you press Create)
bun x tsc --noEmit -p .                        the types
bun test                                       the tests
```

The window finds the kit's Python by itself (`REELFORGE_PYTHON`, else `../.venv`). The Python side's stderr goes to
`dashboard/data/window-log.txt` when ReelForge opens the window.

## What's where

| Path | What it is |
|---|---|
| `src/main.tsx` | Starts the renderer and the Python side, mounts the window or the first-run screens, quits cleanly |
| `src/root.tsx` | The window round the profiles (one per channel): switching starts a Python side on the profile picked (`REELFORGE_PROFILE`) and lets the old one finish; New profile shows the channel's questions inside the window |
| `src/bridge.ts` | The link to `studio/bridge.py`: calls, replies and views |
| `src/dashboard/` | The ReelForge window: `App.tsx` (the header with its sliding tab marker, the bell, the status bar, keys), a file per tab, `Drawer.tsx`, `Dialogs.tsx`, `Profiles.tsx` (the profile button and its menu) |
| `src/setup/` | The first-run screens (`App.tsx`), the channel's questions (`Onboard.tsx`) and the steps and logo above them (`Frame.tsx`) |
| `src/theme.ts` | The colours, and `restyle`: the Python side's colours mapped to them as its messages arrive |
| `src/ui/` | The pieces: buttons, tables and lists, charts, fields, panels, dialogs, pop-ups, block art (the big numbers, sparklines, the bell), and `Motion.tsx` (counting up, growing in, sliding, fading) |
| `src/lib/` | Charts in cells, styled text, fitting parts to a width, number formats, keyboard focus |
| `test/` | `bun test`: the charts and cards on their own, and the window and first-run screens drawn without a terminal, clicked through on demo data with the real Python side |
| `scripts/headless.tsx` | The window on OpenTUI's test renderer (the tests and screenshots use it) |
| `scripts/shots.tsx` | The README's screenshots as SVGs; `scripts/screenshots.py` (in the ReelForge folder) turns them into PNGs |

## How it looks

Calm and dark: panels a step lighter than the window instead of boxes, the app's own chrome in white and greys, so
the colours that show are the platforms' (TikTok cyan, YouTube red, Instagram purple, X white), green and red for up
and down, amber for the marks where a video went up, and the forge's red-to-ember gradient on the buttons that do the
main thing. The Python side's views carry the colours it always has; `restyle` (`src/theme.ts`) puts them in this
palette, so nothing on that side changes.

Things move, briefly: the numbers on the Overview's tiles count up, the charts grow in (again on a new range), the
marker under the tabs slides and the tab you open slides in, the drawer slides in from the right, dialogs fade in,
and pop-ups slide in and fade out. It all runs on OpenTUI's timeline engine, which keeps the renderer drawing only
while something moves; `REELFORGE_MOTION=0` turns it off.

## Keys and the mouse

Everything works with either. Tab and Shift+Tab move between buttons, lists and fields in reading order (a dialog
keeps Tab inside itself); Enter or Space presses a button, the arrows move through a list or table, Enter (or a
click on the highlighted row) opens it. In the ReelForge window 1-6 switch tabs and r / R refresh, except while a
text field has the keyboard, p opens the profile menu and ? the help; Esc leaves the field, closes a dialog or the drawer. Ctrl+Q
quits.
