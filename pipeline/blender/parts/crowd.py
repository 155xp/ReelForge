"""Crowds: tens of thousands of stylised people that stay fast to build and render, and act together.

Every person is a point (a vertex) carrying a few attributes; one Geometry Nodes modifier puts a person mesh on each
point. The meshes come in seven poses and three levels of detail, so a crowd can stand about, wave, film, cheer, look
up, crouch and jump, and people far from the camera cost about a hundred triangles each. Nothing is baked per person:
timing comes from the modifier's inputs, which an effect keys per frame.

  variants()                  the pose meshes (7 poses x 3 levels of detail) in a collection the crowds instance
  materials()                 shirt / pants / skin / hair / shoes / phone / screen / sole, coloured per person
  add_crowd(collection, people, name, camera=...)     the crowd object; `people` is a list of Person
  scatter(...)                Person spots that fill a rectangle or a ring at a density, avoiding obstacles
  key_inputs(crowd, frames, clock=..., jump_at=...)   bake the modifier inputs per frame

Poses (POSES): stand, crouch (the jump's wind-up and landing), air (legs tucked, arms up), wave (right hand up),
cheer (both hands up), film (phone held up) and look (head back, looking up).

Per person (Person fields, stored as point attributes):
  join    clock time (s) they appear (a quick 0.3 s grow-in); -1e9 = there from the start
  yaw     facing, radians (0 faces +Y)
  size    uniform scale (1.0 = 1.75 m; 0.55-0.75 makes children)
  idle    the pose they hold before the action: 0 stand, 3 wave, 5 film, 6 look (any POSES index works)
  react   seconds they lag behind the synchronized moment (0-0.15 s looks natural)
  phase   0..1, desynchronizes the idle sway and the cheering
  shirt   RGB shirt colour; tone 0..1 picks skin, hair, trousers and shoes

Modifier inputs (key them with key_inputs; all times are on the crowd's own clock, in seconds, so an effect can
slow it down or freeze it while the video keeps running):
  Clock        crowd time; Jump At: lift-off time; Crouch: wind-up length (s); Air: time in the air (s);
  Height       jump height (m); Land: landing crouch length (s); Hype From: after this the idle crowd cheers,
               arms going up and down; LOD Dist / LOD Far: beyond these distances from the camera (m) the
               cheaper meshes are used;
  Pop          grow-in time for people who join; Sway: idle sway amount (0..1)
  Join From, Join Span   a person appears at Join From + Join Span x join (defaults 0 and 1: join is a time).
               Store a 0..1 order in `join` instead and let the effect pick the window.
  Act At, Act Pose       from Act At (+ each person's react lag) everyone holds Act Pose (a POSES index): the
               "everyone does it at once" moment for actions without a jump (look up, wave, film, cheer)
The crowd object must keep an identity transform (points are in world metres).
"""
import math
import random
from dataclasses import dataclass

import bpy
import numpy as np
from mathutils import Euler, Vector

import rf_common as rf

POSES = ["stand", "crouch", "air", "wave", "cheer", "film", "look"]
STAND, CROUCH, AIR, WAVE, CHEER, FILM, LOOK = range(7)
SHIRT, PANTS, SKIN, HAIR, SHOES, PHONE, SCREEN, SOLE = range(8)

SHIRTS = [(0.70, 0.08, 0.07), (0.08, 0.22, 0.62), (0.90, 0.90, 0.88), (0.10, 0.10, 0.11), (0.92, 0.62, 0.08),
          (0.15, 0.45, 0.22), (0.52, 0.22, 0.58), (0.86, 0.76, 0.55), (0.26, 0.58, 0.80), (0.88, 0.36, 0.52),
          (0.95, 0.85, 0.15), (0.40, 0.42, 0.45), (0.05, 0.42, 0.48), (0.80, 0.28, 0.10)]

# leg bones (hip to knee, knee to ankle), ankle height above the sole
THIGH, SHIN, ANKLE_Z = 0.43, 0.43, 0.08
HIP_Z = 0.92


@dataclass
class Person:
    x: float
    y: float
    join: float = -1e9
    yaw: float = 0.0
    size: float = 1.0
    idle: int = STAND
    react: float = 0.0
    phase: float = 0.0
    shirt: tuple = (0.7, 0.1, 0.1)
    tone: float = 0.5


# ---------------------------------------------------------------- pose skeletons

def _pose(name):
    """Joint positions for a pose: dict of named points (feet on the ground at z = 0, facing +Y)."""
    drop, py, lean, head = 0.0, 0.0, 0.0, 0.0     # pelvis drop (m), pelvis forward (m), torso lean (deg), head tilt
    ankle_y, ankle_z = 0.0, ANKLE_Z
    # arms as offsets from each shoulder in the torso frame: (elbow, wrist) for right (+x) then left
    down = ((0.04, 0.005, -0.27), (0.02, 0.03, -0.27))
    r_arm = l_arm = down
    if name == "crouch":
        drop, py, lean = 0.30, -0.10, 30.0
        r_arm = l_arm = ((0.05, -0.17, -0.21), (0.02, -0.16, -0.13))
    elif name == "air":
        drop, lean, head = 0.08, -6.0, -8.0
        ankle_y, ankle_z = -0.10, 0.20                 # feet tucked back under the body
        r_arm = l_arm = ((0.10, 0.03, 0.25), (0.07, 0.02, 0.25))
    elif name == "wave":
        r_arm = ((0.14, 0.05, 0.12), (0.06, 0.03, 0.27))
    elif name == "cheer":
        r_arm = l_arm = ((0.13, 0.04, 0.22), (0.10, 0.03, 0.23))
    elif name == "film":
        r_arm = ((0.06, 0.20, 0.0), (-0.08, 0.22, 0.18))
    elif name == "look":
        head = -24.0
    hip_z = HIP_Z - drop
    pivot = Vector((0.0, py, hip_z))
    rot = Euler((math.radians(lean), 0.0, 0.0)).to_matrix()

    def torso(p):
        """A point given in the upright body (pelvis at HIP_Z) moved with the pelvis and leaned forward."""
        q = Vector(p) - Vector((0.0, 0.0, HIP_Z))
        return tuple(pivot + rot @ q)

    j = {"pivot": tuple(pivot), "lean": lean, "head_tilt": head, "torso": torso}
    for side, sx, arm in (("r", 1, r_arm), ("l", -1, l_arm)):
        sh = Vector((sx * 0.195, -0.005, 1.40))
        el = sh + Vector((sx * arm[0][0], arm[0][1], arm[0][2]))
        wr = el + Vector((sx * arm[1][0], arm[1][1], arm[1][2]))
        j[f"{side}_shoulder"], j[f"{side}_elbow"], j[f"{side}_wrist"] = torso(sh), torso(el), torso(wr)
        hip = Vector((sx * 0.10, py, hip_z))
        ankle = Vector((sx * 0.095, ankle_y, ankle_z))
        d = (hip - ankle).length
        mid = (hip + ankle) / 2
        reach = THIGH + SHIN
        if d >= reach * 0.999:
            knee = hip + (ankle - hip).normalized() * THIGH
        else:
            # the knee bends forward (+Y) in the leg's plane
            along = (ankle - hip).normalized()
            fwd = Vector((0.0, 1.0, 0.0))
            perp = (fwd - along * fwd.dot(along)).normalized()
            knee = mid + perp * math.sqrt(max(THIGH * THIGH - (d / 2) ** 2, 0.0))
        j[f"{side}_hip"], j[f"{side}_knee"], j[f"{side}_ankle"] = tuple(hip), tuple(knee), tuple(ankle)
    return j


# ---------------------------------------------------------------- meshes

def _tube(mb, p0, p1, r0, r1, mat, seg):
    p0, p1 = Vector(p0), Vector(p1)
    axis = (p1 - p0)
    if axis.length < 1e-6:
        return
    axis.normalize()
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


def _torso_loft(mb, j, seg, mat_shirt):
    """Shirt-covered torso from the hips to the neck, as rings carried by the body frame."""
    rings = [(0.90, 0.150, 0.095, 0.0), (1.02, 0.148, 0.093, 0.0), (1.18, 0.160, 0.100, 0.005),
             (1.33, 0.190, 0.108, 0.0), (1.43, 0.190, 0.100, -0.005), (1.48, 0.100, 0.065, -0.005)]
    b = len(mb.verts)
    for z, rx, ry, cy in rings:
        for k in range(seg):
            a = 2 * math.pi * k / seg
            mb.verts.append(j["torso"]((rx * math.cos(a), cy + ry * math.sin(a), z)))
    for s in range(len(rings) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            mb.faces.append((b + s * seg + k, b + s * seg + k2, b + (s + 1) * seg + k2, b + (s + 1) * seg + k))
            mb.mats.append(mat_shirt)
    mb.faces.append(tuple(b + k for k in reversed(range(seg))))
    mb.mats.append(mat_shirt)
    last = (len(rings) - 1) * seg
    mb.faces.append(tuple(b + last + k for k in range(seg)))
    mb.mats.append(mat_shirt)


def person_mesh(pose, lod=0, name=None, materials=None):
    """One person in a pose. lod 0: close-up detail (about 3,500 triangles); lod 1: about 600, for the crowd
    beyond LOD Dist; lod 2: about 120, beyond LOD Far. Material slots follow SHIRT .. SOLE."""
    if lod >= 2:
        return _person_far(pose, name, materials)
    j = _pose(pose)
    hi = lod == 0
    seg, sub = (10, 2) if hi else (5, 1)
    mb = rf.MeshBuilder()
    torso = j["torso"]
    for side in ("r", "l"):
        hip, knee, ankle = j[f"{side}_hip"], j[f"{side}_knee"], j[f"{side}_ankle"]
        sx = 1 if side == "r" else -1
        _tube(mb, ankle, knee, 0.052, 0.062, PANTS, seg)
        _tube(mb, knee, hip, 0.064, 0.084, PANTS, seg)
        if hi:
            _shoe(mb, sx * 0.095, ankle[1], ankle[2] - ANKLE_Z)
            mb.ico(knee, (0.062, 0.062, 0.062), 1, PANTS)
            _tube(mb, (ankle[0], ankle[1], ankle[2] - 0.01), (ankle[0], ankle[1], ankle[2] + 0.05), 0.058, 0.056,
                  PANTS, seg)                                                  # trouser hem
        else:
            mb.ico((sx * 0.095, ankle[1] + 0.04, ankle[2] - 0.035), (0.05, 0.12, 0.045), sub, SHOES)
    mb.ico(torso((0.0, 0.0, 0.93)), (0.165, 0.105, 0.10), sub, PANTS)
    if hi:
        _torso_loft(mb, j, 14, SHIRT)
    else:
        _tube(mb, torso((0, 0, 0.95)), torso((0, 0, 1.44)), 0.16, 0.19, SHIRT, 6)
    # neck and head; the head tilts back for "look"
    neck0, neck1 = torso((0, -0.005, 1.46)), torso((0, 0.0, 1.57))
    _tube(mb, neck0, neck1, 0.045, 0.042, SKIN, 8 if hi else 5)
    tilt = Euler((math.radians(j["head_tilt"]), 0.0, 0.0)).to_matrix()

    def head_pt(p):
        return tuple(Vector(neck1) + tilt @ (Vector(torso(p)) - Vector(neck1)))
    mb.ico(head_pt((0, 0.008, 1.645)), (0.083, 0.098, 0.108), sub, SKIN)
    mb.ico(head_pt((0, -0.018, 1.678)), (0.088, 0.098, 0.086), sub, HAIR)
    if hi:
        mb.ico(head_pt((0, 0.105, 1.632)), (0.013, 0.017, 0.022), 1, SKIN)          # nose
    for side in ("r", "l"):
        sh, el, wr = j[f"{side}_shoulder"], j[f"{side}_elbow"], j[f"{side}_wrist"]
        mb.ico(sh, (0.06, 0.06, 0.055), 1, SHIRT)
        _tube(mb, sh, el, 0.05, 0.043, SHIRT, 8 if hi else 4)
        _tube(mb, el, wr, 0.041, 0.034, SKIN, 8 if hi else 4)
        we, ww = Vector(el), Vector(wr)
        mb.ico(tuple(ww + (ww - we).normalized() * 0.05), (0.038, 0.03, 0.05), 1, SKIN)
    if pose == "film":
        # a phone held up in the right hand, screen towards the person
        wr, el = Vector(j["r_wrist"]), Vector(j["r_elbow"])
        c = wr + (wr - el).normalized() * 0.09
        mb.box(c.x - 0.038, c.y - 0.006, c.z - 0.075, c.x + 0.038, c.y + 0.006, c.z + 0.075, PHONE)
        mb.box(c.x - 0.033, c.y - 0.0075, c.z - 0.068, c.x + 0.033, c.y - 0.0055, c.z + 0.068, SCREEN)
    me = mb.build(name or f"crowd_{pose}_{lod}", materials or [], fix_normals=True, smooth=True)
    return me


# ---------------------------------------------------------------- materials (coloured per person)

def _inst(nt, name, socket="Fac"):
    return nt.node("ShaderNodeAttribute", attribute_type="INSTANCER", attribute_name=name).outputs[socket]


def materials():
    """Eight materials; the shirt colour and a 'tone' (skin, hair, trousers, shoes) come from each person's point
    attributes (rf_shirt, rf_tone), so one mesh serves the whole crowd."""
    def tone(nt, stops, offset=0.0):
        t = nt.math("FRACT", nt.math("ADD", _inst(nt, "rf_tone"), offset))
        return nt.ramp(t, stops)

    shirt = rf.make_material("crowd_shirt", lambda nt: _inst(nt, "rf_shirt", "Color"), rough=0.75)
    pants = rf.make_material("crowd_pants", lambda nt: tone(nt, [(0.0, (0.03, 0.04, 0.09)), (0.35, (0.10, 0.10, 0.12)),
                                                                 (0.6, (0.20, 0.20, 0.22)), (0.8, (0.36, 0.30, 0.20)),
                                                                 (1.0, (0.55, 0.50, 0.42))], 0.37), rough=0.85)
    skin = rf.make_material("crowd_skin", lambda nt: tone(nt, [(0.0, (0.10, 0.05, 0.03)), (0.3, (0.30, 0.16, 0.09)),
                                                               (0.6, (0.55, 0.33, 0.21)), (1.0, (0.82, 0.58, 0.45))]),
                            rough=0.55)
    hair = rf.make_material("crowd_hair", lambda nt: tone(nt, [(0.0, (0.015, 0.012, 0.01)), (0.55, (0.07, 0.04, 0.02)),
                                                               (0.8, (0.30, 0.18, 0.08)), (1.0, (0.62, 0.52, 0.32))],
                                                          0.61), rough=0.6)
    shoes = rf.make_material("crowd_shoes", lambda nt: tone(nt, [(0.0, (0.02, 0.02, 0.02)), (0.6, (0.22, 0.20, 0.18)),
                                                                 (1.0, (0.88, 0.88, 0.86))], 0.23), rough=0.5)
    phone = rf.make_material("crowd_phone", (0.02, 0.02, 0.025), rough=0.3, metallic=0.5)
    screen = rf.make_material("crowd_screen", (0.05, 0.07, 0.1), rough=0.2, emission=((0.75, 0.88, 1.0), 2.5))
    sole = rf.make_material("crowd_sole", lambda nt: tone(nt, [(0.0, (0.03, 0.03, 0.03)), (0.5, (0.12, 0.11, 0.10)),
                                                               (1.0, (0.85, 0.84, 0.80))], 0.71), rough=0.7)
    return [shirt, pants, skin, hair, shoes, phone, screen, sole]


def _shoe(mb, x, y, z):
    """A close-up trainer under an ankle at (x, y): rubber sole with a raised toe, rounded upper, heel counter,
    tongue and laces. z is the sole's underside."""
    mb.box(x - 0.047, y - 0.075, z, x + 0.047, y + 0.155, z + 0.028, SOLE)
    mb.ico((x, y + 0.150, z + 0.030), (0.046, 0.030, 0.026), 2, SOLE)                 # toe bumper
    mb.ico((x, y + 0.055, z + 0.052), (0.049, 0.112, 0.042), 2, SHOES)               # upper
    mb.ico((x, y - 0.050, z + 0.065), (0.047, 0.050, 0.052), 2, SHOES)               # heel counter
    mb.ico((x, y + 0.040, z + 0.088), (0.030, 0.060, 0.018), 2, SHOES)               # tongue
    for k in range(4):                                                               # laces
        ly = y + 0.005 + 0.026 * k
        mb.box(x - 0.026, ly - 0.004, z + 0.090 - 0.006 * k, x + 0.026, ly + 0.004, z + 0.098 - 0.006 * k, SOLE)


def _person_far(pose, name, materials):
    """The cheapest person: tubes and a head that still read as the pose from far away."""
    j = _pose(pose)
    torso = j["torso"]
    mb = rf.MeshBuilder()
    for side in ("r", "l"):
        _tube(mb, j[f"{side}_ankle"], j[f"{side}_knee"], 0.06, 0.07, PANTS, 4)
        _tube(mb, j[f"{side}_knee"], j[f"{side}_hip"], 0.07, 0.09, PANTS, 4)
        _tube(mb, j[f"{side}_shoulder"], j[f"{side}_elbow"], 0.055, 0.05, SHIRT, 3)
        _tube(mb, j[f"{side}_elbow"], j[f"{side}_wrist"], 0.05, 0.045, SKIN, 3)
    _tube(mb, torso((0, 0, 0.90)), torso((0, 0, 1.46)), 0.17, 0.19, SHIRT, 5)
    mb.ico(torso((0, 0.0, 1.66)), (0.10, 0.11, 0.12), 1, HAIR)
    return mb.build(name or f"crowd_{pose}_2", materials or [], fix_normals=True, smooth=False)


_VARIANTS = {}


def variants(mats=None):
    """The collection of 21 pose meshes the crowds instance (name order = pose + 7 * lod). Not linked to the scene:
    Geometry Nodes reads it directly, so the originals never show up in a render."""
    if "col" in _VARIANTS:
        return _VARIANTS["col"]
    mats = mats or materials()
    col = bpy.data.collections.new("RF_CrowdVariants")
    col.use_fake_user = True
    for lod in (0, 1, 2):
        for k, pose in enumerate(POSES):
            idx = k + 7 * lod
            me = person_mesh(pose, lod, f"crowd_{idx:02d}_{pose}_{lod}", mats)
            ob = bpy.data.objects.new(f"crowd_{idx:02d}_{pose}_{lod}", me)
            col.objects.link(ob)
    _VARIANTS["col"] = col
    _VARIANTS["mats"] = mats
    return col


# ---------------------------------------------------------------- the node group

INPUTS = [("Clock", "NodeSocketFloat", 0.0), ("Jump At", "NodeSocketFloat", 1e6), ("Crouch", "NodeSocketFloat", 0.32),
          ("Air", "NodeSocketFloat", 0.6), ("Height", "NodeSocketFloat", 0.45), ("Land", "NodeSocketFloat", 0.28),
          ("Hype From", "NodeSocketFloat", 1e6), ("LOD Dist", "NodeSocketFloat", 38.0),
          ("LOD Far", "NodeSocketFloat", 160.0),
          ("Pop", "NodeSocketFloat", 0.3), ("Sway", "NodeSocketFloat", 1.0),
          ("Join From", "NodeSocketFloat", 0.0), ("Join Span", "NodeSocketFloat", 1.0),
          ("Act At", "NodeSocketFloat", 1e6), ("Act Pose", "NodeSocketFloat", float(LOOK))]


class _G:
    """Tiny helper for building a geometry node tree."""

    def __init__(self, ng):
        self.ng, self.n, self.l = ng, ng.nodes, ng.links

    def node(self, typ, **props):
        nd = self.n.new(typ)
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def put(self, sock, v):
        if isinstance(v, (int, float)):
            sock.default_value = v
        else:
            self.l.new(v, sock)

    def m(self, op, a, b=None, c=None):
        nd = self.node("ShaderNodeMath", operation=op)
        self.put(nd.inputs[0], a)
        if b is not None:
            self.put(nd.inputs[1], b)
        if c is not None:
            self.put(nd.inputs[2], c)
        return nd.outputs[0]

    def attr(self, name, dtype="FLOAT"):
        nd = self.node("GeometryNodeInputNamedAttribute", data_type=dtype)
        nd.inputs["Name"].default_value = name
        return nd.outputs[0]

    def clamp01(self, x):
        return self.m("MINIMUM", self.m("MAXIMUM", x, 0.0), 1.0)

    def smooth01(self, x):
        x = self.clamp01(x)
        return self.m("MULTIPLY", self.m("MULTIPLY", x, x), self.m("SUBTRACT", 3.0, self.m("MULTIPLY", x, 2.0)))

    def between(self, x, lo, hi):
        """1 where lo <= x < hi."""
        return self.m("MULTIPLY", self.m("GREATER_THAN", x, self.m("SUBTRACT", lo, 1e-6)), self.m("LESS_THAN", x, hi))

    def xyz(self, x, y, z):
        nd = self.node("ShaderNodeCombineXYZ")
        for k, v in enumerate((x, y, z)):
            self.put(nd.inputs[k], v)
        return nd.outputs[0]


def node_group(camera=None):
    """The Geometry Nodes group that turns people-points into posed, animated people (one per crowd camera)."""
    key = f"RF_Crowd_{camera.name if camera else 'nocam'}"
    if key in bpy.data.node_groups:
        return bpy.data.node_groups[key]
    ng = bpy.data.node_groups.new(key, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    for name, typ, default in INPUTS:
        s = ng.interface.new_socket(name, in_out="INPUT", socket_type=typ)
        s.default_value = default
    g = _G(ng)
    gin = g.node("NodeGroupInput")
    gout = g.node("NodeGroupOutput")
    I = {name: gin.outputs[name] for name, _, _ in INPUTS}
    clock = I["Clock"]

    join, react, phase = g.attr("rf_join"), g.attr("rf_react"), g.attr("rf_phase")
    idle, size, yaw = g.attr("rf_idle"), g.attr("rf_size"), g.attr("rf_yaw")

    # appear at the join time (grow in over Pop seconds)
    join = g.m("ADD", g.m("MULTIPLY", join, I["Join Span"]), I["Join From"])
    since = g.m("SUBTRACT", clock, join)
    shown = g.m("GREATER_THAN", since, 0.0)
    grow = g.smooth01(g.m("DIVIDE", since, g.m("MAXIMUM", I["Pop"], 0.01)))

    # the synchronized action: wind-up crouch, lift-off, flight, landing crouch
    local = g.m("SUBTRACT", g.m("SUBTRACT", clock, I["Jump At"]), react)
    crouch = g.between(local, g.m("MULTIPLY", I["Crouch"], -1.0), 0.0)
    air = g.between(local, 0.0, I["Air"])
    land = g.between(local, I["Air"], g.m("ADD", I["Air"], I["Land"]))
    s = g.clamp01(g.m("DIVIDE", local, g.m("MAXIMUM", I["Air"], 0.01)))
    hop = g.m("MULTIPLY", g.m("MULTIPLY", g.m("MULTIPLY", 4.0, I["Height"]), s), g.m("SUBTRACT", 1.0, s))
    hop = g.m("MULTIPLY", hop, air)

    # idle, or cheering once the hype starts (arms up and down, desynchronized)
    hype = g.m("GREATER_THAN", clock, I["Hype From"])
    wave_t = g.m("FRACT", g.m("ADD", g.m("MULTIPLY", clock, 1.6), phase))
    cheer_pose = g.m("ADD", g.m("MULTIPLY", g.m("LESS_THAN", wave_t, 0.5), CHEER - WAVE), WAVE)   # 4 or 3
    acted = g.m("GREATER_THAN", g.m("SUBTRACT", g.m("SUBTRACT", clock, I["Act At"]), react), 0.0)
    idle = g.m("ADD", g.m("MULTIPLY", acted, g.m("SUBTRACT", I["Act Pose"], idle)), idle)
    calm = g.m("ADD", g.m("MULTIPLY", hype, g.m("SUBTRACT", cheer_pose, idle)), idle)
    acting = g.m("MAXIMUM", g.m("MAXIMUM", crouch, air), land)
    pose = g.m("ADD", g.m("MULTIPLY", g.m("SUBTRACT", 1.0, acting), calm),
               g.m("ADD", g.m("MULTIPLY", g.m("MAXIMUM", crouch, land), CROUCH), g.m("MULTIPLY", air, AIR)))

    # level of detail by distance to the camera
    pos = g.node("GeometryNodeInputPosition").outputs[0]
    if camera is not None:
        oi = g.node("GeometryNodeObjectInfo")
        oi.inputs["Object"].default_value = camera
        dist = g.node("ShaderNodeVectorMath", operation="DISTANCE")
        g.l.new(pos, dist.inputs[0])
        g.l.new(oi.outputs["Location"], dist.inputs[1])
        far = g.m("ADD", g.m("GREATER_THAN", dist.outputs["Value"], I["LOD Dist"]),
                  g.m("GREATER_THAN", dist.outputs["Value"], I["LOD Far"]))
    else:
        far = 2.0
    index = g.m("ADD", g.m("ROUND", pose), g.m("MULTIPLY", far, 7.0))

    # a little life: weight shifts and a slow turn, scaled by Sway (off while acting)
    still = g.m("MULTIPLY", g.m("SUBTRACT", 1.0, acting), I["Sway"])
    sway = g.m("MULTIPLY", g.m("SINE", g.m("MULTIPLY", g.m("ADD", g.m("MULTIPLY", clock, 0.37), phase), 6.2832)), 0.07)
    bob = g.m("MULTIPLY", g.m("SINE", g.m("MULTIPLY", g.m("ADD", g.m("MULTIPLY", clock, 0.9), phase), 6.2832)), 0.008)
    turn = g.m("ADD", yaw, g.m("MULTIPLY", sway, still))

    col = g.node("GeometryNodeCollectionInfo")
    col.inputs["Collection"].default_value = variants()
    col.inputs["Separate Children"].default_value = True
    col.inputs["Reset Children"].default_value = True
    iop = g.node("GeometryNodeInstanceOnPoints")
    g.l.new(gin.outputs["Geometry"], iop.inputs["Points"])
    g.l.new(shown, iop.inputs["Selection"])
    g.l.new(col.outputs[0], iop.inputs["Instance"])
    iop.inputs["Pick Instance"].default_value = True
    g.l.new(index, iop.inputs["Instance Index"])
    rot = g.node("FunctionNodeEulerToRotation")
    g.l.new(g.xyz(0.0, 0.0, turn), rot.inputs[0])
    g.l.new(rot.outputs[0], iop.inputs["Rotation"])
    sc = g.m("MULTIPLY", size, grow)
    g.l.new(g.xyz(sc, sc, sc), iop.inputs["Scale"])
    tr = g.node("GeometryNodeTranslateInstances")
    g.l.new(iop.outputs[0], tr.inputs["Instances"])
    lift = g.m("ADD", g.m("MULTIPLY", hop, size), g.m("MULTIPLY", g.m("MAXIMUM", bob, 0.0), still))
    g.l.new(g.xyz(0.0, 0.0, lift), tr.inputs["Translation"])
    tr.inputs["Local Space"].default_value = False
    g.l.new(tr.outputs[0], gout.inputs["Geometry"])
    return ng


# ---------------------------------------------------------------- building crowds

def add_crowd(collection, people, name="crowd", camera=None, **inputs):
    """A crowd object: one point per Person (world metres, identity transform) and the crowd modifier. Extra
    keyword arguments set modifier inputs by name with spaces as underscores (jump_at=12.0, lod_dist=50)."""
    variants()
    me = bpy.data.meshes.new(name)
    n = len(people)
    me.vertices.add(n)
    xs = np.array([[p.x, p.y, 0.0] for p in people], dtype=np.float32).ravel() if n else np.zeros(0, np.float32)
    me.vertices.foreach_set("co", xs)
    for attr, field in (("rf_join", "join"), ("rf_yaw", "yaw"), ("rf_size", "size"), ("rf_idle", "idle"),
                        ("rf_react", "react"), ("rf_phase", "phase"), ("rf_tone", "tone")):
        a = me.attributes.new(attr, "FLOAT", "POINT")
        a.data.foreach_set("value", [float(getattr(p, field)) for p in people])
    sh = me.attributes.new("rf_shirt", "FLOAT_VECTOR", "POINT")
    sh.data.foreach_set("vector", [c for p in people for c in p.shirt])
    me.update()
    ob = bpy.data.objects.new(name, me)
    collection.objects.link(ob)
    mod = ob.modifiers.new("Crowd", "NODES")
    mod.node_group = node_group(camera)
    for k, v in inputs.items():
        set_input(ob, k.replace("_", " ").title().replace("Lod", "LOD"), v)
    ob["rf_people"] = n
    return ob


def _socket_id(ob, name):
    for item in ob.modifiers["Crowd"].node_group.interface.items_tree:
        if getattr(item, "in_out", None) == "INPUT" and item.name == name:
            return item.identifier
    raise KeyError(name)


def set_input(ob, name, value):
    ob.modifiers["Crowd"][_socket_id(ob, name)] = value


def key_inputs(ob, frames, **series):
    """Bake modifier inputs per frame, e.g. key_inputs(crowd, frames, clock=[...], jump_at=[...])."""
    for k, values in series.items():
        name = k.replace("_", " ").title().replace("Lod", "LOD")
        path = f'modifiers["Crowd"]["{_socket_id(ob, name)}"]'
        rf.key_series(ob, path, -1, frames, values)


def scatter(rnd, x0, y0, x1, y1, density, avoid=(), join_fn=None, idle_mix=None, child_share=0.12, face=None,
            jitter=0.42):
    """People filling the rectangle [x0, x1] x [y0, y1] at `density` people per m^2 on a jittered grid (so no two
    overlap), skipping spots inside `avoid` circles [(x, y, r), ...]. join_fn(x, y) -> join time; idle_mix:
    [(pose, weight), ...] for the idle pose; face: (x, y) everyone roughly turns towards (else random)."""
    pitch = 1.0 / math.sqrt(density)
    idle_mix = idle_mix or [(STAND, 0.62), (FILM, 0.16), (WAVE, 0.10), (LOOK, 0.12)]
    poses, weights = zip(*idle_mix)
    out = []
    ny = int((y1 - y0) / pitch)
    nx = int((x1 - x0) / pitch)
    for iy in range(ny):
        for ix in range(nx):
            x = x0 + (ix + 0.5 + rnd.uniform(-jitter, jitter)) * pitch
            y = y0 + (iy + 0.5 + rnd.uniform(-jitter, jitter)) * pitch
            if any((x - ax) ** 2 + (y - ay) ** 2 < ar * ar for ax, ay, ar in avoid):
                continue
            out.append(_person(rnd, x, y, join_fn, poses, weights, child_share, face))
    return out


def ring(rnd, cx, cy, r0, r1, density, join_fn=None, child_share=0.1, face=None, avoid=()):
    """People filling an annulus round (cx, cy) between radii r0 and r1."""
    pts = scatter(rnd, cx - r1, cy - r1, cx + r1, cy + r1, density, avoid=avoid, join_fn=join_fn,
                  child_share=child_share, face=face)
    return [p for p in pts if r0 * r0 <= (p.x - cx) ** 2 + (p.y - cy) ** 2 <= r1 * r1]


def _person(rnd, x, y, join_fn, poses, weights, child_share, face):
    if face is not None:
        yaw = math.atan2(-(face[0] - x), face[1] - y) + rnd.uniform(-0.6, 0.6)
    else:
        yaw = rnd.uniform(-math.pi, math.pi)
    child = rnd.random() < child_share
    return Person(x=x, y=y, join=join_fn(x, y) if join_fn else -1e9, yaw=yaw,
                  size=rnd.uniform(0.55, 0.75) if child else rnd.uniform(0.9, 1.07),
                  idle=rnd.choices(poses, weights)[0], react=rnd.uniform(0.0, 0.14), phase=rnd.random(),
                  shirt=tuple(c * rnd.uniform(0.82, 1.08) for c in rnd.choice(SHIRTS)), tone=rnd.random())


def person(rnd=None, x=0.0, y=0.0, **fields):
    """One Person with random looks; fields override (yaw=..., idle=..., join=...)."""
    rnd = rnd or random.Random(1)
    p = _person(rnd, x, y, None, [STAND], [1.0], 0.0, None)
    for k, v in fields.items():
        setattr(p, k, v)
    return p
