"""An airliner (64 m twin-jet, origin at its centre, nose along +Y) with navigation lights and contrails, and the
spacecraft that 'past the space station / satellites' lines point at:
  airliner(collection) -> {"plane", "contrail"}
  iss(collection), gps_satellite(collection), geo_satellite(collection) -> object
"""
import math

import bpy

import rf_common as rf
from parts.car import _set


def _mat(name, color, rough=0.4, metallic=0.0, emission=None, haze=1.0):
    return rf.make_material(name, color, rough=rough, metallic=metallic, emission=emission, haze=haze, glitch=False)


def airliner(collection):
    body = _mat("plane_body", (0.86, 0.87, 0.9), 0.3, 0.1)
    wing = _mat("plane_wing", (0.62, 0.64, 0.68), 0.35, 0.3)
    dark = _mat("plane_windows", (0.03, 0.035, 0.05), 0.2)
    tail = _mat("plane_tail", (0.06, 0.16, 0.45), 0.35)
    red = _mat("plane_nav_red", (0.3, 0, 0), emission=((1.0, 0.05, 0.03), 40.0), haze=0.3)
    green = _mat("plane_nav_green", (0, 0.3, 0), emission=((0.1, 1.0, 0.3), 40.0), haze=0.3)
    white = _mat("plane_strobe", (1, 1, 1), emission=((1.0, 1.0, 1.0), 60.0), haze=0.3)
    BODY, WING, DARK, TAIL, RED, GREEN, WHITE = range(7)
    mb = rf.MeshBuilder()
    seg = 16
    prof = [(32.0, 0.15, 0.0), (31.0, 1.2, -0.2), (29.5, 2.2, -0.15), (27.0, 2.8, 0.0), (22.0, 2.95, 0.0),
            (-18.0, 2.95, 0.0), (-24.0, 2.6, 0.35), (-28.5, 1.8, 0.9), (-31.5, 0.8, 1.5), (-32.5, 0.25, 1.8)]
    secs = [(y, [(r * math.cos(2 * math.pi * k / seg), zc + r * math.sin(2 * math.pi * k / seg)) for k in range(seg)])
            for y, r, zc in prof]

    def body_mat(s, k):
        # a dark window band along each side (points 1 and 7 of 16 sit near the band height)
        return DARK if (1 <= s <= 6 and k in (1, 7)) else BODY

    mb.loft(secs, body_mat, cap_mat=BODY)
    # wings: swept, tapered slabs with a little dihedral
    for sx in (-1, 1):
        root_le, root_te, tip_le, tip_te = 8.0, -4.0, -9.5, -12.5
        x_root, x_tip = 2.6, 32.0
        z_root, z_tip = -1.6, 0.6
        v = [(sx * x_root, root_le, z_root), (sx * x_tip, tip_le, z_tip), (sx * x_tip, tip_te, z_tip),
             (sx * x_root, root_te, z_root)]
        b = len(mb.verts)
        for (x, y, z) in v:
            mb.verts.append((x, y, z + 0.35))
        for (x, y, z) in v:
            mb.verts.append((x, y, z - 0.35))
        quads = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
        for q in quads:
            mb.faces.append(tuple(b + i for i in q))
            mb.mats.append(WING)
        # engine nacelle under the wing
        ex, ey = sx * 10.5, 4.5
        nacelle = [(ey + 3.5, 1.3), (ey + 3.0, 1.65), (ey - 1.5, 1.6), (ey - 3.5, 1.1)]
        nsecs = [(y, [(ex + r * math.cos(2 * math.pi * k / 12), -2.6 + r * math.sin(2 * math.pi * k / 12)) for k in range(12)])
                 for y, r in nacelle]
        mb.loft(nsecs, lambda s, k: WING, cap_mat=DARK)
        # wingtip lights
        mb.box(sx * 32.0 - 0.3, -11.6, 0.6, sx * 32.0 + 0.3, -10.8, 1.2, GREEN if sx > 0 else RED)
    # tail: horizontal stabiliser and fin
    for sx in (-1, 1):
        v = [(sx * 1.0, -25.0, 1.6), (sx * 10.5, -31.0, 2.4), (sx * 10.5, -33.0, 2.4), (sx * 1.0, -31.5, 1.6)]
        b = len(mb.verts)
        for (x, y, z) in v:
            mb.verts.append((x, y, z + 0.25))
        for (x, y, z) in v:
            mb.verts.append((x, y, z - 0.25))
        for q in [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
            mb.faces.append(tuple(b + i for i in (q if sx > 0 else q[::-1])))
            mb.mats.append(WING)
    v = [(0.0, -22.0, 2.5), (0.0, -30.0, 11.0), (0.0, -33.5, 11.0), (0.0, -32.0, 2.0)]
    b = len(mb.verts)
    for (x, y, z) in v:
        mb.verts.append((0.25, y, z))
    for (x, y, z) in v:
        mb.verts.append((-0.25, y, z))
    for q in [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]:
        mb.faces.append(tuple(b + i for i in q))
        mb.mats.append(TAIL)
    mb.box(-0.3, -33.8, 10.6, 0.3, -33.2, 11.2, WHITE)
    plane = rf.add_object("airliner", mb.build("airliner", [body, wing, dark, tail, red, green, white], fix_normals=True),
                          collection)
    # contrails: two long tapered tubes behind the engines, fading with distance from the plane
    cmat = bpy.data.materials.new("contrail")
    cmat.use_nodes = True
    nt = rf.NodeTree(cmat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    length = 6000.0
    fade = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", nt.math("MULTIPLY", sep.outputs["Y"], -1.0), length, clamp=True))
    start = nt.math("DIVIDE", nt.math("MULTIPLY", sep.outputs["Y"], -1.0), 60.0, clamp=True)
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 0.02
    n.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    a = nt.math("MULTIPLY", nt.math("MULTIPLY", fade, start), nt.math("ADD", 0.45, nt.math("MULTIPLY", n.outputs["Fac"], 0.6)))
    bsdf = nt.node("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.97, 1.0)
    bsdf.inputs["Roughness"].default_value = 1.0
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.85, 0.75, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.4
    nt.links.new(nt.math("MINIMUM", a, 0.85), bsdf.inputs["Alpha"])
    shader = rf.scene_haze(nt, bsdf.outputs[0], 0.8) if rf.HAZE_SCENE else bsdf.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    _set(cmat, surface_render_method="BLENDED", use_backface_culling=False)
    cb = rf.MeshBuilder()
    for sx in (-1, 1):
        secs = []
        for y, r in ((-6.0, 0.6), (-200.0, 4.0), (-1200.0, 14.0), (-length, 40.0)):
            secs.append((y, [(sx * 10.5 + r * math.cos(2 * math.pi * k / 10), -2.6 + r * math.sin(2 * math.pi * k / 10))
                             for k in range(10)]))
        cb.loft(secs, lambda s, k: 0, cap=False)
    contrail = rf.add_object("contrail", cb.build("contrail", [cmat]), collection)
    contrail.parent = plane
    for ob in (plane, contrail):
        try:
            ob.visible_shadow = False
        except AttributeError:
            pass
    return {"plane": plane, "contrail": contrail}


def _space_mats():
    gold = _mat("mli_gold", (0.85, 0.58, 0.16), 0.3, 1.0, haze=0.0)
    white = _mat("sat_white", (0.85, 0.85, 0.85), 0.4, 0.0, haze=0.0)
    panel = rf.make_material("solar_panel", lambda nt: _panel_color(nt), rough=0.25, metallic=0.5, haze=0.0, glitch=False)
    return gold, white, panel


def _panel_color(nt):
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    gx = nt.math("LESS_THAN", nt.math("FRACT", nt.math("DIVIDE", sep.outputs["X"], 1.2)), 0.06)
    gy = nt.math("LESS_THAN", nt.math("FRACT", nt.math("DIVIDE", sep.outputs["Y"], 1.2)), 0.06)
    grid = nt.math("MAXIMUM", gx, gy)
    return nt.mix_color(grid, (0.05, 0.07, 0.18, 1.0), (0.75, 0.7, 0.55, 1.0))


def iss(collection):
    gold, white, panel = _space_mats()
    W, G, P = 1, 0, 2
    mb = rf.MeshBuilder()
    mb.box(-54, -1.4, -1.4, 54, 1.4, 1.4, W)                     # integrated truss, 109 m
    for y0, y1, r in ((-26, -10, 2.2), (-10, 6, 2.2), (6, 18, 2.1), (18, 30, 2.0)):
        mb.loft([(y0, [(r * math.cos(2 * math.pi * k / 12), r * math.sin(2 * math.pi * k / 12)) for k in range(12)]),
                 (y1, [(r * math.cos(2 * math.pi * k / 12), r * math.sin(2 * math.pi * k / 12)) for k in range(12)])],
                lambda s, k: W, cap_mat=W)
    for x in (-46, -34, 34, 46):
        for s in (-1, 1):
            mb.box(x - 5.8, s * 2.5, -0.08, x + 5.8, s * 36, 0.08, P)  # solar array wings
    for x in (-20, 20):
        mb.box(x - 6, -1.2, -12, x + 6, 1.2, -1.4, W)              # radiators
    ob = rf.add_object("iss", mb.build("iss", [gold, white, panel], fix_normals=True), collection)
    return ob


def gps_satellite(collection):
    gold, white, panel = _space_mats()
    mb = rf.MeshBuilder()
    mb.box(-1.0, -1.0, -1.25, 1.0, 1.0, 1.25, 0)
    mb.box(-0.6, -0.6, -1.6, 0.6, 0.6, -1.25, 1)
    for s in (-1, 1):
        mb.box(s * 1.0, -0.06, -0.06, s * 1.6, 0.06, 0.06, 1)
        mb.box(s * 1.6, -1.1, -0.05, s * 7.0, 1.1, 0.05, 2)
    return rf.add_object("gps_sat", mb.build("gps_sat", [gold, white, panel], fix_normals=True), collection)


def geo_satellite(collection):
    gold, white, panel = _space_mats()
    mb = rf.MeshBuilder()
    mb.box(-1.5, -1.5, -2.0, 1.5, 1.5, 2.0, 0)
    for s in (-1, 1):
        mb.box(s * 1.5, -0.08, -0.08, s * 2.4, 0.08, 0.08, 1)
        mb.box(s * 2.4, -1.3, -0.05, s * 15.0, 1.3, 0.05, 2)
    mb.cyl(0, 0, 2.0, 2.6, 1.6, 16, 1, r_top=0.3)                  # dish
    return rf.add_object("geo_sat", mb.build("geo_sat", [gold, white, panel], fix_normals=True), collection)
