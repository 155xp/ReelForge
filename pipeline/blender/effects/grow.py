"""Effect: "What if your <thing> doubled in size every 2 seconds?"

A subject from parts/subjects.py sits on the street (worlds/street.py, or any world that gives a "spot") and doubles
in size every `double_every` seconds: it outgrows a fire hydrant, you, the cars, the bus, the shops (knocking them
over with debris and dust through the world's crush field), a church steeple, the tallest building on Earth, the
clouds, Mount Everest's height and the airliners, breaks into space (the planet set from parts/space.py takes over),
passes the space station's orbit, the Moon's size and the Earth's size, and finally headbutts the Moon, which
shatters. At `overflow_at` the counter wraps to -2,147,483,648 and the subject glitches; post-production rewinds the
picture into the first frame (`rewind` + `loop_to_start`).

The camera works in render space: it stays at the origin and the world is scaled round it (s = BUDGET / distance
to what it looks at), so nothing is drawn at huge coordinates and every size and angle stays true. Shots are
anchored to the subject's size, so a different start size or doubling period moves every beat with it.

spec["effect"]:
  "type": "grow"
  "subject": "duck"              parts/subjects.py name: duck, donut, soccer_ball, beach_ball
  "start_size": 0.1524           metres at start_at; or "start_size_ft" / "start_size_in". The counter counts this
                                 size (the duck's height, a ball's diameter)
  "start_at": 0.0                when the doubling clock starts (before it the size holds)
  "double_every": 2.0            seconds per doubling
  "int32_max": 2147483647        the counter's limit, in feet
  "overflow_at": null            when the counter wraps (default: the moment the size in feet passes int32_max)
  "yaw": 200                     compass heading the subject faces (default: the world's spot_yaw)
  "space_from": null             when the planet set takes over (default: the subject is 40 km tall)
  "moon_hit": true               place the Moon where the subject's crown hits it, and it shatters (false: the
                                 Moon sits 28 degrees off its path and survives)
  "bounce": 0.06                 the squash-and-stretch on every doubling (0 = none), until space_from
  "debris": 70                   buildings that throw debris when knocked over (nearest first; 0 = none)
  "dust": true                   dust puffs on every knocked-over building and a dust wall round the base
  "haze_dist_mul": 4.0, "haze_max_mul": 0.6     clearer air than look.py's default as the camera climbs
  "shot_sizes": [...]            optional: the 14 subject sizes (m) at which the default shots cut (see SHOT_SIZES);
                                 the last shot, the impact, always starts when the crown reaches the Moon
  "tags": true                   on-screen 'debug' tags (hydrant, you, car, bus, steeple, supertall, Everest's
                                 height, airliner, space station orbit, Moon to scale, Earth, the Moon)
  "seed": 5                      randomness of the debris, dust and camera shake

From the world it uses info["spot"] (where the subject stands, default the origin), "spot_yaw", "sun_dir", "sun",
"world", "mover" (made here if the world has none), "ground_objects", "crush" and "crushables" (the street's crush
field; without them nothing is knocked over), "refs" (positions of the hydrant, you, the car, the bus, the steeple,
the supertall and the Everest-height peak, for the shots that compare them), "people", "traffic", "lamp_lights",
"clouds", "hero" and "night".

series.json (the HUD and the sound):
  "size_m", "size_ft" (int32 feet, -2^31 after the overflow), "size_in" (inches), "size_mi" (miles),
  "earths" (size / Earth's diameter), "crown_c" (the crown's speed as a fraction of light speed),
  "tags", "subject_box" (screen box per frame for text placement), "events":
  doublings, hits (each building/car within 350 m knocked over), cuts, the milestone times hydrant, you, car, bus,
  wider (than Main Street), steeple, tallest_building, clouds, two_miles, everest, cruise, space, iss,
  thousand_miles, moon_size, earth_size, moon_hit, fifth_c, overflow, space_from, and when the first car, the first
  building, the bus, the church and the supertall go over (first_car, first_building, bus_down, church_down,
  supertall_down).
"""
import math
import random

import bpy
import numpy as np
from mathutils import Vector

import camrig
import look
import rf_common as rf
from growth import Growth
from parts import space, subjects
from parts.aircraft import airliner

BUDGET = 4000.0
FT = 0.3048
MILE = 1609.344
# the subject sizes (m) at which the default shots cut: hook | hydrant/you | cars | bus/street | steeple | drone |
# supertall | clouds | Everest | airliner | edge of space | orbit | Moon/Earth size | Earth ball | beyond the Moon as
# its head comes up from far away | (then the impact, from the moment it hits the Moon)
SHOT_SIZES = [0.6537, 2.996, 9.43, 44.8, 192.0, 624.0, 1537.0, 8113.0, 16225.0, 39951.0, 278400.0, 3.146e6,
              2.5167e7, 5.0e7]
CRUISE = 10_668.0                 # 35,000 ft
EVEREST = 8_849.0


# ---------------------------------------------------------------- small helpers

def _ease(u):
    return camrig.smoothstep(u)


def _lerp(a, b, u):
    return a + (b - a) * u


def _sph(c, az, el, d):
    """Point at compass bearing `az` (degrees from +Y towards +X), elevation `el`, distance `d` from c."""
    a, e = math.radians(az), math.radians(el)
    return np.asarray(c, float) + d * np.array([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)])


def aim(cam, p, sx, sy, lens):
    """Camera target that puts world point p at screen pixel (sx, sy)."""
    cam, p = np.asarray(cam, float), np.asarray(p, float)
    dist = float(np.linalg.norm(p - cam))
    f0, r0, u0 = camrig.basis(cam, p)
    k = lens / (camrig.SENSOR / 2)
    tx = (sx / (camrig.W / 2) - 1.0) * (camrig.W / camrig.H) / k
    ty = (1.0 - sy / (camrig.H / 2)) / k
    tgt = cam + f0 * dist
    for _ in range(4):
        f = f0 - tx * r0 - ty * u0
        f /= np.linalg.norm(f)
        tgt = cam + f * dist
        pr = camrig.project(p, cam, tgt, lens)
        if pr is None:
            break
        ex, ey = pr[0] - sx, pr[1] - sy
        if abs(ex) < 0.5 and abs(ey) < 0.5:
            break
        tx += ex / (camrig.W / 2) * (camrig.W / camrig.H) / k
        ty -= ey / (camrig.H / 2) / k
    return tgt


def contact_height(px, py, rad, spot, yaw_deg, ax, ay):
    """Subject size at which its footprint ellipse (half-width ax, half-length ay per unit of size, facing compass
    yaw_deg) first touches an item of support radius `rad` at (px, py); the same rule as the street's crush field."""
    qx, qy = px - spot[0], py - spot[1]
    yaw = math.radians(-yaw_deg)
    lx = qx * math.cos(yaw) + qy * math.sin(yaw)
    ly = -qx * math.sin(yaw) + qy * math.cos(yaw)
    ec = math.hypot(lx / ax, ly / ay)
    q = math.hypot(qx, qy) + 1e-9
    return max(ec * max(1.0 - rad / q, 0.02), 0.01)


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


def dust_material(color=(0.46, 0.42, 0.37)):
    """Billowing dust: 4D noise (obj["phase"] scrolls it), dense in the middle, soft edges, faded by obj["fx"]."""
    mat, nt, out = _new_mat("dust")
    tc = nt.node("ShaderNodeTexCoord")
    n = nt.node("ShaderNodeTexNoise", noise_dimensions="4D")
    n.inputs["Scale"].default_value = 1.6
    n.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    nt.links.new(nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="phase").outputs["Fac"],
                 n.inputs["W"])
    fx = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="fx").outputs["Fac"]
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    core = nt.math("SUBTRACT", 1.0, nt.math("POWER", lw.outputs["Facing"], 1.4))
    a = nt.math("MULTIPLY", nt.math("MULTIPLY", fx, core),
                nt.math("DIVIDE", nt.math("SUBTRACT", n.outputs["Fac"], 0.4), 0.22, clamp=True))
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    nt.links.new(nt.math("MINIMUM", a, 0.92), b.inputs["Alpha"])
    shader = rf.scene_haze(nt, b.outputs[0], 0.8) if rf.HAZE_SCENE else b.outputs[0]
    nt.links.new(shader, out.inputs["Surface"])
    _set(mat, surface_render_method="BLENDED", blend_method="BLEND", use_backface_culling=False)
    return mat


def rubble_materials():
    """Brick, concrete and render, with a little grit."""
    mats = []
    for k, c in enumerate(((0.36, 0.15, 0.09), (0.42, 0.41, 0.39), (0.62, 0.56, 0.45))):
        def base(nt, c=c):
            tc = nt.node("ShaderNodeTexCoord")
            n = nt.node("ShaderNodeTexNoise")
            n.inputs["Scale"].default_value = 3.0
            n.inputs["Detail"].default_value = 4.0
            nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
            return nt.mix_color(n.outputs["Fac"], tuple(v * 0.7 for v in c) + (1.0,), c + (1.0,))
        mats.append(rf.make_material(f"rubble_{k}", base, rough=0.9, haze=1.0, glitch=True))
    return mats


def _debris(collection, mat, centre, out_dir, size, n, rnd, name):
    """A burst of rubble boxes: shape key "v" moves each box by its velocity (1 s), "g" by gravity (1 s^2), so
    keying v = tau and g = tau^2 gives ballistic arcs."""
    mb = rf.MeshBuilder()
    vels = []
    for _ in range(n):
        s = size * rnd.uniform(0.04, 0.13)
        c = Vector((rnd.uniform(-0.3, 0.3) * size, rnd.uniform(-0.3, 0.3) * size, rnd.uniform(0.05, 0.45) * size))
        mb.box(c.x - s, c.y - s * 0.7, c.z - s * 0.5, c.x + s, c.y + s * 0.7, c.z + s * 0.5, rnd.randrange(len(mat)))
        sp = (6.0 + size * 0.5) * rnd.uniform(0.5, 1.3)
        d = Vector((out_dir[0] + rnd.uniform(-0.6, 0.6), out_dir[1] + rnd.uniform(-0.6, 0.6), rnd.uniform(0.3, 1.2)))
        vels.append(d.normalized() * sp)
    me = mb.build(name, mat, fix_normals=True)
    ob = rf.add_object(name, me, collection, tuple(centre))
    ob.shape_key_add(name="Basis")
    kv = ob.shape_key_add(name="v")
    kg = ob.shape_key_add(name="g")
    for kb in (kv, kg):
        kb.slider_min, kb.slider_max = 0.0, 10.0
    for i in range(n):
        for j in range(8):
            vi = i * 8 + j
            co = me.vertices[vi].co
            kv.data[vi].co = co + vels[i]
            kg.data[vi].co = co + Vector((0.0, 0.0, -4.905))
    ob["glitch"] = 0.0
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass
    return ob


# ---------------------------------------------------------------- the effect

def apply(spec, info):
    E = spec["effect"]
    fps = spec["fps"]
    nf = int(round(spec["render_until"] * fps))
    t = np.arange(nf) / fps
    frames = np.arange(1, nf + 1)
    scene = info.get("scene") or bpy.context.scene
    world = info.get("world") or scene.world
    if world is None or "SpaceMix" not in world.node_tree.nodes:
        # this effect climbs into space, so it needs look.py's sky (Nishita that fades to stars)
        world = look.setup_sky(scene, 215.0, 12.0)
    cols = dict(info.get("collections") or {})
    if "hero" not in cols:
        cols["hero"] = rf.new_collection("hero")
    hero_col = cols["hero"]
    sun_ob = info.get("sun") or next((o for o in scene.objects if o.type == "LIGHT" and o.data.type == "SUN"), None)
    if sun_ob is None:
        sun_ob = look.add_sun(hero_col, 215.0, 12.0)
    S = np.array(info.get("spot", (0.0, 0.0, 0.0)), float)
    refs = info.get("refs", {})
    hero = info.get("hero", {})
    yaw_deg = E.get("yaw", info.get("spot_yaw", 200.0))
    theta = math.radians(-yaw_deg)
    R_yaw = np.array([[math.cos(theta), -math.sin(theta), 0.0], [math.sin(theta), math.cos(theta), 0.0], [0, 0, 1]])
    rnd = random.Random(E.get("seed", 5))

    # ---------------- the subject and its growth
    sub = subjects.build(E.get("subject", "duck"), hero_col)
    sob = sub["object"]
    if "start_size" in E:
        size0 = float(E["start_size"])
    elif "start_size_in" in E:
        size0 = float(E["start_size_in"]) * 0.0254
    else:
        size0 = float(E.get("start_size_ft", 0.5)) * FT
    g = Growth(size0, E.get("start_at", 0.0), E.get("double_every", 2.0))
    size = np.array([g.value(x) for x in t])
    H = size * sub["height"]                              # the subject's height in metres
    int_max = E.get("int32_max", 2147483647)
    t_over = E.get("overflow_at") or g.time_at(int_max * FT)
    over = t >= t_over
    top_u = np.array(sub["top"], float)
    crown_dir = R_yaw @ top_u                             # crown position per metre of size, from the spot
    t_space = E.get("space_from") or g.time_at(40_000.0 / sub["height"])
    T_of = lambda height_m: g.time_at(height_m / sub["height"])

    # ---------------- planet set
    E_c = S + np.array([0.0, 0.0, -space.R_EARTH])
    if "sun_dir" in info:
        sun_dir = np.array(info["sun_dir"], float)
    else:                                               # towards the sun: the lamp's +Z axis
        sun_dir = np.array(sun_ob.matrix_world.to_3x3() @ Vector((0.0, 0.0, 1.0)), float)
    if "rf_haze_dist" not in scene:
        look.init_haze(scene, tuple(sun_dir))          # the air keys below need look.py's haze properties
    planet = space.earth(hero_col, tuple(sun_dir), land_at=(0.0, 0.0, 1.0))
    space.space_sky(world, tuple(sun_dir))

    def crown(sz):
        return S + crown_dir * sz

    # the Moon sits where the crown will reach it (just inside its near side)
    lo, hi = 1.0e7, 2.0e9
    for _ in range(80):
        mid = (lo + hi) / 2
        if np.linalg.norm(crown(mid) - E_c) < space.MOON_DIST - 0.35 * space.R_MOON:
            lo = mid
        else:
            hi = mid
    s_hit = (lo + hi) / 2
    t_hit = g.time_at(s_hit)
    u_moon = (crown(s_hit) - E_c) / np.linalg.norm(crown(s_hit) - E_c)
    hit = bool(E.get("moon_hit", True))
    if not hit:                         # keep the Moon off its path: the head sails past it, 28 degrees away
        ax_ = np.cross(u_moon, [0.0, 0.0, 1.0])
        ax_ /= np.linalg.norm(ax_) + 1e-9
        a_ = math.radians(28.0)
        u_moon = u_moon * math.cos(a_) + np.cross(ax_, u_moon) * math.sin(a_)
    M = E_c + u_moon * space.MOON_DIST
    moon = space.moon(hero_col)
    shards = space.moon_shards(hero_col)
    flash = space.flash(hero_col)
    ghost = space.ghost_sphere(hero_col, "moon")
    ring = space.orbit_ring(hero_col, "iss", thickness=0.0028)
    plane = airliner(hero_col)

    # ---------------- shots (each anchored to the subject's size)
    sizes = E.get("shot_sizes", SHOT_SIZES)
    cuts = [0.0] + [g.time_at(x) for x in sizes] + [t_hit, spec["render_until"] + 1.0]
    fp = sub["footprint"]
    # when the footprint reaches each building (debris, dust, sound, camera rumble)
    hit_items = []
    for it in info.get("crushables", []):
        hc = contact_height(it["x"], it["y"], it["rad"], S, yaw_deg, fp[0], fp[1])
        tc = g.time_at(max(hc, size0))
        if 0.05 < tc < t_space:
            hit_items.append((tc, it))
    hit_items.sort(key=lambda p: p[0])
    hits = [round(tc, 3) for tc, it in hit_items
            if it["cls"] in ("building", "church", "bus", "car", "tower", "landmark")
            and math.hypot(it["x"] - S[0], it["y"] - S[1]) < 350.0]
    big_hits = [tc for tc, it in hit_items if it["cls"] in ("building", "church", "bus", "landmark")]

    def rumble(x):
        return min(1.0, sum(camrig.pulse(x, tc, 0.02, 0.5) for tc in big_hits if tc - 0.05 < x < tc + 2.5))
    sup = np.array(refs["supertall"]["pos"], float) if "supertall" in refs else S + np.array([-900.0, 1500.0, 0.0])
    eve = np.array(refs["everest"]["pos"], float) if "everest" in refs else S + np.array([-12000.0, 25000.0, EVEREST])
    steeple = np.array(refs["steeple"]["pos"], float) if "steeple" in refs else S + np.array([10.0, 36.0, 0.0])

    ext = max(sub["height"], 0.6 * max(sub["width"], sub["length"]))     # framing scale per unit of size

    def hm(x):
        return g.value(x) * ext

    def centre(x, k=0.45):
        return S + np.array([0.0, 0.0, k * hm(x)])

    sun_az = math.degrees(math.atan2(sun_dir[0], sun_dir[1]))      # compass bearing of the sun (215 on the street)

    def side_on(a, b, dist, elev, flip=False):
        """Camera looking square-on at the pair a, b (so their heights compare fairly), on the sunny side."""
        mid = (a + b) / 2
        d = b - a
        perp = np.array([-d[1], d[0], 0.0])
        perp /= np.linalg.norm(perp) + 1e-9
        if (np.dot(perp, sun_dir[:2].tolist() + [0.0]) < 0) != flip:
            perp = -perp
        return mid + perp * dist + np.array([0.0, 0.0, elev]), mid

    def shot(k, x):
        """(cam, look_point, screen_x, screen_y, lens, opts) for shot k at time x."""
        t0, t1 = cuts[k], cuts[k + 1]
        u = min(1.0, max(0.0, (x - t0) / max(t1 - t0, 1e-6)))
        e = _ease(u)
        h = hm(x)
        if k == 0:                      # hook: down on the asphalt, three-quarters on, the street behind it
            cam = _sph(S + [0, 0, 0.05], _lerp(209.0, 216.0, e), 3.0, _lerp(0.95, 1.5, e))
            return cam, centre(x, 0.42), 560, 1020, 26.0, {}
        if k == 1:                      # the hydrant and you on the curb
            cam = _sph(S + [0.6, 0.0, 0.0], _lerp(247.0, 257.0, e), _lerp(6.0, 9.0, e), _lerp(8.6, 9.8, e))
            look_ = S + np.array([1.3, 1.9, 0.5 * max(h, 1.6)])
            return cam, look_, 540, 1110, 26.0, {}
        if k == 2:                      # bigger than the parked cars
            cam = S + np.array([_lerp(-8.1, -7.3, e), _lerp(-14.0, -20.0, e), _lerp(1.5, 3.6, e)])
            return cam, centre(x, 0.42), 560, 1100, 26.0, {}
        if k == 3:                      # down the street: the bus in front, then the whole street going down
            cam = S + np.array([-5.9, _lerp(-58.0, -76.0, e), _lerp(3.2, 4.8, e)])
            look_ = S + np.array([-2.0, -6.0, 0.42 * h])
            return cam, look_, 560, 1080, 30.0, {"shake": 0.5}
        if k == 4:                      # side by side with the steeple, which it then knocks over
            cam, mid = side_on(S, steeple, _lerp(165.0, 215.0, e), _lerp(30.0, 55.0, e))
            look_ = S + (steeple - S) * 0.18 + np.array([0.0, 0.0, 0.5 * max(h, 50.0)])
            return cam, look_, 540, 1050, 24.0, {"shake": 0.35}
        if k == 5:                      # drone orbit as Main Street goes down
            cam = _sph(S, _lerp(sun_az - 19.0, sun_az + 31.0, e), _lerp(16.0, 24.0, e), 3.4 * h)
            return cam, centre(x, 0.45), 560, 1060, 28.0, {}
        if k == 6:                      # next to the tallest building on Earth
            cam, mid = side_on(S, sup, _lerp(4600.0, 5600.0, e), _lerp(700.0, 900.0, e))
            look_ = mid + np.array([0.0, 0.0, 0.42 * max(h, 828.0)])
            return cam, look_, 540, 1060, 35.0, {}
        if k == 7:                      # its head through the clouds, from above them
            cam = _sph(S, sun_az + 21.0, 0.0, _lerp(7500.0, 17000.0, e)) + \
                np.array([0.0, 0.0, _lerp(3300.0, 5600.0, e)])
            return cam, centre(x, 0.6), 540, 1010, 35.0, {}
        if k == 8:                      # Everest's height, side by side
            cam, mid = side_on(S, eve * np.array([1, 1, 0]), 58000.0, 5000.0)
            look_ = mid + np.array([0.0, 0.0, 0.45 * max(h, EVEREST)])
            return cam, look_, 540, 1040, 24.0, {}
        if k == 9:                      # an airliner at cruising altitude banks round it
            cam = _sph(S, sun_az + 37.0, 0.0, _lerp(32000.0, 68000.0, e)) + np.array([0.0, 0.0, CRUISE + 90.0])
            return cam, centre(x, 0.42), 540, 980, 30.0, {"plane": True}
        if k == 10:                     # the edge of space
            cam = _sph(S, sun_az + 23.0, 0.0, _lerp(260e3, 700e3, e)) + np.array([0.0, 0.0, _lerp(70e3, 170e3, e)])
            return cam, centre(x, 0.6), 560, 1000, 30.0, {"space": True}
        if k == 11:                     # orbit: the space station's ring
            cam = _sph(S, sun_az + 17.0, 22.0, 4.2 * h)
            return cam, centre(x, 0.5), 560, 1020, 30.0, {"space": True, "ring": True}
        if k == 12:                     # the Moon (a ghost, to scale), then the Earth itself, for size
            cam = _sph(S, sun_az + 13.0, 14.0, 4.0 * h) + np.array([0.0, 0.0, -0.3 * h])
            return cam, S + np.array([0.0, 0.0, 0.3 * h - 0.25 * space.R_EARTH * min(1.0, h / 1.2e7)]), 540, 1190, \
                30.0, {"space": True, "ghost": True}
        if k == 13:                     # a ball under its feet
            cam = _sph(S, sun_az + 7.0, 8.0, 3.3 * h) + np.array([0.0, 0.0, -0.4 * h])
            return cam, S + np.array([0.0, 0.0, 0.25 * h]), 540, 1180, 30.0, {"space": True}
        side = np.cross(u_moon, [0.0, 0.0, 1.0])
        side /= np.linalg.norm(side) + 1e-9
        if np.dot(side, sun_dir) < 0:
            side = -side
        if k == 14:                     # beyond the Moon, looking back down at it as its head comes up from far away
            fwd = R_yaw @ np.array([0.0, 1.0, 0.0])
            cam = M + u_moon * _lerp(3.4e7, 2.05e7, e) + fwd * 0.9e7 + side * 0.6e7
            return cam, M, 540, 640, 40.0, {"space": True, "moon_tag": True}
        # the impact, then the overflow: alongside the head as it carries the wreck of the Moon up
        c_ = crown(g.value(x))
        cam = c_ + side * 0.65 * g.value(x) - u_moon * 0.1 * g.value(x)
        return cam, c_ - u_moon * 0.12 * g.value(x), 540, 1000, 26.0, {"space": True, "shake": 1.0}

    cam_xyz, tgt_xyz, lens, shot_i, opts_l = [], [], [], [], []
    ph = [rnd.uniform(0, 6.28) for _ in range(6)]
    for x in t:
        k = max(i for i in range(len(cuts) - 1) if cuts[i] <= x) if x >= cuts[0] else 0
        k = min(k, len(cuts) - 2)
        cam, look_, sx, sy, ln, op = shot(k, x)
        tgt = aim(cam, look_, sx, sy, ln)
        shake = op.get("shake", 0.0) * max(rumble(x), camrig.pulse(x, t_hit, 0.02, 0.8) if x >= t_hit - 0.05 else 0.0)
        if shake:
            jx, jz = camrig.jitter(x, shake * 0.012, ph)
            f, r, u = camrig.basis(cam, tgt)
            d = np.linalg.norm(tgt - cam)
            tgt = tgt + (r * jx + u * jz) * d
        cam_xyz.append(cam)
        tgt_xyz.append(tgt)
        lens.append(ln)
        shot_i.append(k)
        opts_l.append(op)
    cam_xyz, tgt_xyz, lens = np.array(cam_xyz), np.array(tgt_xyz), np.array(lens)
    in_space = np.array([bool(o.get("space")) for o in opts_l])
    nshots = len(cuts) - 1

    # ---------------- camera and render scale
    cam_ob = rf.add_camera(hero_col, (0, 0, 0), 0.0, 0.0, 30.0)
    tgt_ob = bpy.data.objects.new("CamTarget", None)
    hero_col.objects.link(tgt_ob)
    tr = cam_ob.constraints.new("TRACK_TO")
    tr.target = tgt_ob
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    dist = np.linalg.norm(tgt_xyz - cam_xyz, axis=1)
    s_arr = np.minimum(1.0, BUDGET / np.maximum(dist, 1e-6))

    def key_xyz(ob, data, path="location", interp="LINEAR"):
        data = np.asarray(data, float)
        for k in range(3):
            rf.key_series(ob, path, k, frames, data[:, k], interp=interp)

    def key_vis(ob, vis):
        rf.key_series(ob, "hide_render", -1, frames, (~np.asarray(vis, bool)).astype(float), interp="CONSTANT")

    key_xyz(cam_ob, np.zeros((nf, 3)))
    key_xyz(tgt_ob, (tgt_xyz - cam_xyz) * s_arr[:, None])
    rf.key_series(cam_ob.data, "lens", -1, frames, lens)

    # ground world on the mover (parked far away in space)
    # (a world without a mover gets one here, with everything in its collections parented to it)
    mover = info.get("mover")
    if mover is None:
        mover = bpy.data.objects.new("WorldMover", None)
        hero_col.objects.link(mover)
        hero_obs = set(hero_col.all_objects)
        for ob in list(scene.objects):
            if ob.parent is None and ob is not mover and ob not in hero_obs:
                ob.parent = mover
                info.setdefault("ground_objects", []).append(ob)
    key_xyz(mover, np.where(in_space[:, None], np.array([0.0, 0.0, -1e9]), -cam_xyz * s_arr[:, None]))
    key_xyz(mover, np.repeat(s_arr[:, None], 3, 1), path="scale")
    for ob in info.get("ground_objects", []):
        key_vis(ob, ~in_space)

    # subject: placed, scaled, a squash-and-stretch on each doubling, the overflow glitch
    bounce = np.zeros(nf)
    A = E.get("bounce", 0.06)
    for kd in range(1, 60):
        td = g.t0 + g.T * kd
        if td >= t_space:
            break
        m = t >= td
        tau = t[m] - td
        bounce[m] += A * np.exp(-tau / 0.22) * np.sin(2 * math.pi * tau / 0.36)
    sl = s_arr * size
    key_xyz(sob, (S - cam_xyz) * s_arr[:, None])
    key_xyz(sob, np.stack([sl * (1 - bounce / 2), sl * (1 - bounce / 2), sl * (1 + bounce)], 1), path="scale")
    sob.rotation_euler = (0.0, 0.0, theta)
    rf.key_series(sob, '["glitch"]', 0, frames, over.astype(float), interp="CONSTANT")

    # planet set
    for name in ("surface", "clouds", "atmo"):
        space.render_key(planet[name], frames, np.repeat(E_c[None], nf, 0), space.R_EARTH, cam_xyz, s_arr, in_space)
    alt_e = np.linalg.norm(cam_xyz - E_c, axis=1) - space.R_EARTH
    # the limb glow is for whole-disc views; from low orbit it would fog the ground
    rf.key_series(planet["atmo"], '["fx"]', 0, frames, np.clip((alt_e - 2.0e5) / 3.0e6, 0.12, 1.0))
    after = (t >= t_hit) & hit                     # the Moon has been hit
    moon_vis = in_space & ~after
    space.render_key(moon, frames, np.repeat(M[None], nf, 0), space.R_MOON, cam_xyz, s_arr, moon_vis)
    # the shattered Moon rides the crown outward and spreads
    tau = np.clip(t - t_hit, 0.0, None)
    sh_c = np.array([M + u_moon * (np.linalg.norm(crown(g.value(x)) - E_c) - np.linalg.norm(crown(s_hit) - E_c))
                     if x >= t_hit else M for x in t])
    sh_r = space.R_MOON * (1.0 + 26.0 * tau)
    space.render_key(shards, frames, sh_c, sh_r, cam_xyz, s_arr, in_space & after)
    rf.key_series(shards.data.shape_keys, 'key_blocks["burst"].value', -1, frames, np.clip(tau / 0.35, 0.0, 1.0))
    rf.key_series(shards, '["heat"]', 0, frames, np.exp(-tau / 0.9) * after)
    rf.key_series(shards, '["glitch"]', 0, frames, over.astype(float), interp="CONSTANT")
    # the fireball: grows at about 0.3 c and burns out in a second
    fl_r = space.R_MOON * (3.0 + 70.0 * tau)
    space.render_key(flash, frames, sh_c, fl_r, cam_xyz, s_arr, in_space & after & (tau < 1.2))
    rf.key_series(flash, '["fx"]', 0, frames, 0.9 * np.exp(-tau / 0.16) * after)
    shock = space.orbit_ring(hero_col, "shock", color=(1.0, 0.85, 0.65), thickness=0.02, strength=9.0)
    shock.rotation_mode = "QUATERNION"
    shock.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(Vector(tuple(u_moon)))
    space.render_key(shock, frames, sh_c, space.R_MOON * (2.0 + 70.0 * tau), cam_xyz, s_arr,
                     in_space & after & (tau < 1.2))
    rf.key_series(shock, '["fade"]', 0, frames, np.exp(-tau / 0.35) * after)

    # ghost Moon beside it (to scale), the space station's orbit
    t_moon_size = T_of(2 * space.R_MOON)
    ghost_on = in_space & (t > t_moon_size - 0.4) & (t < t_moon_size + 2.5)
    gc = []
    for i, x in enumerate(t):
        f, r, u = camrig.basis(cam_xyz[i], tgt_xyz[i])
        half_w = 0.55 * max(sub["width"], sub["length"]) * size[i]
        gc.append(S + np.array([0, 0, 0.42 * H[i]]) + r * (half_w + space.R_MOON * 1.2))
    space.render_key(ghost, frames, gc, space.R_MOON, cam_xyz, s_arr, ghost_on)
    rf.key_series(ghost, '["fade"]', 0, frames, ghost_on.astype(float) *
                  np.clip((t - (t_moon_size - 0.4)) / 0.4, 0, 1), interp="LINEAR")
    t_iss = T_of(space.ISS_ALT)
    ring_on = np.array([bool(o.get("ring")) for o in opts_l])
    i_mid = min(nf - 1, int(round(t_iss * fps)))
    vd = S - cam_xyz[i_mid]
    vd[2] = 0.0
    vd /= np.linalg.norm(vd) + 1e-9
    ring.rotation_mode = "QUATERNION"
    ring.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(Vector(tuple(vd)))
    space.render_key(ring, frames, np.repeat(E_c[None], nf, 0), space.R_EARTH + space.ISS_ALT, cam_xyz, s_arr, ring_on)
    rf.key_series(ring, '["fade"]', 0, frames, np.clip((t - (t_iss - 1.2)) / 0.6, 0, 1) * ring_on)

    # the airliner: banks round it at cruising altitude, past the camera
    plane_on = np.array([bool(o.get("plane")) for o in opts_l])
    pl = plane["plane"]
    pl_loc, pl_rot = [], []
    k_pl = next((k for k in range(nshots) if shot_i.count(k) and opts_l[shot_i.index(k)].get("plane")), 9)
    tp0, tp1 = cuts[k_pl], cuts[k_pl + 1]
    i0 = min(nf - 1, int(round(tp0 * fps)))
    c0 = cam_xyz[i0]
    f0, r0, u0 = camrig.basis(c0, tgt_xyz[i0])
    for i, x in enumerate(t):
        tau_p = x - tp0
        f0, r0, u0 = camrig.basis(cam_xyz[i], tgt_xyz[i])
        p = cam_xyz[i] + f0 * 650.0 + r0 * (-430.0 + 250.0 * tau_p) - u0 * 30.0 + f0 * (36.0 * tau_p ** 2)
        p[2] = CRUISE
        pl_loc.append(s_arr[i] * (p - cam_xyz[i]))
        heading = math.atan2(r0[1] + 0.12 * f0[1] * tau_p, r0[0] + 0.12 * f0[0] * tau_p)
        pl_rot.append((0.0, math.radians(-32.0), heading - math.pi / 2))
    key_xyz(pl, pl_loc)
    key_xyz(pl, np.repeat(s_arr[:, None], 3, 1), path="scale")
    key_xyz(pl, pl_rot, path="rotation_euler")
    key_vis(pl, plane_on)
    key_vis(plane["contrail"], plane_on)

    # crush field: everything the footprint reaches tips away from it
    crush = info.get("crush")
    if crush:
        cob, mod, sk = crush["object"], crush["modifier"], crush["sockets"]
        ax_, ay_, _ = sub["footprint"]
        mod[sk["Axis X"]] = float(ax_)
        mod[sk["Axis Y"]] = float(ay_)
        mod[sk["Yaw"]] = float(theta)
        mod[sk["Center X"]] = float(S[0])
        mod[sk["Center Y"]] = float(S[1])
        path = f'modifiers["{mod.name}"]["{sk["LogH"]}"]'
        f_start = 1 + int(round(g.t0 * fps))
        kf = [1, max(f_start, 1), nf]
        vals = [math.log2(size0), math.log2(size0), math.log2(g.value((nf - 1) / fps))]
        if kf[1] == kf[0]:
            kf, vals = kf[1:], vals[1:]
        rf.key_series(cob, path, -1, kf, vals, interp="LINEAR")

    # people and traffic step out of the way before it reaches them; you leave after the second shot
    def reach_t(px, py):
        hc = contact_height(px, py, 1.0, S, yaw_deg, fp[0], fp[1])
        return g.time_at(max(hc / 1.35, size0))

    for ob in info.get("people", []) + info.get("traffic", []) + info.get("lamp_lights", []):
        locs = []
        for f_ in frames:
            fc = [rf.get_fcurve(ob, "location", k) for k in range(2)]
            locs.append([fc[k].evaluate(f_) if fc[k] else ob.location[k] for k in range(2)])
        locs = np.array(locs)
        gone = np.array([x >= reach_t(*locs[i]) for i, x in enumerate(t)])
        gone = np.maximum.accumulate(gone)
        key_vis(ob, ~gone & ~in_space)
    you = hero.get("you")
    if you is not None:
        key_vis(you, (t >= cuts[1]) & (t < cuts[2]) & ~in_space)

    # debris and dust on the buildings it knocks over
    debris_n = E.get("debris", 70)
    rub = rubble_materials()
    dmat = dust_material()
    dust_mesh = None
    near = sorted(hit_items, key=lambda p: math.hypot(p[1]["x"] - S[0], p[1]["y"] - S[1]))
    n_deb = 0
    n_dust = 0
    dust_col = cols.get("ground", hero_col)
    for tc, it in near:
        big = it["cls"] in ("building", "church", "bus", "tower", "landmark")
        if not big:
            continue
        q = np.array([it["x"] - S[0], it["y"] - S[1]])
        qd = q / (np.linalg.norm(q) + 1e-9)
        f0_ = 1 + int(round(tc * fps))
        if n_deb < debris_n:
            n_deb += 1
            sz = max(it["w"], it["d"], it["h"] * 0.6)
            deb = _debris(dust_col, rub, (it["x"], it["y"], 0.0), qd, sz, 30 if it["cls"] != "landmark" else 60, rnd,
                          f"debris_{n_deb}")
            deb.parent = mover
            info.setdefault("ground_objects", []).append(deb)
            tau_d = np.clip(t - tc, 0.0, None)
            kb = deb.data.shape_keys
            rf.key_series(kb, 'key_blocks["v"].value', -1, frames, np.minimum(tau_d, 10.0))
            rf.key_series(kb, 'key_blocks["g"].value', -1, frames, np.minimum(tau_d ** 2, 10.0))
            key_vis(deb, (t >= tc) & (t < tc + 3.2) & ~in_space)
        if E.get("dust", True):
            if dust_mesh is None:
                mbd = rf.MeshBuilder()
                mbd.ico((0, 0, 0), (1, 1, 0.6), 3, 0)
                dust_mesh = mbd.build("dust_puff", [dmat], smooth=True)
            n_dust += 1
            dob = rf.add_object(f"dust_{n_dust}", dust_mesh, dust_col, (it["x"], it["y"], 0.0))
            dob.parent = mover
            dob["fx"] = 0.0
            dob["phase"] = rnd.uniform(0, 10)
            try:
                dob.visible_shadow = False
            except AttributeError:
                pass
            r0_ = max(it["w"], it["d"]) * 0.6
            tau_d = np.clip(t - tc, 0.0, None)
            grow_r = r0_ * (1.0 + 1.6 * (1 - np.exp(-tau_d / 1.2)))
            key_xyz(dob, np.stack([grow_r, grow_r, grow_r * 0.8], 1), path="scale")
            puff = np.clip(tau_d / 0.25, 0, 1) * np.exp(-tau_d / 2.6)
            rf.key_series(dob, '["fx"]', 0, frames, np.where(t >= tc, puff, 0.0))
            rf.key_series(dob, '["phase"]', 0, frames, dob["phase"] + tau_d * 0.6)
            key_vis(dob, (t >= tc) & (t < tc + 6.0) & ~in_space)

    # a wall of dust round its base while it flattens the town
    if E.get("dust", True):
        mbr = rf.MeshBuilder()
        for i in range(34):
            a = 2 * math.pi * (i + rnd.uniform(-0.3, 0.3)) / 34
            rr = rnd.uniform(0.13, 0.22)
            mbr.ico((math.cos(a) * rnd.uniform(0.97, 1.08), math.sin(a) * rnd.uniform(0.97, 1.08), rr * 0.55),
                    (rr, rr, rr * rnd.uniform(0.7, 1.1)), 2, 0, jitter=0.12, rnd=rnd)
        dring = rf.add_object("dust_wall", mbr.build("dust_wall", [dmat], smooth=True), dust_col, (S[0], S[1], 0.0))
        dring.parent = mover
        dring["fx"] = 0.0
        dring["phase"] = 2.0
        rr_ = 1.05 * size * max(fp[0], fp[1])
        key_xyz(dring, np.stack([rr_, rr_, rr_ * 0.75], 1), path="scale")
        t_d0 = T_of(25.0)
        t_d1 = T_of(1400.0)
        wall = np.clip((t - t_d0) / 1.5, 0, 1) * np.clip((t_d1 - t) / 1.2, 0, 1) * 0.85
        rf.key_series(dring, '["fx"]', 0, frames, wall)
        rf.key_series(dring, '["phase"]', 0, frames, 2.0 + t * 0.35)
        key_vis(dring, (t > t_d0) & (t < t_d1) & ~in_space)

    # ---------------- clip planes, sky, haze, sun
    alt = np.where(in_space, alt_e, cam_xyz[:, 2])
    near_l, far_l = [], []
    for i in range(nf):
        c = cam_xyz[i]
        s = s_arr[i]
        ds = [max(np.linalg.norm(S + np.array([0, 0, 0.45 * H[i]]) - c) - 0.75 * H[i], 0.02 * H[i])]
        if plane_on[i]:
            ds.append(max(np.linalg.norm(np.array(pl_loc[i]) / s) - 60.0, 5.0))
        if in_space[i]:
            ds.append(max(np.linalg.norm(c - E_c) - space.R_EARTH - 90_000.0, 1000.0))
            far = max(np.linalg.norm(c - E_c) + space.R_EARTH, np.linalg.norm(c - S) + 2.2 * H[i])
            if moon_vis[i]:
                ds.append(max(np.linalg.norm(c - M) - space.R_MOON * 1.05, 1000.0))
                far = max(far, np.linalg.norm(c - M) + space.R_MOON)
            if after[i]:
                ds.append(max(np.linalg.norm(c - sh_c[i]) - fl_r[i] * 1.1, 1000.0))
            if ghost_on[i]:
                ds.append(max(np.linalg.norm(c - gc[i]) - space.R_MOON * 1.05, 1000.0))
            far *= 1.2
            near = 0.5 * min(ds)
        else:
            far = 260_000.0
            near = 0.5 * min(min(ds), max(0.04, c[2]))
        far_r = far * s
        near_r = max(near * s, far_r / 8.0e6)
        near_l.append(near_r)
        far_l.append(far_r)
    rf.key_series(cam_ob.data, "clip_start", -1, frames, near_l)
    rf.key_series(cam_ob.data, "clip_end", -1, frames, far_l)
    dmul = 1.4 + (E.get("haze_dist_mul", 4.0) - 1.4) * np.clip(alt / 2500.0, 0, 1)
    mmul = 1.0 + (E.get("haze_max_mul", 0.6) - 1.0) * np.clip(alt / 2500.0, 0, 1)
    look.key_air(scene, world, frames, alt, dist_mul=dmul, max_mul=mmul)
    rows = [look.air_at(float(a), float(dm), float(mm)) for a, dm, mm in zip(alt, dmul, mmul)]
    look.key_scene_prop(scene, "rf_haze_dist", frames, [r[3] * s for r, s in zip(rows, s_arr)])
    if info.get("night"):
        # night air: the haze (and the clouds, lit from it) go dark blue instead of the daytime colours
        look.key_scene_prop(scene, "rf_haze_col", frames, np.array([r[5] for r in rows]) * np.array([0.05, 0.06, 0.1]))
        look.key_scene_prop(scene, "rf_haze_sun", frames, np.array([r[6] for r in rows]) * np.array([0.06, 0.06, 0.09]))
        rf.key_series(world.node_tree, 'nodes["StarMix"].outputs[0].default_value', -1, frames,
                      [max(r[2], 0.6) for r in rows])
    sun_l = sun_ob.data
    rf.key_series(sun_l, "energy", -1, frames, np.where(in_space, 3.6, sun_l.energy), interp="CONSTANT")
    for k, white in enumerate((1.0, 0.97, 0.93)):
        rf.key_series(sun_l, "color", k, frames, np.where(in_space, white, sun_l.color[k]), interp="CONSTANT")

    # ---------------- tags and the subject's screen box
    def proj(i, p):
        pr = camrig.project(np.asarray(p, float), cam_xyz[i], tgt_xyz[i], lens[i])
        return None if pr is None else [round(pr[0], 1), round(pr[1], 1)]

    def tag(label, sub_, t0, t1, point_fn):
        xy = [proj(i, point_fn(i, x)) if t0 <= x < t1 else None for i, x in enumerate(t)]
        return {"label": label, "sub": sub_, "from": t0, "to": t1, "xy": xy}

    tags = []
    if E.get("tags", True):
        def at(p):
            return lambda i, x: p

        def ref_top(name, h_):
            p = np.array(refs[name]["pos"], float)
            return p + np.array([0.0, 0.0, h_])

        if "hydrant" in refs:
            tags.append(tag("FIRE HYDRANT", "0.76 M", T_of(0.76) + 0.05, T_of(0.76) + 1.9, at(ref_top("hydrant", 0.8))))
        if "you" in refs:
            tags.append(tag("YOU", "1.76 M", T_of(1.91) + 0.05, min(T_of(1.91) + 1.6, cuts[2]),
                            at(ref_top("you", 1.9))))
        if "car" in refs:
            car_l = refs["car"].get("length", 4.75)
            tags.append(tag("CAR", f"{car_l:.1f} M LONG", T_of(car_l) + 0.1, T_of(car_l) + 1.7,
                            at(ref_top("car", refs["car"].get("h", 1.5)))))
        if "bus" in refs:
            tags.append(tag("CITY BUS", "12.2 M LONG", T_of(12.2) + 0.05, T_of(12.2) + 1.6, at(ref_top("bus", 3.4))))
        if "steeple" in refs:
            tags.append(tag("CHURCH STEEPLE", "50 M", T_of(50.0) + 0.1, T_of(50.0) + 0.85,
                            at(ref_top("steeple", 50.0))))
        if "supertall" in refs:
            tags.append(tag("TALLEST BUILDING ON EARTH", "828 M", T_of(828.0) + 0.05, T_of(828.0) + 1.6,
                            at(ref_top("supertall", 828.0))))
        tags.append(tag("EVEREST'S HEIGHT", "8,849 M", T_of(EVEREST) + 0.1, T_of(EVEREST) + 1.7, at(eve)))
        tags.append(tag("AIRLINER", "35,000 FT", T_of(CRUISE * 1.6), cuts[k_pl + 1] - 0.2,
                        lambda i, x: np.array(pl_loc[i]) / s_arr[i] + cam_xyz[i]))
        tags.append(tag("SPACE STATION ORBIT", "420 KM UP", t_iss + 0.05, t_iss + 1.7,
                        lambda i, x: S + np.array([0.0, 0.0, space.ISS_ALT]) +
                        camrig.basis(cam_xyz[i], tgt_xyz[i])[1] * 0.75 * hm(x)))
        tags.append(tag("MOON, TO SCALE", "3,474 KM WIDE", t_moon_size + 0.05, t_moon_size + 1.8,
                        lambda i, x: gc[i] + np.array([0.0, 0.0, space.R_MOON])))
        t_earth = T_of(2 * space.R_EARTH)
        tags.append(tag("EARTH", "12,742 KM WIDE", t_earth + 0.1, t_earth + 1.9,
                        lambda i, x: E_c + camrig.basis(cam_xyz[i], tgt_xyz[i])[1] * space.R_EARTH * 0.2))
        k_moon = next((s_ for o, s_ in zip(opts_l, shot_i) if o.get("moon_tag")), 14)
        tags.append(tag("THE MOON", "384,400 KM AWAY", cuts[k_moon] + 0.3, cuts[k_moon + 1] - 0.1, at(M)))

    sub_box = []
    corners = np.array([[sx_ * sub["width"] / 2, sy_ * sub["length"] / 2 - sub["footprint"][2], z_]
                        for sx_ in (-1, 1) for sy_ in (-1, 1) for z_ in (0.0, sub["height"])])
    for i, x in enumerate(t):
        pts = [S + R_yaw @ (c * size[i]) for c in corners]
        prs = [camrig.project(p, cam_xyz[i], tgt_xyz[i], lens[i]) for p in pts]
        if any(p is None for p in prs):
            sub_box.append(None)
            continue
        xs_, ys_ = [p[0] for p in prs], [p[1] for p in prs]
        box = [max(min(xs_), 0), max(min(ys_), 0), min(max(xs_), 1080), min(max(ys_), 1920)]
        sub_box.append(None if box[0] >= box[2] or box[1] >= box[3] else [round(v) for v in box])

    # ---------------- HUD series and the events for the sound
    ft = size / FT
    size_ft = np.where(over, -2.0 ** 31, np.minimum(np.floor(ft + 1e-9), int_max))
    c_frac = np.linalg.norm(crown_dir) * size * math.log(2) / g.T / space.C_LIGHT * (t >= g.t0)
    events = {
        "doublings": [g.t0 + g.T * k for k in range(1, 60) if g.t0 + g.T * k < t_over],
        "hits": [round(x, 3) for x in hits],
        "cuts": [round(c, 3) for c in cuts[1:-1]],
        "hydrant": T_of(0.76), "you": T_of(1.91), "car": T_of(refs.get("car", {}).get("length", 4.75)),
        "bus": T_of(12.2),
        "wider": T_of(21.0 / (2 * fp[0]) * sub["height"]), "steeple": T_of(50.0), "tallest_building": T_of(828.0),
        "clouds": T_of((info.get("clouds") or {}).get("base") or 1700.0), "two_miles": T_of(2 * MILE),
        "everest": T_of(EVEREST), "cruise": T_of(CRUISE), "space": T_of(space.KARMAN), "iss": t_iss,
        "thousand_miles": T_of(1000 * MILE), "moon_size": t_moon_size, "earth_size": T_of(2 * space.R_EARTH),
        "fifth_c": g.time_at(0.2 * space.C_LIGHT * g.T / math.log(2) / np.linalg.norm(crown_dir)),
        "moon_hit": t_hit, "overflow": t_over, "space_from": t_space,
    }
    for name, cls in (("first_car", "car"), ("first_building", "building"), ("bus_down", "bus"),
                      ("church_down", "church"), ("supertall_down", "landmark")):
        tc_ = next((tc for tc, it in hit_items if it["cls"] == cls), None)
        if tc_ is not None:
            events[name] = tc_
    print("[grow] " + "  ".join(f"{k} {v:.2f}" for k, v in events.items() if isinstance(v, float)))
    print(f"[grow] {len(hits)} things knocked over before space; crown speed at the Moon "
          f"{np.linalg.norm(crown_dir) * s_hit * math.log(2) / g.T / space.C_LIGHT:.3f} c; shots at "
          + ", ".join(f"{c:.2f}" for c in cuts[1:-1]))
    for k in range(nshots):
        mid_t = (cuts[k] + min(cuts[k + 1], spec["render_until"])) / 2
        i = min(nf - 1, int(round(mid_t * fps)))
        t1_ = min(cuts[k + 1], spec["render_until"])
        print(f"[grow] shot {k:2d} {cuts[k]:6.2f}-{t1_:6.2f}s  subject box {sub_box[i]}  scale {s_arr[i]:.3g}  "
              f"alt {alt[i]:.0f} m")
    return {
        "fps": fps, "frames": nf,
        "size_m": [round(float(v), 4) for v in size],
        "size_ft": [float(v) for v in size_ft],
        "size_in": [float(math.floor(v / 0.0254 + 1e-6)) for v in size],
        "size_mi": [round(float(v / MILE), 5) for v in size],
        "earths": [round(float(v / (2 * space.R_EARTH)), 3) for v in size],
        "crown_c": [round(float(v), 4) for v in c_frac],
        "tags": tags, "subject_box": sub_box, "events": events,
    }
