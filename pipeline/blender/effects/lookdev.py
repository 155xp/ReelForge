"""Effect for look development: a camera tour of a world, one shot per frame (set fps to 1 and render stills).

spec["effect"]["shots"] = [[camera_xyz, target_xyz, lens_mm], ...] in world coordinates (the mover stays put);
the sky and haze follow each shot's camera altitude.
"""
import bpy
import numpy as np

import look
import rf_common as rf


def apply(spec, info):
    shots = spec["effect"]["shots"]
    col = info["collections"]["hero"]
    cam = rf.add_camera(col, (0, 0, 2), 0.0, 0.0, 24.0)
    cam.data.clip_start = 0.3
    cam.data.clip_end = 400_000.0
    tgt = bpy.data.objects.new("CamTarget", None)
    col.objects.link(tgt)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = tgt
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    frames = np.arange(1, len(shots) + 1)
    for k in range(3):
        rf.key_series(cam, "location", k, frames, [s[0][k] for s in shots], interp="CONSTANT")
        rf.key_series(tgt, "location", k, frames, [s[1][k] for s in shots], interp="CONSTANT")
    rf.key_series(cam.data, "lens", -1, frames, [s[2] for s in shots], interp="CONSTANT")
    look.key_air(info["scene"], info["world"], frames, [s[0][2] for s in shots])
    return {"fps": spec["fps"], "frames": len(shots), "events": {}}
