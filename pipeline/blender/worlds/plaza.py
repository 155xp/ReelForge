"""World: a grand city square in the afternoon sun, the city round it, and the real planet under it, from the
cobbles to the whole Earth at true scale.

Built for crowds (parts/crowd.py) and "everyone on Earth at once" stories (effects/everyone.py): a 140 x 100 m square
of granite setts with a two-tier fountain, trees, benches and lamps, ringed by a road and five-to-eight storey
buildings with zinc mansard roofs; four avenues lead out into a city with a river, quays and bridges, parks, tree-lined
boulevards and a cluster of towers; the real Earth lies under it all (parts/globe.py: fields, woods and towns round
the city, the continents, clouds and night lights from orbit). Everything is in true metres, the square's centre at
the origin, +Y north.

spec["world"] keys (all optional):
  seed           layout randomness (default 7)
  home           [lat, lon] where the square is on the planet (default [48.86, 2.35], a European capital: it
                 decides the coastlines, the night lights and the sunlit side seen from space)
  sun            {"heading": 245, "elevation": 24}: compass degrees the sun stands in (from +Y towards +X), degrees
                 above the horizon
  density        people per square metre in the square (default 2.2, a packed event crowd: ~28,600 people)
  streets        people per square metre on the ring road and the avenues (default 1.8; 0 = none)
  city_radius    metres of city round the square (default 6500)
  river          true: a river crosses the city north of the square (default true)
  clouds         a cumulus layer at ~1.8 km round the city, clear overhead (default true)
  hero           [x, y] where "you" stand, facing south (default [0, -15]; the demo uses [6, -36])
  front          metres in front of you kept clear: the crowd fills the square from this line back, so low
                 cameras in front of you have room (default 1.0)

info keys (for the effect): scene, world, sun, sun_dir, camera, collections, hero {"object", "person", "pos"},
crowds [{"name", "object", "order", "n"}] (order: 0..1 join order per person, nearest the hero first), city_radius,
fill_from (metres from the square where the city's streets start filling), planet (parts.globe.build), flat (the
flat world's objects), crowd_objects, low_clouds, home (lat, lon), square (w, d), fountain (x, y, r).
Scene properties the materials read: rf_fill_r (metres: the city's streets are packed with people out to here),
rf_glow (the gold "joined" glow, 0..1), rf_globe_a (parts.globe), rf_lights (street lamps, 0..1), rf_time (seconds,
drives the fountain's water: key it to the crowd's clock and the water freezes with the crowd).
"""
import math
import random

import bpy
import numpy as np

import facades
import look
import rf_common as rf
from parts import crowd, globe, nature

SQ_W, SQ_D = 140.0, 100.0          # the paved square
ROAD = 14.0                        # ring road width round it
WALK = 4.0                         # pavement in front of the buildings
DEPTH = 24.0                       # building depth round the square
AVENUE = 28.0                      # avenue width (road and pavements) at the middle of each side
AVENUE_LEN = 400.0                 # how far the modelled avenues run out from the square
FOUNTAIN_R = 9.0
PERIOD = 130.0                     # city grid: block + street
STREET = 20.0
FLOOR_Z = -0.35                    # the city's ground plane, under the modelled square and streets
RIVER = [(-6800, -500), (-5200, 150), (-3700, 1000), (-2100, 850), (-800, 620), (500, 700), (1900, 420),
         (3300, -250), (4700, -150), (6800, 650)]
RIVER_W = 150.0
QUAY = 14.0


# ---------------------------------------------------------------- material helpers

def _vl(nt, name, sock="Fac"):
    return nt.node("ShaderNodeAttribute", attribute_type="VIEW_LAYER", attribute_name=name).outputs[sock]


def _obj_xyz(nt):
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    return tc.outputs["Object"], sep


def _noise(nt, vec, scale, detail=4.0, rough=0.55):
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def _white(nt, w):
    wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    nt.links.new(w, wn.inputs["W"])
    return wn.outputs["Value"]


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def _bump(nt, bsdf, height, strength=0.3, distance=0.02):
    b = nt.node("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.links.new(height, b.inputs["Height"])
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])


# ---------------------------------------------------------------- materials

def paving_material():
    """Granite setts (20 x 11 cm) in running rows, crossed every 10 m by bands of pale granite slabs, a slab ring round
    the fountain and a slab border; worn and stained where feet go, with sunken joints."""
    store = {}

    def base(nt):
        p, sep = _obj_xyz(nt)
        x, y = sep.outputs["X"], sep.outputs["Y"]
        br = nt.node("ShaderNodeTexBrick")
        br.offset, br.offset_frequency, br.squash, br.squash_frequency = 0.5, 2, 1.0, 2
        for k, v in (("Scale", 1.0), ("Mortar Size", 0.008), ("Mortar Smooth", 0.4), ("Bias", 0.0),
                     ("Brick Width", 0.14), ("Row Height", 0.095)):
            br.inputs[k].default_value = v
        br.inputs["Color1"].default_value = (0.20, 0.19, 0.18, 1.0)
        br.inputs["Color2"].default_value = (0.42, 0.37, 0.32, 1.0)
        br.inputs["Mortar"].default_value = (0.13, 0.12, 0.11, 1.0)
        nt.links.new(p, br.inputs["Vector"])
        setts = br.outputs["Color"]
        grain = _noise(nt, p, 9.0, 3.0)                                       # stone to stone tone
        setts = nt.mix_color(nt.math("MULTIPLY", grain, 0.4), setts, (0.48, 0.44, 0.40, 1.0))
        tone = _noise(nt, p, 0.35, 4.0)
        setts = nt.mix_color(nt.math("MULTIPLY", tone, 0.35), setts, (0.17, 0.16, 0.15, 1.0))
        # pale slab bands every 10 m, a 2 m border and the ring round the fountain
        bx = nt.math("ABSOLUTE", nt.math("SUBTRACT", nt.math("FRACT", nt.math("ADD", nt.math("DIVIDE", x, 10.0), 0.5)), 0.5))
        by = nt.math("ABSOLUTE", nt.math("SUBTRACT", nt.math("FRACT", nt.math("ADD", nt.math("DIVIDE", y, 10.0), 0.5)), 0.5))
        band = nt.math("MAXIMUM", nt.math("LESS_THAN", bx, 0.04), nt.math("LESS_THAN", by, 0.04))
        r = nt.math("SQRT", nt.math("ADD", nt.math("MULTIPLY", x, x), nt.math("MULTIPLY", y, y)))
        ring = nt.band(r, FOUNTAIN_R + 2.0, FOUNTAIN_R + 3.6)
        border = nt.math("MAXIMUM", nt.math("GREATER_THAN", nt.math("ABSOLUTE", x), SQ_W / 2 - 2.0),
                         nt.math("GREATER_THAN", nt.math("ABSOLUTE", y), SQ_D / 2 - 2.0))
        slab_m = nt.math("MAXIMUM", nt.math("MAXIMUM", band, ring), border)
        sx = nt.math("FRACT", nt.math("DIVIDE", nt.math("ADD", x, y), 1.2))
        slab_joint = nt.math("LESS_THAN", nt.math("ABSOLUTE", nt.math("SUBTRACT", sx, 0.5)), 0.006)
        cell = _white(nt, nt.math("FLOOR", nt.math("DIVIDE", nt.math("ADD", x, y), 1.2)))
        slab = nt.mix_color(cell, (0.58, 0.56, 0.52, 1.0), (0.70, 0.68, 0.63, 1.0))
        slab = nt.mix_color(nt.math("MULTIPLY", slab_joint, 0.8), slab, (0.15, 0.14, 0.13, 1.0))
        col = nt.mix_color(slab_m, setts, slab)
        grime = _noise(nt, p, 0.12, 5.0, 0.6)
        col = nt.mix_color(nt.math("MULTIPLY", _smoothn(nt, grime, 0.5, 0.75), 0.45), col, (0.20, 0.18, 0.16, 1.0))
        store["mortar"] = nt.math("MULTIPLY", br.outputs["Fac"], nt.math("SUBTRACT", 1.0, slab_m))
        return col

    mat = rf.make_material("rf_paving", base, rough=0.78, glitch=False)
    nt = rf.NodeTree(mat.node_tree)
    _bump(nt, _bsdf(mat), nt.math("SUBTRACT", 1.0, store["mortar"]), 0.45, 0.012)
    return mat


def _smoothn(nt, x, lo, hi):
    t = nt.math("DIVIDE", nt.math("SUBTRACT", x, lo), hi - lo, clamp=True)
    return nt.math("MULTIPLY", nt.math("MULTIPLY", t, t), nt.math("SUBTRACT", 3.0, nt.math("MULTIPLY", t, 2.0)))


def stone_material(name, col=(0.70, 0.66, 0.58)):
    """Carved limestone with weathering: lighter faces, darker water stains low down and in streaks."""
    def base(nt):
        p, sep = _obj_xyz(nt)
        n = _noise(nt, p, 2.2, 6.0, 0.6)
        c = nt.mix_color(n, tuple(v * 0.82 for v in col) + (1.0,), tuple(min(1.0, v * 1.08) for v in col) + (1.0,))
        streak = _noise(nt, p, 0.9, 3.0)
        low = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", sep.outputs["Z"], 0.8, clamp=True))
        stain = nt.math("MAXIMUM", nt.math("MULTIPLY", low, 0.55), nt.math("MULTIPLY", _smoothn(nt, streak, 0.6, 0.75), 0.3))
        return nt.mix_color(stain, c, (0.30, 0.29, 0.25, 1.0))
    return rf.make_material(name, base, rough=0.62, glitch=False)


def water_material():
    """The basins' water: dark, glossy, rippling (rf_time moves the ripples)."""
    mat = rf.make_material("rf_fountain_water", (0.025, 0.07, 0.085), rough=0.04, glitch=False)
    nt = rf.NodeTree(mat.node_tree)
    p, _ = _obj_xyz(nt)
    shift = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", _vl(nt, "rf_time"), 0.35), shift.inputs[2])
    pp = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(p, pp.inputs[0])
    nt.links.new(shift.outputs[0], pp.inputs[1])
    _bump(nt, _bsdf(mat), _noise(nt, pp.outputs["Vector"], 3.0, 3.0), 0.25, 0.02)
    return mat


def falling_water_material():
    """Sheets of water falling from the bowls: streaks that run downwards with rf_time, translucent white."""
    mat = bpy.data.materials.new("rf_falling_water")
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for nd in list(nt.nodes):
        nt.nodes.remove(nd)
    out = nt.node("ShaderNodeOutputMaterial")
    p, sep = _obj_xyz(nt)
    ang = nt.math("ARCTAN2", sep.outputs["Y"], sep.outputs["X"])
    v = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", nt.math("COSINE", ang), 16.0), v.inputs[0])
    nt.links.new(nt.math("MULTIPLY", nt.math("SINE", ang), 16.0), v.inputs[1])
    nt.links.new(nt.math("ADD", nt.math("MULTIPLY", sep.outputs["Z"], 0.45), nt.math("MULTIPLY", _vl(nt, "rf_time"), 2.6)),
                 v.inputs[2])
    streak = _noise(nt, v.outputs[0], 1.0, 5.0, 0.65)
    ropes = _noise(nt, v.outputs[0], 0.35, 2.0, 0.5)                      # the sheet breaks into ropes and gaps
    alpha = nt.math("MULTIPLY", _smoothn(nt, streak, 0.50, 0.66), _smoothn(nt, ropes, 0.38, 0.55))
    # aerated white water, densest where it lands
    foam = nt.math("SUBTRACT", 1.0, _smoothn(nt, sep.outputs["Z"], 0.5, 1.4))
    alpha = nt.math("MINIMUM", nt.math("ADD", nt.math("MULTIPLY", alpha, 0.75), nt.math("MULTIPLY", foam, 0.35)), 0.9)
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.88, 0.93, 0.96, 1.0)
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Emission Color"].default_value = (0.88, 0.94, 1.0, 1.0)
    b.inputs["Emission Strength"].default_value = 0.22
    nt.links.new(alpha, b.inputs["Alpha"])
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    for prop, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND"), ("use_backface_culling", False)):
        try:
            setattr(mat, prop, val)
        except (AttributeError, TypeError):
            pass
    return mat


def asphalt_material():
    def base(nt):
        p, sep = _obj_xyz(nt)
        n = _noise(nt, p, 1.5, 6.0)
        col = nt.mix_color(n, (0.045, 0.045, 0.05, 1.0), (0.10, 0.10, 0.105, 1.0))
        patch = nt.math("GREATER_THAN", _noise(nt, p, 0.08, 2.0), 0.62)
        return nt.mix_color(nt.math("MULTIPLY", patch, 0.5), col, (0.03, 0.03, 0.035, 1.0))
    return rf.make_material("rf_asphalt", base, rough=0.9, glitch=False)


def concrete_material():
    def base(nt):
        p, sep = _obj_xyz(nt)
        fx = nt.math("FRACT", nt.math("DIVIDE", sep.outputs["X"], 1.6))
        fy = nt.math("FRACT", nt.math("DIVIDE", sep.outputs["Y"], 1.6))
        seam = nt.math("MAXIMUM", nt.math("LESS_THAN", fx, 0.02), nt.math("LESS_THAN", fy, 0.02))
        n = _noise(nt, p, 0.8, 4.0)
        col = nt.mix_color(n, (0.38, 0.37, 0.35, 1.0), (0.50, 0.49, 0.46, 1.0))
        return nt.mix_color(nt.math("MULTIPLY", seam, 0.6), col, (0.18, 0.18, 0.17, 1.0))
    return rf.make_material("rf_concrete", base, rough=0.85, glitch=False)


def leaf_material(name="rf_leaves", scale=0.9):
    def base(nt):
        p, sep = _obj_xyz(nt)
        n = _noise(nt, p, scale, 5.0, 0.65)
        return nt.ramp(n, [(0.3, (0.04, 0.10, 0.025)), (0.55, (0.10, 0.21, 0.045)), (0.75, (0.20, 0.30, 0.07))])
    return rf.make_material(name, base, rough=0.8, glitch=False)


def zinc_material():
    """Paris-style zinc roofing: blue-grey sheets with standing seams, a little metallic sheen."""
    def base(nt):
        p, sep = _obj_xyz(nt)
        s = nt.math("FRACT", nt.math("DIVIDE", nt.math("ADD", sep.outputs["X"], sep.outputs["Y"]), 0.55))
        seam = nt.math("LESS_THAN", s, 0.06)
        n = _noise(nt, p, 0.25, 3.0)
        c = nt.mix_color(n, (0.22, 0.25, 0.29, 1.0), (0.34, 0.37, 0.41, 1.0))
        return nt.mix_color(nt.math("MULTIPLY", seam, 0.5), c, (0.45, 0.48, 0.52, 1.0))
    return rf.make_material("rf_zinc", base, rough=0.42, metallic=0.55, glitch=False)


def roof_material():
    """Flat roofs: tar and gravel with repair patches."""
    def base(nt):
        p, sep = _obj_xyz(nt)
        n = _noise(nt, p, 0.15, 4.0)
        c = nt.mix_color(n, (0.15, 0.15, 0.15, 1.0), (0.27, 0.26, 0.25, 1.0))
        patch = nt.math("GREATER_THAN", _noise(nt, p, 0.05, 2.0), 0.62)
        return nt.mix_color(nt.math("MULTIPLY", patch, 0.6), c, (0.08, 0.08, 0.085, 1.0))
    return rf.make_material("rf_flat_roof", base, rough=0.9, glitch=False)


def far_city_material():
    """The distant blocks merged into a few meshes: walls in the 'boxcol' colour with faint window bands, roofs in
    zinc, slate, gravel or terracotta (the box's random alpha), so the city reads as Paris-like from the air."""
    def base(nt):
        tc = nt.node("ShaderNodeTexCoord")
        pos = nt.node("ShaderNodeSeparateXYZ")
        nrm = nt.node("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], pos.inputs[0])
        nt.links.new(tc.outputs["Normal"], nrm.inputs[0])
        ca = nt.node("ShaderNodeVertexColor")
        ca.layer_name = "boxcol"
        z = pos.outputs["Z"]
        band = nt.math("MULTIPLY", nt.band(nt.math("FRACT", nt.math("DIVIDE", z, 3.4)), 0.35, 0.85),
                       nt.math("GREATER_THAN", z, 4.0))
        wall = nt.mix_color(nt.math("MULTIPLY", band, 0.4), ca.outputs["Color"], (0.05, 0.06, 0.08, 1.0))
        roof = nt.math("GREATER_THAN", nrm.outputs["Z"], 0.5)
        rc = nt.ramp(ca.outputs["Alpha"], [(0.0, (0.25, 0.28, 0.32)), (0.45, (0.15, 0.16, 0.18)),
                                           (0.70, (0.34, 0.33, 0.31)), (0.90, (0.40, 0.20, 0.12))], constant=True)
        rn = _noise(nt, tc.outputs["Object"], 0.08, 3.0)
        rc = nt.mix_color(nt.math("MULTIPLY", rn, 0.35), rc, (0.10, 0.10, 0.11, 1.0))
        return nt.mix_color(roof, wall, rc)
    return rf.make_material("rf_city_far", base, rough=0.8, glitch=False)


def grass_material():
    def base(nt):
        p, sep = _obj_xyz(nt)
        n = _noise(nt, p, 0.05, 5.0, 0.6)
        c = nt.mix_color(n, (0.08, 0.15, 0.04, 1.0), (0.17, 0.25, 0.07, 1.0))
        path = nt.math("LESS_THAN", _noise(nt, p, 0.012, 2.0), 0.35)
        return nt.mix_color(nt.math("MULTIPLY", path, 0.7), c, (0.42, 0.38, 0.30, 1.0))
    return rf.make_material("rf_park_grass", base, rough=0.95, glitch=False)


def river_material():
    """A city river: deep green-grey water, glossy so it mirrors the sky and catches the sun, with a slow ripple."""
    mat = rf.make_material("rf_river", (0.02, 0.05, 0.055), rough=0.07, glitch=False)
    nt = rf.NodeTree(mat.node_tree)
    p, _ = _obj_xyz(nt)
    _bump(nt, _bsdf(mat), _noise(nt, p, 0.15, 4.0), 0.15, 0.5)
    return mat


def _street_mask(nt, x, y):
    half = STREET / PERIOD / 2
    sx = nt.math("FRACT", nt.math("ADD", nt.math("DIVIDE", x, PERIOD), 0.5))
    sy = nt.math("FRACT", nt.math("ADD", nt.math("DIVIDE", y, PERIOD), 0.5))
    return nt.math("MAXIMUM", nt.math("LESS_THAN", nt.math("ABSOLUTE", nt.math("SUBTRACT", sx, 0.5)), half),
                   nt.math("LESS_THAN", nt.math("ABSOLUTE", nt.math("SUBTRACT", sy, 0.5)), half))


def _fill_edge(nt, p, x, y):
    """(distance from the square, the filled front's radius there): the front is ragged, not a perfect circle."""
    r = nt.math("SQRT", nt.math("ADD", nt.math("MULTIPLY", x, x), nt.math("MULTIPLY", y, y)))
    edge = nt.math("SUBTRACT", _vl(nt, "rf_fill_r"), nt.math("MULTIPLY", _noise(nt, p, 1 / 260.0, 2.0), 180.0))
    return r, edge


def _edge_mix(nt, x, y, radius):
    """0 inside the city's ragged edge (the same wave as _edge_wave), 1 a few hundred metres past it."""
    th = nt.math("ARCTAN2", y, x)
    w3 = nt.math("MULTIPLY", nt.math("SINE", nt.math("ADD", nt.math("MULTIPLY", th, 3.0), 1.3)), 0.12)
    w7 = nt.math("MULTIPLY", nt.math("SINE", nt.math("ADD", nt.math("MULTIPLY", th, 7.0), 0.4)), 0.07)
    wave = nt.math("ADD", 1.0, nt.math("ADD", w3, w7))
    rr = nt.math("SQRT", nt.math("ADD", nt.math("MULTIPLY", x, x), nt.math("MULTIPLY", y, y)))
    return _smoothn(nt, nt.math("SUBTRACT", rr, nt.math("MULTIPLY", wave, radius)), -150.0, 400.0)


def city_floor_material(radius):
    """The city's ground from the air: 20 m streets every 130 m and grey lots; past the city's ragged edge the same
    suburbs and fields the planet shows (parts.globe.ground_fine), so the floor's rim can't be seen. Inside
    rf_fill_r of the square the streets are packed with people (dark heads and bright shoulders, as a crowd looks
    from above); a band of gold light (rf_glow) runs along the advancing edge, so the city filling up reads as a
    wave from kilometres up."""
    def base(nt):
        p, sep = _obj_xyz(nt)
        x, y = sep.outputs["X"], sep.outputs["Y"]
        street = _street_mask(nt, x, y)
        bx = nt.math("FLOOR", nt.math("DIVIDE", x, PERIOD))
        by = nt.math("FLOOR", nt.math("DIVIDE", y, PERIOD))
        blk = _white(nt, nt.math("ADD", bx, nt.math("MULTIPLY", by, 31.7)))
        lot = nt.ramp(blk, [(0.0, (0.19, 0.19, 0.18)), (0.55, (0.27, 0.26, 0.24)), (1.0, (0.22, 0.21, 0.20))])
        lot = nt.mix_color(nt.math("MULTIPLY", _noise(nt, p, 1 / 30.0, 3.0), 0.5), lot, (0.12, 0.12, 0.12, 1.0))
        asph = nt.mix_color(_noise(nt, p, 0.05, 3.0), (0.045, 0.045, 0.05, 1.0), (0.085, 0.085, 0.09, 1.0))
        col = nt.mix_color(street, lot, asph)
        r, edge = _fill_edge(nt, p, x, y)
        filled = nt.math("MULTIPLY", street, nt.math("LESS_THAN", r, edge))
        vo = nt.node("ShaderNodeTexVoronoi")
        vo.inputs["Scale"].default_value = 1.6
        nt.links.new(p, vo.inputs["Vector"])
        sc = nt.node("ShaderNodeSeparateColor")
        nt.links.new(vo.outputs["Color"], sc.inputs[0])
        shirt = nt.ramp(sc.outputs[0], [(i / (len(crowd.SHIRTS) - 1), c) for i, c in enumerate(crowd.SHIRTS)],
                        constant=True)
        d = vo.outputs["Distance"]
        shirt = nt.mix_color(0.45, shirt, (0.0, 0.0, 0.0, 1.0))                # shoulders in each other's shade
        person = nt.mix_color(nt.math("LESS_THAN", d, 0.13), shirt, (0.03, 0.024, 0.02, 1.0))
        people = nt.mix_color(nt.math("LESS_THAN", d, 0.27), (0.035, 0.032, 0.032, 1.0), person)
        col = nt.mix_color(filled, col, people)
        flat = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(x, flat.inputs[0])
        nt.links.new(y, flat.inputs[1])
        ground, _town = globe.ground_fine(nt, flat.outputs[0])
        return nt.mix_color(_edge_mix(nt, x, y, radius), col, ground)

    mat = rf.make_material("rf_city_floor", base, rough=0.9, glitch=False)
    nt = rf.NodeTree(mat.node_tree)
    p, sep = _obj_xyz(nt)
    x, y = sep.outputs["X"], sep.outputs["Y"]
    street = nt.math("MULTIPLY", _street_mask(nt, x, y), nt.math("SUBTRACT", 1.0, _edge_mix(nt, x, y, radius)))
    r, edge = _fill_edge(nt, p, x, y)
    inside = nt.math("LESS_THAN", r, edge)
    front = nt.math("MULTIPLY", inside, _smoothn(nt, nt.math("SUBTRACT", r, nt.math("SUBTRACT", edge, 320.0)), 0.0, 320.0))
    glow = nt.math("MULTIPLY", nt.math("MULTIPLY", street, nt.math("ADD", nt.math("MULTIPLY", inside, 0.02),
                                                                    nt.math("MULTIPLY", front, 1.0))),
                   _vl(nt, "rf_glow"))
    bsdf = _bsdf(mat)
    bsdf.inputs["Emission Color"].default_value = globe.GOLD
    nt.links.new(nt.math("MULTIPLY", glow, 5.0), bsdf.inputs["Emission Strength"])
    return mat


def lantern_material():
    mat = rf.make_material("rf_lantern", (0.9, 0.85, 0.7), rough=0.3, glitch=False)
    nt = rf.NodeTree(mat.node_tree)
    bsdf = _bsdf(mat)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.72, 0.38, 1.0)
    nt.links.new(nt.math("ADD", 0.2, nt.math("MULTIPLY", _vl(nt, "rf_lights"), 14.0)), bsdf.inputs["Emission Strength"])
    return mat


# ---------------------------------------------------------------- mesh helpers

def _tube(mb, cx, cy, z0, z1, r0, r1, seg, mat):
    """An open tube (no caps), radius r0 at z0 to r1 at z1."""
    b = len(mb.verts)
    for rad, z in ((r0, z0), (r1, z1)):
        for k in range(seg):
            a = 2 * math.pi * k / seg
            mb.verts.append((cx + rad * math.cos(a), cy + rad * math.sin(a), z))
    for k in range(seg):
        k2 = (k + 1) % seg
        mb.faces.append((b + k, b + k2, b + seg + k2, b + seg + k))
        mb.mats.append(mat)


def _frustum(mb, x0, y0, x1, y1, z0, z1, inset, mat):
    """A box whose top is pulled in by `inset` on every side (a mansard roof storey)."""
    b = len(mb.verts)
    mb.verts += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                 (x0 + inset, y0 + inset, z1), (x1 - inset, y0 + inset, z1), (x1 - inset, y1 - inset, z1),
                 (x0 + inset, y1 - inset, z1)]
    for q in ((4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        mb.faces.append(tuple(b + i for i in q))
        mb.mats.append(mat)


def _roof(mb, rnd, x0, y0, x1, y1, h, mansard, ZINC, ROOF, CHIM, DARK, dormers=True):
    """A roof on a building whose walls end at height h: a zinc mansard storey with dormers and chimney stacks, or a
    flat tar roof with plant boxes and chimneys."""
    if mansard:
        rh = rnd.uniform(3.0, 3.8)
        inset = rnd.uniform(1.4, 1.9)
        _frustum(mb, x0 + 0.15, y0 + 0.15, x1 - 0.15, y1 - 0.15, h, h + rh, inset, ZINC)
        if dormers:
            for (ax0, ay0, ax1, ay1, nx, ny) in ((x0, y0, x1, y0, 0, -1), (x0, y1, x1, y1, 0, 1),
                                                 (x0, y0, x0, y1, -1, 0), (x1, y0, x1, y1, 1, 0)):
                length = abs(ax1 - ax0) + abs(ay1 - ay0)
                k = int((length - 3.0) // 3.4)
                for i in range(k):
                    u = (i + 0.5) / k
                    cx, cy = ax0 + (ax1 - ax0) * u, ay0 + (ay1 - ay0) * u
                    cx -= nx * (inset * 0.45 + 0.15)
                    cy -= ny * (inset * 0.45 + 0.15)
                    w, d = (0.55, 0.45) if nx == 0 else (0.45, 0.55)
                    mb.box(cx - w, cy - d, h + 0.5, cx + w, cy + d, h + 1.9, ZINC)
                    # the dormer's window, a dark pane on its outer face
                    fx, fy = cx + nx * (0.46 if nx else 0), cy + ny * (0.46 if ny else 0)
                    pw = 0.35
                    if nx == 0:
                        mb.box(fx - pw, fy - 0.02 + ny * 0.03, h + 0.7, fx + pw, fy + 0.02 + ny * 0.03, h + 1.65, DARK)
                    else:
                        mb.box(fx - 0.02 + nx * 0.03, fy - pw, h + 0.7, fx + 0.02 + nx * 0.03, fy + pw, h + 1.65, DARK)
        top = h + rh
    else:
        mb.box(x0 + 0.35, y0 + 0.35, h, x1 - 0.35, y1 - 0.35, h + 0.12, ROOF)
        for _ in range(rnd.randint(1, 3)):
            rx, ry = rnd.uniform(x0 + 2, x1 - 5), rnd.uniform(y0 + 2, y1 - 5)
            mb.box(rx, ry, h + 0.12, rx + rnd.uniform(1.5, 3.5), ry + rnd.uniform(1.2, 2.5), h + rnd.uniform(1.0, 2.4),
                   ZINC)
        top = h + 0.12
    # chimney stacks with pots
    for _ in range(rnd.randint(2, 4)):
        cx = rnd.uniform(x0 + 2.5, x1 - 2.5)
        cy = rnd.uniform(y0 + 2.5, y1 - 2.5)
        w, d = (rnd.uniform(0.9, 2.2), 0.5) if rnd.random() < 0.5 else (0.5, rnd.uniform(0.9, 2.2))
        ch = rnd.uniform(1.2, 2.0)
        mb.box(cx - w / 2, cy - d / 2, top - 0.6, cx + w / 2, cy + d / 2, top + ch, CHIM)
        for k in range(max(1, int(max(w, d) / 0.45))):
            u = (k + 0.5) / max(1, int(max(w, d) / 0.45)) - 0.5
            px, py = (cx + u * w, cy) if w > d else (cx, cy + u * d)
            mb.cyl(px, py, top + ch, top + ch + 0.35, 0.09, 6, CHIM, r_top=0.07)


def _edge_wave(th):
    """The city's edge is not a circle: its radius times this, by compass angle (radians)."""
    return 1.0 + 0.12 * math.sin(3 * th + 1.3) + 0.07 * math.sin(7 * th + 0.4)


def _path_dist(x, y, path=RIVER):
    best = 1e18
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        dx, dy = bx - ax, by - ay
        u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy)))
        best = min(best, math.hypot(x - ax - u * dx, y - ay - u * dy))
    return best


def _ribbon(path, half_inner, half_outer, z):
    """Vertices and quads of a strip along a polyline, between the sideways offsets half_inner and half_outer."""
    pts = np.array(path, float)
    tang = np.gradient(pts, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    nrm = np.stack([-tang[:, 1], tang[:, 0]], 1)
    verts, faces = [], []
    for p, n in zip(pts, nrm):
        verts.append((p[0] + n[0] * half_inner, p[1] + n[1] * half_inner, z))
        verts.append((p[0] + n[0] * half_outer, p[1] + n[1] * half_outer, z))
    for i in range(len(pts) - 1):
        a = 2 * i
        faces.append((a, a + 2, a + 3, a + 1))
    return verts, faces


def _densify(path, step=60.0):
    """Points every `step` metres along a smoothed (Catmull-Rom) version of the path."""
    P = [np.array(p, float) for p in path]
    P = [P[0] - (P[1] - P[0])] + P + [P[-1] + (P[-1] - P[-2])]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int(np.linalg.norm(p2 - p1) / step))
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                              (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t))
    out.append(P[-2])
    return [tuple(p) for p in out]


# ---------------------------------------------------------------- the square

def _fountain(mb, stone, water, dark, fall):
    """Round basin with a moulded rim, water, a two-tier centrepiece with water falling from both bowls, and a jet."""
    seg = 48
    mb.cyl(0, 0, 0.0, 0.55, FOUNTAIN_R, seg, stone)
    mb.cyl(0, 0, 0.55, 0.62, FOUNTAIN_R + 0.3, seg, stone)
    mb.cyl(0, 0, 0.62, 0.70, FOUNTAIN_R + 0.15, seg, stone)
    mb.cyl(0, 0, 0.0, 0.44, FOUNTAIN_R - 0.45, seg, water)
    mb.cyl(0, 0, 0.0, 0.25, FOUNTAIN_R + 0.45, seg, stone)               # plinth step
    mb.cyl(0, 0, 0.0, 1.9, 1.5, 24, stone, r_top=1.1)
    mb.cyl(0, 0, 1.75, 1.9, 1.45, 24, stone)
    mb.cyl(0, 0, 1.9, 2.2, 3.4, 32, stone, r_top=3.7)
    mb.cyl(0, 0, 2.18, 2.26, 3.75, 32, stone)
    mb.cyl(0, 0, 2.2, 2.32, 3.3, 32, water)
    mb.cyl(0, 0, 2.2, 4.1, 0.7, 16, stone, r_top=0.5)
    for z in (2.6, 3.3):                                                  # carved rings on the column
        mb.cyl(0, 0, z, z + 0.12, 0.66, 16, stone)
    mb.cyl(0, 0, 4.1, 4.4, 1.8, 24, stone, r_top=2.0)
    mb.cyl(0, 0, 4.38, 4.46, 2.05, 24, stone)
    mb.cyl(0, 0, 4.4, 4.52, 1.85, 24, water)
    mb.cyl(0, 0, 4.4, 5.6, 0.32, 12, stone, r_top=0.22)
    mb.ico((0, 0, 5.85), (0.42, 0.42, 0.42), 2, dark)
    for k in range(8):                                                    # bronze spouts round the column
        a = 2 * math.pi * k / 8
        mb.box(math.cos(a) * 0.62 - 0.08, math.sin(a) * 0.62 - 0.08, 3.4,
               math.cos(a) * 0.62 + 0.08, math.sin(a) * 0.62 + 0.08, 3.6, dark)
    # falling water: from the top bowl to the lower bowl, from the lower bowl into the basin, and a central jet
    _tube(mb, 0, 0, 4.40, 2.32, 2.02, 2.25, 32, fall)
    _tube(mb, 0, 0, 2.20, 0.46, 3.74, 4.15, 48, fall)
    _tube(mb, 0, 0, 6.25, 7.6, 0.07, 0.035, 8, fall)
    _tube(mb, 0, 0, 7.6, 6.7, 0.04, 0.85, 16, fall)
    _tube(mb, 0, 0, 6.7, 4.55, 0.85, 1.55, 24, fall)


def _lamp(mb, x, y, metal, glass):
    mb.cyl(x, y, 0.0, 0.5, 0.22, 10, metal, r_top=0.14)
    mb.cyl(x, y, 0.5, 4.4, 0.075, 8, metal, r_top=0.06)
    mb.cyl(x, y, 4.4, 4.6, 0.14, 8, metal)
    mb.cyl(x, y, 4.6, 5.2, 0.24, 8, glass, r_top=0.30)
    mb.cyl(x, y, 5.2, 5.38, 0.34, 8, metal, r_top=0.08)


def _tree(mb, rnd, x, y, trunk, leaf, planter=None, soil=None, h=None, sub=2, puffs=9):
    if planter is not None:
        mb.box(x - 1.3, y - 1.3, 0.0, x + 1.3, y + 1.3, 0.55, planter)
        mb.box(x - 1.15, y - 1.15, 0.55, x + 1.15, y + 1.15, 0.6, soil)
    h = h or rnd.uniform(6.5, 8.0)
    mb.cyl(x, y, 0.0, h * 0.55, 0.2, 7 if sub > 1 else 5, trunk, r_top=0.14)
    for _ in range(puffs):
        cx = x + rnd.uniform(-1.6, 1.6) * h / 7.5
        cy = y + rnd.uniform(-1.6, 1.6) * h / 7.5
        cz = h * rnd.uniform(0.62, 0.95)
        s = rnd.uniform(1.3, 2.0) * h / 7.5
        mb.ico((cx, cy, cz), (s, s, s * 0.85), sub, leaf, jitter=0.2, rnd=rnd)


def _bench(mb, x, y, wood, metal):
    mb.box(x - 0.9, y - 0.25, 0.42, x + 0.9, y + 0.25, 0.48, wood)
    mb.box(x - 0.9, y + 0.2, 0.48, x + 0.9, y + 0.26, 0.9, wood)
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box(x + sx * 0.76 - 0.04, y + sy * 0.18 - 0.04, 0.0, x + sx * 0.76 + 0.04, y + sy * 0.18 + 0.04, 0.42,
                   metal)


def _square_buildings(col, rnd, mats):
    """Five-to-eight storey buildings round the square, with gaps for the four avenues: stone ones with zinc
    mansards and dormers, the rest with flat roofs; chimney stacks on all. Each is its own object (the facade
    material's colours and windows work per building)."""
    obs = []
    x_front, y_front = SQ_W / 2 + ROAD + WALK, SQ_D / 2 + ROAD + WALK
    slots = [mats["trim"], mats["zinc"], mats["roof"], mats["chimney"], mats["dark"]]

    def building(x0, y0, x1, y1, h, kind):
        mb = rf.MeshBuilder()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        lx0, ly0, lx1, ly1 = x0 - cx, y0 - cy, x1 - cx, y1 - cy
        mb.box(lx0, ly0, 0.0, lx1, ly1, h, 0)
        mb.box(lx0 - 0.35, ly0 - 0.35, h - 0.7, lx1 + 0.35, ly1 + 0.35, h - 0.3, 1)        # cornice
        mb.box(lx0 - 0.2, ly0 - 0.2, 7.6, lx1 + 0.2, ly1 + 0.2, 7.9, 1)                    # first-floor string course
        mb.box(lx0 - 0.15, ly0 - 0.15, 3.9, lx1 + 0.15, ly1 + 0.15, 4.3, 1)                # shopfront fascia
        mansard = kind == "stone" or rnd.random() < 0.45
        _roof(mb, rnd, lx0, ly0, lx1, ly1, h - 0.3, mansard, 2, 3, 4, 5)
        ob = rf.add_object("sq_bldg", mb.build("sq_bldg", [mats[kind]] + slots), col, (cx, cy, 0.0))
        ob["lit"] = 0.0
        obs.append(ob)

    def row(a0, a1, along_x, front, side):
        a = a0
        while a < a1 - 6:
            w = min(rnd.uniform(14, 26), a1 - a)
            h = rnd.choice((18.5, 21.9, 25.3, 28.7))
            kind = "stone" if rnd.random() < 0.45 else "mixed"
            if along_x:
                y0, y1 = (front, front + DEPTH) if side > 0 else (front - DEPTH, front)
                building(a, y0, a + w, y1, h, kind)
            else:
                x0, x1 = (front, front + DEPTH) if side > 0 else (front - DEPTH, front)
                building(x0, a, x1, a + w, h, kind)
            a += w + rnd.uniform(0.0, 0.6)

    gap = AVENUE / 2
    for side in (1, -1):
        row(-x_front - DEPTH, -gap, True, side * y_front, side)
        row(gap, x_front + DEPTH, True, side * y_front, side)
        row(-y_front, -gap, False, side * x_front, side)
        row(gap, y_front, False, side * x_front, side)
    return obs


def _city(col, rnd, mats, radius, river, near=700.0):
    """The city round the square: near blocks as separate facade buildings with roofs, a downtown cluster of glass
    towers to the north-east, far blocks merged into a few meshes; some blocks are parks; blocks by the river are
    left out (quays and bridges take their place). Returns (near objects, far objects, park rectangles)."""
    near_obs, far_meshes, parks = [], [], []
    mb_far = rf.MeshBuilder()
    n = int(radius * 1.2 // PERIOD) + 1
    clear_x = SQ_W / 2 + ROAD + WALK + DEPTH + 4
    clear_y = SQ_D / 2 + ROAD + WALK + DEPTH + 4
    downtown = (1500.0, 2100.0)
    slots = [mats["trim"], mats["zinc"], mats["roof"], mats["chimney"], mats["dark"]]
    for i in range(-n, n):
        for j in range(-n, n):
            bx0, bx1 = i * PERIOD + STREET / 2, (i + 1) * PERIOD - STREET / 2
            by0, by1 = j * PERIOD + STREET / 2, (j + 1) * PERIOD - STREET / 2
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            d = math.hypot(cx, cy)
            if d > radius * _edge_wave(math.atan2(cy, cx)):
                continue
            if (abs(cx) < clear_x + PERIOD / 2 and abs(cy) < clear_y + PERIOD / 2) or \
                    (abs(cx) < PERIOD / 2 and abs(cy) < AVENUE_LEN + PERIOD / 2) or \
                    (abs(cy) < PERIOD / 2 and abs(cx) < AVENUE_LEN + PERIOD / 2):
                continue
            if river and _path_dist(cx, cy) < RIVER_W / 2 + QUAY + 62:
                continue
            if d > 500 and rnd.random() < 0.06:
                parks.append((bx0, by0, bx1, by1))
                continue
            dd = math.hypot(cx - downtown[0], cy - downtown[1])
            tall = dd < 800
            peak = 70 + 170 * math.exp(-(dd ** 2) / (2 * 380.0 ** 2)) if tall else 0
            if d < near or tall:
                for (x0, x1) in ((bx0, (bx0 + bx1) / 2 - 1.5), ((bx0 + bx1) / 2 + 1.5, bx1)):
                    for (y0, y1) in ((by0, (by0 + by1) / 2 - 1.5), ((by0 + by1) / 2 + 1.5, by1)):
                        h = peak * rnd.uniform(0.55, 1.15) if tall else rnd.choice((18.5, 21.9, 25.3))
                        tower = tall and h > 50
                        inset = rnd.uniform(4, 10) if tower else 0.0
                        hw, hd = (x1 - x0) / 2 - inset, (y1 - y0) / 2 - inset
                        me = rf.MeshBuilder()
                        me.box(-hw, -hd, 0.0, hw, hd, h, 0)
                        if tower:
                            me.box(-hw + 0.3, -hd + 0.3, h, hw - 0.3, hd - 0.3, h + 1.2, 1)
                            me.box(-hw * 0.4, -hd * 0.4, h + 1.2, hw * 0.4, hd * 0.4, h + 4.0, 2)
                        else:
                            me.box(-hw - 0.3, -hd - 0.3, h - 0.6, hw + 0.3, hd + 0.3, h - 0.3, 1)
                            _roof(me, rnd, -hw, -hd, hw, hd, h - 0.3, rnd.random() < 0.7, 2, 3, 4, 5,
                                  dormers=d < 400)
                        ob = rf.add_object("city_bldg", me.build("city_bldg", [mats["glass" if tower else "mixed"]]
                                                                 + slots), col, ((x0 + x1) / 2, (y0 + y1) / 2, 0.0))
                        ob["tower"] = 1.0 if tower else 0.0
                        near_obs.append(ob)
            else:
                k = rnd.randint(1, 3)
                for q in range(k):
                    w = (bx1 - bx0) / k
                    h = rnd.uniform(14, 28) * (1.0 if d < 3500 else 0.8)
                    mb_far.box(bx0 + q * w + 1.0, by0 + 1.0, 0.0, bx0 + (q + 1) * w - 1.0, by1 - 1.0, h, 0)
                if len(mb_far.verts) > 400_000:
                    far_meshes.append(mb_far)
                    mb_far = rf.MeshBuilder()
    far_meshes.append(mb_far)
    far_obs = []
    for k, mb in enumerate(far_meshes):
        if not mb.verts:
            continue
        me = mb.build(f"city_far_{k}", [mats["far"]])
        facades.paint_boxes(me, rnd)
        far_obs.append(rf.add_object(f"city_far_{k}", me, col))
    return near_obs, far_obs, parks


def _river(col, rnd, mats, radius):
    """The river with stone quays, bridges at every third street, and plane trees along both banks."""
    path = [p for p in _densify(RIVER, 50.0) if math.hypot(*p) < radius + 1200]
    lim = radius + 500
    mbw = rf.MeshBuilder()
    v, f = _ribbon(path, -RIVER_W / 2, RIVER_W / 2, FLOOR_Z + 0.06)
    mbw.verts += v
    mbw.faces += f
    mbw.mats += [0] * len(f)
    for s in (-1, 1):
        v, f = _ribbon(path, s * RIVER_W / 2, s * (RIVER_W / 2 + QUAY), FLOOR_Z + 0.09)
        b = len(mbw.verts)
        mbw.verts += v
        mbw.faces += [tuple(b + i for i in q) for q in f]
        mbw.mats += [1] * len(f)
    # bridges where every third north-south street crosses
    for k in range(-int(lim // PERIOD), int(lim // PERIOD) + 1, 3):
        x = k * PERIOD
        ys = [p[1] for p in path]
        xs = [p[0] for p in path]
        if not (min(xs) < x < max(xs)):
            continue
        y = float(np.interp(x, xs, ys))
        if math.hypot(x, y) > radius:
            continue
        span = RIVER_W / 2 + QUAY + 4
        mbw.box(x - 9.0, y - span, FLOOR_Z, x + 9.0, y + span, 1.4, 2)
        mbw.box(x - 9.6, y - span, 1.4, x - 9.0, y + span, 2.4, 2)
        mbw.box(x + 9.0, y - span, 1.4, x + 9.6, y + span, 2.4, 2)
        for py in (-RIVER_W / 4, 0.0, RIVER_W / 4):
            mbw.box(x - 9.0, y + py - 2.0, FLOOR_Z, x + 9.0, y + py + 2.0, 1.0, 2)
    river = rf.add_object("river", mbw.build("river", [mats["river"], mats["quay"], mats["bridge"]]), col)
    trees = []
    for s in (-1, 1):
        for i in range(0, len(path) - 1):
            (ax, ay), (bx, by) = path[i], path[i + 1]
            seg = math.hypot(bx - ax, by - ay)
            nx, ny = -(by - ay) / seg, (bx - ax) / seg
            for u in np.arange(0, seg, 11.0):
                x = ax + (bx - ax) * u / seg + nx * s * (RIVER_W / 2 + QUAY - 3.0)
                y = ay + (by - ay) * u / seg + ny * s * (RIVER_W / 2 + QUAY - 3.0)
                if math.hypot(x, y) < radius:
                    trees.append((x, y))
    return river, trees


def _trees(col, rnd, spots, mats, name):
    """Many low trees merged into one mesh (about 100 triangles each)."""
    mb = rf.MeshBuilder()
    for x, y in spots:
        _tree(mb, rnd, x, y, 0, 1, h=rnd.uniform(9.0, 14.0), sub=1, puffs=3)
    me = mb.build(name, [mats["trunk"], mats["city_leaf"]])
    return rf.add_object(name, me, col)


# ---------------------------------------------------------------- crowds

def _crowds(col, rnd, camera, W, hero_xy):
    """The hero ("you"), the square's crowd (join order: nearest the hero first) and the ring-road and avenue
    crowds (order: nearest the square first)."""
    hx, hy = hero_xy
    hero = crowd.person(rnd, hx, hy, yaw=math.pi, idle=crowd.STAND, size=1.0, shirt=(0.74, 0.07, 0.05), tone=0.64,
                        react=0.0, phase=0.2)
    hero_ob = crowd.add_crowd(col, [hero], "crowd_hero", camera=camera)
    trees = [(x, y, 1.7) for x in np.arange(-60, 61, 12.0) for y in (-SQ_D / 2 + 6, SQ_D / 2 - 6)]
    lamps = [(x, y, 0.5) for x in np.arange(-63, 64, 18.0) for y in (-SQ_D / 2 + 1.5, SQ_D / 2 - 1.5)] + \
        [(x, y, 0.5) for x in (-SQ_W / 2 + 1.5, SQ_W / 2 - 1.5) for y in np.arange(-40, 41, 16.0)]
    benches = [(x, y, 1.0) for x in np.arange(-54, 55, 12.0) for y in (-SQ_D / 2 + 3.2, SQ_D / 2 - 3.2)]
    avoid = [(0.0, 0.0, FOUNTAIN_R + 0.8), (hx, hy, 1.6)] + trees + lamps + benches
    density = float(W.get("density", 2.2))
    far = math.hypot(SQ_W / 2 + abs(hx), SQ_D / 2 + abs(hy))
    # you stand at the crowd's front edge: in front of you the square stays clear, so low cameras have room
    front_y = hy - float(W.get("front", 1.0))

    def order_sq(x, y):
        d = math.hypot(x - hx, y - hy)
        return min(1.0, max(0.0, (d / far) ** 0.85 + rnd.uniform(-0.03, 0.03)))

    sq = crowd.scatter(rnd, -SQ_W / 2 + 0.6, front_y, SQ_W / 2 - 0.6, SQ_D / 2 - 0.6, density, avoid=avoid,
                       join_fn=order_sq, face=(hx, hy - 60.0))
    out = [{"name": "square", "object": crowd.add_crowd(col, sq, "crowd_square", camera=camera),
            "order": np.array([p.join for p in sq]), "n": len(sq)}]

    d2 = float(W.get("streets", 1.8))
    if d2 > 0:
        x_out, y_out = SQ_W / 2 + ROAD, SQ_D / 2 + ROAD
        reach = AVENUE_LEN - 20.0

        def order_st(x, y):
            return min(1.0, max(0.0, (math.hypot(x, y) - 60.0) / (reach - 60.0) + rnd.uniform(-0.02, 0.02)))

        strips = [(-x_out, SQ_D / 2 + 0.5, x_out, y_out), (-x_out, -y_out, x_out, -SQ_D / 2 - 0.5),
                  (SQ_W / 2 + 0.5, -SQ_D / 2, x_out, SQ_D / 2), (-x_out, -SQ_D / 2, -SQ_W / 2 - 0.5, SQ_D / 2),
                  (-AVENUE / 2 + 1, y_out, AVENUE / 2 - 1, reach), (-AVENUE / 2 + 1, -reach, AVENUE / 2 - 1, -y_out),
                  (x_out, -AVENUE / 2 + 1, reach, AVENUE / 2 - 1), (-reach, -AVENUE / 2 + 1, -x_out, AVENUE / 2 - 1)]
        st = []
        av_trees = [(sx * (AVENUE / 2 - 2.5), y) for sx in (-1, 1) for y in np.arange(SQ_D / 2 + ROAD + 12, reach, 10.0)]
        av_trees += [(sx * (AVENUE / 2 - 2.5), -y) for sx in (-1, 1) for y in np.arange(SQ_D / 2 + ROAD + 12, reach, 10.0)]
        av_trees += [(x, sy * (AVENUE / 2 - 2.5)) for sy in (-1, 1) for x in np.arange(SQ_W / 2 + ROAD + 12, reach, 10.0)]
        av_trees += [(-x, sy * (AVENUE / 2 - 2.5)) for sy in (-1, 1) for x in np.arange(SQ_W / 2 + ROAD + 12, reach, 10.0)]
        for x0, y0, x1, y1 in strips:
            st += crowd.scatter(rnd, x0, y0, x1, y1, d2, join_fn=order_st, face=(0.0, 0.0),
                                avoid=[(x, y, 1.0) for x, y in av_trees])
        out.append({"name": "streets", "object": crowd.add_crowd(col, st, "crowd_streets", camera=camera),
                    "order": np.array([p.join for p in st]), "n": len(st)})
    return {"object": hero_ob, "person": hero, "pos": (hx, hy)}, out


def _avenue_trees():
    spots = []
    for y in np.arange(SQ_D / 2 + ROAD + 12, AVENUE_LEN - 10, 10.0):
        for sx in (-1, 1):
            spots += [(sx * (AVENUE / 2 - 2.5), y), (sx * (AVENUE / 2 - 2.5), -y)]
    for x in np.arange(SQ_W / 2 + ROAD + 12, AVENUE_LEN - 10, 10.0):
        for sy in (-1, 1):
            spots += [(x, sy * (AVENUE / 2 - 2.5)), (-x, sy * (AVENUE / 2 - 2.5))]
    return spots


# ---------------------------------------------------------------- builder

def build(spec):
    W = spec.get("world", {})
    rnd = random.Random(W.get("seed", 7))
    scene = bpy.context.scene
    sun_cfg = W.get("sun", {})
    heading, elevation = float(sun_cfg.get("heading", 245.0)), float(sun_cfg.get("elevation", 24.0))
    sun_dir = look.sun_vector(heading, elevation)
    home = W.get("home", [48.86, 2.35])

    cols = {k: rf.new_collection(k) for k in ("hero", "square", "city", "planet", "sky", "people")}
    world = look.setup_sky(scene, heading, elevation, gain=0.16, dust=1.2)
    look.add_space_sun(world, sun_dir)
    sun = look.add_sun(cols["sky"], heading, elevation, energy=4.6, color=(1.0, 0.86, 0.68))
    look.init_haze(scene, sun_dir, dist=9000.0, hmax=0.8)
    look.add_bloom(scene, threshold=0.9, size=7, mix=-0.6)
    for prop, val in (("rf_fill_r", 0.0), ("rf_lights", 0.0), ("rf_glow", 0.0), ("rf_globe_a", 0.0), ("rf_time", 0.0)):
        scene[prop] = val
    hero_xy = tuple(W.get("hero", [0.0, -15.0]))
    cam = rf.add_camera(cols["hero"], (hero_xy[0] + 1.2, hero_xy[1] - 6.5, 1.2), 0.0, 0.0, 32.0)
    cam.data.clip_start = 0.05
    cam.data.clip_end = 60_000.0

    mats = {
        "mixed": facades.building_material("rf_bldg_mixed", kind="mixed", lit=0.12),
        "stone": facades.building_material("rf_bldg_stone", kind="stone", lit=0.12),
        "glass": facades.building_material("rf_bldg_glass", kind="glass", lit=0.08),
        "trim": facades.solid_material("rf_trim", (0.62, 0.58, 0.52), rough=0.7),
        "zinc": zinc_material(), "roof": roof_material(),
        "chimney": facades.solid_material("rf_chimney", (0.42, 0.24, 0.17), rough=0.8),
        "dark": facades.solid_material("rf_dormer_glass", (0.02, 0.025, 0.03), rough=0.15),
        "far": far_city_material(),
        "river": river_material(), "quay": stone_material("rf_quay", (0.55, 0.52, 0.46)),
        "bridge": stone_material("rf_bridge", (0.62, 0.58, 0.50)),
        "trunk": facades.solid_material("rf_trunk", (0.16, 0.11, 0.07), rough=0.9),
        "city_leaf": leaf_material("rf_city_leaves", 0.08), "grass": grass_material(),
    }

    # ---- the square
    mb = rf.MeshBuilder()
    PAVE, ASPH, CONC, STONE, WATER, DARK, METAL, GLASS, TRUNK, LEAF, PLANTER, SOIL, MARK, WOOD, FALL = range(15)
    mb.box(-SQ_W / 2, -SQ_D / 2, 0.0, SQ_W / 2, SQ_D / 2, 0.12, PAVE)
    xo, yo = SQ_W / 2 + ROAD, SQ_D / 2 + ROAD
    for x0, y0, x1, y1 in ((-xo, SQ_D / 2, xo, yo), (-xo, -yo, xo, -SQ_D / 2), (SQ_W / 2, -SQ_D / 2, xo, SQ_D / 2),
                           (-xo, -SQ_D / 2, -SQ_W / 2, SQ_D / 2)):
        mb.box(x0, y0, -0.02, x1, y1, 0.0, ASPH)
    xw, yw = xo + WALK, yo + WALK
    for x0, y0, x1, y1 in ((-xw, yo, xw, yw), (-xw, -yw, xw, -yo), (xo, -yo, xw, yo), (-xw, -yo, -xo, yo)):
        mb.box(x0, y0, 0.0, x1, y1, 0.15, CONC)
    road = AVENUE / 2 - 4.0
    for sgn in (1, -1):
        y0, y1 = (yw, AVENUE_LEN) if sgn > 0 else (-AVENUE_LEN, -yw)
        x0, x1 = (xw, AVENUE_LEN) if sgn > 0 else (-AVENUE_LEN, -xw)
        mb.box(-road, y0, -0.02, road, y1, 0.0, ASPH)
        mb.box(x0, -road, -0.02, x1, road, 0.0, ASPH)
        for s2 in (-1, 1):
            a, b = sorted((s2 * road, s2 * AVENUE / 2))
            mb.box(a, y0, 0.0, b, y1, 0.15, CONC)
            mb.box(x0, a, 0.0, x1, b, 0.15, CONC)
    for k in range(-14, 15):                                   # lane marks on the ring road
        x = k * 6.0
        for y in (SQ_D / 2 + ROAD / 2, -SQ_D / 2 - ROAD / 2):
            mb.box(x - 1.5, y - 0.07, 0.0, x + 1.5, y + 0.07, 0.006, MARK)
    _fountain(mb, STONE, WATER, DARK, FALL)
    for x in np.arange(-63, 64, 18.0):
        for y in (-SQ_D / 2 + 1.5, SQ_D / 2 - 1.5):
            _lamp(mb, x, y, METAL, GLASS)
    for x in (-SQ_W / 2 + 1.5, SQ_W / 2 - 1.5):
        for y in np.arange(-40, 41, 16.0):
            _lamp(mb, x, y, METAL, GLASS)
    for x in np.arange(-60, 61, 12.0):
        for y in (-SQ_D / 2 + 6, SQ_D / 2 - 6):
            _tree(mb, rnd, x, y, TRUNK, LEAF, PLANTER, SOIL)
    for x in np.arange(-54, 55, 12.0):
        for y in (-SQ_D / 2 + 3.2, SQ_D / 2 - 3.2):
            _bench(mb, x, y, WOOD, METAL)
    sq_mats = [paving_material(), asphalt_material(), concrete_material(), stone_material("rf_fountain_stone"),
               water_material(), facades.solid_material("rf_bronze", (0.16, 0.11, 0.06), rough=0.35, metallic=0.8),
               facades.solid_material("rf_lamp_metal", (0.03, 0.035, 0.04), rough=0.4, metallic=0.6),
               lantern_material(), mats["trunk"], leaf_material(),
               facades.solid_material("rf_planter", (0.30, 0.29, 0.27), rough=0.8),
               facades.solid_material("rf_soil", (0.08, 0.06, 0.04), rough=1.0),
               facades.solid_material("rf_lane_mark", (0.85, 0.85, 0.80), rough=0.6),
               facades.solid_material("rf_bench_wood", (0.30, 0.18, 0.09), rough=0.7), falling_water_material()]
    square = rf.add_object("square", mb.build("square", sq_mats, smooth=False), cols["square"])
    sq_bldgs = _square_buildings(cols["square"], rnd, mats)

    # ---- the city, its river, parks and trees, and its floor (a disc; the planet's suburbs carry on beyond it)
    radius = float(W.get("city_radius", 6500.0))
    has_river = W.get("river", True)
    near_obs, far_obs, parks = _city(cols["city"], rnd, mats, radius, has_river)
    extra = []
    tree_spots = _avenue_trees()
    if has_river:
        river, river_trees = _river(cols["city"], rnd, mats, radius)
        extra.append(river)
        tree_spots += river_trees
    mbp = rf.MeshBuilder()
    for x0, y0, x1, y1 in parks:
        mbp.box(x0, y0, FLOOR_Z, x1, y1, 0.06, 0)
        for _ in range(int((x1 - x0) * (y1 - y0) / 220)):
            tree_spots.append((rnd.uniform(x0 + 4, x1 - 4), rnd.uniform(y0 + 4, y1 - 4)))
    if parks:
        extra.append(rf.add_object("parks", mbp.build("parks", [mats["grass"]]), cols["city"]))
    extra.append(_trees(cols["city"], rnd, tree_spots, mats, "city_trees"))
    fr = radius * 1.3 + 600.0
    seg = 128
    verts = [(0.0, 0.0, FLOOR_Z)] + [(fr * math.cos(2 * math.pi * k / seg), fr * math.sin(2 * math.pi * k / seg), FLOOR_Z)
                                     for k in range(seg)]
    me = bpy.data.meshes.new("city_floor")
    me.from_pydata(verts, [], [(0, 1 + k, 1 + (k + 1) % seg) for k in range(seg)])
    me.materials.append(city_floor_material(radius))
    me.update()
    floor = rf.add_object("city_floor", me, cols["city"])

    # ---- the planet under it all, and low clouds round the city
    planet = globe.build(cols["planet"], float(home[0]), float(home[1]), sun_dir, drop=2.0)
    low_clouds = []
    if W.get("clouds", True):
        low_clouds = nature.cloud_field(cols["sky"], seed=W.get("seed", 7) + 3, base=1800.0, top=2300.0,
                                        extent=26000.0, tile=4000.0, clear=(0.0, 0.0, 7000.0), coverage=0.32,
                                        near=11000.0, mid=18000.0)

    # ---- people
    hero, crowds = _crowds(cols["people"], rnd, cam, W, hero_xy)
    print(f"[plaza] square people={crowds[0]['n']} street people={crowds[1]['n'] if len(crowds) > 1 else 0} "
          f"near buildings={len(near_obs)} far meshes={len(far_obs)} parks={len(parks)} trees={len(tree_spots)} "
          f"clouds={len(low_clouds)}")

    crowd_objects = [hero["object"]] + [c["object"] for c in crowds]
    flat = [square, floor] + sq_bldgs + near_obs + far_obs + extra
    return {"scene": scene, "world": world, "sun": sun, "sun_dir": tuple(sun_dir), "camera": cam,
            "collections": cols, "hero": hero, "crowds": crowds, "crowd_objects": crowd_objects,
            "city_radius": radius, "fill_from": AVENUE_LEN, "planet": planet, "flat": flat, "low_clouds": low_clouds,
            "home": (float(home[0]), float(home[1])), "square": (SQ_W, SQ_D), "fountain": (0.0, 0.0, FOUNTAIN_R)}
