"""The 'golden hour' look shared by the city worlds: physical (Nishita) sky that darkens with altitude into a
starfield, a warm low sun, aerial haze driven by scene properties (so it can thin out as the camera climbs), and a
little bloom.

Scene properties (keyframe them per frame from the effect; materials read them through VIEW_LAYER attributes):
  rf_haze_dist   metres for the haze to reach 63 % (grows with the camera's altitude so the ground stays readable)
  rf_haze_max    0..1 cap on the haze
  rf_haze_col    haze colour looking away from the sun
  rf_haze_sun    haze colour looking into the sun
  rf_sun_dir     unit vector towards the sun
World nodes: "Sky" (Nishita; key its `altitude`), "SkyGain" (sky brightness), "StarMix" (0..1 stars),
"SpaceMix" (0..1 fades the sky to black).
"""
import math

import bpy
from mathutils import Vector

import rf_common as rf

HAZE_PROPS = ("rf_haze_dist", "rf_haze_max", "rf_haze_col", "rf_haze_sun", "rf_sun_dir")


def sun_vector(heading_deg, elevation_deg):
    """Unit vector towards the sun; heading is a compass angle from +Y towards +X (Nishita's sun_rotation)."""
    h, e = math.radians(heading_deg), math.radians(elevation_deg)
    return Vector((math.cos(e) * math.sin(h), math.cos(e) * math.cos(h), math.sin(e)))


def add_sun(collection, heading_deg, elevation_deg, energy=4.0, color=(1.0, 0.78, 0.55), angle_deg=1.2):
    light = bpy.data.lights.new("Sun", "SUN")
    light.energy = energy
    light.angle = math.radians(angle_deg)
    light.color = color
    try:
        light.use_shadow = True
    except AttributeError:
        pass
    sun = bpy.data.objects.new("Sun", light)
    d = sun_vector(heading_deg, elevation_deg)
    # a sun lamp shines down its local -Z: point -Z away from the sun direction
    sun.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    collection.objects.link(sun)
    return sun


def setup_sky(scene, heading_deg, elevation_deg, gain=0.16, dust=1.6, air=1.0, ozone=1.0, sun_size_deg=1.6,
              star_rotation_deg=(23.0, 41.0, 67.0)):
    world = bpy.data.worlds.new("RF_GoldenSky")
    scene.world = world
    world.use_nodes = True
    nt = rf.NodeTree(world.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputWorld")
    bg = nt.node("ShaderNodeBackground")
    sky = nt.node("ShaderNodeTexSky", name="Sky", label="Sky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(elevation_deg)
    sky.sun_rotation = math.radians(heading_deg)
    sky.altitude = 0.0
    sky.air_density = air
    sky.dust_density = dust
    sky.ozone_density = ozone
    sky.sun_disc = True
    sky.sun_size = math.radians(sun_size_deg)
    sky.sun_intensity = 1.0
    sg = nt.node("ShaderNodeValue", name="SkyGain", label="SkyGain")
    sg.outputs[0].default_value = gain
    lit = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(sky.outputs[0], lit.inputs[0])
    nt.links.new(sg.outputs[0], lit.inputs["Scale"])
    sp = nt.node("ShaderNodeValue", name="SpaceMix", label="SpaceMix")
    sp.outputs[0].default_value = 0.0
    # stars on the view direction (rotated so the Voronoi grid's axis rings stay out of shot)
    tc = nt.node("ShaderNodeTexCoord")
    rot = nt.node("ShaderNodeVectorRotate", name="StarRotate")
    rot.rotation_type = "EULER_XYZ"
    rot.inputs["Rotation"].default_value = tuple(math.radians(a) for a in star_rotation_deg)
    nt.links.new(tc.outputs["Generated"], rot.inputs["Vector"])
    d = rot.outputs["Vector"]
    star = None
    for scale, size, g in ((160.0, 0.15, 5.0), (460.0, 0.2, 2.2), (60.0, 0.1, 9.0)):
        v = nt.node("ShaderNodeTexVoronoi")
        v.inputs["Scale"].default_value = scale
        nt.links.new(d, v.inputs["Vector"])
        vc = nt.node("ShaderNodeSeparateColor")
        nt.links.new(v.outputs["Color"], vc.inputs[0])
        s = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", v.outputs["Distance"], size, clamp=True))
        s = nt.math("MULTIPLY", nt.math("POWER", s, 2.0), nt.math("MULTIPLY", nt.math("POWER", vc.outputs[0], 4.0), g))
        star = s if star is None else nt.math("ADD", star, s)
    smx = nt.node("ShaderNodeValue", name="StarMix", label="StarMix")
    smx.outputs[0].default_value = 0.0
    star = nt.math("MULTIPLY", star, smx.outputs[0])
    st = nt.node("ShaderNodeCombineColor")
    for k, w in enumerate((0.92, 0.96, 1.0)):
        nt.links.new(nt.math("MULTIPLY", star, w), st.inputs[k])
    # sky fades to a deep blue-black, then stars are added on top
    col = nt.mix_color(sp.outputs[0], lit.outputs["Vector"], (0.0015, 0.002, 0.004, 1.0))
    add = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(col, add.inputs[0])
    nt.links.new(st.outputs[0], add.inputs[1])
    nt.links.new(add.outputs["Vector"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return world


def init_haze(scene, sun_dir, dist=6000.0, hmax=0.85, col=(0.55, 0.62, 0.78), sun_col=(1.0, 0.74, 0.5)):
    scene["rf_haze_dist"] = float(dist)
    scene["rf_haze_max"] = float(hmax)
    scene["rf_haze_col"] = tuple(float(c) for c in col)
    scene["rf_haze_sun"] = tuple(float(c) for c in sun_col)
    scene["rf_sun_dir"] = tuple(float(c) for c in sun_dir)
    rf.HAZE_SCENE = True


def key_scene_prop(scene, name, frames, values):
    """Bake a (possibly vector) scene custom property per frame."""
    import numpy as np
    values = np.asarray(values, dtype=float)
    if values.ndim == 1:
        rf.key_series(scene, f'["{name}"]', 0, frames, values)
    else:
        for k in range(values.shape[1]):
            rf.key_series(scene, f'["{name}"]', k, frames, values[:, k])


def smoothstep(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def air_at(alt, dist_mul=1.0, max_mul=1.0):
    """Sky and haze settings for a camera at `alt` metres: (nishita_altitude, space_mix, star_mix, haze_dist,
    haze_max, haze_col, haze_sun_col). Haze thins as you climb so the ground stays readable from above;
    dist_mul / max_mul make the air clearer (> 1 / < 1) for a world that wants it."""
    k = smoothstep(alt / 30000.0)
    dist = (9000.0 + 3.6 * alt + 2e-5 * alt * alt) * dist_mul
    hmax = (0.82 - 0.3 * smoothstep(alt / 40000.0)) * max_mul
    col = tuple(a + (b - a) * k for a, b in zip((0.40, 0.52, 0.74), (0.22, 0.34, 0.66)))
    sun_col = tuple(a + (b - a) * k for a, b in zip((1.0, 0.68, 0.42), (0.85, 0.70, 0.62)))
    return (min(alt, 59000.0), smoothstep((alt - 35000.0) / 45000.0), smoothstep((alt - 20000.0) / 40000.0),
            dist, hmax, col, sun_col)


def key_air(scene, world, frames, alts, dist_mul=1.0, max_mul=1.0):
    """Key the sky and haze for a camera altitude per frame (dist_mul / max_mul: scalars or one per frame)."""
    import numpy as np
    dm = np.broadcast_to(np.asarray(dist_mul, float), (len(alts),))
    mm = np.broadcast_to(np.asarray(max_mul, float), (len(alts),))
    rows = [air_at(float(a), float(d), float(m)) for a, d, m in zip(alts, dm, mm)]
    nodes = world.node_tree
    rf.key_series(nodes, 'nodes["Sky"].altitude', -1, frames, [r[0] for r in rows])
    rf.key_series(nodes, 'nodes["SpaceMix"].outputs[0].default_value', -1, frames, [r[1] for r in rows])
    rf.key_series(nodes, 'nodes["StarMix"].outputs[0].default_value', -1, frames, [r[2] for r in rows])
    key_scene_prop(scene, "rf_haze_dist", frames, [r[3] for r in rows])
    key_scene_prop(scene, "rf_haze_max", frames, [r[4] for r in rows])
    key_scene_prop(scene, "rf_haze_col", frames, np.array([r[5] for r in rows]))
    key_scene_prop(scene, "rf_haze_sun", frames, np.array([r[6] for r in rows]))


def add_bloom(scene, threshold=1.0, size=7, mix=-0.65):
    """Compositor glare so suns, plasma and lit windows bloom a little."""
    scene.use_nodes = True
    tree = scene.node_tree
    for n in list(tree.nodes):
        tree.nodes.remove(n)
    rl = tree.nodes.new("CompositorNodeRLayers")
    comp = tree.nodes.new("CompositorNodeComposite")
    gl = tree.nodes.new("CompositorNodeGlare")
    try:
        gl.glare_type = "BLOOM"
    except TypeError:
        gl.glare_type = "FOG_GLOW"
    for prop, val in (("threshold", threshold), ("size", size), ("mix", mix), ("quality", "HIGH")):
        try:
            setattr(gl, prop, val)
        except (AttributeError, TypeError):
            pass
    # 4.5 moved some glare settings to node inputs
    for name, val in (("Threshold", threshold), ("Size", size / 9.0), ("Strength", 1.0 + mix)):
        if name in gl.inputs:
            try:
                gl.inputs[name].default_value = val
            except (TypeError, AttributeError):
                pass
    tree.links.new(rl.outputs["Image"], gl.inputs["Image"])
    tree.links.new(gl.outputs["Image"], comp.inputs["Image"])
    return gl


def add_space_sun(world, sun_dir, disc_deg=0.45, strength=80.0, halo=2.5, halo_deg=1.6, color=(1.0, 0.95, 0.86)):
    """Put the Sun's disc and a soft halo back into the starfield (the Nishita sun fades out with "SpaceMix"), so
    a shot that looks towards the Sun from space shows it. Scaled by SpaceMix, so it never shows on the ground."""
    nt = rf.NodeTree(world.node_tree)
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    src = bg.inputs["Color"].links[0].from_socket
    tc = nt.node("ShaderNodeTexCoord")
    nrm = nt.node("ShaderNodeVectorMath", operation="NORMALIZE")
    nt.links.new(tc.outputs["Generated"], nrm.inputs[0])
    dot = nt.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nt.links.new(nrm.outputs["Vector"], dot.inputs[0])
    dot.inputs[1].default_value = tuple(sun_dir)
    ang = nt.math("ARCCOSINE", nt.math("MINIMUM", dot.outputs["Value"], 1.0))
    r = math.radians(disc_deg)
    disc = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", nt.math("SUBTRACT", ang, r), r * 0.25, clamp=True))
    glow = nt.math("EXPONENT", nt.math("DIVIDE", ang, -math.radians(halo_deg)))
    k = nt.math("MULTIPLY", nt.math("ADD", nt.math("MULTIPLY", disc, strength), nt.math("MULTIPLY", glow, halo)),
                nt.nodes["SpaceMix"].outputs[0])
    sc = nt.node("ShaderNodeVectorMath", operation="SCALE")
    sc.inputs[0].default_value = tuple(color)
    nt.links.new(k, sc.inputs["Scale"])
    add = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(src, add.inputs[0])
    nt.links.new(sc.outputs["Vector"], add.inputs[1])
    nt.links.new(add.outputs["Vector"], bg.inputs["Color"])
