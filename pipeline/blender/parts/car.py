"""Low-poly sports car: lofted body + cabin, separate wheels, lights, and effect shells.

Object attributes the effect can keyframe:
  body["heat"]    0..1  nose glows orange-white (hypersonic heating)
  plasma["fx"]    0..1  plasma sheath around the nose; plasma["phase"] scrolls its flicker
  vapor["fx"]     0..1  sonic-boom vapour cone
  ring["fx"]      0..1  shock ring opacity (scale it up to expand)
"""
import math
import random

import bpy

import rf_common as rf


def _set(mat, **props):
    for k, v in props.items():
        try:
            setattr(mat, k, v)
        except (AttributeError, TypeError):
            pass


def _new(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return mat, nt, nt.node("ShaderNodeOutputMaterial")


def _principled(name, color, rough, metallic=0.0, emission=None):
    mat, nt, out = _new(name)
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = rf.rgba(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    if emission:
        b.inputs["Emission Color"].default_value = rf.rgba(emission[0])
        b.inputs["Emission Strength"].default_value = emission[1]
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return mat


def _paint(color):
    """Glossy paint whose front half glows when obj["heat"] rises."""
    mat, nt, out = _new("car_paint_hero")
    b = nt.node("ShaderNodeBsdfPrincipled")
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    front = nt.math("DIVIDE", nt.math("SUBTRACT", sep.outputs["Y"], 0.2), 2.1, clamp=True)
    front = nt.math("POWER", front, 1.6)
    heat = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="heat").outputs["Fac"]
    glow = nt.math("MULTIPLY", front, heat)
    base = nt.mix_color(glow, rf.rgba(color), (1.0, 0.55, 0.2, 1.0))
    nt.links.new(base, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.2
    b.inputs["Metallic"].default_value = 0.55
    b.inputs["Emission Color"].default_value = (1.0, 0.42, 0.12, 1.0)
    nt.links.new(nt.math("MULTIPLY", glow, 9.0), b.inputs["Emission Strength"])
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return mat


def _fx(name, color, strength, noise_scale=3.0, fresnel=True, edge=2.0):
    """Additive glow shell: emission * fresnel * noise * obj["fx"]."""
    mat, nt, out = _new(name)
    fx = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fx").outputs["Fac"]
    phase = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="phase").outputs["Fac"]
    tc = nt.node("ShaderNodeTexCoord")
    noise = nt.node("ShaderNodeTexNoise", noise_dimensions="4D")
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(phase, noise.inputs["W"])
    a = nt.math("MULTIPLY", fx, nt.math("POWER", noise.outputs["Fac"], 1.5))
    if fresnel:
        lw = nt.node("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.35
        a = nt.math("MULTIPLY", a, nt.math("POWER", nt.math("SUBTRACT", 1.0, lw.outputs["Facing"]), edge))
    em = nt.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = rf.rgba(color)
    nt.links.new(nt.math("MULTIPLY", a, strength), em.inputs["Strength"])
    tr = nt.node("ShaderNodeBsdfTransparent")
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _set(mat, surface_render_method="BLENDED", use_backface_culling=False)
    return mat


def _vapor():
    """Condensation cone: soft white cloud (not additive) so it reads against a bright, blurred street."""
    mat, nt, out = _new("vapor")
    fx = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fx").outputs["Fac"]
    phase = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="phase").outputs["Fac"]
    tc = nt.node("ShaderNodeTexCoord")
    noise = nt.node("ShaderNodeTexNoise", noise_dimensions="4D")
    noise.inputs["Scale"].default_value = 3.5
    noise.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(phase, noise.inputs["W"])
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.4
    edge = nt.math("POWER", nt.math("SUBTRACT", 1.0, lw.outputs["Facing"]), 0.6)
    a = nt.math("MULTIPLY", nt.math("MULTIPLY", fx, edge), nt.math("ADD", 0.25, nt.math("MULTIPLY", noise.outputs["Fac"], 0.9)))
    a = nt.math("MINIMUM", a, 0.92)
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.95, 0.96, 0.98, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    b.inputs["Emission Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    b.inputs["Emission Strength"].default_value = 0.6
    nt.links.new(a, b.inputs["Alpha"])
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    _set(mat, surface_render_method="BLENDED", use_backface_culling=False)
    return mat


def _streaks():
    """Plasma streaks along the body, fading towards their tails (object-space Y)."""
    mat, nt, out = _new("plasma_streaks")
    fx = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fx").outputs["Fac"]
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    fade = nt.math("DIVIDE", nt.math("ADD", sep.outputs["Y"], 5.0), 7.5, clamp=True)
    em = nt.node("ShaderNodeEmission")
    col = nt.mix_color(fade, (1.0, 0.25, 0.45, 1.0), (1.0, 0.75, 0.35, 1.0))
    nt.links.new(col, em.inputs["Color"])
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", fx, nt.math("POWER", fade, 2.0)), 9.0), em.inputs["Strength"])
    tr = nt.node("ShaderNodeBsdfTransparent")
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _set(mat, surface_render_method="BLENDED", use_backface_culling=False)
    return mat


def build_car(collection, color=(0.55, 0.012, 0.01)):
    M = [_paint(color),
         _principled("car_glass_hero", (0.012, 0.014, 0.018), 0.04, 0.0),
         _principled("car_trim", (0.02, 0.02, 0.022), 0.55),
         _principled("car_tire", (0.012, 0.012, 0.012), 0.92),
         _principled("car_rim", (0.75, 0.75, 0.78), 0.22, 1.0),
         _principled("car_headlight", (1, 1, 1), 0.2, emission=((1.0, 0.95, 0.85), 6.0)),
         _principled("car_taillight", (0.4, 0.0, 0.0), 0.3, emission=((1.0, 0.02, 0.02), 5.0))]
    PAINT, GLASS, TRIM, TIRE, RIM, HEAD, TAIL = range(7)

    mb = rf.MeshBuilder()

    def section(w, z0, z1):
        return [(-w / 2, z0 + 0.08), (-w / 2, z1 - 0.12), (-w / 2 + 0.14, z1), (w / 2 - 0.14, z1),
                (w / 2, z1 - 0.12), (w / 2, z0 + 0.08), (w / 2 - 0.12, z0), (-w / 2 + 0.12, z0)]

    body = [(-2.25, 1.70, 0.32, 0.80), (-2.10, 1.86, 0.28, 0.88), (-1.20, 1.90, 0.26, 0.90),
            (0.00, 1.90, 0.24, 0.88), (0.90, 1.90, 0.24, 0.86), (1.60, 1.86, 0.26, 0.80),
            (2.05, 1.78, 0.28, 0.70), (2.25, 1.60, 0.32, 0.58)]
    mb.loft([(y, section(w, z0, z1)) for y, w, z0, z1 in body],
            lambda s, k: TRIM if k == 6 else PAINT, cap_mat=PAINT)

    cabin = [(-1.25, 1.70, 0.88, 1.30, 0.92), (-0.80, 1.72, 0.89, 1.24, 1.24), (0.15, 1.74, 0.88, 1.24, 1.28),
             (0.55, 1.76, 0.87, 1.26, 1.24), (1.25, 1.80, 0.84, 1.60, 0.86)]

    def cab_mat(s, k):
        if k == 3:
            return TRIM
        if k == 1:
            return PAINT if s in (1, 2) else GLASS
        return PAINT if s == 0 else GLASS

    mb.loft([(y, [(-wb / 2, zb), (-wt / 2, zt), (wt / 2, zt), (wb / 2, zb)]) for y, wb, zb, wt, zt in cabin],
            cab_mat, cap_mat=GLASS)

    for sx in (-1, 1):
        x0, x1 = sorted((sx * 0.52, sx * 0.84))
        mb.box(x0, 2.17, 0.54, x1, 2.27, 0.63, HEAD)
        x0, x1 = sorted((sx * 0.42, sx * 0.84))
        mb.box(x0, -2.29, 0.64, x1, -2.2, 0.74, TAIL)
        x0, x1 = sorted((sx * 0.9, sx * 1.02))
        mb.box(x0, 0.68, 0.9, x1, 0.86, 1.0, PAINT)          # mirrors
        x0, x1 = sorted((sx * 0.55, sx * 0.62))
        mb.box(x0, -1.95, 0.88, x1, -1.85, 1.02, TRIM)        # spoiler posts
    mb.box(-0.42, 2.2, 0.36, 0.42, 2.28, 0.5, TRIM)            # grille
    mb.box(-0.9, -2.0, 1.02, 0.9, -1.72, 1.06, TRIM)           # spoiler wing
    mb.box(-0.8, -2.3, 0.3, 0.8, -2.18, 0.42, TRIM)            # diffuser
    body_ob = rf.add_object("hero_car", mb.build("hero_car", M, fix_normals=True), collection)
    body_ob["heat"] = 0.0

    wb = rf.MeshBuilder()
    wb.cyl_x(0, 0, 0, 0.34, 0.125, 20, TIRE)
    wb.cyl_x(0, 0, 0, 0.23, 0.128, 20, RIM)
    for side in (-1, 1):  # dark slots between five spokes, so the spin reads
        x = side * 0.131
        for k in range(5):
            a0 = 2 * math.pi * (k + 0.18) / 5
            a1 = 2 * math.pi * (k + 0.82) / 5
            b = len(wb.verts)
            for r, a in ((0.07, a0), (0.2, a0), (0.2, a1), (0.07, a1)):
                wb.verts.append((x, r * math.cos(a), r * math.sin(a)))
            wb.faces.append((b, b + 1, b + 2, b + 3) if side > 0 else (b + 3, b + 2, b + 1, b))
            wb.mats.append(TRIM)
    wheel_mesh = wb.build("hero_wheel", M)
    wheels = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            w = rf.add_object("hero_wheel", wheel_mesh, collection, (sx * 0.86, sy * 1.38, 0.34))
            w.parent = body_ob
            wheels.append(w)

    fxc = rf.MeshBuilder()
    fxc.ico((0, 2.95, 0.62), (1.45, 0.85, 0.95), 3, 0)            # bow shock just ahead of the nose
    rr = random.Random(3)
    for _ in range(46):                                            # plasma streaks peeling off the body
        side = rr.choice((-1, 1))
        x = side * rr.uniform(0.75, 1.05)
        z = rr.uniform(0.35, 1.25)
        y0 = rr.uniform(0.5, 2.2)
        th = rr.uniform(0.006, 0.02)
        fxc.box(x - th, -5.0 + rr.uniform(0, 2.5), z - th, x + th, y0, z + th, 1)   # stops short of the camera
    plasma = rf.add_object("plasma", fxc.build("plasma", [_fx("plasma_bow", (1.0, 0.5, 0.3), 9.0, 2.5, edge=3.0),
                                                         _streaks()]), collection)
    vc = rf.MeshBuilder()
    seg = 32
    secs = [(y, [(r * math.cos(2 * math.pi * k / seg), 0.65 + r * math.sin(2 * math.pi * k / seg)) for k in range(seg)])
            for y, r in ((1.2, 1.0), (0.4, 1.55), (-0.8, 2.05), (-2.0, 2.35), (-3.0, 2.45))]
    vc.loft(secs, lambda s, k: 0, cap=False)
    vapor = rf.add_object("vapor_cone", vc.build("vapor_cone", [_vapor()]), collection)
    rg = rf.MeshBuilder()  # flat annulus in the XY plane, scaled up by the effect to expand
    for k in range(48):
        a0, a1 = 2 * math.pi * k / 48, 2 * math.pi * (k + 1) / 48
        b = len(rg.verts)
        for r in (0.82, 1.0):
            rg.verts.append((r * math.cos(a0), r * math.sin(a0), 0.2))
            rg.verts.append((r * math.cos(a1), r * math.sin(a1), 0.2))
        rg.faces.append((b, b + 1, b + 3, b + 2))
        rg.mats.append(0)
    ring = rf.add_object("shock_ring", rg.build("shock_ring", [_fx("shock_ring", (1.0, 1.0, 1.0), 3.0, 1.5,
                                                                 fresnel=False)]), collection)
    for ob in (plasma, vapor, ring):
        ob["fx"] = 0.0
        ob["phase"] = 0.0
        ob.parent = body_ob
        try:
            ob.visible_shadow = False
        except AttributeError:
            pass
    return {"body": body_ob, "wheels": wheels, "plasma": plasma, "vapor": vapor, "ring": ring}
