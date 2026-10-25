"""Make the README's looping previews of the three demo videos (docs/demos/*.webp): eight short moments of each, from
its hook to its ending, as a silent animated WebP that's light enough for the GitHub page.

  .venv\\Scripts\\python scripts\\previews.py

It needs the demos rendered first (episodes/demo_*/final/demo_*.mp4) and ffmpeg. The previews are only for the
GitHub page, so the downloads leave docs/demos/ out (scripts/package.py).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "demos"
WIDTH, FPS, QUALITY, CLIP = 320, 15, 55, 0.8   # pixels wide, frames a second, WebP quality, seconds per moment
PREVIEWS = {  # file: (demo, the second each moment starts)
    "rubber-duck": ("demo_doubling_duck", [1.0, 13.6, 19.6, 31.6, 41.8, 47.6, 61.6, 64.1]),
    "meteor": ("demo_disaster_pov", [0.4, 19.8, 26.0, 33.6, 51.6, 61.8, 65.8, 68.0]),
    "everyone-jumps": ("demo_everyone_jumps", [0.4, 7.6, 13.6, 19.6, 25.8, 27.8, 35.6, 43.6]),
}


def preview(ffmpeg: str, name: str, demo: str, starts: list[float]) -> Path:
    src = ROOT / "episodes" / demo / "final" / f"{demo}.mp4"
    if not src.is_file():
        raise FileNotFoundError(f"{src.relative_to(ROOT)} isn't there: render the {demo} demo first")
    n = len(starts)
    graph = [f"[0:v]split={n}" + "".join(f"[s{i}]" for i in range(n))]
    graph += [f"[s{i}]trim=start={t}:duration={CLIP},setpts=PTS-STARTPTS[v{i}]" for i, t in enumerate(starts)]
    graph.append("".join(f"[v{i}]" for i in range(n))
                 + f"concat=n={n}:v=1:a=0,fps={FPS},scale={WIDTH}:-2:flags=lanczos[out]")
    dest = OUT / f"{name}.webp"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(src), "-filter_complex", ";".join(graph), "-map", "[out]",
                    "-an", "-c:v", "libwebp_anim", "-quality", str(QUALITY), "-compression_level", "6", "-loop", "0",
                    str(dest)], check=True)
    return dest


def main() -> int:
    from studio import tools

    ffmpeg = tools.find_ffmpeg()
    if not ffmpeg:
        print("ffmpeg isn't installed: run reelforge setup first")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (demo, starts) in PREVIEWS.items():
        try:
            dest = preview(ffmpeg, name, demo, starts)
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            print(e)
            return 1
        print(f"wrote {dest.relative_to(ROOT)} ({dest.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
