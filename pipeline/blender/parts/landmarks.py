"""Landmark stand-ins at true height, for 'taller than ...' comparisons. Each returns a list of segment objects
stacked bottom to top (origin at each segment's bottom centre, so an effect can topple or drop them):
  supertall()   828 m Y-plan spire tower (Burj Khalifa's height)
  art_deco()    443 m to the mast tip with setbacks (Empire State Building's height)
  obelisk()     169 m marble obelisk (Washington Monument's height)
"""
import math

import rf_common as rf
import facades


def _segments(builder_fn, cuts, name, mats, collection, location):
    """Build one mesh per height range [cuts[k], cuts[k+1]) with builder_fn(mb, z0, z1, z_offset)."""
    obs = []
    for k in range(len(cuts) - 1):
        z0, z1 = cuts[k], cuts[k + 1]
        mb = rf.MeshBuilder()
        builder_fn(mb, z0, z1)
        mb.verts = [(x, y, z - z0) for x, y, z in mb.verts]
        ob = rf.add_object(f"{name}_{k}", mb.build(f"{name}_{k}", mats, fix_normals=True), collection,
                           (location[0], location[1], location[2] + z0))
        ob["glitch"] = 0.0
        ob["tower"] = 1.0
        ob["shattered"] = 0.0
        ob["lit"] = 0.0
        obs.append(ob)
    return obs


def _clip_box(mb, x0, y0, z0, x1, y1, z1, lo, hi, mat):
    a, b = max(z0, lo), min(z1, hi)
    if b > a:
        mb.box(x0, y0, a, x1, y1, b, mat)


def supertall(collection, location=(0, 0, 0), height=828.0, cuts=None):
    """Three wings round a hexagonal core, stepping back as they rise, then a spire."""
    glass = facades.building_material("supertall_glass", "glass", lit=0.12)
    steel = rf.make_material("supertall_steel", (0.75, 0.77, 0.8), rough=0.25, metallic=0.85, glitch=True)
    cuts = cuts or [0.0, 210.0, 420.0, 600.0, height]
    k_h = height / 828.0
    tiers = []
    z = 0.0
    lengths = [44.0, 44.0, 44.0]
    step = 0
    while z < 585.0 * k_h:
        h = 32.0 * k_h
        tiers.append((z, z + h, tuple(lengths)))
        lengths[step % 3] = max(8.0, lengths[step % 3] - 5.4)
        step += 1
        z += h

    def build(mb, z0, z1):
        for (a, b, L) in tiers:
            for w, length in enumerate(L):
                ang = math.radians(90 + 120 * w)
                # a wing is a box along its axis, rotated into place
                half = 8.5
                pts = [(0, -half), (length, -half), (length, half), (0, half)]
                rot = [(px * math.cos(ang) - py * math.sin(ang), px * math.sin(ang) + py * math.cos(ang)) for px, py in pts]
                lo, hi = max(a, z0), min(b, z1)
                if hi <= lo:
                    continue
                base = len(mb.verts)
                for zz in (lo, hi):
                    for (px, py) in rot:
                        mb.verts.append((px, py, zz))
                for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
                    mb.faces.append(tuple(base + i for i in q))
                    mb.mats.append(0)
        top_core = 600.0 * k_h
        lo, hi = max(0.0, z0), min(top_core, z1)
        if hi > lo:
            mb.cyl(0, 0, lo, hi, 12.0, 6, 0)
        # spire, tapering in stages
        for (a, b, r0, r1) in ((top_core, 700.0 * k_h, 9.0, 6.0), (700.0 * k_h, 790.0 * k_h, 6.0, 2.8),
                               (790.0 * k_h, height, 2.8, 0.5)):
            lo, hi = max(a, z0), min(b, z1)
            if hi > lo:
                f0 = (lo - a) / (b - a)
                f1 = (hi - a) / (b - a)
                mb.cyl(0, 0, lo, hi, r0 + (r1 - r0) * f0, 12, 1, r_top=r0 + (r1 - r0) * f1)

    return _segments(build, cuts, "supertall", [glass, steel], collection, location)


def art_deco(collection, location=(0, 0, 0), cuts=None):
    stone = facades.building_material("artdeco_stone", "stone", lit=0.16)
    metal = rf.make_material("artdeco_mast", (0.7, 0.72, 0.75), rough=0.3, metallic=0.8, glitch=True)
    cuts = cuts or [0.0, 120.0, 250.0, 381.0, 443.0]
    blocks = [(60, 42, 0, 22), (46, 32, 22, 88), (38, 27, 88, 230), (31, 22, 230, 320), (24, 16, 320, 368),
              (16, 12, 368, 381)]

    def build(mb, z0, z1):
        for w, d, a, b in blocks:
            _clip_box(mb, -w / 2, -d / 2, a, w / 2, d / 2, b, z0, z1, 0)
            # vertical piers on the main shaft
            if 88 <= a < 320:
                for sx in (-1, 1):
                    _clip_box(mb, sx * w / 2 - 1.0, -d / 2 - 0.5, a, sx * w / 2 + 1.0, d / 2 + 0.5, b, z0, z1, 0)
        for (a, b, r0, r1) in ((381.0, 404.0, 7.0, 5.0), (404.0, 420.0, 4.0, 3.0), (420.0, 443.0, 1.0, 0.35)):
            lo, hi = max(a, z0), min(b, z1)
            if hi > lo:
                f0, f1 = (lo - a) / (b - a), (hi - a) / (b - a)
                mb.cyl(0, 0, lo, hi, r0 + (r1 - r0) * f0, 10, 1, r_top=r0 + (r1 - r0) * f1)

    return _segments(build, cuts, "artdeco", [stone, metal], collection, location)


def obelisk(collection, location=(0, 0, 0), height=169.3):
    marble = rf.make_material("obelisk_marble", (0.86, 0.84, 0.8), rough=0.45, glitch=True)
    k = height / 169.3

    def build(mb, z0, z1):
        shaft_top = 152.4 * k
        b0, b1 = 8.4 * k, 5.25 * k
        verts = [(-b0, -b0, 0), (b0, -b0, 0), (b0, b0, 0), (-b0, b0, 0),
                 (-b1, -b1, shaft_top), (b1, -b1, shaft_top), (b1, b1, shaft_top), (-b1, b1, shaft_top),
                 (0, 0, height)]
        base = len(mb.verts)
        mb.verts += verts
        for q in ((0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            mb.faces.append(tuple(base + i for i in q))
            mb.mats.append(0)
        for a, b in ((4, 5), (5, 6), (6, 7), (7, 4)):
            mb.faces.append((base + a, base + b, base + 8))
            mb.mats.append(0)

    return _segments(build, [0.0, height], "obelisk", [marble], collection, location)
