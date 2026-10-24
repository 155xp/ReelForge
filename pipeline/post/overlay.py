"""Text layers: title card, story lines, debug HUD, follow call-to-action, end card and cover.

All drawing is Pillow RGBA; layers are cached by content so a frame costs a few alpha-composites.
"""
import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import config

W, H = config.WIDTH, config.HEIGHT

# layout (1080x1920; TikTok's right-hand buttons start near x=940, caption area below y=1500)
TITLE_Y = 430
LINE_Y = 1250
HUD_X, HUD_Y = 64, 590
TEXT_MAX_W = 860
# HUD look: no box behind the readout and no channel name on it. Instead every HUD line is bold with a solid dark
# outline, a soft shadow, and a glyph-shaped glow that strengthens over bright backgrounds, so it is always readable
# over any background; qa.py fails a video whose HUD contrast drops below HUD_MIN_CONTRAST. The old box can still be
# turned on per spec ("hud": {"panel": true}), never by default.
HUD_PANEL = False
HUD_BRAND = False
HUD_OUTLINE = (8, 10, 14)
HUD_MIN_CONTRAST = 4.5                # glyph vs the pixels just round it (WCAG luminance ratio), every HUD line
HUD_VALUE_MAX_W = 900                 # long readouts (64-bit dollar amounts) shrink to fit this width

RED = (255, 59, 59)


@lru_cache(maxsize=None)
def font(path, size):
    return ImageFont.truetype(str(path), size)


def _text_width(text, fnt, tracking):
    if not tracking:
        return fnt.getlength(text)
    return sum(fnt.getlength(ch) for ch in text) + tracking * max(len(text) - 1, 0)


def wrap(text, fnt, max_w, tracking=0):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and _text_width(trial, fnt, tracking) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _glyph_mask(text, path, size, tracking, blur, max_w, align, leading, stroke=0):
    """8-bit coverage of the text (grown by a `stroke` px outline if given), with `pad` px of room on every side."""
    fnt = font(path, size)
    lines = wrap(text, fnt, max_w, tracking) if max_w else [text]
    ascent, descent = fnt.getmetrics()
    line_h = int((ascent + descent) * leading)
    widths = [_text_width(t, fnt, tracking) for t in lines]
    pad = blur * 3 + 4
    w = int(max(widths)) + 2 * pad
    h = line_h * (len(lines) - 1) + ascent + descent + 2 * pad
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    for k, (t, tw) in enumerate(zip(lines, widths)):
        x = pad + ((w - 2 * pad - tw) / 2 if align == "center" else 0)
        y = pad + k * line_h
        if tracking:
            for ch in t:
                d.text((x, y), ch, font=fnt, fill=255, stroke_width=stroke, stroke_fill=255)
                x += fnt.getlength(ch) + tracking
        else:
            d.text((x, y), t, font=fnt, fill=255, stroke_width=stroke, stroke_fill=255)
    return mask, pad


@lru_cache(maxsize=4096)
def text_layer(text, path, size, fill=(255, 255, 255), tracking=0, shadow=150, blur=7, max_w=0,
               align="center", leading=1.18, halo=0, outline=0):
    """Rendered text (optionally wrapped) with a soft drop shadow (and an optional tight dark halo of `halo` px
    so it stays readable on white clouds, or a solid dark `outline` of that many px, the HUD's, which reads on
    any background). Returns an RGBA image."""
    mask, pad = _glyph_mask(text, path, size, tracking, blur, max_w, align, leading)
    w, h = mask.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    edge = _glyph_mask(text, path, size, tracking, blur, max_w, align, leading, outline)[0] if outline else None
    if shadow:
        sh = (edge or mask).filter(ImageFilter.GaussianBlur(blur)).point(lambda v: v * shadow // 255)
        if halo:
            tight = mask.filter(ImageFilter.MaxFilter(2 * halo + 1)).filter(ImageFilter.GaussianBlur(halo * 0.6))
            sh = Image.fromarray(np.maximum(np.asarray(sh), (np.asarray(tight) * 0.62).astype(np.uint8)))
        layer.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 0), sh)
    if outline:
        layer.paste(Image.new("RGBA", (w, h), (*HUD_OUTLINE, 255)), (0, 0), edge)
    layer.paste(Image.new("RGBA", (w, h), (*fill, 255)), (0, 0), mask)
    layer.info["pad"] = pad
    return layer


@lru_cache(maxsize=1024)
def glow_layer(text, path, size, tracking=0, blur=7, spread=7, align="left"):
    """A wide, soft dark glow that follows the glyph shapes (not a box): laid under HUD text over bright
    backgrounds, with its strength set per frame by how bright the background is."""
    mask, pad = _glyph_mask(text, path, size, tracking, blur, 0, align, 1.18)
    g = mask.filter(ImageFilter.MaxFilter(2 * spread + 1)).filter(ImageFilter.GaussianBlur(spread * 1.1))
    layer = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    layer.paste(Image.new("RGBA", mask.size, (0, 0, 0, 255)), (0, 0), g)
    layer.info["pad"] = pad
    return layer


def faded(layer, alpha):
    if alpha >= 0.999:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda v: int(v * alpha)))
    return out


def paste_center(canvas, layer, cx, cy, alpha=1.0):
    if alpha <= 0.001:
        return
    canvas.alpha_composite(faded(layer, alpha), (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def paste_left(canvas, layer, x, y, alpha=1.0):
    if alpha <= 0.001:
        return
    pad = layer.info.get("pad", 0)
    canvas.alpha_composite(faded(layer, alpha), (int(x - pad), int(y - pad)))


def window_alpha(t, start, end, fade_in=0.25, fade_out=0.3):
    if t < start or t >= end:
        return 0.0
    a = 1.0
    if fade_in > 0 and start > 0.01:
        a = min(a, (t - start) / fade_in)
    if fade_out > 0:
        a = min(a, (end - t) / fade_out)
    return max(0.0, min(1.0, a))


# ---------------------------------------------------------------- pieces

def draw_title(canvas, text, alpha, scrim=0.0):
    layer = text_layer(text, config.FONT_SERIF, 80, max_w=900, blur=12, shadow=235)
    if scrim > 0 and alpha > 0.001:
        # a soft dark band behind the title for busy, bright openings (a lit city at night)
        paste_center(canvas, _scrim(layer.width, layer.height), W / 2, TITLE_Y, alpha * scrim)
    paste_center(canvas, layer, W / 2, TITLE_Y, alpha)


def draw_line(canvas, text, alpha, y=None, scrim=0.0):
    layer = text_layer(text, config.FONT_SERIF_ITALIC, 48, max_w=TEXT_MAX_W, blur=8, shadow=200, halo=3)
    cy = LINE_Y if y is None else y
    if scrim > 0 and alpha > 0.001:
        # a soft dark band behind the line, so it reads on white clouds or snow too
        sl = _scrim(layer.width, layer.height)
        paste_center(canvas, sl, W / 2, cy, alpha * scrim)
    paste_center(canvas, layer, W / 2, cy, alpha)


@lru_cache(maxsize=256)
def _scrim(w, h):
    pad = 46
    m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(m).rounded_rectangle([pad + 10, pad + 12, w + pad - 10, h + pad - 12], radius=h // 3, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(24))
    out = Image.new("RGBA", m.size, (6, 8, 12, 255))
    out.putalpha(m)
    return out


TAG_CYAN = (120, 235, 255)


def draw_tag(canvas, x, y, label, sub, alpha, rng=None, avoid=None, tint=None):
    """Debug-overlay object tag: corner brackets round the point, a leader line, and a label box (like a game
    editor's object label). `avoid`: a screen box (x0, y0, x1, y1), e.g. the subject, the label keeps off.
    `tint`: an RGB colour for the brackets, line and box outline (default cyan)."""
    if alpha <= 0.01:
        return
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * alpha)
    col = (*(tint or TAG_CYAN), a)
    s, k = 20, 9
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = x + sx * s, y + sy * s
            d.line([(cx, cy), (cx - sx * k, cy)], fill=col, width=3)
            d.line([(cx, cy), (cx, cy - sy * k)], fill=col, width=3)
    d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=col)
    lab = text_layer(label, config.FONT_MONO_BOLD, 28, fill=(255, 255, 255), tracking=2, shadow=170, blur=4,
                     align="left")
    sub_fill = (205, 235, 245) if tint is None else tuple(int(150 + 0.42 * c) for c in tint)
    sub_l = text_layer(sub, config.FONT_MONO, 22, fill=sub_fill, tracking=2, shadow=170, blur=4,
                       align="left") if sub else None
    tw = max(lab.width, sub_l.width if sub_l else 0) - 2 * lab.info["pad"] + 28
    th = 46 + (30 if sub_l else 0)

    def clash(bx, by):
        """How badly a label box at (bx, by) collides with the frame edges, TikTok's UI, the HUD or the story line."""
        bad = 0.0
        if bx < 20 or bx + tw > 930 or by < 140 or by + th > 1540:
            bad += 10
        if bx < 660 and by + th > 540 and by < 850:          # the HUD panel
            bad += 5
        if by + th > 1190 and by < 1390:                    # the story line band
            bad += 2
        if avoid:                                           # the subject
            w_ = min(bx + tw, avoid[2]) - max(bx, avoid[0])
            h_ = min(by + th, avoid[3]) - max(by, avoid[1])
            if w_ > 0 and h_ > 0:
                bad += 0.5 + 4.0 * w_ * h_ / (tw * th)
        return bad

    best = None
    for right, up, reach in ((True, True, 40), (True, False, 40), (False, True, 40), (False, False, 40),
                             (True, True, 150), (False, True, 150), (True, False, 150), (False, False, 150)):
        lx = x + (s + 26 if right else -(s + 26))
        ly = y + (-(s + reach) if up else (s + reach))
        bx0 = lx if right else lx - tw
        by0 = ly - th / 2
        score = clash(bx0, by0)
        if best is None or score < best[0]:
            best = (score, right, up, lx, ly, bx0, by0)
    _, right, up, lx, ly, bx0, by0 = best
    d.line([(x + (s if right else -s), y + (-s if up else s)), (lx, ly)], fill=col, width=2)
    bx0 = min(max(bx0, 20), 930 - tw)                       # clamp into the safe area as a last resort
    by0 = min(max(by0, 140), 1540 - th)
    d.line([(lx, ly), (bx0 if right else bx0 + tw, ly)], fill=col, width=2)
    d.rectangle([bx0, by0, bx0 + tw, by0 + th], fill=(4, 10, 16, int(170 * alpha)), outline=col, width=2)
    canvas.alpha_composite(layer)
    paste_left(canvas, lab, bx0 + 14, by0 + 8, alpha)
    if sub_l:
        paste_left(canvas, sub_l, bx0 + 14, by0 + 44, alpha * 0.95)


def draw_speedlines(canvas, intensity, rng, center):
    """Anime-style radial speed lines around the vanishing point; intensity 0..1."""
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    reach = math.hypot(max(cx, W - cx), max(cy, H - cy))
    for _ in range(int(18 + 70 * intensity)):
        a = rng.uniform(0, 2 * math.pi)
        r0 = reach * rng.uniform(0.42, 0.85) * (1.15 - 0.35 * intensity)
        r1 = r0 + reach * rng.uniform(0.12, 0.45)
        w = rng.choice((1, 2, 2, 3, 4))
        alpha = int(255 * intensity * rng.uniform(0.25, 0.6))
        d.line([(cx + r0 * math.cos(a), cy + r0 * math.sin(a)), (cx + r1 * math.cos(a), cy + r1 * math.sin(a))],
               fill=(255, 255, 255, alpha), width=w)
    canvas.alpha_composite(layer)


@lru_cache(maxsize=64)
def _value_size(value):
    """The readout's font size: 80 px, smaller when the number is too wide for the frame."""
    fnt = font(config.FONT_MONO_BOLD, 80)
    w = fnt.getlength(value)
    return 80 if w <= HUD_VALUE_MAX_W else max(40, int(80 * HUD_VALUE_MAX_W / w))


def hud_lines(label, value, sub):
    """The unboxed HUD's three lines as (name, text, font, size, tracking, blur, outline, dy): one place for the
    layout, shared by draw_hud and qa.py's contrast check. Bold mono with a solid dark outline, so each glyph
    carries its own contrast over white clouds, billboards or gold light alike."""
    vs = _value_size(value)
    return [("label", label, config.FONT_MONO_BOLD, 27, 4, 5, 3, 44),
            ("value", value, config.FONT_MONO_BOLD, vs, 0, 7, max(3, round(vs / 16)), 80 + (80 - vs) // 2),
            ("sub", sub, config.FONT_MONO_BOLD, 25, 4, 5, 3, 182)]


def _hud_layers(label, value, sub, brand, value_color=None):
    if not HUD_PANEL:
        fills = {"label": (240, 240, 240), "value": value_color or (255, 255, 255), "sub": (235, 235, 235)}
        return [(text_layer(text, f, size, fill=fills[name], tracking=tr, shadow=200, blur=blur, align="left",
                            outline=ol), 0, dy, 1.0, glow_layer(text, f, size, tracking=tr, blur=blur))
                for name, text, f, size, tr, blur, ol, dy in hud_lines(label, value, sub) if text]
    # the old boxed look (only if a spec asks for "panel": true)
    vs = _value_size(value)
    layers = []
    if HUD_BRAND and brand:
        layers.append((text_layer(brand, config.FONT_MONO_BOLD, 22, fill=(235, 235, 235), tracking=6, shadow=140,
                                  blur=5, align="left"), 34, 0, 0.72, None))
    layers += [
        (text_layer(label, config.FONT_MONO, 27, fill=(240, 240, 240), tracking=4, shadow=150, blur=5,
                    align="left"), 0, 44, 0.9, None),
        (text_layer(value, config.FONT_MONO_BOLD, vs, fill=value_color or (255, 255, 255),
                    shadow=170, blur=7, align="left"), 0, 80 + (80 - vs) // 2, 1.0, None),
        (text_layer(sub, config.FONT_MONO, 25, fill=(235, 235, 235), tracking=4, shadow=150, blur=5,
                    align="left"), 0, 182, 0.85, None),
    ]
    return layers


def _bright(canvas, layer, x, y):
    """How bright the picture is under a text layer about to be pasted at (x, y): 0 (dark) .. 1 (white)."""
    pad = layer.info.get("pad", 0)
    box = (max(0, int(x)), max(0, int(y)), min(W, int(x - 2 * pad + layer.width)), min(H, int(y - 2 * pad + layer.height)))
    if box[2] <= box[0] or box[3] <= box[1]:
        return 0.0
    lum = np.asarray(canvas.crop(box).convert("L").reduce(4), np.float32)
    return float(np.percentile(lum, 80)) / 255.0


def draw_hud(canvas, t, label, value, sub, brand, glitch=0.0, rng=None, alpha=1.0, value_color=None):
    rng = rng or random.Random(int(t * 1000))
    ox = int(rng.uniform(-14, 14) * glitch) if glitch else 0
    # translucent debug-console panel behind the readout
    layers = _hud_layers(label, value, sub, brand, value_color)
    if HUD_PANEL:
        pw = max(dx + ly.width - 2 * ly.info["pad"] for ly, dx, _, _, _ in layers) + 44
        panel = Image.new("RGBA", (int(pw), 236), (0, 0, 0, int(105 * alpha)))
        ImageDraw.Draw(panel).rectangle([0, 0, 2, 235], fill=(255, 255, 255, int(120 * alpha)))
        canvas.alpha_composite(panel, (HUD_X - 22 + ox, HUD_Y - 16))
    # blinking cursor block next to the brand mark
    if HUD_BRAND and brand and int(t * 2) % 2 == 0 and alpha > 0:
        block = Image.new("RGBA", (14, 22), (*RED, int(230 * alpha)))
        canvas.alpha_composite(block, (HUD_X + ox, HUD_Y + 3))
    for layer, dx, dy, a, glow in layers:
        if glow is not None:
            # adaptive contrast: over a bright patch (clouds, a lit billboard) a soft glyph-shaped glow deepens the
            # dark around the text; over a dark scene it stays off
            g = min(1.0, max(0.0, (_bright(canvas, glow, HUD_X + dx + ox, HUD_Y + dy) - 0.40) / 0.35))
            paste_left(canvas, glow, HUD_X + dx + ox, HUD_Y + dy, 0.8 * g * a * alpha)
        if glitch > 0.05:
            # chromatic split: red and cyan ghosts either side
            for tint, sx in (((255, 40, 40), 1), ((40, 230, 255), -1)):
                ghost = Image.new("RGBA", layer.size, (*tint, 255))
                ghost.putalpha(layer.getchannel("A").point(lambda v: int(v * 0.55 * glitch * alpha)))
                canvas.alpha_composite(ghost, (int(HUD_X + dx + ox + sx * 7 * glitch - layer.info["pad"]),
                                               int(HUD_Y + dy - layer.info["pad"])))
        paste_left(canvas, layer, HUD_X + dx + ox, HUD_Y + dy, a * alpha)


def draw_cta(canvas, text, sub, alpha, y=1300):
    """Follow call-to-action: big tracked mono line with a red block, plus a smaller serif line."""
    if alpha <= 0:
        return
    big = text_layer(text, config.FONT_MONO_BOLD, 64, tracking=6, shadow=230, blur=10, halo=4)
    paste_center(canvas, big, W / 2, y, alpha)
    block = Image.new("RGBA", (22, 54), (*RED, int(240 * alpha)))
    canvas.alpha_composite(block, (int(W / 2 - big.width / 2 + big.info["pad"] - 40), int(y - 27)))
    if sub:
        paste_center(canvas, text_layer(sub, config.FONT_SERIF_ITALIC, 44, max_w=TEXT_MAX_W, shadow=220, blur=8,
                                        halo=3), W / 2, y + 115, alpha)


def draw_end_card(canvas, title, fact, brand, alpha):
    if alpha <= 0:
        return
    bg = Image.new("RGBA", (W, H), (16, 16, 16, int(255 * alpha)))
    canvas.alpha_composite(bg)
    tl = text_layer(title, config.FONT_SERIF, 66, max_w=880, shadow=0)
    paste_center(canvas, tl, W / 2, 880, alpha)
    fl = text_layer(fact.upper(), config.FONT_MONO, 24, fill=(150, 150, 150), tracking=3, shadow=0, max_w=860,
                    leading=1.5)
    paste_center(canvas, fl, W / 2, 880 + tl.height / 2 + fl.height / 2 - 10, alpha)
    if brand:   # the channel name only if the spec asks for it ("end_card": {"brand": true}); off by default
        bl = text_layer(brand, config.FONT_MONO_BOLD, 20, fill=(110, 110, 110), tracking=7, shadow=0)
        paste_center(canvas, bl, W / 2, 1440, alpha)


def draw_cover(base, kicker, keyword, tail, brand=None):
    """Thumbnail: darkened frame, small tracked kicker, huge keyword with a red/cyan split, and the brand mark only
    if one is passed (off by default: the channel name isn't put on the videos)."""
    canvas = base.convert("RGBA")
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(shade)
    for y in range(H):
        a = int(190 * max(0.0, 1 - y / 1150) ** 1.3)
        d.line([(0, y), (W, y)], fill=(0, 0, 0, a))
    canvas.alpha_composite(shade)
    kl = text_layer(kicker, config.FONT_MONO_BOLD, 34, tracking=7, shadow=160, blur=6)
    paste_center(canvas, kl, W / 2, 360)
    kw = text_layer(keyword + tail, config.FONT_SERIF_BOLD, 128, max_w=980, shadow=200, blur=12, leading=1.02)
    for tint, sx in (((255, 40, 40), 9), ((40, 230, 255), -9)):
        ghost = Image.new("RGBA", kw.size, (*tint, 255))
        ghost.putalpha(kw.getchannel("A").point(lambda v: int(v * 0.6)))
        canvas.alpha_composite(ghost, (int(W / 2 - kw.width / 2 + sx), int(560 - kw.height / 2)))
    paste_center(canvas, kw, W / 2, 560)
    if brand:
        bl = text_layer(brand, config.FONT_MONO_BOLD, 26, tracking=8, shadow=160, blur=5)
        paste_center(canvas, bl, W / 2, 1700)
    return canvas.convert("RGB")


_DEMO_LAYER = None


def demo_watermark(canvas):
    """A big diagonal "DEMO · made with ReelForge" across the frame: on every frame of a video rendered straight from
    one of ReelForge's examples (spec "demo": true), so the same demo can't be posted again and again. New episodes
    (reelforge new-episode) drop the flag."""
    global _DEMO_LAYER
    if _DEMO_LAYER is None:
        big = text_layer("DEMO", config.FONT_MONO_BOLD, 300, fill=(255, 255, 255), tracking=30, shadow=0, outline=6)
        small = text_layer("made with ReelForge", config.FONT_MONO_BOLD, 64, fill=(255, 255, 255), tracking=4,
                           shadow=0, outline=4)
        block = Image.new("RGBA", (max(big.width, small.width), big.height + small.height), (0, 0, 0, 0))
        block.alpha_composite(big, ((block.width - big.width) // 2, 0))
        block.alpha_composite(small, ((block.width - small.width) // 2, big.height - 20))
        block = faded(block, 0.42)
        _DEMO_LAYER = block.rotate(28, resample=Image.BICUBIC, expand=True)
    canvas.alpha_composite(_DEMO_LAYER, (int(W / 2 - _DEMO_LAYER.width / 2), int(H / 2 - _DEMO_LAYER.height / 2)))

