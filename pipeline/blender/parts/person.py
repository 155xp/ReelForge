"""Stylised low-poly person (about 1.75 m, facing +Y, feet at z = 0) built from smooth tubes and ellipsoids.

Poses: "stand" (arms down), "hold" (right hand raised in front of the chest, holding a string), "rail" (hands
resting forward as if on a handrail), "phone" (phone in the right hand, cup in the left), "film" (right arm raised
holding a phone up). Material slots: shirt (object colour), pants, skin, hair, shoes, plus a sixth (dark
glass) when the person wears sunglasses (`shades=True`, which also adds a nose so the face reads at a glance).
`hand_position(pose)` gives the right hand's centre so props (a balloon string) can be attached.
"""
import math

from mathutils import Vector

import rf_common as rf

SHIRT, PANTS, SKIN, HAIR, SHOES, SHADES = range(6)

POSES = {
    #          right elbow           right wrist            left elbow             left wrist
    "stand": ((0.235, 0.0, 1.13), (0.255, 0.03, 0.86), (-0.235, 0.0, 1.13), (-0.255, 0.03, 0.86)),
    "hold": ((0.25, 0.12, 1.16), (0.24, 0.31, 1.25), (-0.235, 0.0, 1.13), (-0.255, 0.03, 0.86)),
    "rail": ((0.25, 0.14, 1.13), (0.22, 0.36, 1.02), (-0.25, 0.14, 1.13), (-0.22, 0.36, 1.02)),
    # phone in the right hand in front of the chest, a cup in the left hand
    "phone": ((0.22, 0.10, 1.10), (0.10, 0.31, 1.20), (-0.23, 0.08, 1.10), (-0.24, 0.30, 1.13)),
    # filming: right arm up holding a phone out at head height
    "film": ((0.25, 0.20, 1.40), (0.17, 0.42, 1.58), (-0.235, 0.0, 1.13), (-0.255, 0.03, 0.86)),
}


def hand_position(pose="hold", side=1):
    e_r, w_r, e_l, w_l = POSES[pose]
    w = Vector(w_r if side > 0 else w_l)
    e = Vector(e_r if side > 0 else e_l)
    return tuple(w + (w - e).normalized() * 0.07)


def _tube(mb, p0, p1, r0, r1, mat, seg=10):
    """Tapered tube between two points with closed ends."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = (p1 - p0).normalized()
    ref = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))
    u = axis.cross(ref).normalized()
    v = axis.cross(u).normalized()
    b = len(mb.verts)
    for p, r in ((p0, r0), (p1, r1)):
        for k in range(seg):
            a = 2 * math.pi * k / seg
            q = p + (u * math.cos(a) + v * math.sin(a)) * r
            mb.verts.append(tuple(q))
    for k in range(seg):
        k2 = (k + 1) % seg
        mb.faces.append((b + k, b + k2, b + seg + k2, b + seg + k))
        mb.mats.append(mat)
    mb.faces.append(tuple(b + seg + k for k in range(seg)))
    mb.mats.append(mat)
    mb.faces.append(tuple(b + k for k in reversed(range(seg))))
    mb.mats.append(mat)


def _blob(mb, c, r, mat, subdiv=2):
    mb.ico(c, r, subdiv, mat)


def _loft_z(mb, sections, mat, seg=14):
    """Closed loft of horizontal ellipses [(z, rx, ry, cy), ...]."""
    b = len(mb.verts)
    for z, rx, ry, cy in sections:
        for k in range(seg):
            a = 2 * math.pi * k / seg
            mb.verts.append((rx * math.cos(a), cy + ry * math.sin(a), z))
    for s in range(len(sections) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            mb.faces.append((b + s * seg + k, b + s * seg + k2, b + (s + 1) * seg + k2, b + (s + 1) * seg + k))
            mb.mats.append(mat)
    mb.faces.append(tuple(b + k for k in reversed(range(seg))))
    mb.mats.append(mat)
    last = (len(sections) - 1) * seg
    mb.faces.append(tuple(b + last + k for k in range(seg)))
    mb.mats.append(mat)


def person_mesh(materials, pose="stand", name=None, shades=False, prop=None):
    """materials: [shirt, pants, skin, hair, shoes] (+ [glass] with shades). prop(mb, pose): adds a hand-held
    prop to the same mesh (its material indices follow the ones above)."""
    mb = rf.MeshBuilder()
    for sx in (-1, 1):
        x = sx * 0.095
        _blob(mb, (x, 0.04, 0.045), (0.055, 0.125, 0.048), SHOES, 2)
        _tube(mb, (x, 0.0, 0.08), (x, 0.0, 0.49), 0.052, 0.064, PANTS)
        _tube(mb, (x, 0.0, 0.47), (sx * 0.1, 0.0, 0.92), 0.066, 0.086, PANTS)
    _blob(mb, (0, 0, 0.93), (0.165, 0.105, 0.1), PANTS, 2)
    _loft_z(mb, [(0.9, 0.15, 0.095, 0.0), (1.02, 0.148, 0.093, 0.0), (1.18, 0.16, 0.1, 0.005),
                 (1.33, 0.19, 0.108, 0.0), (1.43, 0.19, 0.1, -0.005), (1.48, 0.1, 0.065, -0.005)], SHIRT)
    _tube(mb, (0, -0.005, 1.46), (0, 0.0, 1.57), 0.045, 0.042, SKIN, 8)
    _blob(mb, (0, 0.008, 1.645), (0.083, 0.098, 0.108), SKIN, 2)
    _blob(mb, (0, -0.018, 1.678), (0.088, 0.098, 0.086), HAIR, 2)
    if shades:
        _blob(mb, (0, 0.108, 1.632), (0.013, 0.017, 0.022), SKIN, 1)
        for sx in (-1, 1):
            _blob(mb, (sx * 0.034, 0.104, 1.664), (0.027, 0.011, 0.019), SHADES, 2)
            _tube(mb, (sx * 0.06, 0.1, 1.668), (sx * 0.087, 0.0, 1.668), 0.004, 0.004, SHADES, 6)
        _tube(mb, (-0.01, 0.112, 1.668), (0.01, 0.112, 1.668), 0.004, 0.004, SHADES, 6)
    e_r, w_r, e_l, w_l = POSES[pose]
    for sx, e, w in ((1, e_r, w_r), (-1, e_l, w_l)):
        sh = (sx * 0.195, -0.005, 1.4)
        _blob(mb, sh, (0.06, 0.06, 0.055), SHIRT, 1)
        _tube(mb, sh, e, 0.05, 0.043, SHIRT, 8)
        _tube(mb, e, w, 0.041, 0.034, SKIN, 8)
        we, ww = Vector(e), Vector(w)
        _blob(mb, tuple(ww + (ww - we).normalized() * 0.05), (0.038, 0.03, 0.05), SKIN, 1)
    if prop is not None:
        prop(mb, pose)
    me = mb.build(name or f"person_{pose}", materials, fix_normals=True, smooth=True)
    return me


def person_materials(M):
    """Shirt/pants/skin from city_balcony.make_materials(), plus hair and shoes."""
    hair = rf.make_material("hair", lambda nt: nt.ramp(nt.object_random(), [(0.0, (0.02, 0.015, 0.01)),
                                                                            (0.6, (0.09, 0.05, 0.025)),
                                                                            (1.0, (0.35, 0.22, 0.1))]),
                            rough=0.6)
    shoes = rf.make_material("shoes", lambda nt: nt.ramp(nt.object_random(), [(0.0, (0.02, 0.02, 0.02)),
                                                                             (0.7, (0.25, 0.22, 0.2)),
                                                                             (1.0, (0.85, 0.85, 0.85))]),
                             rough=0.5)
    return [M["shirt"], M["pants"], M["skin"], hair, shoes]
