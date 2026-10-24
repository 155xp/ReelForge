"""Retake the README's screenshots (docs/screenshots/*.png) and the dashboard guide's (dashboard/docs/*.png): the
first-run screens, every tab of the ReelForge window on its demo data and a clicked notification, the way Windows
Terminal draws them.

  .venv\\Scripts\\python scripts\\screenshots.py            all of them
  .venv\\Scripts\\python scripts\\screenshots.py app-publish first-run      just these

Nothing on this computer changes (STUDIO_DRY_SYSTEM=1), the demo data goes to a scratch database, and no window
opens: each screen is drawn headless with Textual, saved as SVG, then turned into a PNG by Playwright's browser.
The pictures leave out the demo's DEMO labels (REELFORGE_SCREENSHOTS=1), always have colour (NO_COLOR is ignored
here), and draw block characters (the logo's, and the tops and ends of the charts' bars and areas) as exact
rectangles, the way Windows Terminal draws them: a browser's fonts leave seams between them, or have none at all.

Retaking all of them also writes docs/screenshots/SOURCES.txt (scripts/shot_sources.py): what they were drawn from.
A release won't build once any of that changes, so every release has screenshots of the ReelForge it ships.
"""

from __future__ import annotations

import asyncio
import html
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
GUIDE = ROOT / "dashboard" / "docs"     # the dashboard guide's own pictures (dashboard/README.md)
os.environ.update(STUDIO_DRY_SYSTEM="1", REELFORGE_SCREENSHOTS="1", REELFORGE_SEXTANTS="1", COLORTERM="truecolor")
os.environ.pop("NO_COLOR", None)
sys.path.insert(0, str(ROOT))

APP_SIZE, GUIDE_SIZE, FIRST_RUN_SIZE, ONBOARD_SIZE = (180, 50), (200, 56), (120, 34), (140, 46)
APP_SHOTS = {  # name: (tab, notifications drawer open, select the first video, terminal size, folder)
    "app-overview": ("overview", False, False, APP_SIZE, OUT),
    "app-notifications": ("overview", True, False, APP_SIZE, OUT),
    "app-videos": ("videos", False, False, APP_SIZE, OUT),
    "app-compare": ("compare", False, False, APP_SIZE, OUT),
    "app-publish": ("publish", False, True, GUIDE_SIZE, OUT),   # wide enough for every upload button in one view
    "app-accounts": ("accounts", False, False, APP_SIZE, OUT),
    "app-updates": ("updates", False, False, APP_SIZE, OUT),
    "app-notification-click": ("overview", True, False, APP_SIZE, OUT),
    "overview": ("overview", True, False, GUIDE_SIZE, GUIDE),
    "notification-click": ("overview", True, False, GUIDE_SIZE, GUIDE),
    "updates": ("updates", False, False, GUIDE_SIZE, GUIDE),
}
CLICK_A_VIDEO_NOTE = {"app-notification-click", "notification-click"}  # taken after clicking one about a video
FIRST_RUN_SHOTS = {  # name: (first-run screen, onboarding step)
    "first-run": ("tools", None),
    "onboarding-format": ("onboard", 2),
    "onboarding-look": ("onboard", 4),
}


# ---------------------------------------------------------------- the screens, as SVG

def only_the_demos() -> None:
    """The Publish tab lists just the kit's own demo videos (examples/), whatever else is in this copy's folders."""
    from dashboard import videos

    demos = {p.parent.name for p in (ROOT / "examples").glob("*/episode.json")}
    every = videos.find
    videos.find = lambda cfg: [f for f in every(cfg) if f.stem in demos]


async def click_a_video_note(app, pilot) -> None:
    """Click the newest notification about a video (taking off, or passing a views milestone) in the drawer."""
    from textual.widgets import OptionList

    from dashboard import notify

    note = next(n for n in notify.recent() if notify.target(n).post)
    box = app.query_one("#notes", OptionList)
    box.highlighted = box.get_option_index(f"note-{note['id']}")
    box.focus()
    await pilot.pause(0.2)
    await pilot.press("enter")
    await pilot.pause(0.8)


async def app_shot(name: str, work: Path) -> Path:
    from dashboard import config, db, demo
    from dashboard.app import ReelForge

    tab, drawer, select, size, _ = APP_SHOTS[name]
    path = work / "demo.db"
    for suffix in ("", "-wal", "-shm"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
    db.init(path)
    cfg = config.load_config()
    demo.seed(video=demo.newest_video(cfg))
    app = ReelForge(cfg, demo.platforms(), demo=True, tab=tab, drawer=drawer)
    async with app.run_test(size=size) as pilot:
        await pilot.pause(1.0)
        if select:
            await pilot.press("down")
            await pilot.pause(0.5)
        if name in CLICK_A_VIDEO_NOTE:
            await click_a_video_note(app, pilot)
        app.save_screenshot(f"{name}.svg", str(work))
    return work / f"{name}.svg"


async def first_run_shot(name: str, work: Path) -> Path:
    from studio import firstrun, setup_flow, sounds
    from studio import paths as P

    start, step = FIRST_RUN_SHOTS[name]
    saved = P.ROOT, setup_flow.plan
    P.ROOT = Path(r"C:\Users\you\ReelForge")          # a neutral folder in the picture
    Item = setup_flow.Item
    setup_flow.plan = lambda: [                       # what a computer with nothing installed sees
        Item("blender", "Blender 4.5.5", "builds and renders your 3D scenes", False, "about 400 MB from blender.org",
             400),
        Item("ffmpeg", "ffmpeg", "turns the frames and sound into your video", False, "about 115 MB from gyan.dev",
             115),
        Item("sounds", "Sound effects", "booms, whooshes and hits for your videos", False,
             f"{sounds.mixkit_count()} from Mixkit, about 55 MB", 55),
        Item("command", "The reelforge command", "type reelforge in any terminal to open it", False,
             "no admin rights needed"),
        Item("shortcut", "Desktop shortcut", "a ReelForge icon on your desktop", True, "ready"),
    ]
    app = firstrun.FirstRun(start)
    async with app.run_test(size=FIRST_RUN_SIZE if start == "tools" else ONBOARD_SIZE) as pilot:
        await pilot.pause(0.6)
        if start == "tools":
            for _ in range(50):
                await pilot.pause(0.1)
                if app.screen.query("#items Horizontal"):
                    break
            await pilot.pause(0.3)
        if step is not None:
            await app.screen.show_step(step)
            await pilot.pause(0.4)
        app.save_screenshot(f"{name}.svg", str(work))
    P.ROOT, setup_flow.plan = saved
    return work / f"{name}.svg"


# ---------------------------------------------------------------- block characters as rectangles

# A cell is 8 sub-columns by 24 sub-rows: halves, sextants' thirds and the charts' eighths all land on that grid.
COLS, ROWS = 8, 24
OVERLAP = 1.0     # px: neighbouring rectangles overlap, so no hairline shows between them
BLOCKS = {        # character -> [(first sub-column, end, first sub-row, end)]
    "\u2588": [(0, 8, 0, 24)],
    "\u2580": [(0, 8, 0, 12)],
    "\u2590": [(4, 8, 0, 24)],
    "\u2594": [(0, 8, 0, 3)],
    "\u2595": [(7, 8, 0, 24)],
    **{chr(0x2580 + k): [(0, 8, 24 - 3 * k, 24)] for k in range(1, 8)},   # \u2581\u2582\u2583\u2584\u2585\u2586\u2587: the bars' and areas' tops
    **{chr(0x2590 - k): [(0, k, 0, 24)] for k in range(1, 8)},            # \u2589\u258a\u258b\u258c\u258d\u258e\u258f: the Compare bars' ends
}


def parts(ch: str) -> list[tuple[int, int, int, int]] | None:
    if ch in BLOCKS:
        return BLOCKS[ch]
    if not 0x1FB00 <= ord(ch) <= 0x1FB3B:
        return None
    bits = ord(ch) - 0x1FB00 + 1   # the sextants are the patterns 1..62 without 21 and 42 (the half blocks)
    bits += (bits >= 21) + (bits >= 41)
    return [(p % 2 * 4, p % 2 * 4 + 4, p // 2 * 8, p // 2 * 8 + 8) for p in range(6) if bits >> p & 1]


def draw_blocks(svg: str) -> str:
    fills = dict(re.findall(r"\.([\w-]+)\s*\{\s*fill:\s*(#[0-9a-fA-F]{6})", svg))
    tops = {cid: float(y) for cid, y in re.findall(
        r'<clipPath id="([^"]+-line-\d+)">\s*<rect x="[\d.]+" y="([\d.]+)" width="[\d.]+" height="[\d.]+"\s*/>', svg)}
    ys = sorted(tops.values())
    pitch = ys[1] - ys[0] if len(ys) > 1 else 24.4
    rects: list[str] = []

    def replace(m: re.Match) -> str:
        cls, x, y, length, rest, body = m.groups()
        text = html.unescape(body)
        cells = [parts(ch) for ch in text]
        if not any(cells):
            return m.group(0)
        clip = re.search(r'clip-path="url\(#([^)]+)\)"', rest)
        top = tops.get(clip.group(1)) if clip else None
        top = float(y) - 18.5 if top is None else top
        cw = float(length) / len(text)
        fill = fills.get(cls.split()[0], "#ffffff")
        # Every piece, in sub-cells from the text's start; side-by-side pieces of the same height become one.
        pieces = sorted((r0, r1, COLS * i + c0, COLS * i + c1)
                        for i, cell in enumerate(cells) for c0, c1, r0, r1 in cell or [])
        merged: list[list[int]] = []
        for r0, r1, c0, c1 in pieces:
            if merged and merged[-1][:2] == [r0, r1] and merged[-1][3] == c0:
                merged[-1][3] = c1
            else:
                merged.append([r0, r1, c0, c1])
        for r0, r1, c0, c1 in merged:
            rects.append(f'<rect x="{float(x) + c0 * cw / COLS:.2f}" y="{top + r0 * pitch / ROWS:.2f}" '
                         f'width="{(c1 - c0) * cw / COLS + OVERLAP:.2f}" '
                         f'height="{(r1 - r0) * pitch / ROWS + OVERLAP:.2f}" '
                         f'fill="{fill}" shape-rendering="crispEdges"/>')
        new = "".join("&#160;" if cell or ch == " " else html.escape(ch) for ch, cell in zip(text, cells))
        return m.group(0).replace(">" + body + "</text>", ">" + new + "</text>")

    svg = re.sub(r'<text class="([^"]+)" x="([\d.]+)" y="([\d.]+)" textLength="([\d.]+)"([^>]*)>(.*?)</text>',
                 replace, svg)
    if rects:   # inside the text's own group, so the window's offsets apply to them too
        start = re.search(r'<g class="[^"]+-matrix">', svg)
        end = svg.index("</g>", start.end())
        svg = svg[:end] + "".join(rects) + svg[end:]
    return svg


# ---------------------------------------------------------------- SVG to PNG

async def to_png(svgs: list[Path]) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge" if sys.platform == "win32" else None)
        page = await browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        for svg in svgs:
            png = (APP_SHOTS[svg.stem][4] if svg.stem in APP_SHOTS else OUT) / f"{svg.stem}.png"
            await page.goto(svg.resolve().as_uri())
            await (await page.query_selector("svg")).screenshot(path=str(png))
            print("wrote", png.relative_to(ROOT))
        await browser.close()


async def main(names: list[str]) -> int:
    unknown = [n for n in names if n not in APP_SHOTS and n not in FIRST_RUN_SHOTS]
    if unknown:
        print("unknown:", ", ".join(unknown), "| choose from:", ", ".join([*FIRST_RUN_SHOTS, *APP_SHOTS]))
        return 2
    names = names or [*FIRST_RUN_SHOTS, *APP_SHOTS]
    only_the_demos()
    with tempfile.TemporaryDirectory(prefix="reelforge-shots-") as tmp:
        work = Path(tmp)
        svgs = []
        for name in names:
            svg = await (first_run_shot if name in FIRST_RUN_SHOTS else app_shot)(name, work)
            svg.write_text(draw_blocks(svg.read_text(encoding="utf-8")), encoding="utf-8")
            svgs.append(svg)
        OUT.mkdir(parents=True, exist_ok=True)
        await to_png(svgs)
    if set(names) == {*FIRST_RUN_SHOTS, *APP_SHOTS}:
        import shot_sources

        print("wrote", shot_sources.record().relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
