"""Camera helpers shared by the doubling effects: shot lists with hard cuts, eased moves, look-at framing,
projection to screen pixels (for the debug tags drawn in post), and shake.

A shot list is [(t_start, t_end, keys, opts), ...]. keys = [(t, cam, tgt, lens), ...] with absolute times; cam
and tgt are xyz tuples or callables f(t) -> xyz; lens is a number or callable. Between two shots the camera cuts.
"""
import math

import numpy as np

SENSOR = 36.0
W, H = 1080, 1920


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _val(v, t):
    return v(t) if callable(v) else v


def shot_at(shots, t):
    for k, s in enumerate(shots):
        if s[0] <= t < s[1]:
            return k, s
    return len(shots) - 1, shots[-1]


def pose(shots, t):
    """(cam, tgt, lens, shot_index, opts) at time t."""
    k, (t0, t1, keys, opts) = shot_at(shots, t)
    if t <= keys[0][0]:
        a = keys[0]
        return np.array(_val(a[1], t), float), np.array(_val(a[2], t), float), float(_val(a[3], t)), k, opts
    for a, b in zip(keys, keys[1:]):
        if t <= b[0]:
            s = (t - a[0]) / max(b[0] - a[0], 1e-6)
            s = smoothstep(s) if opts.get("ease", True) else min(1.0, max(0.0, s))
            ca, cb = np.array(_val(a[1], t), float), np.array(_val(b[1], t), float)
            ga, gb = np.array(_val(a[2], t), float), np.array(_val(b[2], t), float)
            la, lb = float(_val(a[3], t)), float(_val(b[3], t))
            return ca + (cb - ca) * s, ga + (gb - ga) * s, la + (lb - la) * s, k, opts
    b = keys[-1]
    return np.array(_val(b[1], t), float), np.array(_val(b[2], t), float), float(_val(b[3], t)), k, opts


def basis(cam, tgt, up=(0.0, 0.0, 1.0)):
    """Camera forward/right/up like Blender's TRACK_TO (-Z to target, Y up)."""
    f = np.asarray(tgt, float) - np.asarray(cam, float)
    f /= np.linalg.norm(f)
    r = np.cross(f, up)
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(f, (0.0, 1.0, 0.0))
    r /= np.linalg.norm(r)
    u = np.cross(r, f)
    return f, r, u


def project(p, cam, tgt, lens):
    """Pixel (x, y) of world point p, or None when it's behind the camera. Portrait frame, sensor fit AUTO
    (the 36 mm sensor spans the 1920 px height)."""
    f, r, u = basis(cam, tgt)
    d = np.asarray(p, float) - np.asarray(cam, float)
    z = float(np.dot(d, f))
    if z <= 1e-6:
        return None
    k = lens / (SENSOR / 2)                     # 1 / tan(vfov / 2)
    y_ndc = float(np.dot(d, u)) / z * k
    x_ndc = float(np.dot(d, r)) / z * k * (H / W)
    return (0.5 + 0.5 * x_ndc) * W, (0.5 - 0.5 * y_ndc) * H


def angular_radius_px(radius, dist, lens):
    """On-screen radius in pixels of a sphere of `radius` at `dist`."""
    if dist <= radius:
        return float("inf")
    a = math.asin(radius / dist)
    return math.tan(a) * lens / (SENSOR / 2) * H / 2


def jitter(t, amp, ph):
    jx = math.sin(t * 9.7 + ph[0]) + 0.6 * math.sin(t * 16.3 + ph[1]) + 0.3 * math.sin(t * 27.9 + ph[2])
    jz = math.sin(t * 8.1 + ph[3]) + 0.6 * math.sin(t * 14.9 + ph[4]) + 0.3 * math.sin(t * 25.3 + ph[5])
    return amp * jx, amp * jz


def pulse(t, at, rise, fall):
    if t < at - rise:
        return 0.0
    if t < at:
        return smoothstep((t - (at - rise)) / rise)
    return math.exp(-(t - at) / fall)
