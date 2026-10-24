"""Composite rendered frames + glitches + text/HUD + audio into the final 9:16 video, or make the cover.

  python pipeline/post/compose.py <episode_dir> --video
  python pipeline/post/compose.py <episode_dir> --cover
  python pipeline/post/compose.py <episode_dir> --preview 5,22,47,67,75   (writes build/preview/*.jpg)
"""
import argparse
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
import overlay  # noqa: E402

W, H = config.WIDTH, config.HEIGHT


# ---------------------------------------------------------------- formatting

def fmt_distance_imperial(m):
    if m >= 804.67:
        return f"{m / 1609.34:.1f} mi"
    ft = m * 3.28084
    return f"{ft:,.0f} ft" if ft >= 1 else "0 ft"


def fmt_miles(v):
    return f"{v * 5280:,.0f} ft" if v < 1 else f"{v:,.0f} mi"


FORMATS = {
    "distance_imperial": fmt_distance_imperial,
    "int_commas": lambda v: f"{int(v):,}",
    "mach": lambda v: f"{v:.1f}",
    "miles": fmt_miles,
    "seconds": lambda v: f"{v:.1f} s",
    "times": lambda v: f"{v:,.1f}",
    "raw": str,
}


def hud_text(spec, series, t, frame_idx):
    hud = spec.get("hud")
    if not hud:
        return None
    for ch in hud["chapters"]:
        if ch["from"] <= t < ch["to"]:
            i = min(max(frame_idx, 0), series["frames"] - 1)
            vars_ = {k: FORMATS[v["format"]](series[v["series"]][i]) for k, v in hud.get("vars", {}).items()}
            color = tuple(ch["color"]) if "color" in ch else None
            return ch["label"].format(**vars_), ch["value"].format(**vars_), ch["sub"].format(**vars_), color
    return None


def keyed(points, t, default=0.0):
    """Piecewise-linear value from [[time, value], ...]."""
    if not points:
        return default
    xs, ys = zip(*points)
    return float(np.interp(t, xs, ys))


def flash_amount(spec, t):
    total, color = 0.0, (255, 255, 255)
    for f in spec.get("flashes", []):
        at, rise, fall = f["at"], f.get("rise", 0.05), f.get("fall", 0.3)
        if at - rise <= t < at:
            a = (t - (at - rise)) / rise
        elif t >= at:
            a = math.exp(-(t - at) / fall)
        else:
            a = 0.0
        a *= f.get("max", 0.8)
        if a > total:
            total, color = a, tuple(f.get("color", (255, 255, 255)))
    return total, color


# ---------------------------------------------------------------- glitches

def glitch_strength(spec, t):
    for g in spec.get("glitches", []):
        if g["start"] <= t < g["end"]:
            if "ramp_from" in g:
                s = (t - g["start"]) / (g["end"] - g["start"])
                return g["ramp_from"] + (g["strength"] - g["ramp_from"]) * s, g
            return g["strength"], g
    return 0.0, None


def glitch_frame(arr, s, rng):
    """Datamosh-ish corruption: RGB split, sliced row offsets, blocky dropouts. arr: HxWx3 uint8."""
    out = arr.copy()
    dx = int(6 + 30 * s)
    out[:, :, 0] = np.roll(arr[:, :, 0], dx, axis=1)
    out[:, :, 2] = np.roll(arr[:, :, 2], -dx, axis=1)
    for _ in range(int(4 + 22 * s)):
        y0 = rng.randrange(0, H - 8)
        hgt = rng.randrange(6, int(30 + 180 * s))
        shift = rng.randrange(-int(40 + 220 * s), int(40 + 220 * s) + 1)
        out[y0:y0 + hgt] = np.roll(out[y0:y0 + hgt], shift, axis=1)
    for _ in range(int(8 * s)):
        bw, bh = rng.randrange(40, 320), rng.randrange(20, 160)
        x0, y0 = rng.randrange(0, W - bw), rng.randrange(0, H - bh)
        if rng.random() < 0.5:
            # missing-texture checker block
            yy, xx = np.mgrid[0:bh, 0:bw]
            chk = ((yy // 16 + xx // 16) % 2).astype(bool)
            out[y0:y0 + bh, x0:x0 + bw] = np.where(chk[..., None], [255, 0, 255], [0, 0, 0])
        else:
            out[y0:y0 + bh, x0:x0 + bw] = out[y0, x0:x0 + bw][None, :, :]
    return out


# ---------------------------------------------------------------- frames

class Episode:
    def __init__(self, ep_dir):
        self.dir = ep_dir
        self.spec = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
        self.series = json.loads((ep_dir / "build" / "series.json").read_text(encoding="utf-8"))
        self.fps = self.spec["fps"]
        self.total = int(round(self.spec["duration"] * self.fps))
        self.rendered = int(round(self.spec["render_until"] * self.fps))
        self.frames_dir = ep_dir / "build" / "frames"
        self.brand = self.spec.get("hud", {}).get("brand", config.CHANNEL_NAME.upper())
        hud_style = self.spec.get("hud", {})
        overlay.HUD_PANEL = bool(hud_style.get("panel", False))
        overlay.HUD_BRAND = bool(hud_style.get("show_brand", False))
        self._prev_value = None
        layout = self.spec.get("layout", {})
        self.line_y = layout.get("line_y", overlay.LINE_Y)        # a number, or [[t, y], ...] to follow the shot
        overlay.TITLE_Y = layout.get("title_y", overlay.TITLE_Y)
        # optional: move each story line off the subject (series["subject_box"]: screen box per frame)
        self.line_y_for = {}
        if layout.get("avoid_subject") and self.series.get("subject_box"):
            for start, end, text, *_ in self.spec.get("lines", []):
                self.line_y_for[(start, text)] = self._clear_y(start, end, text)

    def _clear_y(self, start, end, text):
        boxes = self.series["subject_box"]
        f0, f1 = int(round(start * self.fps)), int(round(end * self.fps))
        bs = [boxes[i] for i in range(max(f0, 0), min(f1, len(boxes))) if boxes[i]]
        y0 = keyed(self.line_y, start) if isinstance(self.line_y, list) else self.line_y
        if not bs:
            return y0
        bx = (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))
        layer = overlay.text_layer(text, config.FONT_SERIF_ITALIC, 48, max_w=overlay.TEXT_MAX_W, blur=8, shadow=200, halo=3)
        hh = (layer.height - 2 * layer.info["pad"]) / 2 + 14
        lo, hi = 870 + hh, 1500 - hh                     # below the HUD panel, above TikTok's caption area

        def overlap(y):
            return max(0.0, min(y + hh, bx[3]) - max(y - hh, bx[1]))

        cands = [y0, bx[3] + hh + 26, bx[1] - hh - 26, hi, lo]
        ok = [y for y in cands if lo <= y <= hi and overlap(y) == 0]
        return ok[0] if ok else min((y for y in cands if lo <= y <= hi), key=overlap, default=y0)

    def world(self, idx):
        """Rendered frame (0-based index) as an RGB array, or black past the render range."""
        if idx >= self.rendered:
            return np.zeros((H, W, 3), np.uint8)
        p = self.frames_dir / f"f_{idx + 1:04d}.jpg"
        if not p.exists() or p.stat().st_size == 0:
            raise FileNotFoundError(f"missing render {p}")
        return np.asarray(Image.open(p).convert("RGB"))

    def frame(self, idx):
        spec, fps = self.spec, self.fps
        t = idx / fps
        rw = spec.get("rewind")
        if spec.get("loop_to_start") and rw and t >= rw["end"]:
            return self.frame(0)  # the last beat is the first frame again, so the video loops seamlessly
        rng = random.Random(idx * 7919 + 13)
        s, g = glitch_strength(spec, t)
        t_src = t
        if rw and rw["start"] <= t < rw["end"]:
            p = (t - rw["start"]) / (rw["end"] - rw["start"])
            t_src = rw["from_time"] + (rw["to_time"] - rw["from_time"]) * p ** 1.6   # accelerating rewind
            s = max(s, rw.get("glitch", 0.4) * rng.uniform(0.5, 1.2))
        src = int(round(t_src * fps))
        if g and g.get("stutter"):
            hold = 1 + int(s * 5)
            g0 = int(round(g["start"] * fps))
            src = g0 + ((idx - g0) // hold) * hold
            if t > g["end"] - 0.45:
                src = int(round((g["end"] - 0.45) * fps))  # final freeze
        arr = self.world(min(src, self.rendered - 1) if t_src < spec["render_until"] else src)
        if s > 0:
            arr = glitch_frame(arr, s, rng)
        b0, b1 = spec.get("blackout", [1e9, 1e9])
        if b0 <= t < b1:
            arr = np.zeros_like(arr)
        canvas = Image.fromarray(arr).convert("RGBA")

        sl = keyed(spec.get("speedlines"), t)
        if sl > 0.01:
            overlay.draw_speedlines(canvas, sl, rng, tuple(spec.get("speedlines_center", (540, 860))))
        fa, fcol = flash_amount(spec, t)
        if fa > 0.01:
            canvas.alpha_composite(Image.new("RGBA", canvas.size, (*fcol, int(255 * min(fa, 1.0)))))

        tc = spec.get("title_card")
        if tc:
            overlay.draw_title(canvas, spec["title"], overlay.window_alpha(t, tc["start"], tc["end"], 0.3, 0.6),
                               scrim=tc.get("scrim", 0.0))
        line_y = keyed(self.line_y, t) if isinstance(self.line_y, list) else self.line_y
        scrim = spec.get("line_style", {}).get("scrim", 0.0)
        for start, end, text, *opt in spec.get("lines", []):
            a = overlay.window_alpha(t, start, end)
            if a > 0:
                # a line may carry its own style, e.g. [s, e, "text", {"scrim": 0.85}] over a bright cloud, or
                # {"y": 1150} to sit clear of the follow call-to-action
                o = opt[0] if opt else {}
                y = o["y"] if "y" in o else self.line_y_for.get((start, text), line_y)
                overlay.draw_line(canvas, text, a, y, scrim=o.get("scrim", scrim))

        # debug tags on objects (screen positions from the effect), following the shown (source) frame
        for tag in self.series.get("tags", []):
            i = min(max(src, 0), len(tag["xy"]) - 1)
            xy = tag["xy"][i]
            if xy is None:
                continue
            ta = overlay.window_alpha(t_src, tag["from"], tag["to"], 0.2, 0.2) if t_src == t else 0.8
            if t_src != t and not (tag["from"] <= t_src < tag["to"]):
                continue
            x, y = xy
            if -40 < x < W + 40 and -40 < y < H + 40:
                boxes = self.series.get("subject_box") or []
                avoid = boxes[min(max(src, 0), len(boxes) - 1)] if boxes else None
                tint, sub = None, tag.get("sub", "")
                if tag.get("gold_at") is not None and t_src >= tag["gold_at"]:
                    # price tags turn gold once you can afford the thing (or pass it: tag["flip_text"])
                    tint, sub = (255, 200, 80), f"{sub}  {tag.get('flip_text', '→ AFFORDABLE')}"
                overlay.draw_tag(canvas, x, y, tag["label"], sub, ta, avoid=avoid, tint=tint)

        hud = hud_text(spec, self.series, t_src, src)
        if hud and not (b0 <= t < b1):
            label, value, sub, vcolor = hud
            if t_src != t:
                sub = rw.get("hud_sub", sub)
            hg = 0.0
            if value != self._prev_value and rng.random() < 0.12:
                hg = 0.35
            if rng.random() < 0.01 + 0.04 * (t / spec["duration"]):
                hg = max(hg, rng.uniform(0.3, 0.9))
            hg = max(hg, s)
            self._prev_value = value
            overlay.draw_hud(canvas, t, label, value, sub, self.brand, glitch=hg, rng=rng, value_color=vcolor)

        ec = spec.get("end_card")
        if ec and t >= ec["start"]:
            overlay.draw_end_card(canvas, spec["title"], ec["fact"], self.brand if ec.get("brand") else "",
                                  min(1.0, (t - ec["start"]) / 0.6))

        cta = spec.get("cta")   # {"start", "end", "text", "sub", "y"}: over the rewind (the loop stays seamless) or the end card
        if cta:
            overlay.draw_cta(canvas, cta["text"], cta.get("sub", ""), overlay.window_alpha(t, cta["start"], cta["end"], 0.2, 0.2),
                             cta.get("y", 1300))
        if spec.get("demo"):
            overlay.demo_watermark(canvas)
        return canvas.convert("RGB")


def make_video(ep):
    final = ep.dir / "final"
    final.mkdir(exist_ok=True)
    out = final / f"{ep.spec['id']}.mp4"
    audio = ep.dir / "build" / "audio.wav"
    cmd = [config.FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(ep.fps), "-i", "-"]
    if audio.exists():
        cmd += ["-i", str(audio), "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-profile:v", "high",
            "-movflags", "+faststart", "-shortest", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for idx in range(ep.total):
        proc.stdin.write(ep.frame(idx).tobytes())
        if idx % 300 == 0:
            print(f"  frame {idx}/{ep.total}", flush=True)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    print(f"  wrote {out}")


def make_cover(ep):
    c = ep.spec["cover"]
    idx = int(round(c["time"] * ep.fps))
    base = Image.fromarray(ep.world(idx))
    img = overlay.draw_cover(base, c["kicker"], c["keyword"], c.get("tail", ""), ep.brand if c.get("brand") else None)
    if ep.spec.get("demo"):
        img = img.convert("RGBA")
        overlay.demo_watermark(img)
        img = img.convert("RGB")
    out = ep.dir / "final" / "cover.jpg"
    out.parent.mkdir(exist_ok=True)
    img.save(out, quality=92)
    print(f"  wrote {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode", type=Path)
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--cover", action="store_true")
    ap.add_argument("--preview", default="")
    args = ap.parse_args()
    if args.video or args.cover:
        config.require_ffmpeg()
    ep = Episode(args.episode.resolve())
    if args.preview:
        d = ep.dir / "build" / "preview"
        d.mkdir(exist_ok=True)
        for s in args.preview.split(","):
            idx = int(round(float(s) * ep.fps))
            ep.frame(idx).save(d / f"p_{float(s):05.1f}.jpg", quality=90)
        print(f"  wrote previews to {d}")
    if args.video:
        make_video(ep)
    if args.cover:
        make_cover(ep)


if __name__ == "__main__":
    main()
