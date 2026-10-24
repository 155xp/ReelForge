"""Facade and roof materials for the city worlds (golden-hour light).

Every material works in object space (metres from the object's origin, object-space normals), so buildings keep
their windows when the effect tilts, sinks or breaks them. Window cells get a random tint and a few glow warm
(lit rooms read well in the low evening light). Objects can carry:
  obj["lit"]      0..1   fraction of windows lit (default from the material)
  obj["glitch"]   0..1   magenta 'missing texture' flash (rf_common wrapper)
"""
import bpy

import rf_common as rf

WALLS = [(0.42, 0.16, 0.10), (0.58, 0.30, 0.18), (0.66, 0.52, 0.36), (0.80, 0.74, 0.62),
         (0.50, 0.50, 0.50), (0.74, 0.60, 0.34), (0.68, 0.46, 0.40), (0.62, 0.64, 0.68),
         (0.30, 0.33, 0.37), (0.85, 0.82, 0.76)]
WARM = (1.0, 0.56, 0.24, 1.0)


def _obj_space(nt):
    tc = nt.node("ShaderNodeTexCoord")
    pos = nt.node("ShaderNodeSeparateXYZ")
    nrm = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], pos.inputs[0])
    nt.links.new(tc.outputs["Normal"], nrm.inputs[0])
    return pos, nrm


def _attr(nt, name):
    return nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=name).outputs["Fac"]


def _windows(nt, pos, nrm, cell_w, cell_h, frac_x, frac_y, z_min=4.0):
    """(window mask, cell id, wall side) for vertical faces."""
    isx = nt.math("GREATER_THAN", nt.math("ABSOLUTE", nrm.outputs["X"]), 0.5)
    u = nt.math("ADD", nt.math("MULTIPLY", pos.outputs["X"], nt.math("SUBTRACT", 1.0, isx)),
                nt.math("MULTIPLY", pos.outputs["Y"], isx))
    z = pos.outputs["Z"]
    vert = nt.math("LESS_THAN", nt.math("ABSOLUTE", nrm.outputs["Z"]), 0.5)
    fx = nt.math("FRACT", nt.math("DIVIDE", u, cell_w))
    fy = nt.math("FRACT", nt.math("DIVIDE", z, cell_h))
    lo_x = (1.0 - frac_x) / 2
    wx = nt.band(fx, lo_x, 1.0 - lo_x)
    wy = nt.band(fy, 1.0 - frac_y - 0.08, 0.92)
    win = nt.math("MULTIPLY", nt.math("MULTIPLY", wx, wy), nt.math("MULTIPLY", vert, nt.math("GREATER_THAN", z, z_min)))
    cell = nt.math("ADD", nt.math("MULTIPLY", nt.math("FLOOR", nt.math("DIVIDE", u, cell_w)), 7.13),
                   nt.math("MULTIPLY", nt.math("FLOOR", nt.math("DIVIDE", z, cell_h)), 13.7))
    cell = nt.math("ADD", cell, nt.math("MULTIPLY", isx, 3.3))
    cell = nt.math("ADD", cell, nt.math("MULTIPLY", nt.object_random(), 97.0))
    return win, cell, vert


def _lit(nt, cell, frac_default):
    """1 for the cells whose room light is on."""
    wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    nt.links.new(nt.math("ADD", cell, 0.37), wn.inputs["W"])
    a = _attr(nt, "lit")
    # obj["lit"] = 0 means 'use the default'; negative switches the lights off
    frac = nt.math("ADD", a, nt.math("MULTIPLY", nt.math("LESS_THAN", nt.math("ABSOLUTE", a), 1e-6), frac_default))
    return nt.math("GREATER_THAN", wn.outputs["Value"], nt.math("SUBTRACT", 1.0, frac))


def building_material(name="city_building", kind="mixed", lit=0.14, haze=1.0):
    """kind: 'mixed' (masonry walls in random colours, punched windows; obj["tower"] = 1 makes it a glass tower),
    'glass' (blue-silver curtain wall), 'stone' (art-deco limestone with vertical window strips)."""
    store = {}

    def base(nt):
        pos, nrm = _obj_space(nt)
        rnd = nt.object_random()
        tower = _attr(nt, "tower")
        if kind == "stone":
            win, cell, vert = _windows(nt, pos, nrm, 2.6, 3.9, 0.42, 0.72, 6.0)
            wall = rf.rgba((0.74, 0.70, 0.62))
            glass_lo, glass_hi = (0.05, 0.06, 0.07), (0.30, 0.34, 0.38)
        elif kind == "glass":
            win, cell, vert = _windows(nt, pos, nrm, 1.6, 3.9, 0.94, 0.86, 0.0)
            wall = rf.rgba((0.55, 0.60, 0.66))
            glass_lo, glass_hi = (0.06, 0.10, 0.15), (0.38, 0.48, 0.60)
        else:
            pw, pcell, vert = _windows(nt, pos, nrm, 3.2, 3.4, 0.6, 0.6, 4.2)     # punched windows
            gw, gcell, _ = _windows(nt, pos, nrm, 1.8, 3.6, 0.92, 0.84, 4.2)      # glass towers
            inv = nt.math("SUBTRACT", 1.0, tower)
            win = nt.math("ADD", nt.math("MULTIPLY", pw, inv), nt.math("MULTIPLY", gw, tower))
            cell = nt.math("ADD", nt.math("MULTIPLY", pcell, inv), nt.math("MULTIPLY", gcell, tower))
            wall = nt.ramp(rnd, [(i / len(WALLS), w) for i, w in enumerate(WALLS)], constant=True)
            wall = nt.mix_color(tower, wall, (0.52, 0.57, 0.63, 1.0))
            glass_lo, glass_hi = (0.04, 0.05, 0.07), (0.36, 0.44, 0.54)
            # ground-floor shopfronts
            sx = nt.math("FRACT", nt.math("DIVIDE", nt.math("ADD", pos.outputs["X"], pos.outputs["Y"]), 6.0))
            shop = nt.math("MULTIPLY", nt.math("MULTIPLY", nt.band(sx, 0.08, 0.92), nt.band(pos.outputs["Z"], 0.5, 3.4)), vert)
            win = nt.math("MAXIMUM", win, shop)
            wall = nt.mix_color(nt.math("LESS_THAN", pos.outputs["Z"], 4.0), wall, nt.mix_color(0.5, wall, (0.08, 0.08, 0.09, 1)))
        wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
        nt.links.new(cell, wn.inputs["W"])
        mid = tuple(a + (b - a) * 0.12 for a, b in zip(glass_lo, glass_hi))
        glass = nt.ramp(wn.outputs["Value"], [(0.0, rf.rgba(glass_lo)), (0.85, rf.rgba(mid)),
                                              (1.0, rf.rgba(tuple(a + (b - a) * 0.3 for a, b in zip(glass_lo, glass_hi))))])
        glass = nt.mix_color(_attr(nt, "shattered"), glass, (0.004, 0.004, 0.005, 1.0))
        col = nt.mix_color(win, wall, glass)
        roof = nt.math("GREATER_THAN", nrm.outputs["Z"], 0.5)
        # roofs: gravel with a little variation
        rn = nt.node("ShaderNodeTexNoise")
        rn.inputs["Scale"].default_value = 0.6
        nt.links.new(nt.node("ShaderNodeTexCoord").outputs["Object"], rn.inputs["Vector"])
        roof_col = nt.mix_color(rn.outputs["Fac"], (0.20, 0.20, 0.21, 1.0), (0.36, 0.35, 0.33, 1.0))
        col = nt.mix_color(roof, col, roof_col)
        store["win"] = nt.math("MULTIPLY", win, nt.math("SUBTRACT", 1.0, roof))
        store["lit"] = nt.math("MULTIPLY", store["win"], _lit(nt, cell, lit))
        store["lit"] = nt.math("MULTIPLY", store["lit"], nt.math("SUBTRACT", 1.0, _attr(nt, "shattered")))
        return col

    def rough(nt):
        return nt.math("SUBTRACT", 0.85, nt.math("MULTIPLY", store["win"], 0.72))

    mat = rf.make_material(name, base, rough=rough, metallic=0.0, haze=haze, glitch=True)
    # warm room lights in the lit cells; glass is a little metallic so it mirrors the evening sky
    nt = rf.NodeTree(mat.node_tree)
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Emission Color"].default_value = WARM
    nt.links.new(nt.math("MULTIPLY", store["lit"], 1.6), bsdf.inputs["Emission Strength"])
    nt.links.new(nt.math("MULTIPLY", store["win"], 0.25), bsdf.inputs["Metallic"])
    return mat


def block_material(name="city_far"):
    """Distant city boxes merged into a few meshes: each box's wall colour comes from the 'boxcol' colour
    attribute; windows are faint bands so they don't alias into a grid from the air; grey roofs."""
    def base(nt):
        pos, nrm = _obj_space(nt)
        ca = nt.node("ShaderNodeVertexColor")
        ca.layer_name = "boxcol"
        z = pos.outputs["Z"]
        band = nt.math("MULTIPLY", nt.band(nt.math("FRACT", nt.math("DIVIDE", z, 3.4)), 0.35, 0.85),
                       nt.math("GREATER_THAN", z, 4.0))
        wall = nt.mix_color(nt.math("MULTIPLY", band, 0.35), ca.outputs["Color"], (0.06, 0.07, 0.09, 1.0))
        roof = nt.math("GREATER_THAN", nrm.outputs["Z"], 0.5)
        return nt.mix_color(roof, wall, nt.mix_color(nt.math("MULTIPLY", ca.outputs["Alpha"], 1.0),
                                                     (0.22, 0.22, 0.23, 1.0), (0.38, 0.33, 0.29, 1.0)))

    return rf.make_material(name, base, rough=0.85, haze=1.0, glitch=False)


def paint_boxes(mesh, rnd, faces_per_box=6, palette=WALLS):
    """Write a random wall colour per box (and a random roof tone in alpha) into the 'boxcol' attribute."""
    import numpy as np
    n_poly = len(mesh.polygons)
    n_box = n_poly // faces_per_box
    cols = np.array([(*palette[rnd.randrange(len(palette))], rnd.random()) for _ in range(n_box)], dtype=np.float32)
    cols[:, :3] *= np.array([rnd.uniform(0.8, 1.1) for _ in range(n_box)], dtype=np.float32)[:, None]
    attr = mesh.color_attributes.new("boxcol", "BYTE_COLOR", "CORNER")
    loop_poly = np.zeros(len(mesh.loops), dtype=np.int64)
    starts = np.zeros(n_poly, dtype=np.int64)
    totals = np.zeros(n_poly, dtype=np.int64)
    mesh.polygons.foreach_get("loop_start", starts)
    mesh.polygons.foreach_get("loop_total", totals)
    for p in range(n_poly):
        loop_poly[starts[p]:starts[p] + totals[p]] = p
    per_loop = cols[np.minimum(loop_poly // faces_per_box, n_box - 1)]
    attr.data.foreach_set("color", per_loop.ravel())


def solid_material(name, color, rough=0.6, metallic=0.0, haze=1.0, emission=None):
    return rf.make_material(name, color, rough=rough, metallic=metallic, haze=haze, emission=emission, glitch=True)
