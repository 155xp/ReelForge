"""Retake the README's screenshots (docs/screenshots/*.png) and the dashboard guide's (dashboard/docs/*.png): the
first-run screens, every tab of the ReelForge window on its demo data, the profile menu and a clicked notification.

  .venv\\Scripts\\python scripts\\screenshots.py            all of them
  .venv\\Scripts\\python scripts\\screenshots.py app-publish first-run      just these

Nothing on this computer changes (STUDIO_DRY_SYSTEM=1), the demo data goes to a scratch database, and no window
opens: ui/scripts/shots.tsx draws each screen with OpenTUI's test renderer and the real Python side (with the sample
data in scripts/shots_preload.py), clicks through it where a picture needs that, and saves it as an SVG of a terminal
window, block characters (the logo's, the bell's, the charts' bars) drawn as exact rectangles the way Windows Terminal
draws them. Playwright's browser then turns each SVG into a PNG.

Retaking all of them also writes docs/screenshots/SOURCES.txt (scripts/shot_sources.py): what they were drawn from.
A release won't build once any of that changes, so every release has screenshots of the ReelForge it ships.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from studio import ui  # noqa: E402

NAMES = ["first-run", "setup-format", "setup-accounts", "first-run-ready", "app-overview",
         "app-notifications", "app-videos", "app-compare", "app-publish", "app-accounts", "app-profiles", "app-settings",
         "app-updates", "app-notification-click", "overview", "notification-click", "updates"]


def draw(names: list[str], work: Path) -> list[tuple[str, Path, Path]]:
    """Each screen as an SVG: (name, its folder in the kit, the SVG). The modules the Python side drew with go in
    work/modules.txt."""
    if not ui.ensure():
        raise SystemExit("The window can't run here (see above).")
    env = dict(os.environ, STUDIO_DRY_SYSTEM="1", REELFORGE_PYTHON=sys.executable, PYTHONUTF8="1",
               REELFORGE_SHOT_MODULES=str(work / "modules.txt"))
    env.pop("NO_COLOR", None)
    res = subprocess.run([str(ui.bun_path()), "scripts/shots.tsx", str(work), *names], cwd=ui.UI, env=env,
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise SystemExit(f"Drawing the screens didn't work:\n{res.stdout}\n{res.stderr}")
    out = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            out.append((parts[0], ROOT / parts[1], Path(parts[2])))
    return out


async def to_png(shots: list[tuple[str, Path, Path]]) -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge" if sys.platform == "win32" else None)
        page = await browser.new_page(viewport={"width": 1600, "height": 1200}, device_scale_factor=1)
        for name, folder, svg in shots:
            folder.mkdir(parents=True, exist_ok=True)
            png = folder / f"{name}.png"
            await page.set_content('<body style="margin:0;background:transparent">' + svg.read_text("utf-8") + "</body>")
            await page.wait_for_timeout(300)  # the font
            await (await page.query_selector("svg")).screenshot(path=str(png), omit_background=True)
            print("wrote", png.relative_to(ROOT))
        await browser.close()


def main(names: list[str]) -> int:
    unknown = [n for n in names if n not in NAMES]
    if unknown:
        print("unknown:", ", ".join(unknown), "| choose from:", ", ".join(NAMES))
        return 2
    names = names or NAMES
    with tempfile.TemporaryDirectory(prefix="reelforge-shots-") as tmp:
        shots = draw(names, Path(tmp))
        asyncio.run(to_png(shots))
        listed = Path(tmp) / "modules.txt"
        modules = {Path(line) for line in listed.read_text("utf-8").splitlines() if line} if listed.exists() else set()
    if set(names) == set(NAMES):
        import shot_sources

        print("wrote", shot_sources.record(modules).relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
