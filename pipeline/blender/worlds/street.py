"""An ordinary small-town main street at true scale (metres), built so it holds up from a 15 cm close-up on the
asphalt to a view from 10 km up: lane markings, crosswalks and manholes on the road, curbs and scored sidewalks,
2-4 storey shops with cornices, awnings and signs, a white church with a 50 m steeple, street trees, lamp posts,
traffic signals, hydrants, benches, meters, parked cars, a bus at its stop, people, a grid of houses and yards out
to the edge of town, farmland, a distant downtown with a supertall, a mountain range with an Everest-height peak,
and a cumulus field.

Main Street runs along +Y (north) with its centreline at x = 0. Cross streets cross it every BLOCK metres; the one
by the subject spot is at y = Y0. The subject spot is a free parking space on the east curb at SPOT (4.7, 0, 0).

Everything on the ground hangs off one empty, info["mover"], so an effect can keep the camera at the origin and
scale the world round it (render space). Most things that can be knocked over are instances of a geometry-nodes
'crush field' (info["crush"]): an effect sets its footprint ("Axis X", "Axis Y": half-width and half-length per
unit of the subject's size; "Yaw"; "Center X/Y") and keys "LogH" (log2 of the subject's size in metres), and
everything inside the growing footprint tips away from it about its far bottom edge, slides out, and disappears once
the subject covers it. The same rule, in Python, is `contact_height()`, and info["crushables"] lists the big items,
so an effect can time debris, dust and sound to each building.

spec["world"]:
  "type": "street"
  "seed": 7                     layout randomness
  "time": "golden"              "golden" (default), "morning", "noon" or "night"
  "sun": {"heading": 215, "elevation": 12}     overrides the time preset (compass degrees from +Y)
  "subject_yaw": 200            which way the subject will face (compass degrees); used for the crush footprint
  "footprint": [0.42, 0.59]     the subject's footprint half-width and half-length per unit of its size (an effect
                                usually overrides these with its subject's own)
  "crowd": 26                   people on the sidewalks near the spot
  "traffic": true               cars driving past in the first seconds
  "town": {"half_x": 1300, "half_y": 1700}
  "downtown": {"at": [-1450, 2350], "towers": 34, "supertall": true, "supertall_at": [-900, 1500]}   or false
  "mountains": {"inner": 22000, "outer": 80000, "base_height": 3300,
                "massifs": [[x, y, peak_m, sigma_m, "LABEL"], ...]}   default: one 8,849 m peak 28 km NNW
  "clouds": {"base": 1300, "top": 1900, "coverage": 0.3, "extent": 30000}   or false

info (besides the usual "scene", "world", "sun", "sun_dir", "collections" with a "hero" collection):
  "mover", "ground_objects" (everything on the mover, e.g. to hide in space), "spot", "spot_yaw",
  "camera" {"location", "target", "lens"}, "crush" {"object", "modifier", "sockets", "footprint"},
  "crushables" [{name, cls, x, y, w, d, h, rad, yaw, tip}], "refs" {name: {"h"/"length", "pos", ...}},
  "hero" {"you", "you_height", "hydrant", "car_n", "car_s", "bus", "church", "steeple_top"}: the props round the
  spot (a hydrant, you filming on the curb, a sedan and an SUV parked either side, the bus at its stop across the
  street, the church on the corner), "people" [objects], "traffic" [objects], "lamp_lights" [night: point lights
  in the lamps near the spot], "landmarks" {"supertall": top xyz, "<massif label>": summit xyz},
  "clouds" {"base", "top", "objects"}, "mountains" {"object", "max", "summits"}, "time", "night"
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import facades
import look
import rf_common as rf
from parts import landmarks, nature
from parts import person as P

ROAD = 6.0                  # Main Street curb line, either side of the centreline
PARK = 2.6                  # parking lane
WALK = 4.5                  # sidewalk
FRONT = ROAD + WALK         # building line
XROAD = 5.0                 # cross streets: curb either side of their centreline
XWALK = 3.0
XFRONT = XROAD + XWALK
BLOCK = 112.0
Y0 = 28.0
SIDE0, SIDE_STEP = 130.0, 120.0    # the first parallel residential street, and the spacing after it
SPOT = (ROAD - PARK / 2, 0.0, 0.0)
LAWN = -0.3                        # the ground plane's height (roads and sidewalks sit on top of it)
MAIN_Y = (-430.0, 470.0)           # the stretch of Main Street with full geometry

TIMES = {
    "golden": dict(heading=215.0, elevation=12.0, energy=4.2, color=(1.0, 0.77, 0.53), gain=0.16, lit=0.14, lamps=1.2),
    "morning": dict(heading=110.0, elevation=16.0, energy=4.0, color=(1.0, 0.87, 0.74), gain=0.18, lit=0.04, lamps=0.0),
    "noon": dict(heading=200.0, elevation=62.0, energy=5.0, color=(1.0, 0.97, 0.93), gain=0.22, lit=0.02, lamps=0.0),
    "night": dict(heading=260.0, elevation=-14.0, energy=0.45, color=(0.55, 0.66, 1.0), gain=0.16, lit=0.55,
                  lamps=12.0),
}


def cross_ys(lo=-4000.0, hi=4000.0):
    k0, k1 = math.ceil((lo - Y0) / BLOCK), math.floor((hi - Y0) / BLOCK)
    return [Y0 + k * BLOCK for k in range(k0, k1 + 1)]


def contact_height(px, py, rad, spot, yaw_deg, ax, ay):
    """Subject height (m) at which its footprint ellipse first touches an item of support radius `rad` at
    (px, py): the Python twin of the crush field's rule."""
    qx, qy = px - spot[0], py - spot[1]
    yaw = math.radians(-yaw_deg)
    lx = qx * math.cos(yaw) + qy * math.sin(yaw)
    ly = -qx * math.sin(yaw) + qy * math.cos(yaw)
    ec = math.hypot(lx / ax, ly / ay)
    q = math.hypot(qx, qy) + 1e-9
    return max(ec * max(1.0 - rad / q, 0.02), 0.01)


# ---------------------------------------------------------------- materials

def _obj(nt):
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    return tc, sep


def _noise(nt, vec, scale, detail=4.0, rough=0.55):
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def _smooth(nt, value, lo, hi):
    mr = nt.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    nt.feed(mr.inputs["Value"], value)
    mr.inputs["From Min"].default_value = lo
    mr.inputs["From Max"].default_value = hi
    return mr.outputs["Result"]


def _bsdf(mat):
    nt = rf.NodeTree(mat.node_tree)
    return nt, next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def _bump(mat, height_fn, strength=0.3, distance=0.02):
    nt, b = _bsdf(mat)
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    nt.feed(bump.inputs["Height"], height_fn(nt))
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])


def _rep(nt, v, period):
    """Distance (signed, centred) of v to the nearest multiple of `period`."""
    return nt.math("SUBTRACT", nt.math("MODULO", nt.math("ADD", v, period * 1000.5), period), period / 2)


def _band(nt, v, lo, hi):
    return nt.band(v, lo, hi)


def _road_y(nt, y):
    """Signed distance from y to the nearest cross-street centreline."""
    return _rep(nt, nt.math("SUBTRACT", y, Y0), BLOCK)


def asphalt_main():
    store = {}

    def base(nt):
        tc, sep = _obj(nt)
        x, y = sep.outputs["X"], sep.outputs["Y"]
        ax = nt.math("ABSOLUTE", x)
        dy = _road_y(nt, y)
        ady = nt.math("ABSOLUTE", dy)
        outside_box = nt.math("GREATER_THAN", ady, XROAD + 0.4)          # no lane paint inside the intersection
        # asphalt: worn binder with lighter aggregate specks, patches and darker oil down the middle of each lane
        grain = _noise(nt, tc.outputs["Object"], 14.0, 8.0, 0.7)
        spk = nt.node("ShaderNodeTexVoronoi")
        spk.inputs["Scale"].default_value = 90.0
        nt.links.new(tc.outputs["Object"], spk.inputs["Vector"])
        specks = _smooth(nt, spk.outputs["Distance"], 0.12, 0.02)
        patch = _smooth(nt, _noise(nt, tc.outputs["Object"], 0.09, 3.0), 0.56, 0.6)
        col = nt.mix_color(grain, (0.06, 0.06, 0.062, 1.0), (0.12, 0.117, 0.112, 1.0))
        col = nt.mix_color(nt.math("MULTIPLY", specks, 0.5), col, (0.22, 0.215, 0.205, 1.0))
        col = nt.mix_color(nt.math("MULTIPLY", patch, 0.7), col, (0.022, 0.022, 0.024, 1.0))
        oil = nt.math("MULTIPLY", _smooth(nt, nt.math("ABSOLUTE", nt.math("SUBTRACT", ax, 1.7)), 0.5, 0.05),
                      _smooth(nt, _noise(nt, tc.outputs["Object"], 0.6, 3.0), 0.45, 0.7))
        col = nt.mix_color(nt.math("MULTIPLY", oil, 0.5), col, (0.012, 0.012, 0.013, 1.0))
        # paint
        yellow = nt.math("MULTIPLY", _band(nt, ax, 0.07, 0.22), outside_box)
        edge = nt.math("MULTIPLY", _band(nt, ax, ROAD - PARK - 0.07, ROAD - PARK + 0.07), outside_box)
        tick_y = nt.math("ABSOLUTE", _rep(nt, y, 6.5))
        ticks = nt.math("MULTIPLY", nt.math("MULTIPLY", _band(nt, ax, ROAD - PARK, ROAD - PARK + 0.75),
                                            nt.math("LESS_THAN", tick_y, 0.07)), outside_box)
        zebra_band = _band(nt, ady, XROAD + 0.6, XROAD + 3.4)
        zebra = nt.math("MULTIPLY", nt.math("MULTIPLY", zebra_band, nt.math("LESS_THAN", nt.math("ABSOLUTE",
                        _rep(nt, x, 1.2)), 0.33)), nt.math("LESS_THAN", ax, ROAD - 0.3))
        stop_n = nt.math("MULTIPLY", _band(nt, dy, -(XROAD + 4.7), -(XROAD + 4.2)), nt.math("GREATER_THAN", x, 0.3))
        stop_s = nt.math("MULTIPLY", _band(nt, dy, XROAD + 4.2, XROAD + 4.7), nt.math("LESS_THAN", x, -0.3))
        stops = nt.math("MAXIMUM", stop_n, stop_s)
        white = nt.math("MAXIMUM", nt.math("MAXIMUM", edge, ticks), nt.math("MAXIMUM", zebra, stops))
        wear = _smooth(nt, _noise(nt, tc.outputs["Object"], 3.0, 6.0), 0.3, 0.55)
        white = nt.math("MULTIPLY", white, wear)
        yellow = nt.math("MULTIPLY", yellow, wear)
        col = nt.mix_color(white, col, (0.62, 0.62, 0.6, 1.0))
        col = nt.mix_color(yellow, col, (0.62, 0.42, 0.04, 1.0))
        # manholes: cast-iron discs with a ring pattern
        man = None
        for (mx, my) in ((1.6, -6.5), (-2.0, 9.5), (2.2, -60.0), (-1.8, 70.0)):
            d = nt.node("ShaderNodeVectorMath", operation="DISTANCE")
            nt.links.new(tc.outputs["Object"], d.inputs[0])
            d.inputs[1].default_value = (mx, my, 0.0)
            m = _smooth(nt, d.outputs["Value"], 0.34, 0.31)
            man = m if man is None else nt.math("MAXIMUM", man, m)
            store.setdefault("man_d", d.outputs["Value"])
        ring = nt.math("GREATER_THAN", nt.math("SINE", nt.math("MULTIPLY", store["man_d"], 60.0)), 0.3)
        iron = nt.mix_color(nt.math("MULTIPLY", ring, 0.5), (0.03, 0.028, 0.026, 1.0), (0.09, 0.08, 0.07, 1.0))
        col = nt.mix_color(man, col, iron)
        store["paint"] = nt.math("MAXIMUM", white, yellow)
        store["man"] = man
        store["grain"] = grain
        store["oil"] = oil
        return col

    def rough(nt):
        r = nt.math("SUBTRACT", 0.93, nt.math("MULTIPLY", store["paint"], 0.3))
        return nt.math("SUBTRACT", r, nt.math("MULTIPLY", store["oil"], 0.35))

    mat = rf.make_material("street_asphalt", base, rough=rough, haze=1.0, glitch=False)
    _bump(mat, lambda nt: nt.math("ADD", store["grain"], nt.math("MULTIPLY", store["paint"], 0.4)), 0.25, 0.01)
    return mat


def asphalt_cross():
    store = {}

    def base(nt):
        tc, sep = _obj(nt)
        x, y = sep.outputs["X"], sep.outputs["Y"]
        ax = nt.math("ABSOLUTE", x)
        dy = _road_y(nt, y)
        grain = _noise(nt, tc.outputs["Object"], 14.0, 8.0, 0.7)
        col = nt.mix_color(grain, (0.062, 0.062, 0.064, 1.0), (0.12, 0.118, 0.112, 1.0))
        patch = _smooth(nt, _noise(nt, tc.outputs["Object"], 0.11, 3.0), 0.56, 0.6)
        col = nt.mix_color(nt.math("MULTIPLY", patch, 0.6), col, (0.024, 0.024, 0.026, 1.0))
        dash = nt.math("LESS_THAN", nt.math("MODULO", nt.math("ADD", x, 3000.0), 9.0), 3.0)
        centre = nt.math("MULTIPLY", nt.math("MULTIPLY", _band(nt, dy, -0.07, 0.07), dash),
                         nt.math("GREATER_THAN", ax, FRONT + 3.0))
        zebra = nt.math("MULTIPLY", nt.math("MULTIPLY", _band(nt, ax, ROAD + 0.6, ROAD + 3.6),
                                            nt.math("LESS_THAN", nt.math("ABSOLUTE", _rep(nt, y, 1.2)), 0.33)),
                        nt.math("LESS_THAN", nt.math("ABSOLUTE", dy), XROAD - 0.3))
        wear = _smooth(nt, _noise(nt, tc.outputs["Object"], 3.0, 6.0), 0.3, 0.55)
        col = nt.mix_color(nt.math("MULTIPLY", zebra, wear), col, (0.62, 0.62, 0.6, 1.0))
        col = nt.mix_color(nt.math("MULTIPLY", centre, wear), col, (0.62, 0.42, 0.04, 1.0))
        store["grain"] = grain
        return col

    mat = rf.make_material("street_asphalt_cross", base, rough=0.92, haze=1.0, glitch=False)
    _bump(mat, lambda nt: store["grain"], 0.2, 0.01)
    return mat


def concrete(name, tone=(0.40, 0.385, 0.36), joints=1.5):
    store = {}

    def base(nt):
        tc, sep = _obj(nt)
        jx = nt.math("LESS_THAN", nt.math("ABSOLUTE", _rep(nt, sep.outputs["X"], joints)), 0.012)
        jy = nt.math("LESS_THAN", nt.math("ABSOLUTE", _rep(nt, sep.outputs["Y"], joints)), 0.012)
        joint = nt.math("MAXIMUM", jx, jy)
        n = _noise(nt, tc.outputs["Object"], 2.0, 6.0)
        stain = _smooth(nt, _noise(nt, tc.outputs["Object"], 0.35, 4.0), 0.55, 0.7)
        col = nt.mix_color(n, tuple(c * 0.85 for c in tone) + (1.0,), tuple(c * 1.12 for c in tone) + (1.0,))
        col = nt.mix_color(nt.math("MULTIPLY", stain, 0.45), col, (0.12, 0.115, 0.11, 1.0))
        col = nt.mix_color(nt.math("MULTIPLY", joint, 0.8), col, (0.08, 0.075, 0.07, 1.0))
        store["j"] = joint
        store["n"] = _noise(nt, tc.outputs["Object"], 30.0, 4.0)
        return col

    mat = rf.make_material(name, base, rough=0.88, haze=1.0, glitch=True)
    _bump(mat, lambda nt: nt.math("SUBTRACT", nt.math("MULTIPLY", store["n"], 0.4), store["j"]), 0.3, 0.01)
    return mat


def land_material(half_x, half_y):
    """The ground out to the mountains: lawns and painted streets in town, then a patchwork of fields, hedgerows
    and woods. Streets near Main Street are real geometry on top of this."""
    def base(nt):
        tc, sep = _obj(nt)
        x, y = sep.outputs["X"], sep.outputs["Y"]
        ax, ay = nt.math("ABSOLUTE", x), nt.math("ABSOLUTE", y)
        wob = nt.math("MULTIPLY", nt.math("SUBTRACT", _noise(nt, tc.outputs["Object"], 0.0015, 2.0), 0.5), 500.0)
        town = nt.math("MULTIPLY", _smooth(nt, nt.math("ADD", ax, wob), half_x + 120, half_x - 120),
                       _smooth(nt, nt.math("ADD", ay, wob), half_y + 120, half_y - 120))
        dyc = nt.math("ABSOLUTE", _road_y(nt, y))
        side = nt.math("ABSOLUTE", _rep(nt, nt.math("SUBTRACT", ax, SIDE0), SIDE_STEP))
        side = nt.math("ADD", side, nt.math("MULTIPLY", nt.math("LESS_THAN", ax, 70.0), 1000.0))
        asph = nt.math("MAXIMUM", nt.math("LESS_THAN", nt.math("MINIMUM", dyc, side), XROAD),
                       nt.math("LESS_THAN", ax, ROAD))
        walk = nt.math("MAXIMUM", nt.math("LESS_THAN", nt.math("MINIMUM", dyc, side), XFRONT - 0.5),
                       nt.math("LESS_THAN", ax, FRONT))
        lot_n = _noise(nt, tc.outputs["Object"], 0.05, 3.0)
        lawn = nt.mix_color(lot_n, (0.045, 0.085, 0.022, 1.0), (0.11, 0.14, 0.05, 1.0))
        dry = _smooth(nt, _noise(nt, tc.outputs["Object"], 0.6, 4.0), 0.5, 0.75)
        lawn = nt.mix_color(nt.math("MULTIPLY", dry, 0.5), lawn, (0.16, 0.15, 0.08, 1.0))
        parking = nt.math("MULTIPLY", nt.math("LESS_THAN", ax, 62.0), nt.math("GREATER_THAN", ax, FRONT))
        town_col = nt.mix_color(nt.math("MULTIPLY", parking, 0.9), lawn, (0.075, 0.073, 0.07, 1.0))
        town_col = nt.mix_color(walk, town_col, (0.33, 0.32, 0.3, 1.0))
        town_col = nt.mix_color(asph, town_col, (0.045, 0.045, 0.048, 1.0))
        # farmland: fields on a slightly rotated grid, one crop per field, hedgerows between, woods on top
        rot = nt.node("ShaderNodeVectorRotate")
        rot.rotation_type = "Z_AXIS"
        rot.inputs["Angle"].default_value = math.radians(11.0)
        nt.links.new(tc.outputs["Object"], rot.inputs["Vector"])
        rs = nt.node("ShaderNodeSeparateXYZ")
        nt.links.new(rot.outputs["Vector"], rs.inputs[0])
        cu = nt.math("DIVIDE", rs.outputs["X"], 430.0)
        cv = nt.math("DIVIDE", rs.outputs["Y"], 310.0)
        cell = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(nt.math("FLOOR", cu), cell.inputs["X"])
        nt.links.new(nt.math("FLOOR", cv), cell.inputs["Y"])
        wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
        nt.links.new(cell.outputs["Vector"], wn.inputs["Vector"])
        crop = nt.ramp(wn.outputs["Value"], [(0.0, (0.26, 0.2, 0.07)), (0.22, (0.07, 0.12, 0.03)),
                                              (0.42, (0.14, 0.17, 0.05)), (0.6, (0.12, 0.08, 0.04)),
                                              (0.78, (0.3, 0.26, 0.13)), (0.9, (0.05, 0.09, 0.025))], constant=True)
        rows = nt.math("MULTIPLY", nt.math("SINE", nt.math("MULTIPLY", rs.outputs["X"], 2.1)), 0.06)
        crop = nt.mix_color(nt.math("ADD", 0.5, rows), (0.0, 0.0, 0.0, 1.0), crop)
        fu = nt.math("ABSOLUTE", nt.math("SUBTRACT", nt.math("FRACT", cu), 0.5))
        fv = nt.math("ABSOLUTE", nt.math("SUBTRACT", nt.math("FRACT", cv), 0.5))
        hedge = nt.math("MAXIMUM", nt.math("GREATER_THAN", fu, 0.488), nt.math("GREATER_THAN", fv, 0.484))
        farm = nt.mix_color(hedge, crop, (0.02, 0.04, 0.012, 1.0))
        woods = _smooth(nt, _noise(nt, tc.outputs["Object"], 0.00035, 4.0), 0.58, 0.61)
        wood_col = nt.mix_color(_noise(nt, tc.outputs["Object"], 0.05, 6.0), (0.012, 0.03, 0.01, 1.0),
                                (0.04, 0.065, 0.018, 1.0))
        farm = nt.mix_color(woods, farm, wood_col)
        return nt.mix_color(town, farm, town_col)

    return rf.make_material("land", base, rough=0.92, haze=1.0, glitch=False)


def _attr(nt, name):
    return nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=name).outputs["Fac"]


def shopfront_material(lit, glow):
    """Main-street facades: brick, stucco or paint per building; sash windows in bays (frames, a few lit rooms);
    a ground floor of big display windows lit warm inside, with mullions and a dark kickplate. Reads the object's
    "halfw", "halfd", "cellw", "celld" (bay widths front and side) and "wtop" (top of the upper floors)."""
    store = {}

    def base(nt):
        tc, sep = _obj(nt)
        nrm = nt.node("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Normal"], nrm.inputs[0])
        x, y, z = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
        isx = nt.math("GREATER_THAN", nt.math("ABSOLUTE", nrm.outputs["X"]), 0.5)
        notx = nt.math("SUBTRACT", 1.0, isx)
        hw, hd = _attr(nt, "halfw"), _attr(nt, "halfd")
        u = nt.math("ADD", nt.math("MULTIPLY", nt.math("ADD", x, hw), notx),
                    nt.math("MULTIPLY", nt.math("ADD", y, hd), isx))
        cell = nt.math("ADD", nt.math("MULTIPLY", _attr(nt, "cellw"), notx),
                       nt.math("MULTIPLY", _attr(nt, "celld"), isx))
        span = nt.math("MULTIPLY", nt.math("ADD", nt.math("MULTIPLY", hw, notx), nt.math("MULTIPLY", hd, isx)), 2.0)
        vert = nt.math("LESS_THAN", nt.math("ABSOLUTE", nrm.outputs["Z"]), 0.5)
        rnd = nt.object_random()
        pal = nt.ramp(rnd, [(0.0, (0.36, 0.11, 0.06)), (0.15, (0.26, 0.09, 0.05)), (0.3, (0.6, 0.47, 0.32)),
                            (0.45, (0.72, 0.62, 0.48)), (0.6, (0.55, 0.55, 0.52)), (0.72, (0.3, 0.38, 0.33)),
                            (0.84, (0.33, 0.37, 0.45)), (0.93, (0.78, 0.76, 0.7)), (1.0, (0.45, 0.2, 0.12))],
                      constant=True)
        brick_on = nt.math("MAXIMUM", nt.math("LESS_THAN", rnd, 0.45), nt.math("GREATER_THAN", rnd, 0.93))
        bv = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(u, bv.inputs["X"])
        nt.links.new(z, bv.inputs["Y"])
        br = nt.node("ShaderNodeTexBrick")
        nt.links.new(bv.outputs["Vector"], br.inputs["Vector"])
        br.inputs["Scale"].default_value = 1.0
        br.inputs["Mortar Size"].default_value = 0.012
        br.inputs["Brick Width"].default_value = 0.25
        br.inputs["Row Height"].default_value = 0.075
        nt.links.new(pal, br.inputs["Color1"])
        dark = nt.mix_color(0.25, pal, (0.0, 0.0, 0.0, 1.0))
        nt.links.new(dark, br.inputs["Color2"])
        br.inputs["Mortar"].default_value = (0.5, 0.48, 0.44, 1.0)
        grime = _smooth(nt, _noise(nt, tc.outputs["Object"], 0.35, 4.0), 0.35, 0.75)
        wall = nt.mix_color(brick_on, pal, br.outputs["Color"])
        wall = nt.mix_color(nt.math("MULTIPLY", grime, 0.25), wall, (0.05, 0.045, 0.04, 1.0))
        # upper floors: sash windows in bays
        zz = nt.math("SUBTRACT", z, 4.6)
        upper = nt.math("MULTIPLY", nt.math("GREATER_THAN", zz, 0.0), nt.math("LESS_THAN", z, _attr(nt, "wtop")))
        fz = nt.math("FRACT", nt.math("DIVIDE", zz, 3.4))
        fu = nt.math("FRACT", nt.math("DIVIDE", u, cell))
        du = nt.math("MULTIPLY", nt.math("ABSOLUTE", nt.math("SUBTRACT", fu, 0.5)), cell)     # metres from bay centre
        inner = nt.math("MULTIPLY", nt.math("LESS_THAN", du, 0.5), _band(nt, fz, 0.24, 0.8))
        frame = nt.math("MULTIPLY", nt.math("LESS_THAN", du, 0.6), _band(nt, fz, 0.21, 0.83))
        bar = nt.math("MULTIPLY", inner, nt.math("LESS_THAN", nt.math("ABSOLUTE", nt.math("SUBTRACT", fz, 0.52)),
                                                 0.012))
        win = nt.math("MULTIPLY", nt.math("MULTIPLY", inner, upper), vert)
        fr = nt.math("MULTIPLY", nt.math("MULTIPLY", nt.math("MAXIMUM", nt.math("SUBTRACT", frame, inner), bar), upper),
                     vert)
        # ground floor: display windows between the end piers, mullions every 1.8 m, kickplate, transom bar
        ground = nt.math("MULTIPLY", nt.math("LESS_THAN", z, 3.45), vert)
        piers = nt.math("MULTIPLY", nt.math("GREATER_THAN", u, 0.5),
                        nt.math("LESS_THAN", u, nt.math("SUBTRACT", span, 0.5)))
        shop = nt.math("MULTIPLY", nt.math("MULTIPLY", ground, piers), _band(nt, z, 0.62, 3.2))
        pane_u = nt.math("FRACT", nt.math("DIVIDE", u, 1.8))
        mull = nt.math("GREATER_THAN", nt.math("ABSOLUTE", nt.math("SUBTRACT", pane_u, 0.5)), 0.483)
        shop_glass = nt.math("MULTIPLY", shop, nt.math("SUBTRACT", 1.0, mull))
        kick = nt.math("MULTIPLY", nt.math("MULTIPLY", ground, piers), nt.math("LESS_THAN", z, 0.62))
        transom = nt.math("MULTIPLY", nt.math("MULTIPLY", ground, piers), _band(nt, z, 3.2, 3.45))
        frame_col = nt.ramp(nt.math("FRACT", nt.math("MULTIPLY", rnd, 13.7)),
                            [(0.0, (0.82, 0.8, 0.74)), (0.55, (0.04, 0.12, 0.08)), (0.75, (0.12, 0.05, 0.04)),
                             (1.0, (0.85, 0.83, 0.78))], constant=True)
        # glass: dark with a hint of sky up top; a few rooms lit
        wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="3D")
        cid = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(nt.math("FLOOR", nt.math("DIVIDE", u, cell)), cid.inputs["X"])
        nt.links.new(nt.math("FLOOR", nt.math("DIVIDE", zz, 3.4)), cid.inputs["Y"])
        nt.links.new(nt.math("MULTIPLY", rnd, 77.0), cid.inputs["Z"])
        nt.links.new(cid.outputs["Vector"], wn.inputs["Vector"])
        room = nt.math("GREATER_THAN", wn.outputs["Value"], 1.0 - lit)
        sky = nt.mix_color(_smooth(nt, fz, 0.3, 0.8), (0.018, 0.022, 0.03, 1.0), (0.11, 0.13, 0.17, 1.0))
        curtain = nt.mix_color(nt.math("GREATER_THAN", wn.outputs["Value"], 0.55), sky, (0.2, 0.17, 0.13, 1.0))
        drawn = nt.math("MULTIPLY", nt.math("GREATER_THAN", fu, 0.5), nt.math("LESS_THAN", wn.outputs["Value"], 0.35))
        glass = nt.mix_color(drawn, sky, curtain)
        pane = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
        pv = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(nt.math("FLOOR", nt.math("DIVIDE", u, 1.8)), pv.inputs["X"])
        nt.links.new(nt.math("MULTIPLY", rnd, 37.0), pv.inputs["Y"])
        nt.links.new(pv.outputs["Vector"], pane.inputs["Vector"])
        glow_n = nt.math("MULTIPLY", nt.math("GREATER_THAN", pane.outputs["Value"], 0.4),
                         nt.math("ADD", 0.55, nt.math("MULTIPLY", _smooth(nt, z, 3.2, 0.8), 0.45)))
        refl = nt.mix_color(_smooth(nt, z, 0.6, 3.2), (0.02, 0.022, 0.026, 1.0), (0.1, 0.12, 0.15, 1.0))
        inside = nt.mix_color(nt.math("MULTIPLY", glow_n, 0.8), refl, (0.2, 0.135, 0.08, 1.0))
        col = nt.mix_color(fr, wall, frame_col)
        col = nt.mix_color(win, col, glass)
        col = nt.mix_color(kick, col, (0.03, 0.03, 0.032, 1.0))
        col = nt.mix_color(transom, col, frame_col)
        col = nt.mix_color(shop_glass, col, inside)
        roof = nt.math("GREATER_THAN", nrm.outputs["Z"], 0.5)
        roof_col = nt.mix_color(_noise(nt, tc.outputs["Object"], 0.6, 3.0), (0.16, 0.16, 0.17, 1.0),
                                (0.3, 0.29, 0.27, 1.0))
        col = nt.mix_color(roof, col, roof_col)
        store["glass"] = nt.math("MAXIMUM", win, shop_glass)
        store["emit"] = nt.math("ADD", nt.math("MULTIPLY", nt.math("MULTIPLY", win, room), 1.3),
                                nt.math("MULTIPLY", nt.math("MULTIPLY", shop_glass, glow_n), glow))
        return col

    def rough(nt):
        return nt.math("SUBTRACT", 0.85, nt.math("MULTIPLY", store["glass"], 0.78))

    mat = rf.make_material("shopfront", base, rough=rough, haze=1.0, glitch=True)
    nt, b = _bsdf(mat)
    b.inputs["Emission Color"].default_value = (1.0, 0.68, 0.38, 1.0)
    nt.links.new(store["emit"], b.inputs["Emission Strength"])
    return mat


def cloud_material():
    """Cumulus at golden hour: warm where the sun reaches, a cool lift in the shade, a bright rim, soft lumps."""
    mat = bpy.data.materials.new("cumulus")
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    tc = nt.node("ShaderNodeTexCoord")
    n = _noise(nt, tc.outputs["Object"], 1 / 45.0, 6.0, 0.62)
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 30.0
    nt.links.new(n, bump.inputs["Height"])
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.9, 0.89, 0.88, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.0
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])

    def attr(name):
        return nt.node("ShaderNodeAttribute", attribute_type="VIEW_LAYER", attribute_name=name)

    dot = nt.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nt.links.new(bump.outputs["Normal"], dot.inputs[0])
    nt.links.new(attr("rf_sun_dir").outputs["Vector"], dot.inputs[1])
    wrap = nt.math("POWER", nt.math("ADD", 0.5, nt.math("MULTIPLY", dot.outputs["Value"], 0.5)), 1.6)
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.45
    rim = nt.math("POWER", lw.outputs["Facing"], 3.0)
    warm = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(attr("rf_haze_sun").outputs["Color"], warm.inputs[0])
    nt.links.new(nt.math("ADD", nt.math("MULTIPLY", wrap, 0.42), nt.math("MULTIPLY", rim, 0.35)), warm.inputs["Scale"])
    cool = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(attr("rf_haze_col").outputs["Color"], cool.inputs[0])
    cool.inputs["Scale"].default_value = 0.3
    em = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(warm.outputs["Vector"], em.inputs[0])
    nt.links.new(cool.outputs["Vector"], em.inputs[1])
    nt.links.new(em.outputs["Vector"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    shader = rf.scene_haze(nt, b.outputs[0], 0.55) if rf.HAZE_SCENE else b.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    return mat



def leaves_material():
    def base(nt):
        tc = nt.node("ShaderNodeTexCoord")
        n = _noise(nt, tc.outputs["Object"], 2.6, 5.0, 0.65)
        tint = nt.ramp(nt.object_random(), [(0.0, (0.05, 0.1, 0.018)), (0.5, (0.09, 0.13, 0.025)),
                                            (0.85, (0.13, 0.15, 0.03)), (1.0, (0.22, 0.12, 0.03))])
        return nt.mix_color(_smooth(nt, n, 0.35, 0.7), (0.012, 0.025, 0.006, 1.0), tint)

    mat = rf.make_material("leaves", base, rough=0.75, haze=1.0, glitch=True)
    nt, b = _bsdf(mat)
    for k, v in (("Subsurface Weight", 0.25), ("Subsurface Scale", 0.2)):
        if k in b.inputs:
            b.inputs[k].default_value = v
    if "Subsurface Radius" in b.inputs:
        b.inputs["Subsurface Radius"].default_value = (0.3, 0.6, 0.1)
    _bump(mat, lambda nt: _noise(nt, nt.node("ShaderNodeTexCoord").outputs["Object"], 3.5, 4.0), 0.8, 0.15)
    return mat


def emissive(name, color, strength, rough=0.3):
    return rf.make_material(name, color, rough=rough, emission=(color, strength), haze=0.6, glitch=True)


def awning_material():
    def base(nt):
        tc, sep = _obj(nt)
        rnd = nt.object_random()
        col = nt.ramp(rnd, [(0.0, (0.35, 0.02, 0.02)), (0.2, (0.02, 0.12, 0.05)), (0.4, (0.02, 0.05, 0.2)),
                            (0.6, (0.4, 0.15, 0.02)), (0.8, (0.05, 0.05, 0.05)), (1.0, (0.3, 0.02, 0.1))],
                      constant=True)
        stripes = nt.math("MULTIPLY", nt.math("GREATER_THAN", nt.math("FRACT", nt.math("MULTIPLY", rnd, 7.3)), 0.5),
                          nt.math("GREATER_THAN", nt.math("SINE", nt.math("MULTIPLY", sep.outputs["X"], 10.5)), 0.0))
        return nt.mix_color(stripes, col, (0.85, 0.82, 0.74, 1.0))

    return rf.make_material("awning", base, rough=0.85, haze=1.0, glitch=True)


def sign_material(glow):
    store = {}

    def base(nt):
        tc, sep = _obj(nt)
        rnd = nt.object_random()
        board = nt.ramp(rnd, [(0.0, (0.02, 0.025, 0.06)), (0.25, (0.25, 0.02, 0.02)), (0.5, (0.01, 0.06, 0.03)),
                              (0.75, (0.015, 0.015, 0.015)), (1.0, (0.45, 0.35, 0.2))], constant=True)
        # a row of 'letters': blocky cells along the board, most of them filled
        u = nt.math("MULTIPLY", nt.math("ADD", sep.outputs["X"], sep.outputs["Y"]), 6.5)
        cell = nt.math("FLOOR", u)
        wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
        cv = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(cell, cv.inputs["X"])
        nt.links.new(nt.math("MULTIPLY", rnd, 50.0), cv.inputs["Y"])
        nt.links.new(cv.outputs["Vector"], wn.inputs["Vector"])
        letter = nt.math("MULTIPLY", nt.math("GREATER_THAN", wn.outputs["Value"], 0.16),
                         _band(nt, nt.math("FRACT", u), 0.2, 0.78))
        # strokes: drop the middle of most glyphs so they read as letters rather than blocks
        fz2 = nt.math("FRACT", nt.math("MULTIPLY", sep.outputs["Z"], 1.6))
        hole = nt.math("MULTIPLY", _band(nt, nt.math("FRACT", u), 0.38, 0.6), _band(nt, fz2, 0.42, 0.6))
        hole = nt.math("MULTIPLY", hole, nt.math("GREATER_THAN", wn.outputs["Value"], 0.45))
        letter = nt.math("MULTIPLY", letter, nt.math("SUBTRACT", 1.0, hole))
        letter = nt.math("MULTIPLY", letter, _band(nt, fz2, 0.33, 0.68))
        store["l"] = letter
        return nt.mix_color(letter, board, (0.92, 0.86, 0.7, 1.0))

    mat = rf.make_material("shop_sign", base, rough=0.45, haze=1.0, glitch=True)
    nt, b = _bsdf(mat)
    b.inputs["Emission Color"].default_value = (1.0, 0.85, 0.6, 1.0)
    nt.links.new(nt.math("MULTIPLY", store["l"], glow), b.inputs["Emission Strength"])
    return mat


def house_material(lit):
    """Painted lap siding in a random colour per house, white-trimmed windows (a few lit), shingle roofs."""
    store = {}

    def base(nt):
        tc, sep = _obj(nt)
        nrm = nt.node("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Normal"], nrm.inputs[0])
        x, y, z = sep.outputs["X"], sep.outputs["Y"], sep.outputs["Z"]
        rnd = nt.object_random()
        siding = nt.ramp(rnd, [(0.0, (0.8, 0.78, 0.72)), (0.16, (0.62, 0.55, 0.36)), (0.3, (0.38, 0.47, 0.55)),
                               (0.45, (0.55, 0.56, 0.54)), (0.6, (0.42, 0.48, 0.36)), (0.75, (0.72, 0.62, 0.48)),
                               (0.88, (0.5, 0.22, 0.16)), (1.0, (0.85, 0.85, 0.82))], constant=True)
        laps = nt.math("GREATER_THAN", nt.math("FRACT", nt.math("MULTIPLY", z, 5.0)), 0.88)
        siding = nt.mix_color(nt.math("MULTIPLY", laps, 0.35), siding, (0.1, 0.1, 0.1, 1.0))
        isx = nt.math("GREATER_THAN", nt.math("ABSOLUTE", nrm.outputs["X"]), 0.5)
        u = nt.math("ADD", nt.math("MULTIPLY", x, nt.math("SUBTRACT", 1.0, isx)), nt.math("MULTIPLY", y, isx))
        fu = nt.math("ABSOLUTE", _rep(nt, u, 2.8))
        vert = nt.math("LESS_THAN", nt.math("ABSOLUTE", nrm.outputs["Z"]), 0.3)
        zf = nt.math("MODULO", z, 2.9)
        win = nt.math("MULTIPLY", nt.math("MULTIPLY", nt.math("LESS_THAN", fu, 0.48), _band(nt, zf, 0.95, 2.25)), vert)
        trim = nt.math("MULTIPLY", nt.math("MULTIPLY", nt.math("LESS_THAN", fu, 0.6), _band(nt, zf, 0.85, 2.35)), vert)
        cellid = nt.math("ADD", nt.math("FLOOR", nt.math("DIVIDE", u, 2.8)),
                         nt.math("MULTIPLY", nt.math("FLOOR", nt.math("DIVIDE", z, 2.9)), 7.0))
        wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
        cv = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(cellid, cv.inputs["X"])
        nt.links.new(nt.math("MULTIPLY", rnd, 91.0), cv.inputs["Y"])
        nt.links.new(cv.outputs["Vector"], wn.inputs["Vector"])
        store["lit"] = nt.math("MULTIPLY", win, nt.math("GREATER_THAN", wn.outputs["Value"], 1.0 - lit))
        store["win"] = win
        col = nt.mix_color(trim, siding, (0.88, 0.87, 0.84, 1.0))
        col = nt.mix_color(win, col, (0.03, 0.035, 0.045, 1.0))
        roof = nt.math("GREATER_THAN", nrm.outputs["Z"], 0.3)
        shingle = nt.ramp(nt.math("FRACT", nt.math("MULTIPLY", rnd, 3.7)), [(0.0, (0.06, 0.06, 0.065)),
                          (0.4, (0.16, 0.1, 0.07)), (0.7, (0.25, 0.08, 0.05)), (1.0, (0.12, 0.13, 0.13))],
                         constant=True)
        rows = nt.math("GREATER_THAN", nt.math("FRACT", nt.math("MULTIPLY", z, 3.2)), 0.85)
        shingle = nt.mix_color(nt.math("MULTIPLY", rows, 0.5), shingle, (0.02, 0.02, 0.02, 1.0))
        return nt.mix_color(roof, col, shingle)

    def rough(nt):
        return nt.math("SUBTRACT", 0.85, nt.math("MULTIPLY", store["win"], 0.7))

    mat = rf.make_material("house", base, rough=rough, haze=1.0, glitch=True)
    nt, b = _bsdf(mat)
    b.inputs["Emission Color"].default_value = facades.WARM
    nt.links.new(nt.math("MULTIPLY", store["lit"], 1.4), b.inputs["Emission Strength"])
    return mat


def church_material():
    def base(nt):
        tc, sep = _obj(nt)
        laps = nt.math("GREATER_THAN", nt.math("FRACT", nt.math("MULTIPLY", sep.outputs["Z"], 4.4)), 0.9)
        return nt.mix_color(nt.math("MULTIPLY", laps, 0.25), (0.86, 0.85, 0.82, 1.0), (0.3, 0.3, 0.3, 1.0))

    return rf.make_material("church_white", base, rough=0.6, haze=1.0, glitch=True)


def clock_material(cx, cz, r):
    """A clock face on the church tower (a disc of radius r centred at x = cx, z = cz in the church's object space):
    a rim, twelve hour marks and the hands at twenty to seven."""
    def base(nt):
        tc, sep = _obj(nt)
        dx = nt.math("SUBTRACT", sep.outputs["X"], cx)
        dz = nt.math("SUBTRACT", sep.outputs["Z"], cz)
        rr = nt.math("SQRT", nt.math("ADD", nt.math("MULTIPLY", dx, dx), nt.math("MULTIPLY", dz, dz)))
        ang = nt.math("ARCTAN2", dx, dz)
        hours = nt.math("FRACT", nt.math("ADD", nt.math("MULTIPLY", ang, 12.0 / (2 * math.pi)), 0.5))
        tick = nt.math("MULTIPLY", nt.math("LESS_THAN", nt.math("ABSOLUTE", nt.math("SUBTRACT", hours, 0.5)), 0.07),
                       _band(nt, rr, 0.74 * r, 0.9 * r))
        ink = nt.math("MAXIMUM", tick, nt.math("GREATER_THAN", rr, 0.95 * r))
        for a_deg, length, width in ((200.0, 0.55 * r, 0.06), (240.0, 0.82 * r, 0.035)):
            a_ = math.radians(a_deg)
            along = nt.math("ADD", nt.math("MULTIPLY", dx, math.sin(a_)), nt.math("MULTIPLY", dz, math.cos(a_)))
            perp = nt.math("SUBTRACT", nt.math("MULTIPLY", dx, math.cos(a_)), nt.math("MULTIPLY", dz, math.sin(a_)))
            hand = nt.math("MULTIPLY", _band(nt, along, -0.1, length),
                           nt.math("LESS_THAN", nt.math("ABSOLUTE", perp), width))
            ink = nt.math("MAXIMUM", ink, hand)
        return nt.mix_color(ink, (0.9, 0.88, 0.82, 1.0), (0.02, 0.02, 0.02, 1.0))

    return rf.make_material("clock_face", base, rough=0.4, haze=1.0, glitch=True)


def stained_glass(glow):
    def base(nt):
        tc = nt.node("ShaderNodeTexCoord")
        v = nt.node("ShaderNodeTexVoronoi")
        v.inputs["Scale"].default_value = 3.5
        nt.links.new(tc.outputs["Object"], v.inputs["Vector"])
        return nt.ramp(v.outputs["Color"], [(0.0, (0.05, 0.08, 0.35)), (0.35, (0.4, 0.04, 0.05)),
                                            (0.6, (0.45, 0.32, 0.03)), (0.8, (0.03, 0.2, 0.08)),
                                            (1.0, (0.1, 0.12, 0.4))],
                       constant=True)

    mat = rf.make_material("stained_glass", base, rough=0.15, haze=1.0, glitch=True)
    nt, b = _bsdf(mat)
    nt.links.new(b.inputs["Base Color"].links[0].from_socket, b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = glow
    return mat


def car_paint():
    def base(nt):
        return nt.ramp(nt.object_random(), [(0.0, (0.75, 0.75, 0.74)), (0.14, (0.02, 0.02, 0.022)),
                                            (0.28, (0.25, 0.26, 0.28)), (0.4, (0.32, 0.01, 0.01)),
                                            (0.52, (0.015, 0.05, 0.16)), (0.64, (0.48, 0.48, 0.47)),
                                            (0.74, (0.05, 0.12, 0.08)), (0.84, (0.6, 0.4, 0.18)),
                                            (0.93, (0.1, 0.1, 0.11)), (1.0, (0.55, 0.05, 0.02))], constant=True)

    mat = rf.make_material("car_paint", base, rough=0.22, metallic=0.4, haze=1.0, glitch=True)
    nt, b = _bsdf(mat)
    for k, v in (("Coat Weight", 0.8), ("Coat Roughness", 0.05)):
        if k in b.inputs:
            b.inputs[k].default_value = v
    return mat


def make_materials(T):
    M = {}
    M["asphalt"] = asphalt_main()
    M["asphalt_x"] = asphalt_cross()
    M["walk"] = concrete("sidewalk")
    M["curb"] = concrete("curb", (0.5, 0.48, 0.45), joints=3.0)
    M["facade"] = shopfront_material(max(T["lit"], 0.1), 0.25 + T["lamps"] * 0.25)
    M["glass_tower"] = facades.building_material("tower_glass", "glass", lit=T["lit"] * 0.8)
    M["trim"] = rf.make_material("trim", lambda nt: nt.ramp(nt.object_random(), [
        (0.0, (0.75, 0.72, 0.64)), (0.5, (0.18, 0.16, 0.14)), (0.8, (0.55, 0.5, 0.42)), (1.0, (0.05, 0.12, 0.08))],
        constant=True), rough=0.6, haze=1.0, glitch=True)
    M["awning"] = awning_material()
    M["sign"] = sign_material(0.35 + T["lamps"] * 0.6)
    M["roof"] = rf.make_material("roof", (0.09, 0.085, 0.08), rough=0.85, haze=1.0, glitch=True)
    M["dark"] = rf.make_material("dark", (0.015, 0.015, 0.017), rough=0.4, haze=1.0, glitch=True)
    M["house"] = house_material(T["lit"])
    M["church"] = church_material()
    M["church_roof"] = rf.make_material("church_roof", (0.05, 0.055, 0.06), rough=0.55, haze=1.0, glitch=True)
    M["stained"] = stained_glass(0.25 + T["lamps"] * 0.4)
    M["red_door"] = rf.make_material("red_door", (0.32, 0.015, 0.012), rough=0.35, haze=1.0, glitch=True)
    M["bark"] = rf.make_material("bark", (0.06, 0.045, 0.035), rough=0.9, haze=1.0, glitch=True)
    M["leaves"] = leaves_material()
    M["lamp_metal"] = rf.make_material("lamp_metal", (0.012, 0.025, 0.018), rough=0.35, metallic=0.6, haze=1.0,
                                       glitch=True)
    M["lamp_glass"] = emissive("lamp_glass", (1.0, 0.72, 0.42), T["lamps"])
    M["signal_body"] = rf.make_material("signal_body", (0.03, 0.03, 0.025), rough=0.5, haze=1.0, glitch=True)
    M["sig_red"] = emissive("sig_red", (1.0, 0.04, 0.02), 9.0)
    M["sig_green"] = emissive("sig_green", (0.1, 1.0, 0.45), 9.0)
    M["sig_off"] = rf.make_material("sig_off", (0.04, 0.04, 0.035), rough=0.2, haze=1.0, glitch=True)
    M["street_sign"] = rf.make_material("street_sign", (0.01, 0.12, 0.04), rough=0.4, haze=1.0, glitch=True)
    M["hydrant"] = rf.make_material("hydrant", (0.5, 0.025, 0.015), rough=0.3, haze=1.0, glitch=True)
    M["hydrant_cap"] = rf.make_material("hydrant_cap", (0.75, 0.6, 0.04), rough=0.35, haze=1.0, glitch=True)
    M["wood"] = rf.make_material("bench_wood", (0.2, 0.1, 0.045), rough=0.7, haze=1.0, glitch=True)
    M["metal"] = rf.make_material("metal", (0.35, 0.36, 0.37), rough=0.35, metallic=0.85, haze=1.0, glitch=True)
    M["green_metal"] = rf.make_material("green_metal", (0.02, 0.07, 0.04), rough=0.45, metallic=0.4, haze=1.0,
                                        glitch=True)
    M["blue_box"] = rf.make_material("blue_box", (0.01, 0.06, 0.25), rough=0.4, haze=1.0, glitch=True)
    M["poster"] = emissive("poster", (0.9, 0.55, 0.25), 0.6 + T["lamps"] * 0.5)
    M["shelter_glass"] = rf.make_material("shelter_glass", (0.08, 0.1, 0.11), rough=0.05, metallic=0.4, haze=1.0,
                                          glitch=True)
    M["paint"] = car_paint()
    M["car_glass"] = rf.make_material("car_glass", (0.01, 0.012, 0.016), rough=0.05, haze=1.0, glitch=True)
    M["car_trim"] = rf.make_material("car_trim", (0.015, 0.015, 0.016), rough=0.6, haze=1.0, glitch=True)
    M["tire"] = rf.make_material("tire", (0.012, 0.012, 0.012), rough=0.92, haze=1.0, glitch=True)
    M["rim"] = rf.make_material("rim", (0.6, 0.6, 0.62), rough=0.25, metallic=1.0, haze=1.0, glitch=True)
    M["headlight"] = emissive("headlight", (1.0, 0.95, 0.85), 0.3 + T["lamps"] * 2.0)
    M["taillight"] = emissive("taillight", (1.0, 0.03, 0.02), 0.6 + T["lamps"])
    M["bus_paint"] = rf.make_material(
        "bus_paint", lambda nt: nt.mix_color(_band(nt, _obj(nt)[1].outputs["Z"], 0.95, 1.25), (0.85, 0.85, 0.83, 1.0),
                                             (0.02, 0.18, 0.55, 1.0)), rough=0.3, haze=1.0, glitch=True)
    M["bus_sign"] = emissive("bus_sign", (1.0, 0.6, 0.05), 3.0)
    M["shirt"] = rf.make_material("shirt", lambda nt: nt.object_color(), rough=0.8, haze=1.0, glitch=True)
    M["pants"] = rf.make_material("pants", lambda nt: nt.ramp(nt.object_random(), [(0.0, (0.03, 0.05, 0.12)),
                                  (0.45, (0.2, 0.17, 0.11)), (0.7, (0.02, 0.02, 0.022)), (1.0, (0.08, 0.1, 0.18))],
                                  constant=True), rough=0.85, haze=1.0, glitch=True)
    M["skin"] = rf.make_material("skin", lambda nt: nt.ramp(nt.object_random(), [(0.0, (0.55, 0.36, 0.26)),
                                 (0.3, (0.33, 0.19, 0.11)), (0.6, (0.7, 0.5, 0.38)), (0.85, (0.18, 0.1, 0.06)),
                                 (1.0, (0.62, 0.42, 0.3))], constant=True), rough=0.5, haze=1.0, glitch=True)
    M["planter"] = concrete("planter", (0.45, 0.43, 0.4), joints=10.0)
    return M


# ---------------------------------------------------------------- mesh helpers

def _tube(mb, p0, p1, r0, r1, mat, seg=8):
    p0, p1 = Vector(p0), Vector(p1)
    axis = (p1 - p0).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    b = len(mb.verts)
    for p, r in ((p0, r0), (p1, r1)):
        for k in range(seg):
            a = 2 * math.pi * k / seg
            mb.verts.append(tuple(p + (u * math.cos(a) + v * math.sin(a)) * r))
    for k in range(seg):
        k2 = (k + 1) % seg
        mb.faces.append((b + k, b + k2, b + seg + k2, b + seg + k))
        mb.mats.append(mat)
    mb.faces.append(tuple(b + seg + k for k in range(seg)))
    mb.mats.append(mat)
    mb.faces.append(tuple(b + k for k in reversed(range(seg))))
    mb.mats.append(mat)


def _prism_roof(mb, x0, y0, x1, y1, z0, rise, mat, along_x=True, overhang=0.35):
    """Gable roof: the ridge runs along x (or y), eaves overhang."""
    x0, y0, x1, y1 = x0 - overhang, y0 - overhang, x1 + overhang, y1 + overhang
    b = len(mb.verts)
    if along_x:
        ym = (y0 + y1) / 2
        mb.verts += [(x0, y0, z0), (x1, y0, z0), (x1, ym, z0 + rise), (x0, ym, z0 + rise),
                     (x0, y1, z0), (x1, y1, z0)]
        quads = [(0, 1, 2, 3), (3, 2, 5, 4)]
        tris = [(0, 3, 4), (1, 5, 2)]
    else:
        xm = (x0 + x1) / 2
        mb.verts += [(x0, y0, z0), (xm, y0, z0 + rise), (xm, y1, z0 + rise), (x0, y1, z0),
                     (x1, y0, z0), (x1, y1, z0)]
        quads = [(0, 1, 2, 3), (1, 4, 5, 2)]
        tris = [(0, 4, 1), (3, 2, 5)]
    for q in quads:
        mb.faces.append(tuple(b + i for i in q))
        mb.mats.append(mat)
    for t in tris:
        mb.faces.append(tuple(b + i for i in t))
        mb.mats.append(mat)
    # underside
    mb.faces.append(tuple(b + i for i in ((0, 4, 5, 1) if along_x else (0, 3, 5, 4))))
    mb.mats.append(mat)


def _blob_crown(mb, rnd, c, r, mat, n=8, subdiv=2):
    for _ in range(n):
        d = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.6, 0.8)))
        if d.length > 1:
            d.normalize()
        rr = r * rnd.uniform(0.42, 0.62)
        p = Vector(c) + Vector((d.x * r * 0.55, d.y * r * 0.55, d.z * r * 0.45))
        mb.ico(tuple(p), (rr, rr, rr * 0.85), subdiv, mat, jitter=0.18, rnd=rnd)


# ---------------------------------------------------------------- variants (instance sources)

class Variants:
    """Objects in an excluded collection that the crush field instances, in name order (= instance index)."""

    def __init__(self, collection):
        self.col = collection
        self.obs = []

    def add(self, name, mesh, **props):
        k = len(self.obs)
        ob = rf.add_object(f"v{k:04d}_{name}", mesh, self.col)
        ob["glitch"] = 0.0
        for p, v in props.items():
            ob[p] = v
        self.obs.append(ob)
        return k


def shop_mesh(rnd, M, w, d, storeys, pitched=False):
    """A main-street building, front face at y = -d/2 (local), origin at the footprint centre.
    Returns (mesh, height, props for the facade shader)."""
    F, TRIM, AWN, SIGN, ROOF, DARK = range(6)
    mb = rf.MeshBuilder()
    H = 4.6 + 3.4 * (storeys - 1)
    mb.box(-w / 2, -d / 2, -0.45, w / 2, d / 2, H, F)
    fy = -d / 2
    nb = max(1, round(w / 2.7))
    cell = w / nb
    props = {"halfw": w / 2, "halfd": d / 2, "cellw": cell, "celld": d / max(1, round(d / 3.0)), "wtop": H}
    for j in range(storeys - 1):                      # sills and lintels round each upper window
        zj = 4.6 + 3.4 * j
        for i in range(nb):
            cx = -w / 2 + (i + 0.5) * cell
            mb.box(cx - 0.7, fy - 0.1, zj + 0.62, cx + 0.7, fy + 0.02, zj + 0.72, TRIM)
            mb.box(cx - 0.68, fy - 0.06, zj + 2.82, cx + 0.68, fy + 0.02, zj + 3.0, TRIM)
    # parapet round a flat roof, or a gable roof
    if pitched:
        _prism_roof(mb, -w / 2, -d / 2, w / 2, d / 2, H, min(4.0, d * 0.32), ROOF, along_x=True, overhang=0.3)
    else:
        t = 0.25
        ph = rnd.uniform(0.7, 1.4)
        for (a, b_, c, e) in ((-w / 2, -d / 2, w / 2, -d / 2 + t), (-w / 2, d / 2 - t, w / 2, d / 2),
                              (-w / 2, -d / 2, -w / 2 + t, d / 2), (w / 2 - t, -d / 2, w / 2, d / 2)):
            mb.box(a, b_, H, c, e, H + ph, F)
        # cornice and a frieze band
        mb.box(-w / 2 - 0.05, fy - 0.45, H + ph - 0.35, w / 2 + 0.05, fy + 0.1, H + ph, TRIM)
        mb.box(-w / 2, fy - 0.2, H + ph - 0.9, w / 2, fy + 0.05, H + ph - 0.35, TRIM)
        # rooftop units
        for _ in range(rnd.randint(0, 2)):
            ux, uy = rnd.uniform(-w / 2 + 1.5, w / 2 - 1.5), rnd.uniform(-d / 2 + 3, d / 2 - 2)
            mb.box(ux - 0.9, uy - 0.7, H, ux + 0.9, uy + 0.7, H + 1.2, TRIM)
    # string course over the shopfront, storey bands, pilasters at the edges
    mb.box(-w / 2, fy - 0.18, 4.1, w / 2, fy + 0.05, 4.45, TRIM)
    for s in range(1, storeys - 1):
        z = 4.6 + 3.4 * s - 0.1
        mb.box(-w / 2, fy - 0.1, z, w / 2, fy + 0.05, z + 0.18, TRIM)
    for sx in (-1, 1):
        mb.box(sx * w / 2 - (0.45 if sx > 0 else 0), fy - 0.15, 0, sx * w / 2 + (0.45 if sx < 0 else 0), fy + 0.05, 4.1,
               TRIM)
    # awning: sloped canvas from the facade over the sidewalk, with a valance
    if rnd.random() < 0.8:
        aw = w * rnd.uniform(0.62, 0.9)
        out, z_hi, z_lo = rnd.uniform(1.3, 1.8), 3.75, 3.05
        b = len(mb.verts)
        mb.verts += [(-aw / 2, fy, z_hi), (aw / 2, fy, z_hi), (aw / 2, fy - out, z_lo), (-aw / 2, fy - out, z_lo),
                     (-aw / 2, fy, z_hi + 0.06), (aw / 2, fy, z_hi + 0.06), (aw / 2, fy - out, z_lo + 0.06),
                     (-aw / 2, fy - out, z_lo + 0.06)]
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (3, 7, 6, 2), (0, 4, 7, 3), (1, 2, 6, 5)):
            mb.faces.append(tuple(b + i for i in q))
            mb.mats.append(AWN)
        mb.box(-aw / 2, fy - out - 0.03, z_lo - 0.32, aw / 2, fy - out + 0.02, z_lo + 0.03, AWN)
    # sign board over the shopfront, sometimes a projecting blade sign
    sw = w * rnd.uniform(0.45, 0.75)
    mb.box(-sw / 2, fy - 0.2, 3.9 if storeys == 1 else 4.5, sw / 2, fy - 0.05, 4.4 if storeys == 1 else 5.3, SIGN)
    if rnd.random() < 0.35 and storeys > 1:
        bx = rnd.choice((-1, 1)) * (w / 2 - 0.6)
        mb.box(bx - 0.06, fy - 1.3, 5.2, bx + 0.06, fy - 0.1, 6.9, SIGN)
    # recessed doorway
    dx = rnd.uniform(-w / 2 + 1.2, w / 2 - 1.2)
    mb.box(dx - 0.6, fy - 0.02, 0.0, dx + 0.6, fy + 0.02, 2.5, DARK)
    me = mb.build("shop", [M["facade"], M["trim"], M["awning"], M["sign"], M["roof"], M["dark"]], fix_normals=True)
    return me, H + (min(4.0, d * 0.32) if pitched else 1.2), props


def house_mesh(rnd, M, kind):
    """A detached house, front at y = -d/2, origin at the footprint centre. Returns (mesh, w, d, h)."""
    HOUSE, ROOF, TRIM, DARK = range(4)
    w, d = rnd.uniform(8.5, 12.5), rnd.uniform(8.0, 11.5)
    st = 2 if kind % 3 != 0 else 1
    H = 2.9 * st + 0.3
    mb = rf.MeshBuilder()
    mb.box(-w / 2, -d / 2, 0, w / 2, d / 2, H, HOUSE)
    along = kind % 2 == 0
    rise = (d if along else w) * rnd.uniform(0.28, 0.42)
    _prism_roof(mb, -w / 2, -d / 2, w / 2, d / 2, H, rise, ROOF, along_x=along)
    # porch with a roof and posts
    if kind % 4 != 3:
        pw = w * rnd.uniform(0.4, 0.7)
        px = rnd.uniform(-w / 2 + pw / 2, w / 2 - pw / 2)
        mb.box(px - pw / 2, -d / 2 - 2.2, 0, px + pw / 2, -d / 2, 0.45, TRIM)
        mb.box(px - pw / 2 - 0.2, -d / 2 - 2.4, 2.8, px + pw / 2 + 0.2, -d / 2, 3.0, ROOF)
        for sx in (-1, 1):
            mb.box(px + sx * pw / 2 - 0.1, -d / 2 - 2.3, 0.45, px + sx * pw / 2 + 0.1, -d / 2 - 2.1, 2.8, TRIM)
    mb.box(-0.5, -d / 2 - 0.03, 0.3, 0.5, -d / 2 + 0.02, 2.3, DARK)              # front door
    cx = rnd.uniform(-w / 2 + 1, w / 2 - 1)
    mb.box(cx - 0.45, d / 4 - 0.45, H, cx + 0.45, d / 4 + 0.45, H + rise + 1.0, TRIM)   # chimney
    if kind % 5 == 4:                                                            # attached garage
        mb.box(w / 2, -d / 2 + 1, 0, w / 2 + 6.5, d / 2, 3.0, HOUSE)
        _prism_roof(mb, w / 2, -d / 2 + 1, w / 2 + 6.5, d / 2, 3.0, 1.6, ROOF, along_x=False, overhang=0.25)
        mb.box(w / 2 + 0.8, -d / 2 + 0.97, 0.0, w / 2 + 5.7, -d / 2 + 1.0, 2.4, TRIM)
        w += 6.5
    me = mb.build("house", [M["house"], M["house"], M["trim"], M["dark"]], fix_normals=True)
    # the roof faces use the same 'house' material (its shader paints anything facing up as shingles)
    return me, w, d, H + rise


def church_mesh(M):
    """White clapboard church: nave with a steep roof, a front tower with a belfry and a spire to 50 m.
    Local frame: front (with the tower) at y = -d/2; the tower sits on the front-left corner."""
    WHITE, ROOF, GLASS, DOOR, DARK, CLOCK = range(6)
    mb = rf.MeshBuilder()
    w, d = 15.0, 30.0
    mb.box(-w / 2, -d / 2, 0, w / 2, d / 2, 9.0, WHITE)
    _prism_roof(mb, -w / 2, -d / 2, w / 2, d / 2, 9.0, 7.5, ROOF, along_x=False, overhang=0.45)
    for k in range(5):                                       # tall windows down each side
        y = -d / 2 + 5.0 + k * 5.0
        for sx in (-1, 1):
            mb.box(sx * w / 2 - 0.08, y - 0.7, 2.2, sx * w / 2 + 0.08, y + 0.7, 7.0, GLASS)
            mb.box(sx * w / 2 - 0.12, y - 0.85, 7.0, sx * w / 2 + 0.12, y + 0.85, 7.35, WHITE)
    # tower: plain shaft, a belfry with dark openings, a clock, then the spire
    tx, ty, ts = -w / 2 + 3.6, -d / 2 - 1.0, 7.0
    clock = clock_material(tx, 16.5, 1.3)
    mb.box(tx - ts / 2, ty - ts / 2, 0, tx + ts / 2, ty + ts / 2, 20.0, WHITE)
    mb.box(tx - ts / 2 - 0.3, ty - ts / 2 - 0.3, 20.0, tx + ts / 2 + 0.3, ty + ts / 2 + 0.3, 20.6, WHITE)
    bs = 5.6
    mb.box(tx - bs / 2, ty - bs / 2, 20.6, tx + bs / 2, ty + bs / 2, 26.5, WHITE)
    for (nx, ny) in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        cx_, cy_ = tx + nx * (bs / 2), ty + ny * (bs / 2)
        if nx == 0:
            mb.box(cx_ - 1.0, cy_ - 0.06, 21.6, cx_ + 1.0, cy_ + 0.06, 25.4, DARK)
        else:
            mb.box(cx_ - 0.06, cy_ - 1.0, 21.6, cx_ + 0.06, cy_ + 1.0, 25.4, DARK)
    mb.box(tx - bs / 2 - 0.25, ty - bs / 2 - 0.25, 26.5, tx + bs / 2 + 0.25, ty + bs / 2 + 0.25, 27.1, WHITE)
    # clock face on the front of the shaft
    mb.cyl(0, 0, 0, 0.1, 1.3, 24, CLOCK)
    clock_idx = len(mb.verts) - 48
    for i in range(clock_idx, len(mb.verts)):
        x, y, z = mb.verts[i]
        mb.verts[i] = (tx + x, ty - ts / 2 - 0.05 - z, 16.5 + y)
    # spire: a tall square pyramid with a finial
    b = len(mb.verts)
    s2 = 2.4
    mb.verts += [(tx - s2, ty - s2, 27.1), (tx + s2, ty - s2, 27.1), (tx + s2, ty + s2, 27.1), (tx - s2, ty + s2, 27.1),
                 (tx, ty, 49.0)]
    for q in ((0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)):
        mb.faces.append(tuple(b + i for i in q))
        mb.mats.append(WHITE)
    mb.cyl(tx, ty, 49.0, 50.0, 0.12, 6, DARK)
    mb.box(tx - 0.5, ty - 0.06, 49.5, tx + 0.5, ty + 0.06, 49.7, DARK)
    # front doors and steps
    mb.box(tx - 1.1, ty - ts / 2 - 0.05, 0.0, tx + 1.1, ty - ts / 2 + 0.02, 3.4, DOOR)
    mb.box(1.0, -d / 2 - 0.05, 0.0, 3.4, -d / 2 + 0.02, 3.4, DOOR)
    mb.box(tx - 2.5, ty - ts / 2 - 2.0, 0, tx + 2.5, ty - ts / 2, 0.45, WHITE)
    me = mb.build("church", [M["church"], M["church_roof"], M["stained"], M["red_door"], M["dark"], clock],
                  fix_normals=True)
    return me, w, d + 1.0 + ts / 2, 50.0, (tx, ty)


def tree_mesh(rnd, M, height):
    BARK, LEAF = range(2)
    mb = rf.MeshBuilder()
    trunk_h = height * rnd.uniform(0.35, 0.45)
    _tube(mb, (0, 0, 0), (0, 0, trunk_h + 0.5), 0.17 * height / 9, 0.11 * height / 9, BARK)
    for _ in range(4):
        a = rnd.uniform(0, 2 * math.pi)
        tip = (math.cos(a) * height * 0.18, math.sin(a) * height * 0.18, trunk_h + height * 0.22)
        _tube(mb, (0, 0, trunk_h * 0.9), tip, 0.08, 0.04, BARK, 6)
    crown_r = height * rnd.uniform(0.32, 0.4)
    _blob_crown(mb, rnd, (0, 0, trunk_h + crown_r * 0.95), crown_r, LEAF, n=rnd.randint(8, 10))
    _blob_crown(mb, rnd, (0, 0, trunk_h + crown_r * 1.05), crown_r * 1.12, LEAF, n=rnd.randint(14, 18), subdiv=1)
    return mb.build("tree", [M["bark"], M["leaves"]], fix_normals=True, smooth=True)


def lamp_mesh(M):
    METAL, GLASS = range(2)
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 0.5, 0.2, 12, METAL, r_top=0.14)
    mb.cyl(0, 0, 0.5, 4.2, 0.075, 12, METAL, r_top=0.06)
    for z in (0.9, 2.6, 4.1):
        mb.cyl(0, 0, z, z + 0.08, 0.1, 12, METAL)
    mb.cyl(0, 0, 4.2, 4.35, 0.16, 12, METAL)
    mb.ico((0, 0, 4.62), (0.22, 0.22, 0.32), 2, GLASS)
    mb.cyl(0, 0, 4.88, 5.02, 0.2, 12, METAL, r_top=0.05)
    mb.cyl(0, 0, 5.02, 5.2, 0.03, 6, METAL)
    return mb.build("lamp", [M["lamp_metal"], M["lamp_glass"]], fix_normals=True, smooth=False)


def signal_mesh(M, arm=7.5):
    """Traffic signal mast: pole at the origin, arm along -x over the road (yaw it into place)."""
    BODY, RED, GREEN, OFF, SIGN = range(5)
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 7.0, 0.16, 12, BODY, r_top=0.12)
    mb.cyl(0, 0, 0, 0.6, 0.3, 12, BODY, r_top=0.2)
    _tube(mb, (0, 0, 6.2), (-arm, 0, 6.35), 0.1, 0.07, BODY)
    _tube(mb, (0, 0, 6.9), (-arm * 0.45, 0, 6.35), 0.04, 0.03, BODY, 6)
    for k, x in enumerate((-arm * 0.5, -arm * 0.92)):
        mb.box(x - 0.18, -0.18, 5.0, x + 0.18, 0.12, 6.25, BODY)
        mb.box(x - 0.32, 0.1, 4.92, x + 0.32, 0.14, 6.33, BODY)          # backplate
        for j, (z, mat) in enumerate(((6.0, RED), (5.62, OFF), (5.24, GREEN))):
            lb = len(mb.verts)
            mb.cyl(0, 0, 0, 0.05, 0.13, 12, mat)
            for i in range(lb, len(mb.verts)):
                vx, vy, vz = mb.verts[i]
                mb.verts[i] = (x + vx, -0.18 - vz, z + vy)
            # visor
            mb.box(x - 0.15, -0.42, z + 0.12, x + 0.15, -0.18, z + 0.15, BODY)
    mb.box(-arm * 0.25 - 1.0, -0.02, 6.6, -arm * 0.25 + 1.0, 0.02, 6.95, SIGN)    # street name blade
    mb.box(-0.32, -0.32, 2.6, 0.0, 0.0, 3.2, BODY)                               # pedestrian head
    return mb.build("signal", [M["signal_body"], M["sig_red"], M["sig_green"], M["sig_off"], M["street_sign"]],
                    fix_normals=True)


def hydrant_mesh(M):
    RED, CAP = range(2)
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 0.08, 0.17, 16, RED)
    mb.cyl(0, 0, 0.08, 0.56, 0.125, 16, RED, r_top=0.115)
    mb.cyl(0, 0, 0.56, 0.62, 0.15, 16, RED)
    mb.ico((0, 0, 0.64), (0.13, 0.13, 0.1), 2, CAP)
    mb.cyl(0, 0, 0.7, 0.76, 0.03, 6, CAP)
    for sx in (-1, 1):
        mb.cyl_x(sx * 0.15, 0, 0.42, 0.055, 0.05, 12, RED)
        mb.cyl_x(sx * 0.21, 0, 0.42, 0.065, 0.015, 12, CAP)
    lb = len(mb.verts)
    mb.cyl_x(0, 0, 0, 0.075, 0.07, 12, RED)
    for i in range(lb, len(mb.verts)):
        vx, vy, vz = mb.verts[i]
        mb.verts[i] = (vy, -0.17 - vx, 0.36 + vz)
    return mb.build("hydrant", [M["hydrant"], M["hydrant_cap"]], fix_normals=True, smooth=True)


def bench_mesh(M):
    WOOD, MET = range(2)
    mb = rf.MeshBuilder()
    for k in range(3):
        mb.box(-0.9, -0.25 + k * 0.17, 0.43, 0.9, -0.12 + k * 0.17, 0.47, WOOD)
    for k in range(2):
        mb.box(-0.9, 0.25 + k * 0.03, 0.55 + k * 0.15, 0.9, 0.28 + k * 0.03, 0.66 + k * 0.15, WOOD)
    for sx in (-0.75, 0.75):
        mb.box(sx - 0.03, -0.27, 0, sx + 0.03, 0.3, 0.45, MET)
        mb.box(sx - 0.03, 0.24, 0.45, sx + 0.03, 0.32, 0.85, MET)
    return mb.build("bench", [M["wood"], M["green_metal"]], fix_normals=True)


def can_mesh(M):
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 0.95, 0.28, 16, 0)
    mb.cyl(0, 0, 0.95, 1.05, 0.3, 16, 0, r_top=0.2)
    return mb.build("trash_can", [M["green_metal"]], fix_normals=True, smooth=True)


def meter_mesh(M):
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 1.15, 0.035, 8, 0)
    mb.box(-0.1, -0.08, 1.15, 0.1, 0.08, 1.45, 0)
    mb.ico((0, 0, 1.47), (0.1, 0.08, 0.06), 1, 1)
    return mb.build("meter", [M["metal"], M["car_glass"]], fix_normals=True)


def newsbox_mesh(M):
    mb = rf.MeshBuilder()
    mb.box(-0.25, -0.22, 0.25, 0.25, 0.22, 1.1, 0)
    mb.box(-0.2, -0.235, 0.6, 0.2, -0.22, 0.95, 1)
    for sx in (-0.2, 0.2):
        for sy in (-0.17, 0.17):
            mb.box(sx - 0.02, sy - 0.02, 0, sx + 0.02, sy + 0.02, 0.25, 2)
    return mb.build("newsbox", [M["blue_box"], M["car_glass"], M["metal"]], fix_normals=True)


def mailbox_mesh(M):
    mb = rf.MeshBuilder()
    mb.box(-0.27, -0.3, 0.3, 0.27, 0.3, 1.05, 0)
    lb = len(mb.verts)
    mb.cyl_x(0, 0, 1.05, 0.3, 0.27, 16, 0)
    for sx in (-0.22, 0.22):
        for sy in (-0.25, 0.25):
            mb.box(sx - 0.03, sy - 0.03, 0, sx + 0.03, sy + 0.03, 0.3, 1)
    return mb.build("mailbox", [M["blue_box"], M["metal"]], fix_normals=True)


def shelter_mesh(M):
    GLASS, MET, POSTER, WOOD = range(4)
    mb = rf.MeshBuilder()
    L, D, Hh = 4.2, 1.6, 2.5
    for sx in (-L / 2, L / 2):
        for sy in (-D / 2, D / 2):
            mb.box(sx - 0.05, sy - 0.05, 0, sx + 0.05, sy + 0.05, Hh, MET)
    mb.box(-L / 2 - 0.15, -D / 2 - 0.25, Hh, L / 2 + 0.15, D / 2 + 0.15, Hh + 0.12, MET)
    mb.box(-L / 2, D / 2 - 0.02, 0.15, L / 2, D / 2 + 0.02, Hh - 0.1, GLASS)
    mb.box(L / 2 - 0.02, -D / 2 + 0.1, 0.15, L / 2 + 0.02, D / 2, Hh - 0.1, POSTER)
    mb.box(-L / 2 - 0.02, -D / 2 + 0.1, 0.15, -L / 2 + 0.02, D / 2, Hh - 0.1, GLASS)
    mb.box(-1.6, D / 2 - 0.5, 0.45, 1.6, D / 2 - 0.1, 0.5, WOOD)
    return mb.build("shelter", [M["shelter_glass"], M["metal"], M["poster"], M["wood"]], fix_normals=True)


def planter_mesh(rnd, M):
    mb = rf.MeshBuilder()
    mb.box(-0.6, -0.6, 0, 0.6, 0.6, 0.55, 0)
    _blob_crown(mb, rnd, (0, 0, 0.95), 0.75, 1, n=4, subdiv=1)
    return mb.build("planter", [M["planter"], M["leaves"]], fix_normals=True)


CAR_KINDS = {
    #          L     W     body z0/z1  roof   belt  cabin(front, back)   wheel r
    "sedan": (4.75, 1.84, 0.28, 0.92, 1.45, 0.92, (0.75, -1.25), 0.33),
    "hatch": (4.2, 1.78, 0.28, 0.94, 1.5, 0.94, (0.55, -1.75), 0.32),
    "suv": (4.8, 1.92, 0.4, 1.12, 1.78, 1.12, (0.7, -2.0), 0.38),
    "pickup": (5.7, 2.0, 0.45, 1.15, 1.88, 1.15, (0.95, -0.55), 0.4),
    "van": (5.2, 2.0, 0.35, 1.0, 2.05, 1.0, (1.4, -2.45), 0.36),
}


def _rrect(w, a, b, rc, n=3):
    """Closed rounded-rectangle section [(x, z), ...] from z = a to b, width w, corner radius rc."""
    pts = []
    for cx, cz, a0 in ((w / 2 - rc, b - rc, 0.0), (-w / 2 + rc, b - rc, 90.0), (-w / 2 + rc, a + rc, 180.0),
                       (w / 2 - rc, a + rc, 270.0)):
        for k in range(n + 1):
            ang = math.radians(a0 + 90.0 * k / n)
            pts.append((cx + rc * math.cos(ang), cz + rc * math.sin(ang)))
    return pts


def car_mesh(M, kind):
    """A parked car, nose at +y, origin at the footprint centre on the ground: a rounded body, a glasshouse with
    pillars and a painted roof, lights, a grille, mirrors, and wheels with rims."""
    PAINT, GLASS, TRIM, TIRE, RIM, HEAD, TAIL = range(7)
    L, W, z0, z1, roof, belt, (cf, cb), wr = CAR_KINDS[kind]
    mb = rf.MeshBuilder()
    rc = 0.12
    # body: rear bumper, full width, hood dropping to a rounded nose
    prof = [(-L / 2, 0.92, 0.12, -0.1), (-L / 2 + 0.1, 0.97, 0.05, -0.03), (-L / 2 + 0.32, 1.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0), (L / 2 - 0.62, 1.0, 0.0, -0.03), (L / 2 - 0.3, 0.98, 0.02, -0.1),
            (L / 2 - 0.1, 0.95, 0.06, -0.17), (L / 2, 0.9, 0.11, -0.24)]
    secs = [(y, _rrect(W * kw, z0 + da, z1 + db, rc)) for y, kw, da, db in prof]
    npts = len(secs[0][1])
    mb.loft(secs, lambda s_, k: TRIM if k in (npts // 2 + 1, npts // 2 + 2) else PAINT, cap_mat=PAINT)
    # glasshouse: windshield, side windows between painted pillars, roof, rear window
    if kind == "pickup":
        gh = [(cf, 0.9, belt), (cf - 0.42, 0.82, roof), (cb + 0.12, 0.82, roof), (cb, 0.9, belt)]
        for sx in (-1, 1):
            x0, x1 = sorted((sx * W / 2, sx * (W / 2 - 0.07)))
            mb.box(x0, -L / 2 + 0.15, z1 - 0.02, x1, cb - 0.12, z1 + 0.3, PAINT)
        mb.box(-W / 2, -L / 2 + 0.08, z1 - 0.02, W / 2, -L / 2 + 0.16, z1 + 0.3, PAINT)
    else:
        rake = 0.62 if kind in ("sedan", "hatch") else 0.32
        back = 0.42 if kind == "sedan" else 0.12
        gh = [(cf + rake, 0.9, belt), (cf, 0.8, roof - 0.02), (cf - 0.15, 0.79, roof), (cb + back + 0.1, 0.79, roof),
              (cb + back, 0.8, roof - 0.02), (cb, 0.9, belt)]

    def gsec(kw, z):
        wb, wt = W * 0.9, W * kw
        if z <= belt + 1e-6:
            return [(-wb / 2, belt), (-wb / 2 + 0.02, belt + 0.05), (-wt / 2 + 0.02, belt + 0.07),
                    (wt / 2 - 0.02, belt + 0.07), (wb / 2 - 0.02, belt + 0.05), (wb / 2, belt)]
        return [(-wb / 2, belt), (-wt / 2, z - 0.06), (-wt / 2 + 0.08, z), (wt / 2 - 0.08, z), (wt / 2, z - 0.06),
                (wb / 2, belt)]

    def gmat(s_, k):
        if s_ in (0, len(gh) - 2):
            return GLASS if k in (1, 2, 3) else PAINT                 # windshield / rear window, pillars at the sides
        if k in (1, 2, 3):
            return PAINT                                            # roof
        return GLASS                                                # side windows

    mb.loft([(y, gsec(kw, z)) for y, kw, z in gh], gmat, cap_mat=PAINT)
    if kind != "pickup":
        ym = (cf + cb) / 2 + 0.1                                     # B-pillars
        for sx in (-1, 1):
            x0, x1 = sorted((sx * W * 0.4, sx * W * 0.452))
            mb.box(x0, ym - 0.06, belt, x1, ym + 0.06, roof - 0.04, PAINT)
    # lights, grille, plate, mirrors, wheel arches
    for sx in (-1, 1):
        x0, x1 = sorted((sx * W * 0.24, sx * W * 0.44))
        mb.box(x0, L / 2 - 0.12, z1 - 0.38, x1, L / 2 + 0.005, z1 - 0.26, HEAD)
        mb.box(x0, -L / 2 - 0.005, z1 - 0.3, x1, -L / 2 + 0.12, z1 - 0.18, TAIL)
        x0, x1 = sorted((sx * (W / 2 - 0.02), sx * (W / 2 + 0.13)))
        mb.box(x0, cf - 0.12, belt + 0.02, x1, cf + 0.02, belt + 0.13, PAINT)
        for y in (L / 2 - 0.85 - wr, -L / 2 + 0.8 + wr):
            x0, x1 = sorted((sx * (W / 2 - 0.02), sx * (W / 2 + 0.012)))
            mb.box(x0, y - wr - 0.08, z0 + 0.02, x1, y + wr + 0.08, z0 + wr * 0.95, TRIM)
    mb.box(-W * 0.22, L / 2 - 0.02, z0 + 0.16, W * 0.22, L / 2 + 0.03, z0 + 0.36, TRIM)
    mb.box(-0.26, -L / 2 - 0.02, z0 + 0.2, 0.26, -L / 2 + 0.02, z0 + 0.32, RIM)
    ax_f, ax_b = L / 2 - 0.85 - wr, -L / 2 + 0.8 + wr
    for y in (ax_f, ax_b):
        for sx in (-1, 1):
            mb.cyl_x(sx * (W / 2 - 0.13), y, wr, wr, 0.11, 20, TIRE)
            mb.cyl_x(sx * (W / 2 - 0.11), y, wr, wr * 0.6, 0.106, 14, RIM)
            mb.cyl_x(sx * (W / 2 - 0.105), y, wr, wr * 0.18, 0.106, 8, TRIM)
    return mb.build(f"car_{kind}", [M["paint"], M["car_glass"], M["car_trim"], M["tire"], M["rim"], M["headlight"],
                                    M["taillight"]], fix_normals=True)


def bus_mesh(M):
    """City bus, 12.2 m, nose at +y."""
    PAINT, GLASS, TRIM, TIRE, RIM, SIGN, HEAD, TAIL = range(8)
    mb = rf.MeshBuilder()
    L, W = 12.2, 2.55
    mb.box(-W / 2, -L / 2, 0.32, W / 2, L / 2, 1.2, PAINT)
    mb.box(-W / 2 + 0.03, -L / 2 + 0.3, 1.2, W / 2 - 0.03, L / 2 - 0.5, 2.55, GLASS)
    for y in np.linspace(-L / 2 + 0.3, L / 2 - 0.5, 9):
        for sx in (-1, 1):
            mb.box(sx * W / 2 - 0.05, y - 0.07, 1.2, sx * W / 2 + 0.05, y + 0.07, 2.55, PAINT)        # window pillars
    mb.box(-W / 2, -L / 2, 2.55, W / 2, L / 2, 3.05, PAINT)
    mb.box(-W / 2, L / 2 - 0.5, 1.2, W / 2, L / 2, 2.55, GLASS)                    # windshield
    mb.box(-W / 2, -L / 2, 1.2, W / 2, -L / 2 + 0.3, 2.55, PAINT)
    mb.box(-W / 2 + 0.25, L / 2 - 0.02, 2.62, W / 2 - 0.25, L / 2 + 0.02, 2.95, SIGN)
    mb.box(-W / 2 + 0.3, -L / 2 - 0.6, 3.05, W / 2 - 0.3, L / 2 - 2.5, 3.35, PAINT)  # roof pod
    for y0 in (L / 2 - 1.6, 0.4):
        mb.box(W / 2 - 0.02, y0 - 1.1, 0.35, W / 2 + 0.02, y0, 2.5, TRIM)          # doors
    for sx in (-1, 1):
        x0, x1 = sorted((sx * 0.75, sx * 1.15))
        mb.box(x0, L / 2 - 0.02, 0.55, x1, L / 2 + 0.02, 0.75, HEAD)
        mb.box(x0, -L / 2 - 0.02, 0.6, x1, -L / 2 + 0.02, 0.85, TAIL)
    for y in (L / 2 - 2.6, -L / 2 + 3.2):
        for sx in (-1, 1):
            mb.cyl_x(sx * (W / 2 - 0.2), y, 0.5, 0.5, 0.15, 18, TIRE)
            mb.cyl_x(sx * (W / 2 - 0.17), y, 0.5, 0.3, 0.145, 12, RIM)
    return mb.build("bus", [M["bus_paint"], M["car_glass"], M["car_trim"], M["tire"], M["rim"], M["bus_sign"],
                            M["headlight"], M["taillight"]], fix_normals=True)


def tower_mesh(rnd, M, w, d, h):
    mb = rf.MeshBuilder()
    mb.box(-w / 2, -d / 2, 0, w / 2, d / 2, h * 0.72, 0)
    s = rnd.uniform(0.62, 0.85)
    mb.box(-w * s / 2, -d * s / 2, h * 0.72, w * s / 2, d * s / 2, h * 0.92, 0)
    mb.box(-w * s * 0.6 / 2, -d * s * 0.6 / 2, h * 0.92, w * s * 0.6 / 2, d * s * 0.6 / 2, h, 1)
    return mb.build("tower", [M["glass_tower"], M["trim"]], fix_normals=True)


def _merge_objects(obs, name):
    """Join objects (with their locations) into one mesh; their material lists must match."""
    bm = bmesh.new()
    mats = None
    for ob in obs:
        me = ob.data.copy()
        me.transform(Matrix.Translation(ob.location))
        bm.from_mesh(me)
        mats = mats or list(ob.data.materials)
        bpy.data.meshes.remove(me)
    out = bpy.data.meshes.new(name)
    bm.to_mesh(out)
    bm.free()
    for m in mats or []:
        out.materials.append(m)
    for ob in obs:
        bpy.data.objects.remove(ob, do_unlink=True)
    return out


# ---------------------------------------------------------------- the crush field (geometry nodes)

CRUSH_INPUTS = ("Center X", "Center Y", "Yaw", "Axis X", "Axis Y", "LogH", "Band", "Push")


def crush_node_group():
    """Instances every point (attributes kind, yaw, scale, rad, hgt, tip) and knocks over those the subject's
    footprint has reached; see the module docstring."""
    ng = bpy.data.node_groups.new("rf_crush_field", "GeometryNodeTree")
    io = ng.interface
    io.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    io.new_socket("Instances", in_out="INPUT", socket_type="NodeSocketCollection")
    defaults = {"Center X": 0.0, "Center Y": 0.0, "Yaw": 0.0, "Axis X": 0.42, "Axis Y": 0.59, "LogH": -40.0,
                "Band": 0.3, "Push": 0.8}
    for name in CRUSH_INPUTS:
        s = io.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
        s.default_value = defaults[name]
    io.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    nt = rf.NodeTree(ng)
    gi = nt.node("NodeGroupInput")
    go = nt.node("NodeGroupOutput")

    def attr(name, typ="FLOAT"):
        n = nt.node("GeometryNodeInputNamedAttribute", data_type=typ)
        n.inputs["Name"].default_value = name
        return n.outputs["Attribute"]

    pos = nt.node("GeometryNodeInputPosition")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(pos.outputs["Position"], sep.inputs[0])
    qx = nt.math("SUBTRACT", sep.outputs["X"], gi.outputs["Center X"])
    qy = nt.math("SUBTRACT", sep.outputs["Y"], gi.outputs["Center Y"])
    cyaw, syaw = nt.math("COSINE", gi.outputs["Yaw"]), nt.math("SINE", gi.outputs["Yaw"])
    lx = nt.math("ADD", nt.math("MULTIPLY", qx, cyaw), nt.math("MULTIPLY", qy, syaw))
    ly = nt.math("SUBTRACT", nt.math("MULTIPLY", qy, cyaw), nt.math("MULTIPLY", qx, syaw))
    ec = nt.math("SQRT", nt.math("ADD", nt.math("POWER", nt.math("DIVIDE", lx, gi.outputs["Axis X"]), 2.0),
                                 nt.math("POWER", nt.math("DIVIDE", ly, gi.outputs["Axis Y"]), 2.0)))
    q = nt.math("MAXIMUM", nt.math("SQRT", nt.math("ADD", nt.math("MULTIPLY", qx, qx), nt.math("MULTIPLY", qy, qy))),
                1e-3)
    rad, hgt, tip = attr("rad"), attr("hgt"), attr("tip")
    en = nt.math("MULTIPLY", ec, nt.math("MAXIMUM", nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", rad, q)), 0.02))
    log_en = nt.math("LOGARITHM", nt.math("MAXIMUM", en, 0.01), 2.0)
    u = nt.math("DIVIDE", nt.math("SUBTRACT", gi.outputs["LogH"], log_en), gi.outputs["Band"], clamp=True)
    us = nt.math("MULTIPLY", nt.math("MULTIPLY", u, u), nt.math("SUBTRACT", 3.0, nt.math("MULTIPLY", u, 2.0)))
    theta = nt.math("MULTIPLY", us, tip)
    hx, hy = nt.math("DIVIDE", qx, q), nt.math("DIVIDE", qy, q)
    axis = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", hy, -1.0), axis.inputs["X"])
    nt.links.new(hx, axis.inputs["Y"])
    rq = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", hx, rad), rq.inputs["X"])
    nt.links.new(nt.math("MULTIPLY", hy, rad), rq.inputs["Y"])
    pivot = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(pos.outputs["Position"], pivot.inputs[0])
    nt.links.new(rq.outputs["Vector"], pivot.inputs[1])
    push = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(rq.outputs["Vector"], push.inputs[0])
    nt.links.new(nt.math("MULTIPLY", us, gi.outputs["Push"]), push.inputs["Scale"])
    # gone once the subject covers the item, fallen length and all
    ef = nt.math("MULTIPLY", ec, nt.math("ADD", 1.0, nt.math("DIVIDE", nt.math("ADD", rad, hgt), q)))
    gone = nt.math("GREATER_THAN", gi.outputs["LogH"],
                   nt.math("ADD", nt.math("LOGARITHM", nt.math("MAXIMUM", ef, 0.01), 2.0), 0.05))

    geo = gi.outputs["Geometry"]
    for name, sock, typ in (("tip_ang", theta, "FLOAT"), ("tip_axis", axis.outputs["Vector"], "FLOAT_VECTOR"),
                            ("tip_pivot", pivot.outputs["Vector"], "FLOAT_VECTOR"),
                            ("tip_push", push.outputs["Vector"], "FLOAT_VECTOR")):
        st = nt.node("GeometryNodeStoreNamedAttribute", data_type=typ, domain="POINT")
        nt.links.new(geo, st.inputs["Geometry"])
        st.inputs["Name"].default_value = name
        nt.links.new(sock, st.inputs["Value"])
        geo = st.outputs["Geometry"]
    dele = nt.node("GeometryNodeDeleteGeometry", domain="POINT")
    nt.links.new(geo, dele.inputs["Geometry"])
    nt.links.new(gone, dele.inputs["Selection"])
    ci = nt.node("GeometryNodeCollectionInfo", transform_space="ORIGINAL")
    nt.links.new(gi.outputs["Instances"], ci.inputs["Collection"])
    ci.inputs["Separate Children"].default_value = True
    ci.inputs["Reset Children"].default_value = True
    iop = nt.node("GeometryNodeInstanceOnPoints")
    nt.links.new(dele.outputs["Geometry"], iop.inputs["Points"])
    nt.links.new(ci.outputs["Instances"], iop.inputs["Instance"])
    iop.inputs["Pick Instance"].default_value = True
    nt.links.new(attr("kind", "INT"), iop.inputs["Instance Index"])
    eul = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(attr("yaw"), eul.inputs["Z"])
    e2r = nt.node("FunctionNodeEulerToRotation")
    nt.links.new(eul.outputs["Vector"], e2r.inputs["Euler"])
    nt.links.new(e2r.outputs["Rotation"], iop.inputs["Rotation"])
    sc = nt.node("ShaderNodeCombineXYZ")
    for k in ("X", "Y", "Z"):
        nt.links.new(attr("scale"), sc.inputs[k])
    nt.links.new(sc.outputs["Vector"], iop.inputs["Scale"])
    tr = nt.node("GeometryNodeTranslateInstances")
    nt.links.new(iop.outputs["Instances"], tr.inputs["Instances"])
    nt.links.new(attr("tip_push", "FLOAT_VECTOR"), tr.inputs["Translation"])
    tr.inputs["Local Space"].default_value = False
    aa = nt.node("FunctionNodeAxisAngleToRotation")
    nt.links.new(attr("tip_axis", "FLOAT_VECTOR"), aa.inputs["Axis"])
    nt.links.new(attr("tip_ang"), aa.inputs["Angle"])
    ro = nt.node("GeometryNodeRotateInstances")
    nt.links.new(tr.outputs["Instances"], ro.inputs["Instances"])
    nt.links.new(aa.outputs["Rotation"], ro.inputs["Rotation"])
    piv = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(attr("tip_pivot", "FLOAT_VECTOR"), piv.inputs[0])
    nt.links.new(attr("tip_push", "FLOAT_VECTOR"), piv.inputs[1])
    nt.links.new(piv.outputs["Vector"], ro.inputs["Pivot Point"])
    ro.inputs["Local Space"].default_value = False
    nt.links.new(ro.outputs["Instances"], go.inputs["Geometry"])
    return ng


def crush_field(collection, variants, items, spot, yaw_deg, footprint):
    """One point per item, the crush node group on top. items: dicts with x, y, kind, yaw, scale, rad, hgt, tip."""
    me = bpy.data.meshes.new("crushables")
    me.vertices.add(len(items))
    me.vertices.foreach_set("co", np.array([(it["x"], it["y"], it.get("z", 0.0)) for it in items], np.float32).ravel())
    for name, typ, key in (("kind", "INT", "kind"), ("yaw", "FLOAT", "yaw"), ("scale", "FLOAT", "scale"),
                           ("rad", "FLOAT", "rad"), ("hgt", "FLOAT", "h"), ("tip", "FLOAT", "tip")):
        a = me.attributes.new(name, typ, "POINT")
        vals = [it.get(key, 1.0) for it in items]
        a.data.foreach_set("value", np.array(vals, np.int32 if typ == "INT" else np.float32))
    me.update()
    ob = rf.add_object("crush_field", me, collection)
    mod = ob.modifiers.new("Crush", "NODES")
    mod.node_group = crush_node_group()
    sockets = {}
    for item in mod.node_group.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT":
            sockets[item.name] = item.identifier
    mod[sockets["Instances"]] = variants.col
    vals = {"Center X": spot[0], "Center Y": spot[1], "Yaw": math.radians(-yaw_deg), "Axis X": footprint[0],
            "Axis Y": footprint[1], "LogH": -40.0, "Band": 0.3, "Push": 0.8}
    for k, v in vals.items():
        mod[sockets[k]] = float(v)
    return ob, mod, sockets


# ---------------------------------------------------------------- the world

def build(spec):
    W = spec["world"]
    seed = W.get("seed", 7)
    rnd = random.Random(seed)
    scene = bpy.context.scene
    tname = W.get("time", "golden")
    T = dict(TIMES[tname])
    if "sun" in W:
        T["heading"] = W["sun"].get("heading", T["heading"])
        T["elevation"] = W["sun"].get("elevation", T["elevation"])
    night = tname == "night"
    yaw_deg = W.get("subject_yaw", 200.0)
    foot = W.get("footprint", [0.42, 0.59])
    town = {"half_x": 1300.0, "half_y": 1700.0, **W.get("town", {})}

    col_hero = rf.new_collection("hero")
    col_ground = rf.new_collection("ground")
    col_far = rf.new_collection("far")
    col_clouds = rf.new_collection("clouds")
    inst = bpy.data.collections.new("street_instances")
    scene.collection.children.link(inst)
    bpy.context.view_layer.layer_collection.children[inst.name].exclude = True

    # light, sky, haze
    sun_dir = look.sun_vector(T["heading"], max(T["elevation"], 2.0) if not night else 35.0)
    world = look.setup_sky(scene, T["heading"], T["elevation"], gain=T["gain"])
    if night:
        world.node_tree.nodes["StarMix"].outputs[0].default_value = 0.6
        sun = look.add_sun(col_hero, 120.0, 35.0, energy=T["energy"], color=T["color"], angle_deg=0.6)
    else:
        sun = look.add_sun(col_hero, T["heading"], T["elevation"], energy=T["energy"], color=T["color"])
    look.init_haze(scene, tuple(sun_dir), dist=6000.0, hmax=0.82)
    look.add_bloom(scene)
    M = make_materials(T)

    mover = bpy.data.objects.new("WorldMover", None)
    col_ground.objects.link(mover)
    ground_objects = []

    def on_mover(ob):
        ob.parent = mover
        ground_objects.append(ob)
        return ob

    V = Variants(inst)
    items = []

    def item(kind, x, y, yaw, w, d, h, cls, tip=1.3, scale=1.0, name="", z=None):
        qx, qy = x - SPOT[0], y - SPOT[1]
        q = math.hypot(qx, qy) + 1e-9
        ux, uy = qx / q, qy / q
        c, s = math.cos(yaw), math.sin(yaw)
        # support distance of the w x d rectangle (rotated by yaw) in the direction of the subject
        rad = abs(ux * c + uy * s) * w * scale / 2 + abs(-ux * s + uy * c) * d * scale / 2
        if z is None:
            z = {"tree": 0.15, "lamp": 0.15, "prop": 0.15, "signal": 0.15, "house": LAWN, "tower": LAWN,
                 "landmark": LAWN}.get(cls, 0.0)
        items.append({"kind": kind, "x": x, "y": y, "z": z, "yaw": yaw, "scale": scale, "rad": rad, "h": h * scale,
                      "tip": tip, "cls": cls, "w": w * scale, "d": d * scale, "name": name})

    # ---------------- roads, curbs, sidewalks (real geometry near Main Street)
    y_lo, y_hi = MAIN_Y
    mb = rf.MeshBuilder()
    mb.box(-ROAD, y_lo, -0.05, ROAD, y_hi, 0.0, 0)
    road = on_mover(rf.add_object("main_street", mb.build("main_street", [M["asphalt"]]), col_ground))
    xs = [y for y in cross_ys(y_lo + 20, y_hi - 20)]
    mb = rf.MeshBuilder()
    for yc in xs:
        for sx in (-1, 1):
            x0, x1 = sorted((sx * ROAD, sx * (SIDE0 + SIDE_STEP * 2)))
            mb.box(x0, yc - XROAD, -0.05, x1, yc + XROAD, 0.0, 0)
    on_mover(rf.add_object("cross_streets", mb.build("cross_streets", [M["asphalt_x"]]), col_ground))
    mb_w, mb_c = rf.MeshBuilder(), rf.MeshBuilder()
    edges = [y_lo] + sum([[yc - XROAD, yc + XROAD] for yc in xs], []) + [y_hi]
    for k in range(0, len(edges), 2):
        a, b = edges[k], edges[k + 1]
        for sx in (-1, 1):
            x0, x1 = sorted((sx * (ROAD + 0.25), sx * FRONT))
            mb_w.box(x0, a, 0.0, x1, b, 0.15, 0)
            c0, c1 = sorted((sx * ROAD, sx * (ROAD + 0.25)))
            mb_c.box(c0, a, 0.0, c1, b, 0.16, 0)
    for yc in xs:                                     # cross-street sidewalks out to the first side street
        for sx in (-1, 1):
            for sy in (-1, 1):
                x0, x1 = sorted((sx * FRONT, sx * (SIDE0 + SIDE_STEP * 2)))
                y0, y1 = sorted((yc + sy * (XROAD + 0.2), yc + sy * XFRONT))
                mb_w.box(x0, y0, 0.0, x1, y1, 0.15, 0)
                c0, c1 = sorted((yc + sy * XROAD, yc + sy * (XROAD + 0.2)))
                mb_c.box(x0, c0, 0.0, x1, c1, 0.16, 0)
    on_mover(rf.add_object("sidewalks", mb_w.build("sidewalks", [M["walk"]]), col_ground))
    on_mover(rf.add_object("curbs", mb_c.build("curbs", [M["curb"]]), col_ground))

    # ground plane: flat to 21 km, then sinking under the mountains' foothills
    n = 72
    gx = np.linspace(-27000.0, 27000.0, n)
    GX, GY = np.meshgrid(gx, gx)
    R = np.hypot(GX, GY)
    GZ = LAWN - np.clip((R - 21000.0) / 4000.0, 0, 1) * 60.0
    verts = np.stack([GX.ravel(), GY.ravel(), GZ.ravel()], 1)
    idx = np.arange(n * n).reshape(n, n)
    faces = np.concatenate([np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:]], -1).reshape(-1, 3),
                            np.stack([idx[:-1, :-1], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 3)])
    land_me = nature.mesh_from_arrays("land", verts, faces, [land_material(town["half_x"], town["half_y"])],
                                      smooth=False)
    land = on_mover(rf.add_object("land", land_me, col_far))

    # ---------------- variants
    k_tree = [V.add("tree", tree_mesh(rnd, M, h)) for h in (8.5, 11.0, 13.0)]
    tree_h = [8.5, 11.0, 13.0]
    k_lamp = V.add("lamp", lamp_mesh(M))
    k_signal = V.add("signal", signal_mesh(M))
    k_hydrant = V.add("hydrant", hydrant_mesh(M))
    k_bench = V.add("bench", bench_mesh(M))
    k_can = V.add("can", can_mesh(M))
    k_meter = V.add("meter", meter_mesh(M))
    k_news = V.add("newsbox", newsbox_mesh(M))
    k_mail = V.add("mailbox", mailbox_mesh(M))
    k_shelter = V.add("shelter", shelter_mesh(M))
    k_planter = V.add("planter", planter_mesh(rnd, M))
    car_meshes = {k: car_mesh(M, k) for k in CAR_KINDS}
    k_car = {k: V.add(f"car_{k}", car_meshes[k]) for k in CAR_KINDS}
    bus_me = bus_mesh(M)
    k_bus = V.add("bus", bus_me)
    houses = []
    for k in range(10):
        me, w, d, h = house_mesh(rnd, M, k)
        houses.append((V.add(f"house{k}", me), w, d, h))
    church_me, cw, cd, ch, (ctx, cty) = church_mesh(M)
    k_church = V.add("church", church_me)

    # ---------------- Main Street buildings
    refs = {}
    hero = {}
    church_lot = (FRONT, Y0 + XFRONT, FRONT + cw + 4.0, Y0 + XFRONT + cd + 2.0)
    ys_ = cross_ys(y_lo - BLOCK, y_hi)
    blocks = [(a + XFRONT, b - XFRONT) for a, b in zip(ys_[:-1], ys_[1:]) if b - XFRONT > y_lo and a + XFRONT < y_hi]
    for side in (-1, 1):
        for (b0, b1) in blocks:
            y = b0
            while y < b1 - 5.0:
                w = min(rnd.uniform(7.0, 14.0), b1 - y)
                if b1 - (y + w) < 5.0:
                    w = b1 - y
                cy_ = y + w / 2
                if side > 0 and church_lot[1] - 1 < cy_ < church_lot[3] + 1:
                    y += w
                    continue
                dist = abs(cy_)
                d = rnd.uniform(16.0, 28.0)
                near = dist < 160
                storeys = rnd.choice((1, 2, 2, 3, 3, 4) if near else (1, 1, 2, 2, 3))
                if side < 0 and -75.0 < cy_ < 14.0:
                    storeys = 1                    # keep the low sun on the subject spot
                pitched = storeys <= 2 and rnd.random() < 0.25
                me, h, props = shop_mesh(rnd, M, w, d, storeys, pitched)
                k = V.add("shop", me, **props)
                x = side * (FRONT + d / 2)
                yaw = math.radians(-90.0 if side > 0 else 90.0)
                item(k, x, cy_, yaw, w, d, h, "building", tip=1.25, name=f"shop {storeys}st")
                y += w
    # the church on the corner north-east of the spot, its tower on the street corner
    cx_c = FRONT + cw / 2 + 0.5
    cy_c = Y0 + XFRONT + cd / 2 + 3.5
    item(k_church, cx_c, cy_c, 0.0, cw, cd, ch, "church", tip=1.2, name="church")
    steeple_xy = (cx_c + ctx, cy_c + cty)
    hero["church"] = (cx_c, cy_c)
    hero["steeple_top"] = (steeple_xy[0], steeple_xy[1], 50.0)
    refs["steeple"] = {"h": 50.0, "pos": (steeple_xy[0], steeple_xy[1], 0.0), "label": "CHURCH STEEPLE"}

    # ---------------- street furniture along Main Street
    for side in (-1, 1):
        xc = side * (ROAD + 0.9)
        for (b0, b1) in blocks:
            for y in np.arange(b0 + 6.0, b1 - 4.0, 15.0):          # small street trees, so the street stays open
                if abs(y - SPOT[1]) < 4.0 and side > 0:
                    continue
                sc = rnd.uniform(0.72, 0.88)
                item(k_tree[0], xc, y + rnd.uniform(-1, 1), rnd.uniform(0, 6.28), 0.6, 0.6, tree_h[0], "tree", tip=1.45,
                     scale=sc)
            for y in np.arange(b0 + 1.5, b1, 25.0):
                item(k_lamp, side * (ROAD + 0.45), y, 0.0, 0.4, 0.4, 5.2, "lamp", tip=1.5)
            for y in np.arange(b0 + 3.0, b1 - 2.0, 6.5):
                if rnd.random() < 0.7 and abs(y - SPOT[1]) > 6:
                    item(k_meter, side * (ROAD + 0.4), y + 0.2, 0.0, 0.2, 0.2, 1.5, "prop", tip=1.5)
            for _ in range(rnd.randint(1, 3)):
                y = rnd.uniform(b0 + 4, b1 - 4)
                kind = rnd.choice((k_bench, k_can, k_can, k_news, k_planter))
                item(kind, side * (FRONT - 1.0), y, math.radians(90.0 if side > 0 else -90.0), 1.8, 0.6, 1.0, "prop",
                     tip=1.5)
    for yc in xs:
        for sx in (-1, 1):
            for sy in (-1, 1):
                item(k_signal, sx * (ROAD + 0.5), yc + sy * (XROAD + 0.6), 0.0 if sx > 0 else math.pi, 0.4, 0.4, 7.0,
                     "signal", tip=1.4)
            box_k = k_mail if rnd.random() < 0.5 else k_news
            item(box_k, sx * (ROAD + 1.4), yc - (XROAD + 2.2), 0.0, 0.6, 0.6, 1.2, "prop")
        for sx in (-1, 1):
            item(k_hydrant, sx * (ROAD + 0.55), yc - XFRONT - 4.0, 0.0, 0.3, 0.3, 0.76, "prop", tip=1.5)
    # the hero hydrant beside the spot, and the bus stop south of it
    hydrant_xy = (ROAD + 0.55, -1.3)
    item(k_hydrant, hydrant_xy[0], hydrant_xy[1], math.radians(10.0), 0.3, 0.3, 0.76, "prop", tip=1.5, name="hydrant")
    hero["hydrant"] = (hydrant_xy[0], hydrant_xy[1], 0.0)
    refs["hydrant"] = {"h": 0.76, "pos": hero["hydrant"], "label": "FIRE HYDRANT"}
    item(k_shelter, -(FRONT - 1.1), -30.0, math.radians(90.0), 4.2, 1.6, 2.6, "prop", tip=1.4)

    # ---------------- parked cars, the bus
    car_list = list(CAR_KINDS)
    hero_cars = {"car_n": (SPOT[0], 7.6), "car_s": (SPOT[0], -7.9)}
    for side in (-1, 1):
        xc = side * (ROAD - PARK / 2)
        for (b0, b1) in blocks:
            for y in np.arange(b0 + 9.0, b1 - 8.0, 6.6):
                if (side > 0 and -12.0 < y < 12.0) or (side < 0 and -41.0 < y < -19.0):
                    continue                          # the subject's space and the bus stop
                if rnd.random() < 0.72:
                    kd = rnd.choice(car_list)
                    item(k_car[kd], xc, y + rnd.uniform(-0.6, 0.6), 0.0 if side > 0 else math.pi,
                         CAR_KINDS[kd][1], CAR_KINDS[kd][0], CAR_KINDS[kd][4], "car", tip=1.9)
    for key, (x, y) in hero_cars.items():
        kd = "sedan" if key == "car_n" else "suv"
        item(k_car[kd], x, y, 0.0, CAR_KINDS[kd][1], CAR_KINDS[kd][0], CAR_KINDS[kd][4], "car", tip=1.9, name=key)
        hero[key] = (x, y, 0.0)
    refs["car"] = {"length": CAR_KINDS["suv"][0], "h": CAR_KINDS["suv"][4], "pos": hero["car_s"], "label": "CAR"}
    bus_xy = (-(ROAD - PARK / 2) - 0.1, -30.0)
    item(k_bus, bus_xy[0], bus_xy[1], math.pi, 2.55, 12.2, 3.35, "bus", tip=1.6, name="bus")
    hero["bus"] = (bus_xy[0], bus_xy[1], 0.0)
    refs["bus"] = {"length": 12.2, "h": 3.35, "pos": hero["bus"], "label": "CITY BUS"}

    # ---------------- houses, yard trees and driveway cars over the rest of town
    dt = W.get("downtown", {"at": [-1450.0, 2350.0], "towers": 34, "supertall": True})
    keep_out = []
    if dt:
        keep_out.append((*dt.get("at", [-1450.0, 2350.0]), 760.0))
        keep_out.append((*dt.get("supertall_at", [-900.0, 1500.0]), 140.0))
    for yc in cross_ys(-town["half_y"], town["half_y"]):
        for sy in (-1, 1):
            row_y = yc + sy * (XFRONT + 14.0)
            # lots along both sides of each cross street, from behind the Main Street shops to the town edge
            for sx in (-1, 1):
                x = 52.0
                while x < town["half_x"]:
                    side_d = abs(((x - SIDE0) % SIDE_STEP) - SIDE_STEP / 2)
                    if side_d > SIDE_STEP / 2 - 12.0:
                        x += 14.0
                        continue
                    lot = rnd.uniform(15.0, 21.0)
                    kh, w, d, h = houses[rnd.randrange(len(houses))]
                    px = sx * (x + lot / 2)
                    if abs(row_y) < MAIN_Y[1] and abs(px) < 62.0:
                        x += lot
                        continue
                    if sx > 0 and church_lot[0] - 6 < px < church_lot[2] + 6 and \
                            church_lot[1] - 6 < row_y < church_lot[3] + 20:
                        x += lot
                        continue
                    if any(math.hypot(px - cx, row_y - cy) < cr for cx, cy, cr in keep_out):
                        x += lot
                        continue
                    yaw = 0.0 if sy > 0 else math.pi
                    item(kh, px + rnd.uniform(-1, 1), row_y + sy * rnd.uniform(0, 3), yaw, w, d, h, "house", tip=1.3)
                    if rnd.random() < 0.65:
                        kt = rnd.randrange(3)
                        item(k_tree[kt], px + rnd.uniform(-lot / 2, lot / 2), row_y + sy * rnd.uniform(14, 22),
                             rnd.uniform(0, 6.28), 0.6, 0.6, tree_h[kt], "tree", tip=1.45, scale=rnd.uniform(0.8, 1.15),
                             z=LAWN)
                    if rnd.random() < 0.45:
                        kd = rnd.choice(car_list)
                        item(k_car[kd], px + sx * (w / 2 + 2.0), row_y - sy * 3.5, rnd.choice((0.0, math.pi)),
                             CAR_KINDS[kd][1], CAR_KINDS[kd][0], CAR_KINDS[kd][4], "car", tip=1.9, z=LAWN)
                    x += lot
    # street trees along the cross streets near Main Street
    for yc in xs:
        for sx in (-1, 1):
            for sy in (-1, 1):
                for x in np.arange(FRONT + 30.0, SIDE0 + SIDE_STEP * 2, 15.0):
                    kt = rnd.randrange(3)
                    item(k_tree[kt], sx * x, yc + sy * (XROAD + 0.9), rnd.uniform(0, 6.28), 0.6, 0.6, tree_h[kt],
                         "tree", tip=1.45, scale=0.9)

    # ---------------- downtown on the horizon, with a supertall at true height
    landmark_tops = {}
    # (dt: the downtown spec, read above with the houses)
    if dt:
        dx, dy = dt.get("at", [-1450.0, 2350.0])
        for k in range(dt.get("towers", 34)):
            a = rnd.uniform(0, 2 * math.pi)
            r = 650.0 * math.sqrt(rnd.random())
            w, d = rnd.uniform(28, 55), rnd.uniform(28, 55)
            h = rnd.uniform(70, 300) * (1.25 - r / 900.0)
            kt = V.add("tower", tower_mesh(rnd, M, w, d, h), tower=1.0, lit=0.0)
            item(kt, dx + r * math.cos(a), dy + r * math.sin(a), rnd.uniform(0, 1.5), w, d, h, "tower", tip=1.2)
        if dt.get("supertall", True):
            tmp = bpy.data.collections.new("tmp_landmark")
            scene.collection.children.link(tmp)
            segs = landmarks.supertall(tmp, (0.0, 0.0, 0.0))
            me = _merge_objects(segs, "supertall")
            bpy.data.collections.remove(tmp)
            ks = V.add("supertall", me, tower=1.0, lit=0.0, shattered=0.0)
            sx_, sy_ = dt.get("supertall_at", [-900.0, 1500.0])
            item(ks, sx_, sy_, 0.3, 60.0, 60.0, 828.0, "landmark", tip=1.15, name="supertall")
            landmark_tops["supertall"] = (sx_, sy_, 828.0)
            refs["supertall"] = {"h": 828.0, "pos": (sx_, sy_, 0.0), "label": "TALLEST BUILDING ON EARTH"}

    crush_ob, crush_mod, sockets = crush_field(col_ground, V, items, SPOT, yaw_deg, foot)
    on_mover(crush_ob)

    # ---------------- mountains and clouds
    mt = {"inner": 22000.0, "outer": 80000.0, "base_height": 3300.0,
          "massifs": [[-12000.0, 25500.0, 8849.0, 5200.0, "EVEREST HEIGHT"]], **W.get("mountains", {})}
    massifs = [(m[0], m[1], m[2], m[3]) for m in mt["massifs"]]
    mtn, mtn_max, summits = nature.mountain_range(col_far, seed=seed, inner=mt["inner"], outer=mt["outer"], res=400,
                                                  base_height=mt["base_height"], massifs=massifs)
    on_mover(mtn)
    for m, s in zip(mt["massifs"], summits):
        landmark_tops[(m[4] if len(m) > 4 else "peak").lower()] = s
    if summits:
        label = mt["massifs"][0][4] if len(mt["massifs"][0]) > 4 else "PEAK"
        refs["everest"] = {"h": summits[0][2], "pos": summits[0], "label": label}
    cl = W.get("clouds", {"base": 1300.0, "top": 1900.0, "coverage": 0.3, "extent": 30000.0})
    cloud_obs = []
    if cl:
        cloud_obs = nature.cloud_field(col_clouds, seed=seed + 3, base=cl.get("base", 1300.0),
                                       top=cl.get("top", 1900.0), extent=cl.get("extent", 30000.0), tile=3000.0,
                                       coverage=cl.get("coverage", 0.3), near=7000.0, mid=16000.0,
                                       material=cloud_material())
        for ob in cloud_obs:
            on_mover(ob)
            try:
                ob.visible_shadow = False
            except AttributeError:
                pass

    # ---------------- people, 'you', the traffic
    pm = P.person_materials(M)
    poses = {p: P.person_mesh(pm, p, name=f"person_{p}") for p in ("stand", "phone", "film")}
    shirts = [(0.6, 0.05, 0.03), (0.05, 0.2, 0.5), (0.8, 0.75, 0.6), (0.1, 0.35, 0.15), (0.75, 0.45, 0.05),
              (0.02, 0.02, 0.02), (0.55, 0.55, 0.55), (0.45, 0.1, 0.35)]
    people = []
    fps, t_end = spec["fps"], spec["render_until"]
    frames_end = int(round(t_end * fps)) + 1
    for k in range(W.get("crowd", 26)):
        side = rnd.choice((-1, 1))
        y0 = rnd.uniform(-90.0, 110.0)
        if abs(y0) < 5.0:
            y0 += 10.0
        x0 = side * rnd.uniform(ROAD + 1.6, FRONT - 1.5)
        pose = rnd.choice(("stand", "phone", "stand"))
        ob = on_mover(rf.add_object(f"person_{k}", poses[pose], col_ground, (x0, y0, 0.15)))
        ob.color = (*rnd.choice(shirts), 1.0)
        walk = rnd.random() < 0.6
        if walk:
            v = rnd.choice((-1, 1)) * rnd.uniform(1.1, 1.5)
            ob.rotation_euler = (0.0, 0.0, 0.0 if v > 0 else math.pi)
            ob.keyframe_insert("location", frame=1)
            ob.location = (x0, y0 + v * t_end, 0.15)
            ob.keyframe_insert("location", frame=frames_end)
            rf.set_interpolation(ob, "LINEAR", "location")
        else:
            ob.rotation_euler = (0.0, 0.0, rnd.uniform(0, 2 * math.pi))
        people.append(ob)
    you_xy = (ROAD + 1.4, 5.0)
    you = on_mover(rf.add_object("you", poses["film"], col_ground, (you_xy[0], you_xy[1], 0.15)))
    you.color = (0.85, 0.2, 0.05, 1.0)
    you.rotation_euler = (0.0, 0.0, math.atan2(-(SPOT[0] - you_xy[0]), SPOT[1] - you_xy[1]))   # facing it, phone up
    hero["you"] = you
    hero["you_height"] = 1.76
    refs["you"] = {"h": 1.76, "pos": (you_xy[0], you_xy[1], 0.15), "label": "YOU"}
    traffic = []
    lamp_lights = []
    if night:                          # the street lamps near the spot really light the street (and the subject)
        for it in items:
            if it["cls"] == "lamp" and math.hypot(it["x"] - SPOT[0], it["y"] - SPOT[1]) < 70.0:
                ld = bpy.data.lights.new(f"lamp_light_{len(lamp_lights)}", "POINT")
                ld.energy = 450.0
                ld.color = (1.0, 0.72, 0.42)
                ld.shadow_soft_size = 0.25
                lo = on_mover(bpy.data.objects.new(ld.name, ld))
                lo.location = (it["x"], it["y"], 4.75)
                col_ground.objects.link(lo)
                lamp_lights.append(lo)
    if W.get("traffic", True):
        # southbound only (the bus holds the northbound lane at its stop), all past the spot before it gets big
        lanes = [(-1.75, -1, 25.0), (-1.75, -1, 72.0), (-1.75, -1, 140.0)]
        for k, (x, dirn, y0) in enumerate(lanes):
            kd = car_list[k % len(car_list)]
            ob = on_mover(rf.add_object(f"traffic_{k}", car_meshes[kd], col_ground, (x, y0, 0.0)))
            ob.rotation_euler = (0.0, 0.0, 0.0 if dirn > 0 else math.pi)
            v = 12.0
            ob.keyframe_insert("location", frame=1)
            ob.location = (x, y0 + dirn * v * t_end, 0.0)
            ob.keyframe_insert("location", frame=frames_end)
            rf.set_interpolation(ob, "LINEAR", "location")
            traffic.append(ob)
        for k, (yc, dirn, x0) in enumerate(((Y0 - 2.5, 1, -120.0), (Y0 + 2.5, -1, 150.0))):
            kd = car_list[(k + 2) % len(car_list)]
            ob = on_mover(rf.add_object(f"traffic_x{k}", car_meshes[kd], col_ground, (x0, yc, 0.0)))
            ob.rotation_euler = (0.0, 0.0, -math.pi / 2 if dirn > 0 else math.pi / 2)
            ob.keyframe_insert("location", frame=1)
            ob.location = (x0 + dirn * 11.0 * t_end, yc, 0.0)
            ob.keyframe_insert("location", frame=frames_end)
            rf.set_interpolation(ob, "LINEAR", "location")
            traffic.append(ob)

    # the default view: low on the road south of the spot, looking up the street
    cam = {"location": (SPOT[0] - 0.25, SPOT[1] - 1.1, 0.16), "target": (SPOT[0] - 0.6, SPOT[1] + 6.0, 0.35),
           "lens": 24.0}
    tracked = ("building", "church", "bus", "landmark", "tower", "house", "car", "tree")
    crushables = [dict(it) for it in items if it["cls"] in tracked]
    print(f"[street] {len(items)} crushable instances from {len(V.obs)} variants; {len(crushables)} tracked; "
          f"{len(people)} people, {len(traffic)} moving cars; mountains to {mtn_max:.0f} m; "
          f"{len(cloud_obs)} cloud tiles")
    return {
        "scene": scene, "world": world, "sun": sun, "sun_dir": tuple(sun_dir), "time": tname, "night": night,
        "collections": {"hero": col_hero, "ground": col_ground, "far": col_far, "clouds": col_clouds,
                        "instances": inst},
        "mover": mover, "ground_objects": ground_objects, "camera": cam,
        "spot": SPOT, "spot_yaw": yaw_deg, "M": M,
        "crush": {"object": crush_ob, "modifier": crush_mod, "sockets": sockets, "footprint": foot},
        "crushables": crushables, "refs": refs, "hero": hero, "people": people, "traffic": traffic,
        "lamp_lights": lamp_lights,
        "landmarks": landmark_tops,
        "clouds": {"base": cl.get("base", 1300.0) if cl else None, "top": cl.get("top", 1900.0) if cl else None,
                   "objects": cloud_obs},
        "mountains": {"object": mtn, "max": float(mtn_max), "summits": summits},
        "land": land, "road": road,
    }
