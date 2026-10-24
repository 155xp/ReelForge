"""World: the balcony city (worlds/city_balcony.py) made ready for a disaster.

Everything city_balcony builds is kept: the low-poly city seen from a 3rd-floor balcony up an avenue, the downtown
towers, the mountains, the traffic and the people. On top of that:
  - the aerial haze follows scene properties (look.init_haze), so an effect can turn the light orange, brown or
    green-grey over time (look.key_scene_prop: rf_haze_dist, rf_haze_max, rf_haze_col, rf_haze_sun);
  - the sky is rebuilt with keyframable colours (see SKY NODES below), a sun glow, and a second glow that an
    effect can point at its threat (a fireball, a flash, a storm);
  - the city is built wide enough to look round (the camera can turn about 20 degrees either way), with more
    mountains to the sides and fields out to the horizon;
  - the buildings nearest to you get ledges, parapets, rooftop units and window air-conditioners (parented, so
    they go with the building when it falls), and the balcony railing is dark metal, so the view holds up when the
    camera looks down at the street;
  - spec["world"]["coast"] (optional) swaps the far fields and mountains for a sea with a beach, so a wave has
    somewhere to come from: {"shore_y": 3000} (shore distance in metres up the avenue).

Spec keys (spec["world"]): everything city_balcony takes ("seed", "camera": {"location", "heading_deg",
"pitch_deg", "lens_mm"}, "props"), plus "coast", "sky" (optional starting colours: "horizon", "mid", "zenith",
RGB 0..1), "sun" ({"heading_deg": 245, "elevation_deg": 36, "energy": 4.2, "color": [1, 0.95, 0.88]}: where the
light comes from; a low sun from the side, e.g. heading 285 / elevation 22 with the camera at heading 13, rakes
across the avenue and keeps the sky in front clear for the threat), "haze_m" (7500: metres for the air to
reach 63 % haze; smaller is mistier), "build_lens_mm" (13: the lens the city is built for; wider than the camera's
so it can look round) and "detail_m" (170: buildings this close get the extra detail; 0 for none).

SKY NODES (world node tree; key them with rf.key_series(world.node_tree, 'nodes["Name"].outputs[0].default_value',
k, frames, values) for each RGB channel k, or index -1 for a value):
  SkyHorizon, SkyMid, SkyZenith   RGB colours at the horizon, ~10 degrees up and overhead
  SkyGain                         overall sky brightness (1 = as built)
  SunGlowGain                     the glow round the sun (0..)
  ThreatColor, ThreatGain, ThreatWidth   a glow round info["threat_dir"] (set once with set_threat_dir), its
                                  colour, strength and angular width (radians)
  VoidColor                       below the horizon (only seen past the edge of the world)

info gains: "sun" (the sun lamp), "sun_dir", "haze_m", "collections" ({"city", "life", "sky", "near", "hero"}), "sea" (with
coast), and the helper key "sky_nodes" (names above).
"""
import math
import random

import bpy
from mathutils import Matrix

import look
import rf_common as rf
from worlds import city_balcony as cb

HORIZON = (0.80, 0.83, 0.88)
MID = (0.50, 0.64, 0.86)
ZENITH = (0.17, 0.32, 0.72)
SUN_HEADING, SUN_ELEVATION = 245.0, 36.0          # city_balcony's sun (rf.add_sun)
SKY_NODES = ("SkyHorizon", "SkyMid", "SkyZenith", "SkyGain", "SunGlowGain", "ThreatColor", "ThreatGain",
             "ThreatWidth", "VoidColor")


def _sun(W):
    S = W.get("sun", {})
    return (float(S.get("heading_deg", SUN_HEADING)), float(S.get("elevation_deg", SUN_ELEVATION)),
            float(S.get("energy", 4.2)), tuple(S.get("color", (1.0, 0.95, 0.88))))


def make_sky(scene, sun_dir, horizon=HORIZON, mid=MID, zenith=ZENITH):
    """Gradient sky with keyframable colours, a sun glow and a 'threat' glow. Returns the world."""
    world = bpy.data.worlds.new("RF_DisasterSky")
    scene.world = world
    world.use_nodes = True
    nt = rf.NodeTree(world.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputWorld")
    bg = nt.node("ShaderNodeBackground")

    def rgb(name, col):
        nd = nt.node("ShaderNodeRGB", name=name, label=name)
        nd.outputs[0].default_value = rf.rgba(col)
        return nd.outputs[0]

    def val(name, v):
        nd = nt.node("ShaderNodeValue", name=name, label=name)
        nd.outputs[0].default_value = v
        return nd.outputs[0]

    tc = nt.node("ShaderNodeTexCoord")
    nrm = nt.node("ShaderNodeVectorMath", operation="NORMALIZE")
    nt.links.new(tc.outputs["Generated"], nrm.inputs[0])
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(nrm.outputs["Vector"], sep.inputs[0])
    z = sep.outputs["Z"]
    hz, md, zn = rgb("SkyHorizon", horizon), rgb("SkyMid", mid), rgb("SkyZenith", zenith)
    lo = nt.math("DIVIDE", z, 0.17, clamp=True)                       # horizon -> mid over the first ~10 degrees
    hi = nt.math("POWER", nt.math("DIVIDE", nt.math("SUBTRACT", z, 0.17), 0.83, clamp=True), 0.7)
    col = nt.mix_color(nt.math("POWER", lo, 0.8), hz, md)
    col = nt.mix_color(hi, col, zn)

    def glow(direction_sock, color, gain, width):
        dot = nt.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        nt.links.new(nrm.outputs["Vector"], dot.inputs[0])
        if isinstance(direction_sock, tuple):
            dot.inputs[1].default_value = direction_sock
        else:
            nt.links.new(direction_sock, dot.inputs[1])
        ang = nt.math("ARCCOSINE", nt.math("MINIMUM", dot.outputs["Value"], 1.0))
        g = nt.math("EXPONENT", nt.math("DIVIDE", ang, nt.math("MULTIPLY", width, -1.0)))
        sc = nt.node("ShaderNodeVectorMath", operation="SCALE")
        nt.links.new(color, sc.inputs[0])
        nt.links.new(nt.math("MULTIPLY", g, gain), sc.inputs["Scale"])
        return sc.outputs["Vector"]

    sun_glow = glow(tuple(sun_dir), rgb("SunGlowColor", (1.0, 0.86, 0.66)), val("SunGlowGain", 0.35), 0.22)
    tdir = nt.node("ShaderNodeCombineXYZ", name="ThreatDir", label="ThreatDir")
    tdir.inputs[1].default_value = 1.0
    threat = glow(tdir.outputs[0], rgb("ThreatColor", (1.0, 0.6, 0.3)), val("ThreatGain", 0.0), val("ThreatWidth", 0.2))
    add = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(col, add.inputs[0])
    nt.links.new(sun_glow, add.inputs[1])
    add2 = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(add.outputs["Vector"], add2.inputs[0])
    nt.links.new(threat, add2.inputs[1])
    gain = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(add2.outputs["Vector"], gain.inputs[0])
    nt.links.new(val("SkyGain", 1.0), gain.inputs["Scale"])
    below = nt.math("LESS_THAN", z, -0.004)
    final = nt.mix_color(below, gain.outputs["Vector"], rgb("VoidColor", (0.03, 0.03, 0.035)))
    nt.links.new(final, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return world


def set_threat_dir(world, direction):
    nd = world.node_tree.nodes["ThreatDir"]
    for k in range(3):
        nd.inputs[k].default_value = float(direction[k])


def _sea_material():
    """Deep blue-green water: glossy, with a slow noise ripple in the normal and a darker trough colour."""
    def base(nt):
        tc = nt.node("ShaderNodeTexCoord")
        n = nt.node("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 1 / 70.0
        n.inputs["Detail"].default_value = 6.0
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
        return nt.mix_color(n.outputs["Fac"], (0.012, 0.045, 0.06, 1.0), (0.03, 0.10, 0.12, 1.0))

    mat = rf.make_material("sea", base, rough=0.12, haze=1.0, glitch=False)
    nt = rf.NodeTree(mat.node_tree)
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tc = nt.node("ShaderNodeTexCoord")
    wav = nt.node("ShaderNodeTexWave")
    wav.inputs["Scale"].default_value = 1 / 30.0
    wav.inputs["Distortion"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], wav.inputs["Vector"])
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    nt.links.new(wav.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _make_coast(info, W, collections):
    """Far fields and mountains out, a beach and a sea in (for a wave)."""
    C = W.get("coast", {})
    shore = float(C.get("shore_y", 3000.0))
    keep = []
    for ob in info["static"]:
        far_field = ob.name.startswith("chunk_") and ob.data and ob.data.name.startswith("chunk_field")
        if ob.name.startswith("mountain_") or far_field or (ob.name.startswith("chunk_") and ob.location.y > shore):
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        if ob.name.startswith("bldg") and ob.location.y > shore - 60:
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        keep.append(ob)
    info["static"] = keep
    sand = rf.make_material("beach", (0.62, 0.55, 0.40), rough=0.95)
    mb = rf.MeshBuilder()
    mb.box(-8000, shore - 62, -0.2, 8000, shore + 140, 0.12, 0)
    beach = rf.add_object("beach", mb.build("beach", [sand]), collections["city"])
    beach["rf_ud"] = shore
    beach["rf_size"] = 200.0
    mb = rf.MeshBuilder()
    mb.verts += [(-60000, shore + 60, 0.0), (60000, shore + 60, 0.0), (60000, 90000, 0.0), (-60000, 90000, 0.0)]
    mb.faces.append((0, 1, 2, 3))
    mb.mats.append(0)
    sea = rf.add_object("sea", mb.build("sea", [_sea_material()]), collections["city"])
    sea["rf_ud"] = shore
    sea["rf_size"] = 90000.0
    info["static"] += [beach, sea]
    info["sea"] = sea
    info["shore_y"] = shore


def _extra_mountains(info, W, cam_pos, heading, collection):
    """city_balcony's range covers -18..+50 degrees round the view; add crags further round both sides."""
    mat, snow = bpy.data.materials.get("mountain"), bpy.data.materials.get("snow")
    if mat is None:
        return
    rnd = random.Random(W.get("seed", 1) * 31 + 7)
    for k, h_rel in enumerate((-25.5, -33.0, -40.5, -48.0, -55.5, -63.0, 57.0, 64.5)):
        my = rnd.uniform(3550, 3850)
        mx = cam_pos.x + (my - cam_pos.y) * math.tan(math.radians(heading + h_rel))
        rx, ry, rz = rnd.uniform(700, 1300), rnd.uniform(300, 450), rnd.uniform(500, 1050)
        mb = rf.MeshBuilder()
        mb.ico((0, 0, -rz * 0.2), (rx, ry, rz), 2, 0, jitter=0.12, rnd=rnd)
        if rz > 650:
            mb.ico((0, 0, rz * 0.66), (rx * 0.2, ry * 0.25, rz * 0.15), 1, 1, jitter=0.1, rnd=rnd)
        ob = rf.add_object(f"mountain_x{k}", mb.build(f"mountain_x{k}", [mat, snow]), collection, (mx, my, 0.0))
        ob["rf_ud"] = math.hypot(mx - cam_pos.x, my - cam_pos.y) - rx
        ob["rf_size"] = 2 * rx
        ob["glitch"] = 0.0
        info["static"].append(ob)


def _far_ground(cam_pos, collection):
    """Fields from under the city out to the horizon, all the way round."""
    mat = bpy.data.materials.get("field")
    mb = rf.MeshBuilder()
    seg, radii = 96, (150.0, 3000.0, 12000.0, 45000.0)
    for r in radii:
        for k in range(seg):
            a = 2 * math.pi * k / seg
            mb.verts.append((cam_pos.x + r * math.cos(a), cam_pos.y + r * math.sin(a), -0.6))
    for j in range(len(radii) - 1):
        for k in range(seg):
            k2 = (k + 1) % seg
            mb.faces.append((j * seg + k, j * seg + k2, (j + 1) * seg + k2, (j + 1) * seg + k))
            mb.mats.append(0)
    ob = rf.add_object("far_ground", mb.build("far_ground", [mat] if mat else []), collection)
    ob["glitch"] = 0.0
    return ob


def _dress(info, W, cam_pos, collection):
    """Ledges, a parapet, rooftop units and window air-conditioners on the buildings nearest to you, parented to
    each building (keeping their place), so they fall with it."""
    near_m = float(W.get("detail_m", 170.0))
    if near_m <= 0:
        return 0
    rnd = random.Random(W.get("seed", 1) * 17 + 3)
    ledge = rf.make_material("ledge", (0.62, 0.60, 0.56), rough=0.8, glitch=False)
    unit = rf.make_material("roof_unit", (0.58, 0.59, 0.60), rough=0.45, metallic=0.3, glitch=False)
    dark = rf.make_material("roof_dark", (0.16, 0.15, 0.15), rough=0.7, glitch=False)
    n = 0
    for ob in list(info["static"]):
        if not ob.name.startswith("bldg") or ob.get("rf_ud", 1e9) > near_m:
            continue
        w, d, h = ob.scale
        cx, cy, z0 = ob.location
        x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2
        top = z0 + h
        mb = rf.MeshBuilder()
        k = 2
        while 3.4 * k < h - 1.5:                               # a ledge round every floor
            z = z0 + 3.4 * k
            mb.box(x0 - 0.22, y0 - 0.22, z - 0.1, x1 + 0.22, y1 + 0.22, z + 0.1, 0)
            k += 1
        t = 0.32                                                # the parapet round the roof
        for bx in ((x0, y0, x1, y0 + t), (x0, y1 - t, x1, y1), (x0, y0, x0 + t, y1), (x1 - t, y0, x1, y1)):
            mb.box(bx[0] - 0.05, bx[1] - 0.05, top, bx[2] + 0.05, bx[3] + 0.05, top + 1.1, 0)
        for _ in range(rnd.randint(1, 3)):                      # air handlers and stair huts on the roof
            sx, sy, sz = rnd.uniform(2, max(2.5, min(6, w * 0.3))), rnd.uniform(2, max(2.5, min(5, d * 0.3))), \
                rnd.uniform(1.2, 3.2)
            px, py = rnd.uniform(x0 + 1.5, max(x0 + 1.6, x1 - 1.5 - sx)), rnd.uniform(y0 + 1.5, max(y0 + 1.6, y1 - 1.5 - sy))
            mb.box(px, py, top, px + sx, py + sy, top + sz, 1 if rnd.random() < 0.6 else 2)
        if rnd.random() < 0.35 and w > 14 and d > 14:           # a water tank on legs
            px, py = rnd.uniform(x0 + 4, x1 - 4), rnd.uniform(y0 + 4, y1 - 4)
            for lx, ly in ((-1.2, -1.2), (1.2, -1.2), (1.2, 1.2), (-1.2, 1.2)):
                mb.box(px + lx - 0.12, py + ly - 0.12, top, px + lx + 0.12, py + ly + 0.12, top + 1.6, 2)
            mb.cyl(px, py, top + 1.6, top + 4.4, 1.9, 12, 2, r_top=1.7)
        # window air-conditioners under a few windows on the faces you can see
        faces = []
        if cam_pos.y < y0:
            faces.append(("y", y0, -1, x0, x1))
        elif cam_pos.y > y1:
            faces.append(("y", y1, 1, x0, x1))
        if cam_pos.x < x0:
            faces.append(("x", x0, -1, y0, y1))
        elif cam_pos.x > x1:
            faces.append(("x", x1, 1, y0, y1))
        for axis, at, sgn, u0, u1 in faces:
            for _ in range(rnd.randint(3, 9)):
                u = 3.2 * (math.floor(rnd.uniform(u0, u1) / 3.2) + 0.5)
                fl = rnd.randint(2, max(2, int(h / 3.4) - 1))
                z = z0 + 3.4 * fl + 0.28 * 3.4 - 0.55
                if not (u0 + 0.8 < u < u1 - 0.8) or z > top - 2:
                    continue
                o0, o1 = (at - 0.55, at) if sgn < 0 else (at, at + 0.55)
                if axis == "y":
                    mb.box(u - 0.45, o0, z - 0.3, u + 0.45, o1, z + 0.3, 1)
                else:
                    mb.box(o0, u - 0.45, z - 0.3, o1, u + 0.45, z + 0.3, 1)
        dr = rf.add_object("bldg_detail", mb.build("bldg_detail", [ledge, unit, dark]), collection)
        dr["glitch"] = 0.0
        dr.parent = ob
        dr.matrix_parent_inverse = Matrix.LocRotScale(ob.location, ob.rotation_euler.to_quaternion(),
                                                      ob.scale).inverted()
        n += 1
    return n


def _restyle_railing():
    """city_balcony's railing is white; up close a dark metal one reads better against the city."""
    mat = bpy.data.materials.get("rail")
    bsdf = next((nd for nd in mat.node_tree.nodes if nd.type == "BSDF_PRINCIPLED"), None) if mat else None
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.05, 0.055, 0.06, 1.0)
        bsdf.inputs["Metallic"].default_value = 0.65
        bsdf.inputs["Roughness"].default_value = 0.35


def build(spec):
    W = spec["world"]
    scene = bpy.context.scene
    heading, elevation, energy, color = _sun(W)
    sun_dir = look.sun_vector(heading, elevation)
    # haze driven by scene properties, so the effect can change its colour and density over time
    haze_m = float(W.get("haze_m", 7500.0))
    look.init_haze(scene, sun_dir, dist=haze_m, hmax=0.85, col=(0.70, 0.76, 0.85), sun_col=(1.0, 0.86, 0.66))
    cam_spec = W["camera"]
    build_lens = float(W.get("build_lens_mm", min(cam_spec["lens_mm"], 13.0)))
    info = cb.build(dict(spec, world=dict(W, camera=dict(cam_spec, lens_mm=build_lens))))   # wide enough to look round
    info["camera"].data.lens = cam_spec["lens_mm"]
    S = W.get("sky", {})
    world = make_sky(scene, sun_dir, S.get("horizon", HORIZON), S.get("mid", MID), S.get("zenith", ZENITH))
    info["world"] = world
    sun = bpy.data.objects.get("Sun")
    if sun:
        # the same convention as rf.add_sun: the lamp shines down its -Z, away from where the sun is
        sun.rotation_euler = (math.radians(90.0 - elevation), 0.0, math.radians(-heading + 180.0))
        sun.data.energy = energy
        sun.data.color = color
    info["sun"] = sun
    info["sun_dir"] = sun_dir
    info["haze_m"] = haze_m
    cols = {"city": bpy.data.collections["City"], "life": bpy.data.collections["Life"],
            "sky": bpy.data.collections["Sky"], "near": bpy.data.collections["Balcony"]}
    cols["hero"] = cols["near"]
    info["collections"] = cols
    info["scene"] = scene
    info["sky_nodes"] = SKY_NODES
    cam_pos = info["cam_pos"]
    _far_ground(cam_pos, cols["city"])
    if W.get("coast"):
        _make_coast(info, W, cols)
    else:
        _extra_mountains(info, W, cam_pos, cam_spec["heading_deg"], cols["city"])
    dressed = _dress(info, W, cam_pos, cols["city"])
    _restyle_railing()
    print(f"[disaster_city] coast={bool(W.get('coast'))} static={len(info['static'])} detailed buildings={dressed}")
    return info
