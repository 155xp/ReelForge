"""Big procedural scenery for the city worlds: a mountain range round the city plain, a cumulus cloud field with
a thin deck underneath, built with numpy so a few million triangles stay quick to generate.

  mountain_range(...)   heightfield ring (ridged noise + named massifs, e.g. an 8,849 m 'Everest')
  cloud_field(...)      puff clusters in tiles (finer near the centre), flat bottoms at the cloud base
  cloud_deck(...)       noise-alpha sheet under the puffs so the far field reads as one layer
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils import noise as mnoise

import rf_common as rf

_ICO = {}


def unit_ico(subdiv):
    if subdiv not in _ICO:
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        v = np.array([tuple(x.co) for x in bm.verts], dtype=np.float32)
        f = np.array([[x.index for x in face.verts] for face in bm.faces], dtype=np.int32)
        bm.free()
        _ICO[subdiv] = (v, f)
    return _ICO[subdiv]


def mesh_from_arrays(name, verts, faces, materials, mat_index=None, smooth=True):
    """Triangle mesh from numpy arrays (verts N x 3, faces M x 3)."""
    me = bpy.data.meshes.new(name)
    verts = np.asarray(verts, dtype=np.float32)
    faces = np.asarray(faces, dtype=np.int32)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    n = len(faces)
    me.loops.add(n * 3)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(n)
    me.polygons.foreach_set("loop_start", np.arange(0, n * 3, 3, dtype=np.int32))
    if hasattr(me.polygons[0] if n else None, "loop_total"):
        try:
            me.polygons.foreach_set("loop_total", np.full(n, 3, dtype=np.int32))
        except (AttributeError, RuntimeError):
            pass
    for m in materials:
        me.materials.append(m)
    if mat_index is not None:
        me.polygons.foreach_set("material_index", np.asarray(mat_index, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate()
    if smooth:
        me.polygons.foreach_set("use_smooth", np.ones(len(me.polygons), dtype=bool))
    return me


# ---------------------------------------------------------------- mountains

def _mountain_material():
    def base(nt):
        tc = nt.node("ShaderNodeTexCoord")
        sep = nt.node("ShaderNodeSeparateXYZ")
        nrm = nt.node("ShaderNodeSeparateXYZ")
        nt.links.new(tc.outputs["Object"], sep.inputs[0])
        nt.links.new(tc.outputs["Normal"], nrm.inputs[0])
        z = sep.outputs["Z"]
        n = nt.node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1 / 900.0
        n.inputs["Detail"].default_value = 8.0
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        jitter = nt.math("MULTIPLY", nt.math("SUBTRACT", n.outputs["Fac"], 0.5), 1400.0)
        zz = nt.math("ADD", z, jitter)
        rock = nt.mix_color(n.outputs["Fac"], (0.16, 0.14, 0.13, 1.0), (0.30, 0.27, 0.24, 1.0))
        forest = nt.mix_color(n.outputs["Fac"], (0.05, 0.09, 0.04, 1.0), (0.12, 0.16, 0.07, 1.0))
        col = nt.mix_color(nt.math("DIVIDE", nt.math("SUBTRACT", zz, 900.0), 900.0, clamp=True), forest, rock)
        flat = nt.math("DIVIDE", nt.math("SUBTRACT", nrm.outputs["Z"], 0.55), 0.2, clamp=True)
        snow = nt.math("MULTIPLY", nt.math("DIVIDE", nt.math("SUBTRACT", zz, 4500.0), 900.0, clamp=True),
                       nt.math("ADD", 0.25, nt.math("MULTIPLY", flat, 0.75)))
        return nt.mix_color(snow, col, (0.88, 0.9, 0.95, 1.0))

    return rf.make_material("mountains", base, rough=0.85, haze=1.0, glitch=False)


def mountain_range(collection, seed=5, inner=24000.0, outer=80000.0, res=420, base_height=5200.0, massifs=()):
    """Heightfield over [-outer, outer]^2, flat (and dropped out) inside `inner`. massifs: [(x, y, peak, sigma)]."""
    xs = np.linspace(-outer, outer, res)
    X, Y = np.meshgrid(xs, xs)
    R = np.hypot(X, Y)
    rise = np.clip((R - inner) / 14000.0, 0, 1)
    rise = rise * rise * (3 - 2 * rise)
    H = np.zeros_like(X)
    off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
    for i in range(res):
        for j in range(res):
            if rise[i, j] <= 0:
                continue
            p = Vector((X[i, j] / 21000.0, Y[i, j] / 21000.0, 0.0)) + off
            h = mnoise.ridged_multi_fractal(p, 0.9, 2.1, 7, 1.0, 2.0)
            H[i, j] = h
    ridge = np.clip(H / max(H.max(), 1e-6), 0, 1)
    H = ridge ** 1.6 * base_height * rise
    summits = []
    for (mx, my, peak, sigma) in massifs:
        d = np.sqrt((X - mx) ** 2 + (Y - my) ** 2)
        # a massif: broad base, rounded top, carved by the same ridges so it keeps its gullies; scaled so its
        # highest point is exactly `peak`
        env = 1.0 / (1.0 + (d / sigma) ** 2)
        m = env * (0.5 + 0.5 * ridge ** 0.7) * rise
        k = np.unravel_index(np.argmax(m), X.shape)
        H = np.maximum(H, m * (peak / m[k]))
        summits.append((float(X[k]), float(Y[k]), float(peak)))
    H = np.where(rise > 0, H, -40.0)
    verts = np.stack([X.ravel(), Y.ravel(), H.ravel()], 1)
    idx = np.arange(res * res).reshape(res, res)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    keep = (rise[:-1, :-1] + rise[:-1, 1:] + rise[1:, 1:] + rise[1:, :-1]) > 0
    t1 = np.stack([a[keep], b[keep], c[keep]], 1)
    t2 = np.stack([a[keep], c[keep], d[keep]], 1)
    faces = np.concatenate([t1, t2])
    used = np.unique(faces)
    remap = -np.ones(res * res, dtype=np.int64)
    remap[used] = np.arange(len(used))
    me = mesh_from_arrays("mountains", verts[used], remap[faces], [_mountain_material()])
    ob = rf.add_object("mountains", me, collection)
    return ob, H.max(), summits


# ---------------------------------------------------------------- clouds

def cloud_material(name="cloud_puff"):
    """Matte white with a soft wrap-around fill: lit sides take the sun's colour, shaded sides go blue-grey rather
    than black (light scattering through the cloud), plus a thin silver lining on the edges."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    tc = nt.node("ShaderNodeTexCoord")
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 1 / 60.0
    n.inputs["Detail"].default_value = 6.0
    n.inputs["Roughness"].default_value = 0.6
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    bump.inputs["Distance"].default_value = 25.0
    nt.links.new(n.outputs["Fac"], bump.inputs["Height"])
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.86, 0.86, 0.9, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    attr = lambda name: nt.node("ShaderNodeAttribute", attribute_type="VIEW_LAYER", attribute_name=name)
    dot = nt.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nt.links.new(bump.outputs["Normal"], dot.inputs[0])
    nt.links.new(attr("rf_sun_dir").outputs["Vector"], dot.inputs[1])
    wrap = nt.math("POWER", nt.math("ADD", 0.5, nt.math("MULTIPLY", dot.outputs["Value"], 0.5)), 2.0)
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.4
    rim = nt.math("POWER", lw.outputs["Facing"], 4.0)          # Facing is 0 head-on, 1 at the silhouette
    warm = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(attr("rf_haze_sun").outputs["Color"], warm.inputs[0])
    nt.links.new(nt.math("ADD", nt.math("MULTIPLY", wrap, 0.22), nt.math("MULTIPLY", rim, 0.3)), warm.inputs["Scale"])
    cool = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(attr("rf_haze_col").outputs["Color"], cool.inputs[0])
    cool.inputs["Scale"].default_value = 0.16
    em = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(warm.outputs["Vector"], em.inputs[0])
    nt.links.new(cool.outputs["Vector"], em.inputs[1])
    nt.links.new(em.outputs["Vector"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    shader = rf.scene_haze(nt, b.outputs[0], 0.7) if rf.HAZE_SCENE else b.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    return mat


def _lumpy(p, c, r, phases):
    """Push sphere vertices in and out with a few sine octaves, so puffs read as cauliflower, not balls."""
    q = (p - c) / r
    d = np.zeros(len(p), dtype=np.float32)
    for (fx, fy, fz, ph, amp) in phases:
        d += amp * np.sin(q[:, 0] * fx + ph) * np.sin(q[:, 1] * fy + ph * 1.7) * np.sin(q[:, 2] * fz + ph * 0.6)
    return c + (p - c) * (1.0 + d)[:, None]


def _cumulus(rnd, px, py, base, s, uv, uf):
    """One cumulus cluster: a wide flat-bottomed base tier, then smaller domes stacked on top."""
    verts, faces = [], []
    r0 = 230.0 * s
    tiers = [(rnd.randint(3, 5), r0, 0.35, 1.25), (rnd.randint(2, 4), r0 * 0.72, 0.95, 0.8),
             (rnd.randint(1, 3), r0 * 0.5, 1.55, 0.5)]
    if rnd.random() < 0.35:
        tiers.append((rnd.randint(1, 2), r0 * 0.38, 2.05, 0.3))
    for n, r, zf, spread in tiers:
        for _ in range(n):
            rr = r * rnd.uniform(0.8, 1.2)
            c = np.array([px + rnd.uniform(-spread, spread) * r0, py + rnd.uniform(-spread, spread) * r0,
                          base + zf * r0 + rnd.uniform(-0.1, 0.1) * r0], dtype=np.float32)
            p = uv * np.array([rr * rnd.uniform(1.0, 1.3), rr * rnd.uniform(1.0, 1.3), rr * 0.9], dtype=np.float32) + c
            phases = [(rnd.uniform(3, 6), rnd.uniform(3, 6), rnd.uniform(3, 6), rnd.uniform(0, 6.3), 0.07),
                      (rnd.uniform(8, 13), rnd.uniform(8, 13), rnd.uniform(8, 13), rnd.uniform(0, 6.3), 0.035)]
            p = _lumpy(p, c, rr, phases)
            p[:, 2] = np.maximum(p[:, 2], base)          # flat cloud base
            verts.append(p)
            faces.append(uf)
    return verts, faces


def cloud_field(collection, seed=3, base=1700.0, top=2300.0, extent=45000.0, tile=3000.0, clear=None,
                coverage=0.7, near=6000.0, mid=16000.0, material=None, gaps=(), banks=()):
    """Cumulus clusters on a jittered grid, kept where a coverage noise is high. clear = (x, y, r): no clouds
    there. Detail drops with distance from the centre. Returns the tile objects."""
    rnd = random.Random(seed)
    mat = material or cloud_material()
    obs = []
    n_tiles = int(math.ceil(2 * extent / tile))
    off = Vector((seed * 1.7, seed * 2.9, 0.5))
    s_top = max(0.6, (top - base) / 460.0)
    for ti in range(n_tiles):
        for tj in range(n_tiles):
            x0, y0 = -extent + ti * tile, -extent + tj * tile
            cx, cy = x0 + tile / 2, y0 + tile / 2
            dist = math.hypot(cx, cy)
            sub = 3 if dist < near else (2 if dist < mid else 1)
            uv, uf = unit_ico(sub)
            V, F = [], []
            nv = 0
            step = 700.0
            gx = max(1, int(tile // step))
            for a in range(gx):
                for b in range(gx):
                    px = x0 + (a + rnd.random()) * tile / gx
                    py = y0 + (b + rnd.random()) * tile / gx
                    if (clear and math.hypot(px - clear[0], py - clear[1]) < clear[2]) or \
                            any(math.hypot(px - gx_, py - gy_) < gr_ for gx_, gy_, gr_ in gaps):
                        continue
                    cov = mnoise.noise(Vector((px / 11000.0, py / 11000.0, 0.0)) + off) * 0.5 + 0.5
                    cov += 0.22 * mnoise.noise(Vector((px / 3000.0, py / 3000.0, 3.0)) + off)
                    if any(math.hypot(px - bx_, py - by_) < br_ for bx_, by_, br_ in banks):
                        cov = max(cov, 1.05)          # a dense bank (e.g. round a tower the camera climbs through)
                    if cov < 1.0 - coverage:
                        continue
                    s = rnd.uniform(0.7, 1.2) * (0.75 + 0.5 * min(1.0, (cov - (1 - coverage)) * 2.5)) * s_top
                    vs, fs = _cumulus(rnd, px, py, base, s, uv, uf)
                    for v, f in zip(vs, fs):
                        V.append(v)
                        F.append(f + nv)
                        nv += len(v)
            if not V:
                continue
            me = mesh_from_arrays(f"clouds_{ti}_{tj}", np.concatenate(V), np.concatenate(F), [mat])
            ob = rf.add_object(f"clouds_{ti}_{tj}", me, collection)
            obs.append(ob)
    return obs


def cloud_deck(collection, z, extent=90000.0, name="cloud_deck", alpha_lo=0.5, alpha_span=0.18):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    tc = nt.node("ShaderNodeTexCoord")
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 1 / 4000.0
    n.inputs["Detail"].default_value = 9.0
    n.inputs["Roughness"].default_value = 0.62
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    alpha = nt.math("DIVIDE", nt.math("SUBTRACT", n.outputs["Fac"], alpha_lo), alpha_span, clamp=True)
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.9, 0.9, 0.93, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    nt.links.new(alpha, b.inputs["Alpha"])
    shader = rf.scene_haze(nt, b.outputs[0], 0.8) if rf.HAZE_SCENE else b.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    try:
        mat.surface_render_method = "BLENDED"
    except (AttributeError, TypeError):
        pass
    mb = rf.MeshBuilder()
    mb.verts += [(-extent, -extent, z), (extent, -extent, z), (extent, extent, z), (-extent, extent, z)]
    mb.faces.append((0, 1, 2, 3))
    mb.mats.append(0)
    ob = rf.add_object(name, mb.build(name, [mat]), collection)
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass
    return ob
