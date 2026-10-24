"""Effect: reality has a render distance that shrinks to zero.

Anything farther from the camera than the current render distance is hidden (unloaded). For a few frames
before it disappears (or after it pops back in) it flashes a magenta/black "missing texture" checker.
Spec keys (spec["effect"]):
  keys                 [[seconds, metres], ...]  render distance over time (interpolated in log space)
  sky_unload_at        seconds: the sky switches to a flat grey void
  fall_at              seconds: the camera drops and the editor grid appears below
  glitch_flash_frames  frames of checker flash around each unload
"""
import math

import numpy as np

import rf_common as rf


def render_distance_curve(keys, t):
    kt = np.array([k[0] for k in keys], dtype=float)
    kv = np.log(np.maximum([k[1] for k in keys], 1e-3))
    idx = np.clip(np.searchsorted(kt, t, side="right") - 1, 0, len(kt) - 2)
    t0, t1 = kt[idx], kt[idx + 1]
    s = np.clip((t - t0) / np.maximum(t1 - t0, 1e-6), 0.0, 1.0)
    s = 0.5 * (s + s * s * (3 - 2 * s))  # gentle ease
    return np.exp(kv[idx] + (kv[idx + 1] - kv[idx]) * s)


def keyframe_visibility(obj, vis, flash):
    """vis: bool array per frame (index 0 = frame 1). Returns list of (frame, appeared)."""
    changes = np.flatnonzero(vis[1:] != vis[:-1]) + 1
    if not vis.any():
        obj.hide_render = True
        return []
    obj["glitch"] = 0.0
    obj.hide_render = not bool(vis[0])
    obj.keyframe_insert("hide_render", frame=1)
    obj.keyframe_insert('["glitch"]', frame=1)
    events = []
    for c in changes:
        f = int(c) + 1
        if vis[c]:
            obj.hide_render = False
            obj.keyframe_insert("hide_render", frame=f)
            obj["glitch"] = 1.0
            obj.keyframe_insert('["glitch"]', frame=f)
            obj["glitch"] = 0.0
            obj.keyframe_insert('["glitch"]', frame=f + flash)
        else:
            obj["glitch"] = 1.0
            obj.keyframe_insert('["glitch"]', frame=max(2, f - flash))
            obj.hide_render = True
            obj.keyframe_insert("hide_render", frame=f)
            obj["glitch"] = 0.0
            obj.keyframe_insert('["glitch"]', frame=f)
        events.append((f, bool(vis[c])))
    rf.set_interpolation(obj, "CONSTANT", '["glitch"]')
    return events


def apply(spec, info):
    E = spec["effect"]
    fps = spec["fps"]
    nf = int(round(spec["render_until"] * fps))
    t = np.arange(nf) / fps
    rd = render_distance_curve(E["keys"], t)
    flash = int(E.get("glitch_flash_frames", 3))
    cam = np.array(info["cam_pos"][:])

    rf.set_interp("CONSTANT")
    loaded = np.zeros(nf, dtype=np.int64)
    events = []
    for ob in info["static"]:
        vis = rd >= ob["rf_ud"]
        loaded += vis
        for f, appeared in keyframe_visibility(ob, vis, flash):
            events.append([f, "load" if appeared else "unload", ob["rf_size"]])
    for ob, p0, v in info["movers"]:
        pos = np.array(p0)[None, :] + np.array(v)[None, :] * t[:, None]
        vis = rd >= np.linalg.norm(pos - cam[None, :], axis=1)
        loaded += vis
        for f, appeared in keyframe_visibility(ob, vis, flash):
            events.append([f, "load" if appeared else "unload", ob["rf_size"]])
    events.sort(key=lambda e: e[0])

    # the sky unloads in one frame
    f_sky = int(round(E["sky_unload_at"] * fps)) + 1
    off = info["world"].node_tree.nodes["SkyOff"].outputs[0]
    off.default_value = 0.0
    off.keyframe_insert("default_value", frame=f_sky - 1)
    off.default_value = 1.0
    off.keyframe_insert("default_value", frame=f_sky)
    rf.set_interpolation(info["world"].node_tree, "CONSTANT")

    # camera: subtle handheld sway all along, then the fall
    camobj = info["camera"]
    f_fall = int(round(E["fall_at"] * fps)) + 1
    loc0 = camobj.location.copy()
    rot0 = camobj.rotation_euler.copy()
    rf.set_interp("BEZIER")
    for f in (1, f_fall):
        camobj.location = loc0
        camobj.rotation_euler = rot0
        camobj.keyframe_insert("location", frame=f)
        camobj.keyframe_insert("rotation_euler", frame=f)
    camobj.location = (loc0.x, loc0.y + 1.5, loc0.z - 24.0)
    camobj.rotation_euler = (math.radians(38.0), rot0.y + math.radians(9.0), rot0.z + math.radians(6.0))
    camobj.keyframe_insert("location", frame=nf)
    camobj.keyframe_insert("rotation_euler", frame=nf)
    for idx, s in ((0, 0.0035), (2, 0.0045)):
        rf.add_noise(camobj, "rotation_euler", idx, s, 70.0)
        rf.add_noise(camobj, "rotation_euler", idx, s * 10, 6.0, frame_range=(f_fall, nf), blend=6)

    # the void grid below appears as the camera falls
    rf.set_interp("CONSTANT")
    grid = info["grid"]
    grid.hide_render = True
    grid.keyframe_insert("hide_render", frame=1)
    grid.hide_render = False
    grid.keyframe_insert("hide_render", frame=f_fall)

    print(f"[render_distance] frames={nf} events={len(events)} loaded0={int(loaded[0])}")
    return {"fps": fps, "frames": nf, "rd_m": [round(float(x), 3) for x in rd],
            "loaded": [int(x) for x in loaded], "events": events}
