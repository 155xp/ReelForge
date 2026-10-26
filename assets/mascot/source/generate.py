#!/usr/bin/env python3
"""ReelForge mascot animation generator.

Every animation is drawn from the one 35x22 sprite below, so the GIFs and the
OpenTUI frames always match. Edit the sprite or an animation, then re-run:

    python source/generate.py

Needs Pillow (pip install pillow). Writes gifs/, opentui/reelforge-frames.ts
and preview.html next to this folder.
"""
import math
import os
import random

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ── colours ────────────────────────────────────────────────────────────────
STATIC = {
    "b": "#171618",  # body
    "d": "#0c0b0d",  # deep shadow / face plate
    "g": "#2c2a2e",  # dim bevel
    "G": "#4e4a4f",  # bevel highlight
}
# The glowing parts (r, R, O, E) recolour with heat: -2 cold ... 3 white-hot.
HEAT = {
    -2: {"r": "#3d1015", "R": "#5e1419", "O": "#6e1d17", "E": "#7c1d18"},
    -1: {"r": "#6e131d", "R": "#a5161f", "O": "#b72c1f", "E": "#c42b22"},
    0: {"r": "#b81a2a", "R": "#f71e27", "O": "#fd4b33", "E": "#ff3b2e"},
    1: {"r": "#e0242a", "R": "#ff4a2a", "O": "#ff7a2e", "E": "#ff5a30"},
    2: {"r": "#ff4a2a", "R": "#ff7a2e", "O": "#ffb340", "E": "#ff8a3a"},
    3: {"r": "#ff7a2e", "R": "#ffb340", "O": "#ffefc2", "E": "#ffd34d"},
}
FX = {
    "w": "#fff4d6",  # white-hot spark
    "y": "#ffd34d",
    "o": "#ff8a2a",
    "R": "#f71e27",
    "m": "#8a1620",  # dying ember
    "k": "#141316",  # hammer outline
    "s": "#d4cfd8",  # steel light
    "t": "#938e99",  # steel mid
    "u": "#5a5660",  # steel dark
    "h": "#a1683c",  # handle light
    "H": "#6a4024",  # handle dark
    "z": "#a9a5b5",  # zzz / thinking dots
    "c": "#77737d",  # smoke light
    "C": "#4d4a53",  # smoke dark
}

# ── the mascot, 35 x 22 ─────────────────────────────────────────────────────
#  b body  d shadow  g/G bevels  r/R/O glow  E eyes  . transparent
ANVIL = """
................OOOOOOOO...........
.....RRRRRRRRRRRRRRROOOOO.RRRRRRROO
.....bbbbbbbbbbRRRRRROOOOObbbbbbbbO
.RRRRbbbbbbbbbbbbbbbbbbbbObGGGGGGbO
GGGGGGggggggggggbbbbbbbbbObgggbbbR.
GbbbbbGbbbbbbbbbbbbbbbbbbObbbbbbR..
GbbbbbGbbbbbbbbbbbbbbbbbbObbbbbR...
GbbbbbGbbbbbbbbbbbbbbbbbbRbbbbR....
.gggbbGbbbbbbbbbbbbbbbbbbRbbbR.....
....gggddddddddddddddddbbRbrr......
.......ggddddEEddddEEddbbR.........
.........gdddEEddddEEdbbb..........
..........bddEEddddEEdbb...........
........rdbbdddddddddbbR...........
.......rddbbbdddddddbbbR...........
......rdddbbbbbbbbbbbbbRR..........
.....RddddbbbbbbbbbbbbbbR..........
....RdddggggggddddddgggggR.........
...RddddGGGGG.dddddd.GGGGGR........
...RddddGbbbR.dddddd.GbbbbRR.......
...rddddGbbbR.dddddd.GbbbbRR.......
........GbbbR........GbbbbRR.......
""".split()
AW, AH = 35, 22
EYE_L, EYE_R = (13, 10), (19, 10)
# Shared canvas for every animation, in anvil coords: centred on the anvil,
# room above for the hammer and effects, one empty row under the feet.
CANVAS_X, CANVAS_Y, CANVAS_W, CANVAS_H = -4, -13, 43, 36

# name: (left eye, right eye, left offset, right offset); X = lit pixel
EYES = {
    "open": (["XX", "XX", "XX"], ["XX", "XX", "XX"], (0, 0), (0, 0)),
    "half": (["XX", "XX"], ["XX", "XX"], (0, 1), (0, 1)),
    "closed": (["XX"], ["XX"], (0, 2), (0, 2)),
    "sleepy": (["X..X", ".XX."], ["X..X", ".XX."], (-1, 1), (-1, 1)),
    "happy": ([".XX.", "X..X"], [".XX.", "X..X"], (-1, 0), (-1, 0)),
    "squint": (["X.", ".X", "X."], [".X", "X.", ".X"], (0, 0), (0, 0)),
    "x": (["X.X", ".X.", "X.X"], ["X.X", ".X.", "X.X"], (-1, 0), (0, 0)),
    "focused": (["X.", "XX", "XX"], [".X", "XX", "XX"], (0, 0), (0, 0)),
    "sad": ([".X", "XX", "XX"], ["X.", "XX", "XX"], (0, 0), (0, 0)),
    "wink": (["XX", "XX", "XX"], [".XX.", "X..X"], (0, 0), (-1, 1)),
    "winkhalf": (["XX", "XX", "XX"], ["XX", "XX"], (0, 0), (0, 1)),
}


def anvil(eyes="open", look=(0, 0), squash=0):
    """The sprite as a grid. squash > 0 drops waist rows, < 0 stretches."""
    g = [list(r.replace("E", "d")) for r in ANVIL]
    left, right, offl, offr = EYES[eyes]
    for pat, (ax, ay), (ox, oy) in ((left, EYE_L, offl), (right, EYE_R, offr)):
        for y, row in enumerate(pat):
            for x, ch in enumerate(row):
                if ch == "X":
                    g[ay + oy + y + look[1]][ax + ox + x + look[0]] = "E"
    for _ in range(max(squash, 0)):
        del g[13]
    for _ in range(max(-squash, 0)):
        g.insert(13, list(g[13]))
    return g


class Frame:
    def __init__(self):
        self.px = {}

    def set(self, x, y, color):
        self.px[(int(x), int(y))] = color

    def blit(self, rows, x0, y0, key):
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != ".":
                    self.set(x0 + x, y0 + y, FX[key if key else ch])


def put_anvil(f, grid, dx=0, dy=0, heat=0, hot=None):
    """Draw the anvil standing on row 21 (dy < 0 lifts it). hot: {(x, y): extra heat}."""
    top = AH - len(grid) + dy
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            if ch in STATIC:
                c = STATIC[ch]
            else:
                lvl = heat + (hot or {}).get((x, y), 0)
                c = HEAT[max(-2, min(3, lvl))][ch]
            f.set(x + dx, top + y, c)


# Hot pixels of the face, for shimmer.
HOT_BAND = [(x, y) for y in range(3) for x in range(AW) if ANVIL[y][x] in "RO"]


def shimmer(rng, n=2):
    return {p: 1 for p in rng.sample(HOT_BAND, n)}


# ── hammer ─────────────────────────────────────────────────────────────────
HAMMER = [
    ".kkk.",
    "kssuk",
    "kstuk",
    "kstukhhhhhhhh",
    "kstukHHHHHHHH",
    "ktuuk",
    ".kkk.",
]
HAMMER_AT = (17, -7)  # top-left at the moment of impact, anvil coords
HAMMER_PIVOT = (13.0, 4.0)  # end of the handle, hammer coords


def hammer_point(angle, hx, hy, dy=0):
    a = math.radians(angle)
    vx, vy = hx - HAMMER_PIVOT[0], hy - HAMMER_PIVOT[1]
    px, py = HAMMER_AT[0] + HAMMER_PIVOT[0], HAMMER_AT[1] + HAMMER_PIVOT[1] + dy
    return px + vx * math.cos(a) - vy * math.sin(a), py + vx * math.sin(a) + vy * math.cos(a)


def swoosh(f, start, end):
    """Motion arcs traced by the head's outer edge between two angles."""
    for hy, key in ((0.5, "t"), (6.5, "s")):
        a = end + 3
        while a < start:
            x, y = hammer_point(a, 0.5, hy)
            f.set(math.floor(x), math.floor(y), FX[key])
            a += 3


def put_hammer(f, angle, dy=0):
    """Swing the hammer about its handle end; positive angle lifts the head."""
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    px, py = HAMMER_AT[0] + HAMMER_PIVOT[0], HAMMER_AT[1] + HAMMER_PIVOT[1] + dy
    hw = max(len(r) for r in HAMMER)
    hh = len(HAMMER)
    xs, ys = [], []
    for cx, cy in ((0, 0), (hw, 0), (0, hh), (hw, hh)):
        vx, vy = cx - HAMMER_PIVOT[0], cy - HAMMER_PIVOT[1]
        xs.append(px + vx * ca - vy * sa)
        ys.append(py + vx * sa + vy * ca)
    for ty in range(math.floor(min(ys)) - 1, math.ceil(max(ys)) + 1):
        for tx in range(math.floor(min(xs)) - 1, math.ceil(max(xs)) + 1):
            counts = {}
            for sy in range(4):
                for sx in range(4):
                    qx = tx + (sx + 0.5) / 4 - px
                    qy = ty + (sy + 0.5) / 4 - py
                    hx = math.floor(qx * ca + qy * sa + HAMMER_PIVOT[0])
                    hy = math.floor(-qx * sa + qy * ca + HAMMER_PIVOT[1])
                    if 0 <= hy < hh and 0 <= hx < len(HAMMER[hy]) and HAMMER[hy][hx] != ".":
                        ch = HAMMER[hy][hx]
                        counts[ch] = counts.get(ch, 0) + 1
            if sum(counts.values()) >= 7:
                ch = max(counts, key=lambda k: (counts[k], k != "k"))
                f.set(tx, ty, FX[ch])


# ── particles & overlays ───────────────────────────────────────────────────
SPARK_RAMP = ["w", "y", "o", "R", "m"]


def spark_burst(seed, n=11, x0=15.5, x1=23.5):
    rng = random.Random(seed)
    parts = []
    for _ in range(n):
        sx = rng.uniform(x0, x1)
        side = -1 if sx < (x0 + x1) / 2 else 1
        parts.append((sx, side * rng.uniform(0.5, 2.7), -rng.uniform(1.0, 2.9), rng.randint(3, 5)))
    return parts


def draw_sparks(f, parts, t, y0=-1, gravity=0.55):
    for sx, vx, vy, life in parts:
        if t >= life:
            continue
        age = t + (1 if life == 3 else 0)
        for back, shade in ((0.55, 1), (0, 0)):
            tt = t + 1 - back
            if back and t > 1:
                continue
            x = sx + vx * tt
            y = y0 + vy * tt + 0.5 * gravity * tt * tt
            f.set(round(x), round(y), FX[SPARK_RAMP[min(age + shade, 4)]])


def sparkle(f, x, y, stage):
    """stage 0 dot, 1 plus, 2 star."""
    if stage < 0:
        return
    if stage >= 1:
        for d in (1, -1):
            f.set(x + d, y, FX["y"])
            f.set(x, y + d, FX["y"])
    if stage >= 2:
        for d in (2, -2):
            f.set(x + d, y, FX["o"])
            f.set(x, y + d, FX["o"])
    f.set(x, y, FX["w"])


Z4 = ["zzzz", "..z.", ".z..", "zzzz"]
Z5 = ["zzzzz", "...z.", "..z..", ".z...", "zzzzz"]
BANG = ["RR", "RR", "RR", "..", "RR"]
DOT = [".z.", "zzz", ".z."]
PUFFS = [  # a smoke puff growing, then breaking up
    [".c.", "ccc", ".c."],
    [".cc.", "cccc", "cCCc", ".CC."],
    [".ccc.", "ccccc", "cccCc", "cCCCc", ".CCC."],
    [".c.c.", "c...c", "..C..", "C...C", ".C.C."],
    [".....", ".c...", "....C", "..C..", "....."],
]


def put_puff(f, stage, cx, base=-1):
    """Puff centred on cx, rising two pixels per stage from row `base`."""
    glyph = PUFFS[stage]
    f.blit(glyph, cx - len(glyph[0]) // 2, base - 2 * stage - len(glyph) + 1, None)


def broken(rows, keep):
    """Thin a glyph out to fade it on any background."""
    return ["".join(ch if (x + y) % 2 == keep else "." for x, ch in enumerate(r)) for y, r in enumerate(rows)]


# ── animations ─────────────────────────────────────────────────────────────
def idle():
    rng = random.Random(7)
    seq = (
        [("open", 0, 140)] * 6
        + [("open", 1, 140)] * 5
        + [("open", 0, 140)] * 3
        + [("half", 0, 50), ("closed", 0, 70), ("half", 0, 50)]
        + [("open", 0, 140)] * 3
        + [("open", 1, 140)] * 5
    )
    out = []
    for eyes, sq, dur in seq:
        f = Frame()
        put_anvil(f, anvil(eyes, squash=sq), hot=shimmer(rng))
        out.append((f, dur))
    return out


def look():
    seq = [
        ("open", (0, 0), 500),
        ("open", (-1, 0), 600),
        ("open", (0, 0), 120),
        ("open", (1, 0), 600),
        ("open", (0, 0), 400),
        ("half", (0, 0), 50),
        ("closed", (0, 0), 70),
        ("half", (0, 0), 50),
        ("open", (0, 0), 300),
    ]
    out = []
    for eyes, lk, dur in seq:
        f = Frame()
        put_anvil(f, anvil(eyes, look=lk))
        out.append((f, dur))
    return out


def forge():
    angles = [30, 14, 0, 5, 14, 22, 30]
    durs = [160, 50, 90, 70, 70, 80, 110]
    flash = {2: 3, 3: 2, 4: 1}  # frame -> extra heat on the work piece
    out = []
    for strike in range(2):
        parts = spark_burst(11 + strike * 7, n=13)
        for i, (ang, dur) in enumerate(zip(angles, durs)):
            f = Frame()
            impact = i == 2
            hot = {}
            if i in flash:
                for x in range(16, 24):
                    hot[(x, 0)] = flash[i]
                for x in range(14, 25):
                    hot[(x, 1)] = max(flash[i] - 1, 0)
            put_anvil(f, anvil("squint" if impact else "focused", squash=1 if impact else 0), hot=hot)
            if i == 1:
                swoosh(f, angles[0], ang)
            put_hammer(f, ang, dy=1 if impact else 0)
            if impact:
                for x, y in ((14, 0), (13, -1), (25, 0), (26, -1)):
                    f.set(x, y, FX["w"])
            if i >= 2:
                draw_sparks(f, parts, i - 2, y0=0 if impact else -1)
            out.append((f, dur))
    return out


def think():
    out = []
    for i in range(12):
        f = Frame()
        lk = (1, -1) if i < 6 else (-1, -1)
        put_anvil(f, anvil("open", look=lk))
        for k in range([0, 1, 2, 3, 3, 0][i % 6]):
            f.blit(DOT, 11 + k * 5, -6, None)
        out.append((f, 200))
    return out


def success():
    seq = [
        (0, 0, "open", 160),
        (0, 1, "happy", 90),
        (-3, -1, "happy", 60),
        (-5, 0, "happy", 80),
        (-6, 0, "happy", 140),
        (-5, 0, "happy", 80),
        (-3, -1, "happy", 60),
        (0, 1, "happy", 80),
        (0, 0, "happy", 120),
        (0, 0, "happy", 140),
        (0, 0, "happy", 140),
        (0, 0, "happy", 300),
    ]
    spots = [((-1, 2), 2), ((35, 6), 3), ((5, -8), 4), ((29, -10), 5), ((1, 12), 6), ((32, 15), 7)]
    twinkle = [0, 1, 2, 1, 0]
    out = []
    for i, (dy, sq, eyes, dur) in enumerate(seq):
        f = Frame()
        put_anvil(f, anvil(eyes, squash=sq), dy=dy, hot={p: 1 for p in HOT_BAND} if dy < 0 else None)
        for (x, y), start in spots:
            k = i - start
            if 0 <= k < len(twinkle):
                sparkle(f, x, y, twinkle[k])
        out.append((f, dur))
    return out


def error():
    seq = [
        (0, "x", True, None, 120),
        (-1, "x", True, None, 50),
        (1, "x", True, None, 50),
        (-1, "x", True, None, 50),
        (1, "x", True, None, 50),
        (-1, "x", False, None, 50),
        (1, "x", False, None, 50),
        (0, "x", False, 0, 140),
        (0, "sad", False, 1, 160),
        (0, "sad", False, 2, 160),
        (0, "sad", False, 3, 160),
        (0, "sad", False, 4, 160),
        (0, "sad", False, None, 500),
    ]
    out = []
    for dx, eyes, bang, puff, dur in seq:
        f = Frame()
        put_anvil(f, anvil(eyes), dx=dx, heat=-1 if eyes == "sad" else 0)
        if bang:
            f.blit(BANG, 29 + dx, -8, None)
        if puff is not None:
            put_puff(f, puff, 20)
            if puff >= 1:
                put_puff(f, puff - 1, 10, base=0)
        out.append((f, dur))
    return out


def sleep():
    out = []
    for i in range(20):
        f = Frame()
        sq = 1 if (i // 5) % 2 else 0
        put_anvil(f, anvil("sleepy", squash=sq), heat=-2)
        for j in range(3):
            t = (i - 7 * j) % 20
            if t >= 13:
                continue
            glyph = Z4 if t < 5 else Z5
            if t >= 11:
                glyph = broken(glyph, t % 2)
            f.blit(glyph, 24 + round(t * 0.75), -1 - round(t * 0.6) - len(glyph) + 1, None)
        out.append((f, 150))
    return out


def heat():
    levels = [0, 1, 2, 3, 3, 2, 1, 0, -1, -1]
    rng = random.Random(3)
    out = []
    for lvl in levels:
        f = Frame()
        put_anvil(f, anvil("open"), heat=lvl)
        if lvl >= 2:
            for _ in range(2 + lvl):
                x = rng.randint(6, 30)
                y = -rng.randint(1, 2 + lvl)
                f.set(x, y, FX["o" if lvl == 2 else "y"])
        out.append((f, 120))
    return out


def wink():
    seq = [
        ("open", 0, -1, 500),
        ("winkhalf", 0, -1, 60),
        ("wink", 1, 0, 80),
        ("wink", 0, 1, 100),
        ("wink", 0, 2, 300),
        ("wink", 0, 1, 100),
        ("wink", 0, 0, 80),
        ("winkhalf", 0, -1, 60),
        ("open", 0, -1, 700),
    ]
    out = []
    for eyes, sq, star, dur in seq:
        f = Frame()
        put_anvil(f, anvil(eyes, squash=sq))
        sparkle(f, 29, 12, star)
        out.append((f, dur))
    return out


ANIMATIONS = {
    "idle": (idle, "Breathing, blinking, hot face shimmering. Default state."),
    "look": (look, "Glances left and right, then blinks."),
    "forge": (forge, "Hammer strikes with sparks. Working / rendering / loading."),
    "think": (think, "Eyes up, dots counting. Thinking / waiting on a reply."),
    "success": (success, "Happy hop with sparkles. Done / export finished."),
    "error": (error, "Shake with X eyes, then a sad puff of smoke. Something failed."),
    "sleep": (sleep, "Forge cooled down, snoozing with Zzz. Idle for a long time / offline."),
    "heat": (heat, "Heats up to white-hot and cools. Charging / processing."),
    "wink": (wink, "Winks with a sparkle. Hello / tips / easter egg."),
}


# ── output ─────────────────────────────────────────────────────────────────
def build():
    """Rasterise every animation onto the shared canvas.
    Returns {name: [(grid, ms)]} and each animation's own bounding box on it."""
    grids, bounds = {}, {}
    for name, (fn, _) in ANIMATIONS.items():
        seq, xs, ys = [], [], []
        for f, dur in fn():
            grid = [[None] * CANVAS_W for _ in range(CANVAS_H)]
            for (x, y), c in f.px.items():
                gx, gy = x - CANVAS_X, y - CANVAS_Y
                if 0 <= gx < CANVAS_W and 0 <= gy < CANVAS_H:
                    grid[gy][gx] = c
                    xs.append(gx)
                    ys.append(gy)
                else:
                    print(f"warning: {name} draws outside the canvas at {x},{y}")
            seq.append((grid, dur))
        grids[name] = seq
        bounds[name] = (min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
    return grids, bounds


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def save_gif(frames, path, scale=1, background=None):
    colors = sorted({c for grid, _ in frames for row in grid for c in row if c})
    lut = {c: i + 1 for i, c in enumerate(colors)}
    pal = [hex_rgb(background) if background else (0, 0, 0)] + [hex_rgb(c) for c in colors]
    flat = [v for rgb in pal for v in rgb] + [0] * (768 - 3 * len(pal))
    images = []
    for grid, _ in frames:
        h, w = len(grid), len(grid[0])
        im = Image.new("P", (w, h), 0)
        im.putpalette(flat)
        im.putdata([lut[c] if c else 0 for row in grid for c in row])
        if scale > 1:
            im = im.resize((w * scale, h * scale), Image.NEAREST)
        images.append(im)
    opts = dict(save_all=True, append_images=images[1:], duration=[d for _, d in frames], loop=0, optimize=False)
    if background:
        opts["disposal"] = 1
    else:
        opts.update(transparency=0, disposal=2)
    images[0].save(path, **opts)


def save_png(grid, path, scale=1):
    h, w = len(grid), len(grid[0])
    im = Image.new("RGBA", (w, h))
    im.putdata([hex_rgb(c) + (255,) if c else (0, 0, 0, 0) for row in grid for c in row])
    if scale > 1:
        im = im.resize((w * scale, h * scale), Image.NEAREST)
    im.save(path, optimize=True)


CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def write_ts(grids, bounds, path):
    width, height = CANVAS_W, CANVAS_H
    colors = sorted({c for frames in grids.values() for grid, _ in frames for row in grid for c in row if c})
    assert len(colors) <= len(CHARS), "too many colours for the frame encoding"
    key = {c: CHARS[i] for i, c in enumerate(colors)}
    rows, row_index = [], {}
    frames, frame_index = [], {}
    anim_out = {}
    for name, seq in grids.items():
        ids, durs = [], []
        for grid, dur in seq:
            enc = []
            for row in grid:
                s = "".join(key[c] if c else "." for c in row)
                if s not in row_index:
                    row_index[s] = len(rows)
                    rows.append(s)
                enc.append(row_index[s])
            t = tuple(enc)
            if t not in frame_index:
                frame_index[t] = len(frames)
                frames.append(t)
            ids.append(frame_index[t])
            durs.append(dur)
        anim_out[name] = (ids, durs)

    lines = [
        "// Generated by source/generate.py. Do not edit by hand: change the generator and re-run it.",
        "//",
        f"// {width}x{height} pixels per frame. Each frame is a list of row ids; each row is a string with",
        "// one char per pixel: \".\" is transparent, any other char is an index into PALETTE via CHARS.",
        "",
        f"export const MASCOT_WIDTH = {width}",
        f"export const MASCOT_HEIGHT = {height}",
        f"export const CHARS = {CHARS!r}".replace("'", '"'),
        "export const PALETTE = [" + ", ".join(f'"{c}"' for c in colors) + "] as const",
        "",
        "export const ROWS: readonly string[] = [",
    ]
    lines += [f'  "{r}",' for r in rows]
    lines += ["]", "", "export const FRAMES: readonly (readonly number[])[] = ["]
    lines += ["  [" + ",".join(map(str, fr)) + "]," for fr in frames]
    lines += ["]", "", "export const ANIMATIONS = {"]
    for name, (ids, durs) in anim_out.items():
        x, y, w, h = bounds[name]
        lines.append(f"  /** {ANIMATIONS[name][1]} */")
        lines.append(f"  {name}: {{")
        lines.append(f"    frames: [{', '.join(map(str, ids))}],")
        lines.append(f"    durations: [{', '.join(map(str, durs))}],")
        lines.append(f"    bounds: {{ x: {x}, y: {y}, width: {w}, height: {h} }},")
        lines.append("  },")
    lines += [
        "} as const satisfies Record<string, MascotAnimationData>",
        "",
        "export type MascotAnimation = keyof typeof ANIMATIONS",
        "",
        "export interface MascotAnimationData {",
        "  /** Indices into FRAMES, played in order and looped. */",
        "  frames: readonly number[]",
        "  /** How long each frame stays up, in milliseconds. */",
        "  durations: readonly number[]",
        "  /** The part of the canvas this animation ever draws on, in pixels. */",
        "  bounds: { x: number; y: number; width: number; height: number }",
        "}",
        "",
    ]
    with open(path, "w", newline="\n") as fh:
        fh.write("\n".join(lines))
    return len(rows), len(frames)


def write_preview(grids, sizes, path):
    width, height = CANVAS_W, CANVAS_H
    cards = []
    for name, (_, desc) in ANIMATIONS.items():
        total = sum(d for _, d in grids[name])
        links = " ".join(f'<a href="gifs/{s}x/reelforge-{name}.gif">{s}x</a>' for s in sizes)
        cards.append(
            f'<figure><div class="stage"><img src="gifs/8x/reelforge-{name}.gif" alt="ReelForge {name} animation" '
            f'width="{width * 8}" height="{height * 8}"></div><figcaption><b>{name}</b> '
            f"<span>{len(grids[name])} frames · {total / 1000:.2f}s loop</span><p>{desc}</p>"
            f"<p class=links>{links} · <a href=\"gifs/black-8x/reelforge-{name}.gif\">on black</a></p></figcaption></figure>"
        )
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ReelForge Mascot</title>
<style>
  :root {{ --bg: #0b0b0c; --card: #141315; --fg: #ecebee; --muted: #8d8892; --line: #262428; --stage: #000; }}
  :root[data-bg="light"] {{ --bg: #f4f3f5; --card: #fff; --fg: #141316; --muted: #66616b; --line: #e2e0e4; --stage: #fff; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--fg); font: 14px/1.45 system-ui, sans-serif; }}
  header {{ max-width: 1100px; margin: 0 auto 20px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  h1 {{ font-size: 20px; margin: 0; flex: 1; }}
  button {{ font: inherit; color: inherit; background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 6px 12px; cursor: pointer; }}
  main {{ max-width: 1200px; margin: 0 auto; display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(min(380px, 100%), 1fr)); }}
  figure {{ margin: 0; background: var(--card); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
  .stage {{ background: var(--stage); display: grid; place-items: center; padding: 12px; }}
  img {{ image-rendering: pixelated; max-width: 100%; height: auto; }}
  figcaption {{ padding: 12px 14px; }}
  figcaption span {{ color: var(--muted); margin-left: 6px; }}
  figcaption p {{ margin: 6px 0 0; color: var(--muted); }}
  a {{ color: #fd4b33; }}
</style>
</head>
<body>
<header><h1>ReelForge mascot · {len(ANIMATIONS)} animations · {width}×{height} px</h1>
<button id="bg">Light background</button></header>
<main>
{chr(10).join(cards)}
</main>
<script>
  const b = document.getElementById("bg");
  b.onclick = () => {{
    const light = document.documentElement.dataset.bg !== "light";
    document.documentElement.dataset.bg = light ? "light" : "";
    b.textContent = light ? "Dark background" : "Light background";
  }};
</script>
</body>
</html>
"""
    with open(path, "w", newline="\n", encoding="utf-8") as fh:
        fh.write(html)


def main():
    grids, bounds = build()
    sizes = (1, 4, 8, 16)
    for s in sizes:
        os.makedirs(os.path.join(ROOT, "gifs", f"{s}x"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "gifs", "black-8x"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "opentui"), exist_ok=True)
    for name, frames in grids.items():
        for s in sizes:
            save_gif(frames, os.path.join(ROOT, "gifs", f"{s}x", f"reelforge-{name}.gif"), s)
        save_gif(frames, os.path.join(ROOT, "gifs", "black-8x", f"reelforge-{name}.gif"), 8, background="#000000")
    # Stills: the bare anvil for logos, and the full canvas as a reduced-motion stand-in for the GIFs.
    os.makedirs(os.path.join(ROOT, "png"), exist_ok=True)
    still = Frame()
    put_anvil(still, anvil("open"))
    bare = [[still.px.get((x, y)) for x in range(AW)] for y in range(AH)]
    full = [[still.px.get((CANVAS_X + x, CANVAS_Y + y)) for x in range(CANVAS_W)] for y in range(CANVAS_H)]
    for s in (1, 8, 16):
        save_png(bare, os.path.join(ROOT, "png", f"reelforge-anvil-{s}x.png"), s)
    for s in (1, 8):
        save_png(full, os.path.join(ROOT, "png", f"reelforge-still-{s}x.png"), s)
    nrows, nframes = write_ts(grids, bounds, os.path.join(ROOT, "opentui", "reelforge-frames.ts"))
    write_preview(grids, sizes, os.path.join(ROOT, "preview.html"))
    print(f"canvas {CANVAS_W}x{CANVAS_H}, {sum(len(f) for f in grids.values())} frames "
          f"({nframes} unique, {nrows} unique rows) in {len(grids)} animations")
    for name, b in bounds.items():
        print(f"  {name:8} bounds x={b[0]} y={b[1]} {b[2]}x{b[3]}")


if __name__ == "__main__":
    main()
