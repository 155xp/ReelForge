"""Growable hero subjects for the doubling effects: close-up quality, one unit in size, origin at the centre of the
base (scale the object by a size in metres and it stands on the ground at its location).

  build(name, collection) -> dict      name: one of NAMES
  NAMES                                {name: what one unit measures}

Subjects (each faces +Y; materials carry the 'missing texture' flash, obj["glitch"] 0..1):
  "duck"         classic yellow bath duck: blended head/chest/body/tail and wings (metaballs), orange two-part beak,
                 painted cartoon eyes, the moulding seam down its middle, glossy vinyl. Unit = its height.
  "donut"        fried ring with a pink glaze shell (rounded edge, drips), ~240 sprinkles in six colours, a pale
                 frying ring round its middle. Unit = its outer diameter.
  "soccer_ball"  truncated icosahedron (12 black pentagons, 20 white hexagons) with puffed panels, sunken seams and
                 a leather grain. Unit = its diameter.
  "beach_ball"   six glossy vinyl gores (red, yellow, blue, white, green, orange), white caps, a valve. Unit = its
                 diameter.

The dict:
  "object"      the mesh object (origin at the base centre, z up, facing +Y)
  "name"        e.g. "duck";  "label": e.g. "RUBBER DUCK" (for HUD/tags)
  "size_of"     what one unit measures: "height" or "diameter"
  "height", "width", "length"   bounding size in units (x, y = width, length)
  "top"         (x, y, z) of the highest point in units (the duck's crown), e.g. for a "reaches the Moon" contact
  "footprint"   (ax, ay, cy): half-width, half-length and y-offset of the widest horizontal section below 62 % of
                the height, per unit; the ellipse an effect uses to decide what the subject is pushing over
  "radius"      the largest distance of any point from the origin (units), for clip planes and screen boxes
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

import rf_common as rf

NAMES = {"duck": "height", "donut": "diameter", "soccer_ball": "diameter", "beach_ball": "diameter"}
LABELS = {"duck": "RUBBER DUCK", "donut": "DONUT", "soccer_ball": "SOCCER BALL", "beach_ball": "BEACH BALL"}


# ---------------------------------------------------------------- shared helpers

def _bsdf(mat):
    nt = rf.NodeTree(mat.node_tree)
    return nt, next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def _set(bsdf, **kw):
    """Set Principled inputs by name (underscores for spaces), skipping any this Blender doesn't have."""
    for k, v in kw.items():
        name = k.replace("_", " ")
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = v


def _obj_xyz(nt):
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    return tc, sep


def _smooth_mask(nt, value, lo, hi):
    """1 below lo, 0 above hi, smooth in between (a soft-edged 'inside' mask)."""
    mr = nt.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    nt.feed(mr.inputs["Value"], value)
    mr.inputs["From Min"].default_value = lo
    mr.inputs["From Max"].default_value = hi
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.0
    return mr.outputs["Result"]


def _dist(nt, vec, point):
    d = nt.node("ShaderNodeVectorMath", operation="DISTANCE")
    nt.links.new(vec, d.inputs[0])
    d.inputs[1].default_value = tuple(point)
    return d.outputs["Value"]


def _bump(nt, bsdf, height, strength=0.3, distance=0.01):
    b = nt.node("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = distance
    nt.feed(b.inputs["Height"], height)
    nt.links.new(b.outputs["Normal"], bsdf.inputs["Normal"])
    if "Coat Normal" in bsdf.inputs:
        nt.links.new(b.outputs["Normal"], bsdf.inputs["Coat Normal"])
    return b


def _noise(nt, vec, scale, detail=4.0, rough=0.5):
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def _finish(name, me, collection, info):
    """Common tail: object at the origin, glitch prop, smooth shading, and the measured extents."""
    ob = rf.add_object(name, me, collection)
    ob["glitch"] = 0.0
    v = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", v)
    v = v.reshape(-1, 3)
    low = v[v[:, 2] < 0.62 * v[:, 2].max()]
    k = int(np.argmax(v[:, 2]))
    info.update({
        "object": ob,
        "height": float(v[:, 2].max() - v[:, 2].min()),
        "width": float(v[:, 0].max() - v[:, 0].min()),
        "length": float(v[:, 1].max() - v[:, 1].min()),
        "top": tuple(float(c) for c in v[k]),
        "footprint": (float(np.abs(low[:, 0]).max()), float((low[:, 1].max() - low[:, 1].min()) / 2),
                      float((low[:, 1].max() + low[:, 1].min()) / 2)),
        "radius": float(np.linalg.norm(v, axis=1).max()),
    })
    return info


# ---------------------------------------------------------------- rubber duck

# a lone metaball's surface radius / its element radius (stiffness 2, threshold 0.6)
_ISO = math.sqrt(1.0 - (0.6 / 2.0) ** (1.0 / 3.0))


def _metaball_mesh(name, elements, resolution):
    """Polygonise metaball elements [(type, centre, semi_axes, euler_deg, stiffness)] into a mesh. semi_axes are
    the surface's semi-axes for a lone element (stiffness 2); nearby elements blend into smooth fillets."""
    mb = bpy.data.metaballs.new(name)
    mb.resolution = resolution
    mb.render_resolution = resolution
    mb.threshold = 0.6
    for kind, co, semi, rot, stiff in elements:
        el = mb.elements.new(type=kind)
        el.co = co
        el.radius = 1.0
        el.stiffness = stiff
        sx, sy, sz = (a / _ISO for a in semi)
        if kind == "ELLIPSOID":
            el.size_x, el.size_y, el.size_z = sx, sy, sz
        else:
            el.radius = sx
        if rot:
            el.rotation = Euler(tuple(math.radians(a) for a in rot), "XYZ").to_quaternion()
    ob = bpy.data.objects.new(name, mb)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(deps))
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.metaballs.remove(mb)
    return me


# design coordinates (facing +Y, roughly 1 tall); normalised to height 1 with the base centre at the origin below
_DUCK_BODY = [
    ("ELLIPSOID", (0.0, 0.0, 0.30), (0.385, 0.44, 0.275), None, 2.0),            # hull
    ("ELLIPSOID", (0.0, -0.22, 0.33), (0.30, 0.30, 0.235), None, 2.0),           # back, narrowing to the tail
    ("ELLIPSOID", (0.0, 0.20, 0.31), (0.30, 0.25, 0.255), None, 2.0),            # chest
    ("ELLIPSOID", (0.0, -0.45, 0.475), (0.135, 0.20, 0.09), (-40, 0, 0), 2.2),   # tail, tipped up
    ("ELLIPSOID", (0.0, 0.13, 0.54), (0.175, 0.16, 0.15), None, 1.6),             # neck
    ("BALL", (0.0, 0.15, 0.75), (0.258, 0.258, 0.258), None, 2.0),               # head
    ("ELLIPSOID", (0.11, 0.25, 0.70), (0.10, 0.09, 0.085), None, 1.2),            # cheeks
    ("ELLIPSOID", (-0.11, 0.25, 0.70), (0.10, 0.09, 0.085), None, 1.2),
    ("ELLIPSOID", (0.335, -0.03, 0.40), (0.04, 0.19, 0.09), (-12, 0, 4), 1.1),    # wings: a soft ridge on each side
    ("ELLIPSOID", (-0.335, -0.03, 0.40), (0.04, 0.19, 0.09), (-12, 0, -4), 1.1),
]
_DUCK_BEAK = [
    ("ELLIPSOID", (0.0, 0.405, 0.705), (0.125, 0.125, 0.047), (-9, 0, 0), 2.0),   # upper mandible
    ("ELLIPSOID", (0.0, 0.375, 0.648), (0.105, 0.10, 0.034), (-4, 0, 0), 2.0),    # lower mandible
]
_EYE_DIR = Vector((0.60, 0.70, 0.33)).normalized()           # from the head centre, before mirroring


def _duck_materials(eye, pupil, glint, seam_w):
    store = {}

    def base(nt):
        tc, sep = _obj_xyz(nt)
        ax = nt.math("ABSOLUTE", sep.outputs["X"])
        mirrored = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(ax, mirrored.inputs["X"])
        nt.links.new(sep.outputs["Y"], mirrored.inputs["Y"])
        nt.links.new(sep.outputs["Z"], mirrored.inputs["Z"])
        p = mirrored.outputs["Vector"]
        white = _smooth_mask(nt, _dist(nt, p, eye[0]), eye[1] - 0.003, eye[1] + 0.003)
        black = _smooth_mask(nt, _dist(nt, p, pupil[0]), pupil[1] - 0.003, pupil[1] + 0.003)
        shine = _smooth_mask(nt, _dist(nt, p, glint[0]), glint[1] - 0.002, glint[1] + 0.002)
        # vinyl: a faint mottle so the big flat-lit areas aren't a single flat yellow
        mott = _noise(nt, tc.outputs["Object"], 9.0, 3.0)
        col = nt.mix_color(nt.math("MULTIPLY", mott, 0.35), (1.0, 0.63, 0.0, 1.0), (1.0, 0.53, 0.0, 1.0))
        col = nt.mix_color(white, col, (0.93, 0.93, 0.9, 1.0))
        col = nt.mix_color(black, col, (0.008, 0.008, 0.01, 1.0))
        col = nt.mix_color(shine, col, (1.0, 1.0, 1.0, 1.0))
        store["paint"] = nt.math("MAXIMUM", white, black)
        store["x"] = ax
        store["obj"] = tc.outputs["Object"]
        return col

    def rough(nt):
        return nt.math("SUBTRACT", 0.36, nt.math("MULTIPLY", store["paint"], 0.24))

    body = rf.make_material("duck_vinyl", base, rough=rough, haze=0.1, glitch=True)
    nt, b = _bsdf(body)
    _set(b, Coat_Weight=0.4, Coat_Roughness=0.1, Subsurface_Weight=0.06, Subsurface_Scale=0.02,
         Subsurface_Radius=(1.0, 0.45, 0.1), Specular_IOR_Level=0.5)
    # the moulding seam down its middle (a fine raised ridge) and a soft-touch grain
    seam = _smooth_mask(nt, store["x"], seam_w * 0.25, seam_w)
    grain = nt.math("MULTIPLY", _noise(nt, store["obj"], 220.0, 2.0), 0.15)
    _bump(nt, b, nt.math("ADD", nt.math("MULTIPLY", seam, 0.6), grain), strength=0.25, distance=0.004)

    def beak_base(nt):
        tc, sep = _obj_xyz(nt)
        mott = _noise(nt, tc.outputs["Object"], 14.0, 3.0)
        return nt.mix_color(nt.math("MULTIPLY", mott, 0.4), (1.0, 0.30, 0.012, 1.0), (0.92, 0.2, 0.01, 1.0))

    beak = rf.make_material("duck_beak", beak_base, rough=0.3, haze=0.1, glitch=True)
    nt2, b2 = _bsdf(beak)
    _set(b2, Coat_Weight=0.45, Coat_Roughness=0.1, Subsurface_Weight=0.1, Subsurface_Scale=0.02,
         Subsurface_Radius=(1.0, 0.35, 0.1))
    return [body, beak]


def duck(collection, resolution=0.0105):
    body = _metaball_mesh("duck_body_mb", _DUCK_BODY, resolution)
    beak = _metaball_mesh("duck_beak_mb", _DUCK_BEAK, resolution)
    bm = bmesh.new()
    bm.from_mesh(body)
    n_body = len(bm.faces)
    bm.from_mesh(beak)
    bm.faces.ensure_lookup_table()
    for i in range(n_body, len(bm.faces)):
        bm.faces[i].material_index = 1
    bpy.data.meshes.remove(body)
    bpy.data.meshes.remove(beak)
    # a flat base (it floats, and it has to stand on a road), then normalise: height 1, base centre at the origin
    z_floor = 0.055
    for v in bm.verts:
        if v.co.z < z_floor:
            v.co.z = z_floor
    zs = [v.co.z for v in bm.verts]
    top = max(zs)
    base_ys = [v.co.y for v in bm.verts if v.co.z < z_floor + 1e-5]
    yc = (min(base_ys) + max(base_ys)) / 2
    k = 1.0 / (top - z_floor)

    def norm(p):
        return Vector(((p[0]) * k, (p[1] - yc) * k, (p[2] - z_floor) * k))

    for v in bm.verts:
        v.co = norm(v.co)
    for f in bm.faces:
        f.smooth = True
    bm.normal_update()
    # painted eyes: find the head surface along the eye direction, then a white eye with a pupil looking forward
    head_c = norm((0.0, 0.15, 0.75))
    best = max(bm.verts, key=lambda v: (v.co - head_c).normalized().dot(_EYE_DIR) if v.co.x > 0 else -2)
    e = best.co.copy()
    out = (e - head_c).normalized()
    fwd = Vector((0.0, 1.0, 0.0))
    side = fwd.cross(out).normalized()
    up = out.cross(side).normalized()
    eye = (tuple(e), 0.072)
    pupil = (tuple(e + up * 0.012 + (fwd - out * fwd.dot(out)).normalized() * 0.022), 0.043)
    glint = (tuple(e + up * 0.032 + (fwd - out * fwd.dot(out)).normalized() * 0.026), 0.012)
    me = bpy.data.meshes.new("duck")
    bm.to_mesh(me)
    bm.free()
    for m in _duck_materials(eye, pupil, glint, seam_w=0.006):
        me.materials.append(m)
    return _finish("duck", me, collection, {"name": "duck", "label": LABELS["duck"], "size_of": "height"})


# ---------------------------------------------------------------- donut

def _donut_materials(R, r, squash):
    def dough(nt):
        tc, sep = _obj_xyz(nt)
        xy = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(sep.outputs["X"], xy.inputs["X"])
        nt.links.new(sep.outputs["Y"], xy.inputs["Y"])
        rho = nt.node("ShaderNodeVectorMath", operation="LENGTH")
        nt.links.new(xy.outputs["Vector"], rho.inputs[0])
        dr = nt.math("SUBTRACT", rho.outputs["Value"], R)
        dz = nt.math("DIVIDE", nt.math("SUBTRACT", sep.outputs["Z"], r * squash), squash)
        cos_t = nt.math("DIVIDE", dr, nt.math("MAXIMUM", nt.math("SQRT", nt.math("ADD", nt.math("MULTIPLY", dr, dr),
                                                                                   nt.math("MULTIPLY", dz, dz))), 1e-4))
        # the pale ring round the outside where it floated in the oil, browner top and bottom
        ring = nt.math("MULTIPLY", nt.math("POWER", nt.math("MAXIMUM", cos_t, 0.0), 7.0),
                       nt.math("ADD", 0.6, nt.math("MULTIPLY", _noise(nt, tc.outputs["Object"], 18.0, 4.0), 0.6)))
        brown = nt.mix_color(_noise(nt, tc.outputs["Object"], 40.0, 6.0), (0.30, 0.12, 0.035, 1.0),
                             (0.52, 0.25, 0.08, 1.0))
        return nt.mix_color(nt.math("MINIMUM", ring, 1.0), brown, (0.92, 0.72, 0.45, 1.0))

    dmat = rf.make_material("donut_dough", dough, rough=0.72, haze=0.1, glitch=True)
    nt, b = _bsdf(dmat)
    tc = nt.node("ShaderNodeTexCoord")
    _bump(nt, b, nt.math("ADD", _noise(nt, tc.outputs["Object"], 60.0, 8.0, 0.7),
                         nt.math("MULTIPLY", _noise(nt, tc.outputs["Object"], 260.0, 2.0), 0.4)), 0.35, 0.006)
    _set(b, Subsurface_Weight=0.15, Subsurface_Scale=0.03, Subsurface_Radius=(1.0, 0.5, 0.25), Sheen_Weight=0.3)

    glaze = rf.make_material("donut_glaze", lambda nt: nt.mix_color(
        _noise(nt, nt.node("ShaderNodeTexCoord").outputs["Object"], 6.0, 3.0), (1.0, 0.30, 0.50, 1.0),
        (1.0, 0.42, 0.62, 1.0)), rough=0.14, haze=0.1, glitch=True)
    nt, b = _bsdf(glaze)
    _set(b, Coat_Weight=0.6, Coat_Roughness=0.05, Subsurface_Weight=0.25, Subsurface_Scale=0.02,
         Subsurface_Radius=(1.0, 0.4, 0.5))
    tc = nt.node("ShaderNodeTexCoord")
    _bump(nt, b, _noise(nt, tc.outputs["Object"], 24.0, 3.0), 0.12, 0.004)
    cols = [(1.0, 0.95, 0.9), (1.0, 0.82, 0.05), (0.05, 0.45, 1.0), (0.1, 0.75, 0.2), (1.0, 0.35, 0.02),
            (0.55, 0.12, 0.85)]
    sprinkles = []
    for k, c in enumerate(cols):
        m = rf.make_material(f"sprinkle_{k}", c, rough=0.35, haze=0.1, glitch=True)
        _set(_bsdf(m)[1], Coat_Weight=0.5, Coat_Roughness=0.15)
        sprinkles.append(m)
    return [dmat, glaze] + sprinkles


def donut(collection, seed=4, n_sprinkles=240):
    rnd = random.Random(seed)
    R, r, squash = 0.32, 0.18, 0.86
    NU, NV = 160, 64
    bump_ph = [rnd.uniform(0, 6.3) for _ in range(4)]

    def tube_r(phi):
        return r * (1.0 + 0.035 * math.sin(3 * phi + bump_ph[0]) + 0.02 * math.sin(7 * phi + bump_ph[1]))

    def point(phi, theta, extra=0.0):
        rr = tube_r(phi) + extra
        x = (R + rr * math.cos(theta))
        z = rr * math.sin(theta) * squash
        return (x * math.cos(phi), x * math.sin(phi), z + r * squash)

    mb = rf.MeshBuilder()
    for i in range(NU):
        for j in range(NV):
            mb.verts.append(point(2 * math.pi * i / NU, 2 * math.pi * j / NV))
    for i in range(NU):
        for j in range(NV):
            a, b_ = i * NV + j, i * NV + (j + 1) % NV
            c, d = ((i + 1) % NU) * NV + (j + 1) % NV, ((i + 1) % NU) * NV + j
            mb.faces.append((a, d, c, b_))
            mb.mats.append(0)

    # glaze shell: from a wavy, dripping edge on the outside over the top to a wavy edge inside the hole
    drips = [(rnd.uniform(0, 2 * math.pi), rnd.uniform(0.05, 0.11), rnd.uniform(0.25, 0.6)) for _ in range(9)]

    def edge_out(phi):
        d = sum(L * math.exp(-((math.atan2(math.sin(phi - p0), math.cos(phi - p0))) / w) ** 2) for p0, w, L in drips)
        return -0.28 - d - 0.06 * math.sin(5 * phi + bump_ph[2])

    def edge_in(phi):
        return math.pi + 0.35 + 0.08 * math.sin(4 * phi + bump_ph[3])

    GU, GV = 200, 44
    T = 0.016
    b0 = len(mb.verts)
    for i in range(GU):
        phi = 2 * math.pi * i / GU
        t0, t1 = edge_out(phi), edge_in(phi)
        for j in range(GV + 1):
            u = j / GV
            th = t0 + (t1 - t0) * u
            e = 0.07
            thick = T * min(1.0, u / e) ** 0.5 * min(1.0, (1.0 - u) / e) ** 0.5 + 0.0015
            mb.verts.append(point(phi, th, thick))
    for i in range(GU):
        for j in range(GV):
            a, b_ = b0 + i * (GV + 1) + j, b0 + i * (GV + 1) + j + 1
            c, d = b0 + ((i + 1) % GU) * (GV + 1) + j + 1, b0 + ((i + 1) % GU) * (GV + 1) + j
            mb.faces.append((a, d, c, b_))
            mb.mats.append(1)

    # sprinkles: little rods lying on the glaze, any direction
    for _ in range(n_sprinkles):
        phi = rnd.uniform(0, 2 * math.pi)
        lo, hi = edge_out(phi) + 0.35, edge_in(phi) - 0.45
        th = rnd.uniform(lo, hi)
        p = Vector(point(phi, th, T + 0.004))
        q = Vector(point(phi, th, T + 0.05))
        n = (q - p).normalized()
        tang = n.orthogonal().normalized()
        ang = rnd.uniform(0, math.pi)
        bit = n.cross(tang)
        d = (tang * math.cos(ang) + bit * math.sin(ang)).normalized()
        L, rad = rnd.uniform(0.045, 0.065) / 2, 0.0085
        mat = 2 + rnd.randrange(6)
        a, c = p - d * L, p + d * L
        u = d.orthogonal().normalized()
        v = d.cross(u)
        seg = 6
        base = len(mb.verts)
        for end in (a, c):
            for kk in range(seg):
                ang2 = 2 * math.pi * kk / seg
                mb.verts.append(tuple(end + (u * math.cos(ang2) + v * math.sin(ang2)) * rad))
        for kk in range(seg):
            k2 = (kk + 1) % seg
            mb.faces.append((base + kk, base + k2, base + seg + k2, base + seg + kk))
            mb.mats.append(mat)
        for end, sgn, off in ((a, -1, 0), (c, 1, seg)):          # rounded ends: a small cone-ish cap
            tip = len(mb.verts)
            mb.verts.append(tuple(end + d * (sgn * rad * 0.9)))
            for kk in range(seg):
                k2 = (kk + 1) % seg
                if sgn > 0:
                    mb.faces.append((base + off + kk, base + off + k2, tip))
                else:
                    mb.faces.append((base + off + k2, base + off + kk, tip))
                mb.mats.append(mat)
    me = mb.build("donut", _donut_materials(R, r, squash), fix_normals=True, smooth=True)
    return _finish("donut", me, collection, {"name": "donut", "label": LABELS["donut"], "size_of": "diameter"})


# ---------------------------------------------------------------- soccer ball

def _icosahedron():
    p = (1 + 5 ** 0.5) / 2
    v = [(-1, p, 0), (1, p, 0), (-1, -p, 0), (1, -p, 0), (0, -1, p), (0, 1, p), (0, -1, -p), (0, 1, -p),
         (p, 0, -1), (p, 0, 1), (-p, 0, -1), (-p, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
         (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
         (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    return [Vector(x).normalized() for x in v], f


def _ball_materials():
    def leather(color):
        def base(nt):
            tc = nt.node("ShaderNodeTexCoord")
            return nt.mix_color(nt.math("MULTIPLY", _noise(nt, tc.outputs["Object"], 30.0, 4.0), 0.2), color,
                                tuple(c * 0.85 for c in color[:3]) + (1.0,))
        m = rf.make_material(f"ball_{'white' if color[0] > 0.5 else 'black'}", base, rough=0.38, haze=0.1, glitch=True)
        nt, b = _bsdf(m)
        tc = nt.node("ShaderNodeTexCoord")
        vor = nt.node("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 160.0
        nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
        _bump(nt, b, vor.outputs["Distance"], 0.18, 0.002)
        _set(b, Coat_Weight=0.35, Coat_Roughness=0.2)
        return m

    return [leather((0.86, 0.86, 0.84, 1.0)), leather((0.02, 0.02, 0.025, 1.0))]


def soccer_ball(collection, rows=8, seam=0.012, seam_w=0.22):
    iv, ifc = _icosahedron()
    edge_pts = {}

    def third(a, b):
        key = (a, b)
        if key not in edge_pts:
            edge_pts[key] = (iv[a] * 2 + iv[b]) / 3
        return edge_pts[key]

    polys = []                                   # (points on the sphere in order, is_pentagon)
    for (a, b, c) in ifc:
        polys.append(([third(a, b), third(b, a), third(b, c), third(c, b), third(c, a), third(a, c)], False))
    for vi in range(len(iv)):
        ring = []
        faces = [f for f in ifc if vi in f]
        # walk the faces round the vertex in order
        f = faces[0]
        order = [f]
        while len(order) < len(faces):
            last = order[-1]
            k = last.index(vi)
            nxt_v = last[(k + 2) % 3]
            f2 = next(g for g in faces if g not in order and nxt_v in g)
            order.append(f2)
        for f in order:
            k = f.index(vi)
            ring.append(third(vi, f[(k + 1) % 3]))
        polys.append((ring, True))
    mb = rf.MeshBuilder()
    for pts, pent in polys:
        pts = [p.normalized() for p in pts]
        cen = sum(pts, Vector()).normalized()
        if (pts[1] - pts[0]).cross(pts[2] - pts[0]).dot(cen) < 0:
            pts = pts[::-1]
        for i in range(len(pts)):
            A, B = pts[i], pts[(i + 1) % len(pts)]
            idx = {}
            for r_ in range(rows + 1):
                for s_ in range(rows + 1 - r_):
                    wc = 1.0 - (r_ + s_) / rows            # weight of the centre: 0 on the panel's edge
                    p = cen * wc + A * (r_ / rows) + B * (s_ / rows)
                    p = p.normalized()
                    groove = seam * (1.0 - min(1.0, wc / seam_w)) ** 2.2
                    puff = 0.004 * math.sin(math.pi * min(1.0, wc * 1.2))
                    rad = 0.5 * (1.0 - groove + puff)
                    idx[(r_, s_)] = len(mb.verts)
                    mb.verts.append(tuple(p * rad + Vector((0, 0, 0.5))))
            for r_ in range(rows):
                for s_ in range(rows - r_):
                    mb.faces.append((idx[(r_, s_)], idx[(r_ + 1, s_)], idx[(r_, s_ + 1)]))
                    mb.mats.append(1 if pent else 0)
                    if r_ + s_ < rows - 1:
                        mb.faces.append((idx[(r_ + 1, s_)], idx[(r_ + 1, s_ + 1)], idx[(r_, s_ + 1)]))
                        mb.mats.append(1 if pent else 0)
    me = mb.build("soccer_ball", _ball_materials(), fix_normals=True, smooth=True)
    return _finish("soccer_ball", me, collection, {"name": "soccer_ball", "label": LABELS["soccer_ball"],
                                                   "size_of": "diameter"})


# ---------------------------------------------------------------- beach ball

def beach_ball(collection, nu=96, nv=48):
    cols = [(0.85, 0.03, 0.02), (1.0, 0.75, 0.02), (0.02, 0.2, 0.85), (0.9, 0.9, 0.88), (0.05, 0.6, 0.12),
            (1.0, 0.32, 0.02)]
    mats = []
    for k, c in enumerate(cols + [(0.92, 0.92, 0.9)]):
        m = rf.make_material(f"beachball_{k}", c, rough=0.12, haze=0.1, glitch=True)
        _set(_bsdf(m)[1], Coat_Weight=0.5, Coat_Roughness=0.05, Subsurface_Weight=0.1, Subsurface_Scale=0.02)
        mats.append(m)
    cap = 6
    mb = rf.MeshBuilder()
    for j in range(nv + 1):
        th = math.pi * j / nv
        for i in range(nu):
            ph = 2 * math.pi * i / nu
            gore = (ph / (2 * math.pi / 6)) % 1.0
            dent = 0.004 * (1.0 - min(1.0, min(gore, 1 - gore) / 0.03)) if 0.08 < th < math.pi - 0.08 else 0.0
            rr = 0.5 * (1.0 - dent) * (1.0 - 0.012 * math.sin(th) ** 8)
            mb.verts.append((rr * math.sin(th) * math.cos(ph), rr * math.sin(th) * math.sin(ph),
                             0.5 + rr * math.cos(th)))
    for j in range(nv):
        for i in range(nu):
            a, b_ = j * nu + i, j * nu + (i + 1) % nu
            c, d = (j + 1) * nu + (i + 1) % nu, (j + 1) * nu + i
            th = math.pi * (j + 0.5) / nv
            m = cap if (th < 0.3 or th > math.pi - 0.3) else int(((i + 0.5) / nu) * 6) % 6
            mb.faces.append((a, b_, c, d))
            mb.mats.append(m)
    # the valve on the white gore, near the top cap
    ph, th = 2 * math.pi * 3.5 / 6, 0.42
    n = Vector((math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)))
    c = n * 0.5 + Vector((0, 0, 0.5))
    u = n.orthogonal().normalized()
    v = n.cross(u)
    base = len(mb.verts)
    for k_, (rad, h) in enumerate(((0.03, -0.004), (0.03, 0.006), (0.016, 0.008), (0.016, 0.02))):
        for kk in range(12):
            a_ = 2 * math.pi * kk / 12
            mb.verts.append(tuple(c + n * h + (u * math.cos(a_) + v * math.sin(a_)) * rad))
    for ring in range(3):
        for kk in range(12):
            k2 = (kk + 1) % 12
            o = base + ring * 12
            mb.faces.append((o + kk, o + k2, o + 12 + k2, o + 12 + kk))
            mb.mats.append(cap)
    mb.faces.append(tuple(base + 36 + kk for kk in range(12)))
    mb.mats.append(cap)
    me = mb.build("beach_ball", mats, fix_normals=True, smooth=True)
    return _finish("beach_ball", me, collection, {"name": "beach_ball", "label": LABELS["beach_ball"],
                                                  "size_of": "diameter"})


BUILDERS = {"duck": duck, "donut": donut, "soccer_ball": soccer_ball, "beach_ball": beach_ball}


def build(name, collection):
    if name not in BUILDERS:
        raise KeyError(f"unknown subject {name!r}; choose one of {', '.join(BUILDERS)}")
    return BUILDERS[name](collection)
