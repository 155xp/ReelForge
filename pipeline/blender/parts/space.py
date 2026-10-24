"""The planet set, for effects that leave the ground: the Earth (procedural oceans, continents, deserts, ice, a
cloud layer, city lights on the night side, a blue atmosphere rim), the Moon (maria and craters, and a version
that shatters), the Sun's disc and glare, the starfield, plus 'for scale' ghost spheres and glowing orbit rings.

Everything is built at unit size around its own origin and lives in true metres: scale a body by its radius and
move it each frame with the effect's render space (`render_key`). Objects are never rotated, so a material's
object-space direction is a world direction (the sun, the poles and the land under you stay put).

  earth(collection, sun_dir, land_at=(0, 0, 1), latitude=40.0, seed=3)
      -> {"surface", "clouds", "atmo"}   unit spheres; scale all three by R_EARTH and give them the same centre.
         `land_at` is the direction (from the centre) of the spot that must be dry land (the town under the
         subject); `latitude` tilts the poles so that spot sits at that latitude, north towards +Y.
  moon(collection, seed=7) -> object                       unit sphere (scale by R_MOON)
  moon_shards(collection, moon_ob, n=160, seed=9) -> object  chunks of the Moon that fly apart: key the shape
         key "burst" (0 = whole, 1 = every chunk SHARD_SPREAD radii out), and obj["heat"] 0..1 (glowing breaks)
  flash(collection, color) -> object                      unit glow sphere for an impact flash (obj["fx"] 0..1)
  ghost_sphere(collection, name, color) -> object          translucent 'for scale' sphere (obj["fade"] 0..1)
  orbit_ring(collection, name, color, thickness) -> object a thin glowing circle of radius 1 in the XY plane
  space_sky(world, sun_dir)                                adds the Sun's disc and halo to a look.setup_sky world
                                                           (seen once its "SpaceMix" is up)
  render_key(ob, frames, centres, radii, cams, scales, visible=None)
      bake location = s * (centre - camera) and scale = s * radius per frame (the effect's render space)
  angular_radius_px(radius, dist, lens), distance_for_px(radius, px, lens), horizon_distance(alt)

Constants (metres): R_EARTH, R_MOON, MOON_DIST, R_SUN, AU, KARMAN, ISS_ALT, GPS_ALT, GEO_ALT, C_LIGHT.
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import look
import rf_common as rf

R_EARTH = 6_371_000.0          # mean radius
R_MOON = 1_737_400.0           # mean radius
MOON_DIST = 384_400_000.0      # mean centre-to-centre distance
R_SUN = 696_340_000.0
AU = 149_597_870_700.0
KARMAN = 100_000.0             # the edge of space
ISS_ALT = 420_000.0            # the space station's typical altitude
GPS_ALT = 20_200_000.0
GEO_ALT = 35_786_000.0
C_LIGHT = 299_792_458.0
SHARD_SPREAD = 9.0


# ---------------------------------------------------------------- small helpers

def _sphere_mesh(name, segments=256, rings=128, radius=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return me


def _new_mat(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return mat, nt, nt.node("ShaderNodeOutputMaterial")


def _set(mat, **props):
    for k, v in props.items():
        try:
            setattr(mat, k, v)
        except (AttributeError, TypeError):
            pass


def _transparent(mat):
    _set(mat, surface_render_method="BLENDED", blend_method="BLEND", use_backface_culling=True,
         show_transparent_back=False)


def _dir(nt):
    """Unit direction from the body's centre (object space)."""
    tc = nt.node("ShaderNodeTexCoord")
    nrm = nt.node("ShaderNodeVectorMath", operation="NORMALIZE")
    nt.links.new(tc.outputs["Object"], nrm.inputs[0])
    return nrm.outputs["Vector"]


def _dot(nt, vec, const):
    d = nt.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nt.links.new(vec, d.inputs[0])
    d.inputs[1].default_value = tuple(const)
    return d.outputs["Value"]


def _smooth(nt, value, lo, hi):
    mr = nt.node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    nt.feed(mr.inputs["Value"], value)
    mr.inputs["From Min"].default_value = lo
    mr.inputs["From Max"].default_value = hi
    return mr.outputs["Result"]


def _noise(nt, vec, scale, detail, rough=0.55, lac=2.0, w=None):
    n = nt.node("ShaderNodeTexNoise")
    if w is not None:
        n.noise_dimensions = "4D"
        n.inputs["W"].default_value = w
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = rough
    if "Lacunarity" in n.inputs:
        n.inputs["Lacunarity"].default_value = lac
    nt.links.new(vec, n.inputs["Vector"])
    return n


def _vadd(nt, a, b, scale_b=1.0):
    if scale_b != 1.0:
        s = nt.node("ShaderNodeVectorMath", operation="SCALE")
        nt.links.new(b, s.inputs[0])
        s.inputs["Scale"].default_value = scale_b
        b = s.outputs["Vector"]
    add = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(a, add.inputs[0])
    nt.links.new(b, add.inputs[1])
    return add.outputs["Vector"]


def _glitch_wrap(nt, shader):
    """Mix in the pipeline's magenta 'missing texture' checker when obj["glitch"] rises (the overflow)."""
    attr = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="glitch")
    tc = nt.node("ShaderNodeTexCoord")
    chk = nt.node("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 24.0
    chk.inputs["Color1"].default_value = (1.0, 0.0, 1.0, 1.0)
    chk.inputs["Color2"].default_value = (0.0, 0.0, 0.0, 1.0)
    nt.links.new(tc.outputs["Object"], chk.inputs["Vector"])
    em = nt.node("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.4
    nt.links.new(chk.outputs["Color"], em.inputs["Color"])
    mix = nt.node("ShaderNodeMixShader")
    nt.links.new(attr.outputs["Fac"], mix.inputs[0])
    nt.links.new(shader, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    return mix.outputs[0]


# ---------------------------------------------------------------- the Earth

def pole_for(land_at, latitude):
    """North-pole direction that puts `land_at` at `latitude` degrees north, with north towards +Y."""
    up = Vector(land_at).normalized()
    north = Vector((0.0, 1.0, 0.0))
    north = (north - up * north.dot(up)).normalized()
    a = math.radians(90.0 - latitude)
    return tuple(up * math.cos(a) + north * math.sin(a))


def earth_material(sun_dir, land_at=(0.0, 0.0, 1.0), latitude=40.0, seed=3):
    mat, nt, out = _new_mat("earth_surface")
    n = _dir(nt)
    pole = pole_for(land_at, latitude)
    off = Vector((seed * 3.17, seed * 1.31, seed * 2.03))
    # continents: domain-warped fractal noise, nudged up round the spot that has to be land
    shift = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(n, shift.inputs[0])
    shift.inputs[1].default_value = tuple(off)
    warp = _noise(nt, shift.outputs["Vector"], 1.1, 3.0)
    wv = nt.node("ShaderNodeVectorMath", operation="SUBTRACT")
    nt.links.new(warp.outputs["Color"], wv.inputs[0])
    wv.inputs[1].default_value = (0.5, 0.5, 0.5)
    p = _vadd(nt, shift.outputs["Vector"], wv.outputs["Vector"], 0.55)
    cont = _noise(nt, p, 1.25, 15.0, 0.56)
    home = _smooth(nt, _dot(nt, n, land_at), math.cos(math.radians(22.0)), math.cos(math.radians(4.0)))
    c = nt.math("ADD", cont.outputs["Fac"], nt.math("MULTIPLY", home, 0.22))
    land = _smooth(nt, c, 0.515, 0.525)
    coast = nt.math("MULTIPLY", _smooth(nt, c, 0.46, 0.515), nt.math("SUBTRACT", 1.0, land))
    lat = nt.math("ABSOLUTE", _dot(nt, n, pole))                 # sine of the latitude
    detail = _noise(nt, p, 9.0, 15.0, 0.6)
    jit = nt.math("MULTIPLY", nt.math("SUBTRACT", detail.outputs["Fac"], 0.5), 0.16)
    # ice caps: land above ~68 degrees, sea ice above ~76
    sea = nt.math("MULTIPLY", nt.math("SUBTRACT", 1.0, land), 0.05)
    ice = _smooth(nt, nt.math("ADD", lat, nt.math("SUBTRACT", jit, sea)), 0.925, 0.945)
    # dry belts round 15-35 degrees, broken up by the noise
    dry_band = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", nt.math("ABSOLUTE", nt.math("SUBTRACT", lat, 0.42)), 0.2,
                                                clamp=True))
    desert = nt.math("MULTIPLY", dry_band, _smooth(nt, detail.outputs["Fac"], 0.56, 0.68))
    high = _smooth(nt, c, 0.6, 0.7)                                  # inland highs: mountains
    forest = nt.mix_color(detail.outputs["Fac"], (0.025, 0.07, 0.016, 1.0), (0.07, 0.11, 0.03, 1.0))
    plains = nt.mix_color(_smooth(nt, detail.outputs["Fac"], 0.45, 0.62), forest, (0.17, 0.16, 0.07, 1.0))
    col = nt.mix_color(desert, plains, (0.42, 0.31, 0.17, 1.0))
    col = nt.mix_color(nt.math("MULTIPLY", high, 0.7), col, (0.2, 0.16, 0.12, 1.0))
    tundra = _smooth(nt, lat, 0.72, 0.84)
    col = nt.mix_color(nt.math("MULTIPLY", tundra, 0.8), col, (0.16, 0.14, 0.11, 1.0))
    ocean = nt.mix_color(coast, (0.004, 0.016, 0.05, 1.0), (0.012, 0.07, 0.11, 1.0))
    col = nt.mix_color(land, ocean, col)
    col = nt.mix_color(ice, col, (0.82, 0.85, 0.9, 1.0))
    b = nt.node("ShaderNodeBsdfPrincipled")
    nt.links.new(col, b.inputs["Base Color"])
    rough = nt.math("ADD", nt.math("MULTIPLY", land, 0.72), 0.16)
    nt.links.new(nt.math("MAXIMUM", rough, nt.math("MULTIPLY", ice, 0.55)), b.inputs["Roughness"])
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nt.links.new(nt.math("MULTIPLY", detail.outputs["Fac"], land), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    # city lights on the night side: clusters of warm dots on land, fewer in deserts and none on ice
    day = _smooth(nt, _dot(nt, n, sun_dir), -0.12, 0.12)
    vor = nt.node("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 1100.0
    nt.links.new(p, vor.inputs["Vector"])
    dots = _smooth(nt, vor.outputs["Distance"], 0.22, 0.06)
    clusters = _smooth(nt, _noise(nt, p, 30.0, 6.0).outputs["Fac"], 0.5, 0.66)
    lights = nt.math("MULTIPLY", nt.math("MULTIPLY", dots, clusters), land)
    dark = nt.math("MAXIMUM", ice, nt.math("MULTIPLY", desert, 0.8))
    lights = nt.math("MULTIPLY", lights, nt.math("SUBTRACT", 1.0, dark))
    lights = nt.math("MULTIPLY", lights, nt.math("SUBTRACT", 1.0, day))
    b.inputs["Emission Color"].default_value = (1.0, 0.62, 0.28, 1.0)
    nt.links.new(nt.math("MULTIPLY", lights, 2.2), b.inputs["Emission Strength"])
    nt.links.new(_glitch_wrap(nt, b.outputs[0]), out.inputs["Surface"])
    return mat


def cloud_layer_material(sun_dir, seed=3, coverage=0.5):
    mat, nt, out = _new_mat("earth_clouds")
    n = _dir(nt)
    shift = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(n, shift.inputs[0])
    shift.inputs[1].default_value = (seed * 0.7, seed * 2.3, seed * 1.9)
    swirl = _noise(nt, shift.outputs["Vector"], 2.2, 4.0)
    sv = nt.node("ShaderNodeVectorMath", operation="SUBTRACT")
    nt.links.new(swirl.outputs["Color"], sv.inputs[0])
    sv.inputs[1].default_value = (0.5, 0.5, 0.5)
    p = _vadd(nt, shift.outputs["Vector"], sv.outputs["Vector"], 0.9)
    systems = _smooth(nt, _noise(nt, p, 2.0, 4.0, 0.5).outputs["Fac"], 0.40 - 0.1 * coverage, 0.62 - 0.1 * coverage)
    fine = _noise(nt, _vadd(nt, p, sv.outputs["Vector"], 0.35), 16.0, 15.0, 0.64).outputs["Fac"]
    dens = nt.math("ADD", nt.math("MULTIPLY", systems, 0.3), nt.math("MULTIPLY", fine, 0.75))
    a = _smooth(nt, dens, 0.64, 0.8)
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.95, 0.95, 0.97, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.0
    nt.links.new(nt.math("MULTIPLY", a, 0.92), b.inputs["Alpha"])
    nt.links.new(_glitch_wrap(nt, b.outputs[0]), out.inputs["Surface"])
    _transparent(mat)
    return mat


def atmosphere_material(sun_dir, gain=2.6, power=3.2):
    """A limb glow: blue where the day side's air is seen edge-on, warm along the terminator, nothing head-on. Only the
    shell's far side glows (it shows round the planet's edge), so it never fogs the planet or anything in front of it.
    obj["fx"] scales it."""
    mat, nt, out = _new_mat("earth_atmosphere")
    n = _dir(nt)
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    edge = nt.math("POWER", lw.outputs["Facing"], power)
    sd = _dot(nt, n, sun_dir)
    lit = _smooth(nt, sd, -0.28, 0.25)
    dusk = nt.math("SUBTRACT", 1.0, _smooth(nt, nt.math("ABSOLUTE", sd), 0.0, 0.3))
    col = nt.mix_color(nt.math("MULTIPLY", dusk, 0.7), (0.22, 0.5, 1.0, 1.0), (1.0, 0.45, 0.16, 1.0))
    em = nt.node("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    fx = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fx").outputs["Fac"]
    back = nt.node("ShaderNodeNewGeometry").outputs["Backfacing"]
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", nt.math("MULTIPLY", nt.math("MULTIPLY", edge, lit), gain), fx),
                         back), em.inputs["Strength"])
    tr = nt.node("ShaderNodeBsdfTransparent")
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _transparent(mat)
    _set(mat, use_backface_culling=False)
    return mat


def earth(collection, sun_dir, land_at=(0.0, 0.0, 1.0), latitude=40.0, seed=3, cloud_alt=9000.0, atmo_alt=80_000.0,
          cloud_coverage=0.5):
    surf = rf.add_object("earth", _sphere_mesh("earth", 384, 192), collection)
    surf.data.materials.append(earth_material(sun_dir, land_at, latitude, seed))
    clouds = rf.add_object("earth_clouds", _sphere_mesh("earth_clouds", 256, 128, 1.0 + cloud_alt / R_EARTH),
                           collection)
    clouds.data.materials.append(cloud_layer_material(sun_dir, seed, cloud_coverage))
    atmo = rf.add_object("earth_atmo", _sphere_mesh("earth_atmo", 192, 96, 1.0 + atmo_alt / R_EARTH), collection)
    atmo.data.materials.append(atmosphere_material(sun_dir))
    for ob in (surf, clouds, atmo):
        ob["glitch"] = 0.0
    atmo["fx"] = 1.0
    for ob in (clouds, atmo):
        try:
            ob.visible_shadow = False
        except AttributeError:
            pass
    return {"surface": surf, "clouds": clouds, "atmo": atmo}


# ---------------------------------------------------------------- the Moon

def moon_material(name="moon", heat=False):
    mat, nt, out = _new_mat(name)
    tc = nt.node("ShaderNodeTexCoord")
    n = _dir(nt)
    maria = _smooth(nt, _noise(nt, n, 1.6, 6.0, 0.5).outputs["Fac"], 0.5, 0.58)
    height = None
    rims = None
    for scale, weight, keep in ((4.0, 1.0, 0.45), (11.0, 0.6, 0.35), (30.0, 0.35, 0.3), (85.0, 0.2, 0.25)):
        v = nt.node("ShaderNodeTexVoronoi")
        v.inputs["Scale"].default_value = scale
        nt.links.new(n, v.inputs["Vector"])
        rnd = nt.node("ShaderNodeSeparateColor")
        nt.links.new(v.outputs["Color"], rnd.inputs[0])
        r = nt.math("ADD", 0.1, nt.math("MULTIPLY", rnd.outputs[0], 0.3))            # crater radius per cell
        on = nt.math("GREATER_THAN", rnd.outputs[1], keep)                           # not every cell has one
        x = nt.math("DIVIDE", v.outputs["Distance"], r)
        bowl = nt.math("MULTIPLY", _smooth(nt, x, 1.0, 0.0), -weight)
        rim = nt.math("MULTIPLY", nt.math("EXPONENT", nt.math("MULTIPLY", nt.math("POWER", nt.math("DIVIDE",
                      nt.math("SUBTRACT", x, 1.05), 0.22), 2.0), -1.0)), weight * 0.6)
        h = nt.math("MULTIPLY", nt.math("ADD", bowl, rim), on)
        height = h if height is None else nt.math("ADD", height, h)
        rims = nt.math("MULTIPLY", rim, on) if rims is None else nt.math("ADD", rims, nt.math("MULTIPLY", rim, on))
    fine = _noise(nt, n, 60.0, 8.0, 0.6)
    height = nt.math("ADD", height, nt.math("MULTIPLY", fine.outputs["Fac"], 0.4))
    grey = nt.mix_color(_noise(nt, n, 8.0, 6.0).outputs["Fac"], (0.16, 0.155, 0.15, 1.0), (0.3, 0.29, 0.28, 1.0))
    col = nt.mix_color(nt.math("MULTIPLY", maria, 0.85), grey, (0.055, 0.055, 0.058, 1.0))
    col = nt.mix_color(nt.math("MINIMUM", nt.math("MULTIPLY", rims, 0.3), 0.45), col, (0.42, 0.41, 0.39, 1.0))
    b = nt.node("ShaderNodeBsdfPrincipled")
    nt.links.new(col, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.97
    if "Specular IOR Level" in b.inputs:
        b.inputs["Specular IOR Level"].default_value = 0.15
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.85
    nt.links.new(height, bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    if heat:
        # broken faces glow: obj["heat"] lights the cracks orange-white
        attr = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="heat")
        b.inputs["Emission Color"].default_value = (1.0, 0.45, 0.12, 1.0)
        crack = _smooth(nt, _noise(nt, tc.outputs["Object"], 9.0, 6.0).outputs["Fac"], 0.56, 0.66)
        nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", attr.outputs["Fac"], crack), 6.0),
                     b.inputs["Emission Strength"])
    nt.links.new(_glitch_wrap(nt, b.outputs[0]), out.inputs["Surface"])
    return mat


def moon(collection, seed=7, name="moon"):
    ob = rf.add_object(name, _sphere_mesh(name, 256, 128), collection)
    ob.data.materials.append(moon_material(name))
    ob["glitch"] = 0.0
    return ob


def moon_shards(collection, moon_ob=None, n=160, seed=9, name="moon_shards"):
    """The Moon as chunks that fly apart: shape key "burst" moves every chunk out along its direction to
    SHARD_SPREAD times the Moon's radius (with a little spin), so keying it 0 -> 1 over a second is an explosion."""
    rnd = random.Random(seed)
    mb = rf.MeshBuilder()
    dirs, sizes = [], []
    for k in range(n):
        z = rnd.uniform(-1, 1)
        a = rnd.uniform(0, 2 * math.pi)
        d = Vector((math.sqrt(1 - z * z) * math.cos(a), math.sqrt(1 - z * z) * math.sin(a), z))
        depth = rnd.uniform(0.35, 0.95)
        size = rnd.uniform(0.09, 0.26) * (1.25 - depth * 0.4)
        c = d * depth
        mb.ico(tuple(c), (size, size * rnd.uniform(0.6, 1.1), size * rnd.uniform(0.5, 0.9)), 1, 0, jitter=0.35, rnd=rnd)
        dirs.append((d, depth))
        sizes.append(size)
    me = mb.build(name, [moon_material("moon_shard", heat=True)], fix_normals=True)
    ob = rf.add_object(name, me, collection)
    ob.shape_key_add(name="Basis")
    sk = ob.shape_key_add(name="burst")
    sk.slider_max = 1.0
    per = len(me.vertices) // n
    for k, (d, depth) in enumerate(dirs):
        speed = SHARD_SPREAD * rnd.uniform(0.55, 1.15)
        spin = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * 0.4
        c = d * depth
        for i in range(k * per, (k + 1) * per):
            v = me.vertices[i].co
            sk.data[i].co = v + d * speed + (v - c).cross(spin)
    ob["heat"] = 0.0
    ob["glitch"] = 0.0
    return ob


def flash(collection, color=(1.0, 0.85, 0.6), name="impact_flash"):
    mat, nt, out = _new_mat(name)
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    core = nt.math("POWER", nt.math("SUBTRACT", 1.0, lw.outputs["Facing"]), 3.0)
    fx = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fx")
    em = nt.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = rf.rgba(color)
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", core, fx.outputs["Fac"]), 20.0), em.inputs["Strength"])
    tr = nt.node("ShaderNodeBsdfTransparent")
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _transparent(mat)
    ob = rf.add_object(name, _sphere_mesh(name, 48, 24), collection)
    ob.data.materials.append(mat)
    ob["fx"] = 0.0
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass
    return ob


# ---------------------------------------------------------------- comparison helpers

def ghost_sphere(collection, name, color=(0.45, 0.85, 1.0), gain=3.0):
    """A see-through 'for scale' sphere: a bright rim and a faint fill, faded by obj["fade"]."""
    mat, nt, out = _new_mat(f"ghost_{name}")
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    rim = nt.math("ADD", nt.math("POWER", lw.outputs["Facing"], 3.0), 0.06)
    fade = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fade")
    em = nt.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = rf.rgba(color)
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", rim, fade.outputs["Fac"]), gain), em.inputs["Strength"])
    tr = nt.node("ShaderNodeBsdfTransparent")
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(tr.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _transparent(mat)
    ob = rf.add_object(f"ghost_{name}", _sphere_mesh(f"ghost_{name}", 96, 48), collection)
    ob.data.materials.append(mat)
    ob["fade"] = 0.0
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass
    return ob


def orbit_ring(collection, name, color=(0.5, 0.9, 1.0), thickness=0.0035, strength=6.0, segments=720):
    """A glowing circle of radius 1 round the origin in the XY plane (scale by the orbit's radius). obj["fade"]."""
    mat, nt, out = _new_mat(f"orbit_{name}")
    fade = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fade")
    em = nt.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = rf.rgba(color)
    nt.links.new(nt.math("MULTIPLY", fade.outputs["Fac"], strength), em.inputs["Strength"])
    tr = nt.node("ShaderNodeBsdfTransparent")
    mix = nt.node("ShaderNodeMixShader")
    nt.links.new(fade.outputs["Fac"], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    _transparent(mat)
    mb = rf.MeshBuilder()
    seg2 = 8
    for i in range(segments):
        a = 2 * math.pi * i / segments
        c = Vector((math.cos(a), math.sin(a), 0.0))
        for j in range(seg2):
            b = 2 * math.pi * j / seg2
            mb.verts.append(tuple(c * (1.0 + thickness * math.cos(b)) + Vector((0, 0, thickness * math.sin(b)))))
    for i in range(segments):
        for j in range(seg2):
            i2, j2 = (i + 1) % segments, (j + 1) % seg2
            mb.faces.append((i * seg2 + j, i2 * seg2 + j, i2 * seg2 + j2, i * seg2 + j2))
            mb.mats.append(0)
    ob = rf.add_object(f"orbit_{name}", mb.build(f"orbit_{name}", [mat], smooth=True), collection)
    ob["fade"] = 0.0
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass
    return ob


def space_sky(world, sun_dir):
    """The Sun's disc and halo in space (look.add_space_sun), only where the sky has faded to space."""
    look.add_space_sun(world, sun_dir, disc_deg=0.27, strength=120.0, halo=3.0, halo_deg=1.4)


# ---------------------------------------------------------------- placing things in render space

def render_key(ob, frames, centres, radii, cams, scales, visible=None):
    """Bake location = s * (centre - camera) and uniform scale = s * radius for every frame (all arrays per frame;
    `radii` may be a number). `visible` (bools) keys hide_render."""
    c = np.asarray(centres, float)
    cam = np.asarray(cams, float)
    s = np.asarray(scales, float)
    r = np.broadcast_to(np.asarray(radii, float), s.shape)
    loc = (c - cam) * s[:, None]
    for k in range(3):
        rf.key_series(ob, "location", k, frames, loc[:, k])
        rf.key_series(ob, "scale", k, frames, s * r)
    if visible is not None:
        rf.key_series(ob, "hide_render", -1, frames, (~np.asarray(visible, bool)).astype(float), interp="CONSTANT")


def angular_radius_px(radius, dist, lens, height_px=1920, sensor=36.0):
    """On-screen radius in pixels of a sphere `radius` at `dist` (portrait frame, the sensor spans the height)."""
    if dist <= radius:
        return float("inf")
    return math.tan(math.asin(radius / dist)) * lens / (sensor / 2) * height_px / 2


def distance_for_px(radius, px, lens, height_px=1920, sensor=36.0):
    """How far away a sphere `radius` must be to show `px` pixels of radius."""
    t = px / (lens / (sensor / 2) * height_px / 2)
    return radius / math.sin(math.atan(t))


def horizon_distance(alt, radius=R_EARTH):
    """Distance to the horizon from `alt` metres up."""
    return math.sqrt(max(alt, 0.0) * (2 * radius + max(alt, 0.0)))
