"""Effect: a threat approaches you (the disaster POV format). Use it with the disaster_city world.

You stand on your balcony and react to something enormous coming at the city: you look down at the street, up at
the sky, flinch, turn to the fires, and it reaches you at the end (the HUD's label becomes <THREAT> / HERE). Threats:

  "meteor"  a fireball that hardly moves across the sky because it is coming your way, brightening until it
            outshines the Sun, then exploding in the air (an airburst): a flash, a fireball inside a rising
            mushroom cloud, fires breaking out block by block, people running, cars braking, the ground shaking
            (seismic waves outrun the air) with the street lamps and trees rocking, transformers blowing on the
            roofs, then the blast wave: a towering bank of dust that comes over the mountains and swallows the
            city; the windows of the buildings near you burst outward floor by floor, it throws you back, and
            the dust takes everything.
  "wave"    EXPERIMENTAL (not at the meteor's standard yet): a wall of water (needs the world's "coast") rising on
            the horizon with mist blowing off its lip, the light going green-grey, buildings going over and spray
            bursting where it hits. Reads best from higher up (a camera 50-80 m up) with a wave taller than the
            skyline (400-600 m). Check its stills hard before using it.

Physics, so the HUD and the lines can be true: the blast wave's speed comes from its free-air overpressure for the
yield (Kinney & Graham 1985) through the shock relation U = c0 sqrt(1 + 6/7 dp/p0); the meteor flies a straight line
at its entry speed; the ground shakes when the blast reaches ground zero plus the time seismic waves take through the
rock (6 km/s); no sound can arrive before the blast does. The build log prints the key moments
("[approach] times appear 0.00, flash 21.80, quake 32.38, mountains 59.15, downtown 62.56, arrive 68.50"; also in
series.json "times"): put the HUD chapters, the lines and the blackout on them, and check the lines against stills.

Spec keys (spec["effect"]), all optional unless marked:
  threat           "meteor" | "wave" (required)
  seed             random seed (which buildings topple, where the fires start, debris); each part has its own
                   stream, so tuning one part doesn't reshuffle the others
  clip             [near, far] camera clip in metres (default [0.25, 32000])
  look             where you look, smoothstep-eased between keys (a key 0.25 s after another is a flinch, 2-5 s a
                   turn of the head; aim for a new framing every few seconds): [t, yaw_deg, pitch_deg] relative to
                   the world camera (+ yaw = right, + pitch = up; the world is built for about +-20 deg of yaw), or
                   [t, "target", yaw_offset, pitch_offset] to follow something as it moves: "ahead", "street"
                   (down at the avenue), and for the meteor "meteor", "burst" (the fireball), "cloud", "front" (the
                   dust bank where it crosses your line of sight), "downtown"; for the wave "wave"
  zoom             [[t, lens_mm], ...] the focal length, eased (e.g. a push in on the meteor, out at the flash)
  shake            [[t, deg], ...] extra camera shake on top of the automatic one (flinch, quake, the blast)
  knockback        true: the blast throws you back when it arrives (a jolt, the view tips up and rolls, then
                   steadies); false to stay put
  people           {"stop_at": s, "stop_s": 1.0, "run_at": s, "run_spread_s": 3.0, "run_mps": 3.6}: people stop
                   and turn to face the threat, then run along the pavement away from it
  traffic          {"stop_at": s, "stop_s": 3.0}  cars brake to a stop
  react_radius_m   only things this close to you react when the front reaches them (default 6000)

  meteor (an airburst):
    burst   {"at": s, "distance_m": its ground distance from you, "azimuth_deg": right of your view,
             "altitude_m", "yield_mt": megatons of TNT (sets the blast wave)}                         (required)
    meteor  {"appear": s, "speed_mps": 18000, "from_altitude_m": 100000 (where it starts to glow),
             "track_deg": 10 (its ground track's angle to your line of sight: 0 = straight at you, + = from your
             right), "flares": [s, ...] (fragmentation flashes), "min_size_deg": 0.12 (its glare never looks
             smaller than this)}
    front   {"dust_height_m": 900 (the bank of dust the 100-200 mph wind behind the shock lifts; ~1300 shows it
             over the mountains sooner), "dust_lag_m": 100 (how far the dust rises behind the shock, so what the
             shock hits is seen breaking first), "dust_color": [r, g, b], "c0": 343 (the speed of sound)}
    fires   {"count": 18, "from": s, "until": s, "min_m": 450, "max_m": 2600, "sides": [[t, yaw_deg], ...]
             (fires lit from time t on are put near that direction, the nearer the likelier: where your head will
             turn)}; none in the middle of the view, where a plume would hide what is coming
    sparks  {"times": [s, ...], "sides": [[t, yaw_deg], ...], "min_m": 250, "max_m": 1500}: transformers blowing
             on rooftops, a blue-white flash that lights the walls round it
    cloud   {"top_m": 16000 (the cloud's top `rise_s` after the burst), "rise_s": 45, "radius_m": 7000}
    light   {"dust": 1.0} how much the dust and smoke warm and dim the air
  wave (needs "coast" in the world):
    wave    {"start_at": s, "from_m": its distance from you when it appears, "height_m", "speed_mps" (over the
             sea), "city_speed_mps" (ashore), "drawback_at": s (the sea pulls back first)}           (required)

Returned series (one value per frame, for the HUD; formats in post/compose.py FORMATS):
  front_m       how far the blast wave (or the water) still has to travel to reach you, metres
                ("distance_imperial" -> 14.3 mi / 900 ft)
  front_mph     its speed ("int_commas");  eta_s  seconds until it reaches you ("seconds")
  meteor_alt_m, meteor_mph, front_psi (free-air overpressure at the front), burst_m (your distance to the
  explosion), cloud_ft (the cloud's top)                                                         (meteor)
  wave_ft       the wave's height                                                                (wave)
  events        {"flash", "quake", "arrive", "collapse", "fires", "flares", "sparks", "windows", "shore"}: seconds,
                for the cue sheet ("hits" at "arrive"; sounds of anything near the front only from "arrive" on:
                no sound outruns the blast)
  times         the key moments by name (appear, flash, quake, mountains, downtown, arrive, shore, drawback)
"""
import math
import random
import zlib

import bpy
import numpy as np
from mathutils import Quaternion, Vector

import look
import rf_common as rf
from parts import nature
from worlds import disaster_city as dc

MPH = 2.2369363
FT = 3.28084
PSI = 14.696
SEISMIC = 6000.0          # m/s, P waves through the crust
VIS = 14000.0             # far things (the meteor, the explosion) are drawn this far away at their true angular size


# ---------------------------------------------------------------- small helpers

def _smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _eased(keys, t, idx=1, default=0.0):
    """A value per time from [[t, v, ...], ...] (column `idx`), smoothstep-eased between the keys."""
    if not keys:
        return np.full_like(t, default, dtype=float)
    xs = np.array([k[0] for k in keys], float)
    ys = np.array([k[idx] for k in keys], float)
    if len(xs) == 1:
        return np.full_like(t, ys[0], dtype=float)
    j = np.clip(np.searchsorted(xs, t, side="right") - 1, 0, len(xs) - 2)
    u = _smooth((t - xs[j]) / np.maximum(xs[j + 1] - xs[j], 1e-6))
    return np.where(t <= xs[0], ys[0], np.where(t >= xs[-1], ys[-1], ys[j] + (ys[j + 1] - ys[j]) * u))


def _curve(points, t, default=0.0):
    if not points:
        return np.full_like(t, default, dtype=float)
    xs, ys = zip(*points)
    return np.interp(t, xs, ys)


def _mix(a, b, s):
    s = np.asarray(s, float)[:, None]
    return np.asarray(a, float)[None, :] * (1 - s) + np.asarray(b, float)[None, :] * s


def _mix_rows(rows, color, s):
    """Per-frame colours (N x 3) blended towards one colour by s (N)."""
    s = np.asarray(s, float)[:, None]
    return np.asarray(rows, float) * (1 - s) + np.asarray(color, float)[None, :] * s


def _set(idblock, **props):
    for k, v in props.items():
        try:
            setattr(idblock, k, v)
        except (AttributeError, TypeError):
            pass


def _no_shadow(ob):
    try:
        ob.visible_shadow = False
    except AttributeError:
        pass
    return ob


def _new_mat(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return mat, nt, nt.node("ShaderNodeOutputMaterial")


def _cutout(nt, shader, alpha):
    """Hazed shader shown where alpha > 0 and see-through elsewhere. (The haze is an emission, so it has to be
    masked here: a Principled alpha alone would leave the haze glowing over the transparent parts.)"""
    mix = nt.node("ShaderNodeMixShader")
    nt.links.new(alpha, mix.inputs[0])
    nt.links.new(nt.node("ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    nt.links.new(shader, mix.inputs[2])
    return mix.outputs[0]


def _attr(nt, name, kind="OBJECT"):
    nd = nt.node("ShaderNodeAttribute", attribute_type=kind, attribute_name=name)
    return nd.outputs["Color"] if kind == "VIEW_LAYER" and name in ("rf_haze_col", "rf_haze_sun") else nd.outputs["Fac"]


def _key_vis(ob, spans):
    """Render `ob` only during the frame spans [(f0, f1), ...] (constant keys on hide_render)."""
    ob.hide_render = True
    ob.keyframe_insert("hide_render", frame=1)
    for f0, f1 in spans:
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=max(1, f0 - 1))
        ob.hide_render = False
        ob.keyframe_insert("hide_render", frame=max(1, f0))
        ob.hide_render = True
        ob.keyframe_insert("hide_render", frame=max(1, f1))
    rf.set_interpolation(ob, "CONSTANT", "hide_render")


class Ctx:
    def __init__(self, spec, info):
        self.spec, self.info = spec, info
        self.E = spec["effect"]
        self.fps = spec["fps"]
        self.nf = int(round(spec["render_until"] * self.fps))
        self.frames = np.arange(1, self.nf + 1)
        self.t = (self.frames - 1) / self.fps
        self.scene = info["scene"]
        self.world = info["world"]
        self.cam = info["camera"]
        self.cam_pos = Vector(info["cam_pos"])
        self.heading = spec["world"]["camera"]["heading_deg"]
        self.pitch = spec["world"]["camera"]["pitch_deg"]
        self.col = info["collections"]
        self.events = {}
        self.times = {}

    def f(self, t):
        return int(round(t * self.fps)) + 1

    def rng(self, name):
        """A random stream of its own for each part, so tuning one part doesn't reshuffle the others."""
        return random.Random(zlib.crc32(f"{self.E.get('seed', 7)}:{name}".encode()))

    def ground_point(self, dist, az_rel, z=0.0):
        a = math.radians(self.heading + az_rel)
        return Vector((self.cam_pos.x + dist * math.sin(a), self.cam_pos.y + dist * math.cos(a), z))

    def key(self, idblock, path, index, values):
        rf.key_series(idblock, path, index, self.frames, values)

    def key_world(self, node, values, rgb=False):
        nt = self.world.node_tree
        if rgb:
            values = np.asarray(values, float)
            for k in range(3):
                rf.key_series(nt, f'nodes["{node}"].outputs[0].default_value', k, self.frames, values[:, k])
        else:
            rf.key_series(nt, f'nodes["{node}"].outputs[0].default_value', -1, self.frames, values)

    def event(self, name, t):
        self.events.setdefault(name, []).append(round(float(t), 3))


# ---------------------------------------------------------------- materials

def _glow_mat(name, color, strength, edge=1.6, attr="fx"):
    """An additive glow sphere: bright in the middle, fading to its edge, scaled by obj[attr]."""
    mat, nt, out = _new_mat(name)
    fx = _attr(nt, attr)
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    core = nt.math("POWER", nt.math("SUBTRACT", 1.0, lw.outputs["Facing"]), edge)
    em = nt.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = rf.rgba(color)
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", core, fx), strength), em.inputs["Strength"])
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(nt.node("ShaderNodeBsdfTransparent").outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _set(mat, surface_render_method="BLENDED", use_backface_culling=False)
    return mat


def _fireball_mat(name, gain=22.0, additive=False):
    """White-hot core going yellow, orange and red as obj["heat"] (0..1.2) falls, with churning turbulence
    (obj["phase"] scrolls it). gain: emission at full heat. additive: light only, so it fades to nothing as it
    cools instead of turning into a dark ball."""
    mat, nt, out = _new_mat(name)
    heat = _attr(nt, "heat")
    tc = nt.node("ShaderNodeTexCoord")
    n = nt.node("ShaderNodeTexNoise", noise_dimensions="4D")
    n.inputs["Scale"].default_value = 2.4
    n.inputs["Detail"].default_value = 8.0
    n.inputs["Roughness"].default_value = 0.62
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    nt.links.new(_attr(nt, "phase"), n.inputs["W"])
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.45
    centre = nt.math("SUBTRACT", 1.0, lw.outputs["Facing"])
    k = nt.math("ADD", nt.math("MULTIPLY", heat, 0.85), nt.math("MULTIPLY", nt.math("SUBTRACT", n.outputs["Fac"], 0.5), 0.6))
    k = nt.math("ADD", k, nt.math("MULTIPLY", centre, 0.22))
    col = nt.ramp(k, [(0.0, (0.25, 0.04, 0.01)), (0.25, (0.85, 0.18, 0.03)), (0.5, (1.0, 0.45, 0.08)),
                      (0.75, (1.0, 0.78, 0.35)), (1.0, (1.0, 0.97, 0.9))])
    em = nt.node("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    strength = nt.math("MULTIPLY", nt.math("POWER", nt.math("ADD", heat, 0.05), 2.2), gain)
    nt.links.new(nt.math("MULTIPLY", strength, nt.math("ADD", 0.4, nt.math("MULTIPLY", n.outputs["Fac"], 0.9))),
                 em.inputs["Strength"])
    if additive:
        add = nt.node("ShaderNodeAddShader")
        nt.links.new(nt.node("ShaderNodeBsdfTransparent").outputs[0], add.inputs[0])
        nt.links.new(em.outputs[0], add.inputs[1])
        nt.links.new(add.outputs[0], out.inputs["Surface"])
        _set(mat, surface_render_method="BLENDED", use_backface_culling=True)
    else:
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def _smoke_mat(name, color=(0.30, 0.27, 0.25), glow=(1.0, 0.42, 0.12), noise_scale=4.0, fill=0.12, haze=0.9,
               glow_pow=2.0, evolve=False, shade_low=0.0, bump=0.7, dark=0.55, detail=8.0):
    """Billowing smoke or dust: lit by the sun, a fill from the sky so the shadow side never goes black, noise in the
    colour and the bumps, a soft silhouette, and a glow from below scaled by obj["heat"] (a cloud over a fire;
    glow_pow: how tightly it hugs the bottom). shade_low darkens the bottom of the object (dense, shadowed dust).
    obj["fx"] fades it in and out; with evolve, the billows boil upward through it by obj["phase"] (object units).
    Dithered transparency, so overlapping clouds sort correctly."""
    mat, nt, out = _new_mat(name)
    heat = _attr(nt, "heat")
    fx = _attr(nt, "fx")
    tc = nt.node("ShaderNodeTexCoord")
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = noise_scale
    n.inputs["Detail"].default_value = detail
    n.inputs["Roughness"].default_value = 0.62
    if evolve:
        rise = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(nt.math("MULTIPLY", _attr(nt, "phase"), -1.0), rise.inputs[2])
        drift = nt.node("ShaderNodeVectorMath", operation="ADD")
        nt.links.new(tc.outputs["Object"], drift.inputs[0])
        nt.links.new(rise.outputs[0], drift.inputs[1])
        nt.links.new(drift.outputs["Vector"], n.inputs["Vector"])
    else:
        nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    bmp = nt.node("ShaderNodeBump")
    bmp.inputs["Strength"].default_value = bump
    nt.links.new(n.outputs["Fac"], bmp.inputs["Height"])
    b = nt.node("ShaderNodeBsdfPrincipled")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    base = nt.mix_color(n.outputs["Fac"], rf.rgba(tuple(c * dark for c in color)), rf.rgba(color))
    if shade_low:
        k = nt.math("ADD", 1.0 - shade_low, nt.math("MULTIPLY", nt.math("POWER", sep.outputs["Z"], 0.6), shade_low))
        vm = nt.node("ShaderNodeVectorMath", operation="SCALE")
        nt.links.new(base, vm.inputs[0])
        nt.links.new(k, vm.inputs["Scale"])
        base = vm.outputs["Vector"]
    nt.links.new(base, b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 1.0
    nt.links.new(bmp.outputs["Normal"], b.inputs["Normal"])
    low = nt.math("POWER", nt.math("SUBTRACT", 1.0, sep.outputs["Z"]), glow_pow)
    g = nt.math("MULTIPLY", nt.math("MULTIPLY", heat, low), nt.math("ADD", 0.3, n.outputs["Fac"]))
    glowv = nt.node("ShaderNodeVectorMath", operation="SCALE")
    glowv.inputs[0].default_value = tuple(glow)
    nt.links.new(nt.math("MULTIPLY", g, 6.0), glowv.inputs["Scale"])
    fillv = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(_attr(nt, "rf_haze_col", "VIEW_LAYER"), fillv.inputs[0])
    fillv.inputs["Scale"].default_value = fill
    emc = nt.node("ShaderNodeVectorMath", operation="ADD")
    nt.links.new(glowv.outputs["Vector"], emc.inputs[0])
    nt.links.new(fillv.outputs["Vector"], emc.inputs[1])
    nt.links.new(emc.outputs["Vector"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    lw = nt.node("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.3
    edge = nt.math("SUBTRACT", 1.0, nt.math("POWER", lw.outputs["Facing"], 3.0))
    a = nt.math("MULTIPLY", nt.math("MULTIPLY", fx, edge), nt.math("ADD", 0.6, nt.math("MULTIPLY", n.outputs["Fac"], 0.9)))
    nt.links.new(_cutout(nt, rf.scene_haze(nt, b.outputs[0], haze), nt.math("MINIMUM", a, 1.0)), out.inputs["Surface"])
    _set(mat, use_backface_culling=False, use_transparent_shadow=False)
    return mat


def _trail_mat(dur):
    """The meteor's trail on a ribbon (UV u = along the path, v = across): white-hot just behind the head, cooling to
    orange, then a grey smoke trail that widens for a minute. obj["head"] = the head's u, obj["age_after"] = seconds
    since the burst."""
    mat, nt, out = _new_mat("meteor_trail")
    head = _attr(nt, "head")
    uvn = nt.node("ShaderNodeUVMap")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(uvn.outputs["UV"], sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]
    seen = nt.math("LESS_THAN", u, nt.math("ADD", head, 0.0005))
    age = nt.math("ADD", nt.math("MULTIPLY", nt.math("MAXIMUM", nt.math("SUBTRACT", head, u), 0.0), dur),
                  _attr(nt, "age_after"))
    hot = nt.math("EXPONENT", nt.math("DIVIDE", age, -0.5))
    warm = nt.math("EXPONENT", nt.math("DIVIDE", age, -3.0))
    width = nt.math("ADD", 0.16, nt.math("MULTIPLY", nt.math("MINIMUM", nt.math("DIVIDE", age, 25.0), 1.0), 0.84))
    av = nt.math("ABSOLUTE", v)
    band = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", nt.math("SUBTRACT", av, nt.math("MULTIPLY", width, 0.35)),
                                            nt.math("MULTIPLY", width, 0.65), clamp=True))
    core_band = nt.math("POWER", nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", av, 0.3, clamp=True)), 1.5)
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 3.0
    n.inputs["Detail"].default_value = 6.0
    comb = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", u, 70.0), comb.inputs[0])
    nt.links.new(nt.math("MULTIPLY", v, 1.6), comb.inputs[1])
    nt.links.new(nt.math("MULTIPLY", age, 0.04), comb.inputs[2])
    nt.links.new(comb.outputs[0], n.inputs["Vector"])
    em = nt.node("ShaderNodeEmission")
    nt.links.new(nt.mix_color(hot, (1.0, 0.42, 0.12, 1.0), (1.0, 0.92, 0.75, 1.0)), em.inputs["Color"])
    glow = nt.math("ADD", nt.math("MULTIPLY", hot, 30.0), nt.math("MULTIPLY", warm, 4.0))
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", glow, core_band), seen), em.inputs["Strength"])
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.78, 0.76, 0.74, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    fill = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(_attr(nt, "rf_haze_sun", "VIEW_LAYER"), fill.inputs[0])
    fill.inputs["Scale"].default_value = 0.45
    nt.links.new(fill.outputs["Vector"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    smoke = nt.math("MULTIPLY", nt.math("DIVIDE", nt.math("SUBTRACT", age, 1.2), 4.0, clamp=True),
                    nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", nt.math("SUBTRACT", age, 50.0), 60.0, clamp=True)))
    alpha = nt.math("MULTIPLY", nt.math("MULTIPLY", smoke, band), seen)
    alpha = nt.math("MULTIPLY", alpha, nt.math("ADD", 0.35, nt.math("MULTIPLY", n.outputs["Fac"], 0.8)))
    add = nt.node("ShaderNodeAddShader")
    nt.links.new(_cutout(nt, rf.scene_haze(nt, b.outputs[0], 0.5), nt.math("MINIMUM", alpha, 0.85)), add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    _set(mat, surface_render_method="BLENDED", use_backface_culling=False)
    return mat


# ---------------------------------------------------------------- shared geometry

def _billow_mesh(name, mat, puffs, rnd, subdiv=2, flat_base=None):
    """One mesh of lumpy spheres, puffs = [(centre xyz, radii xyz), ...]: cauliflower billows."""
    uv, uf = nature.unit_ico(subdiv)
    V, F, nv = [], [], 0
    for c, r in puffs:
        c = np.asarray(c, np.float32)
        p = uv * np.asarray(r, np.float32) + c
        phases = [(rnd.uniform(3, 6), rnd.uniform(3, 6), rnd.uniform(3, 6), rnd.uniform(0, 6.3), 0.09),
                  (rnd.uniform(8, 13), rnd.uniform(8, 13), rnd.uniform(8, 13), rnd.uniform(0, 6.3), 0.045)]
        p = nature._lumpy(p, c, float(max(r)), phases)
        if flat_base is not None:
            p[:, 2] = np.maximum(p[:, 2], flat_base)
        V.append(p)
        F.append(uf + nv)
        nv += len(p)
    return nature.mesh_from_arrays(name, np.concatenate(V), np.concatenate(F), [mat])


def _proxy(ctx, name, true_pos):
    """An empty standing in for something far away: on the camera ray at VIS metres, scaled so its children
    (modelled in true metres round true_pos) keep their true angular size."""
    c = ctx.cam_pos
    d = Vector(true_pos) - c
    k = VIS / d.length
    emp = bpy.data.objects.new(name, None)
    ctx.col["sky"].objects.link(emp)
    emp.location = c + d * k
    emp.scale = (k, k, k)
    return emp


# ---------------------------------------------------------------- the blast front

def _overpressure(R, yield_mt):
    """Free-air peak overpressure (atmospheres) at slant range R (m) from `yield_mt` megatons (Kinney & Graham)."""
    Z = np.maximum(np.asarray(R, float), 1.0) / (yield_mt * 1e9) ** (1 / 3)
    return 808.0 * (1 + (Z / 4.5) ** 2) / np.sqrt((1 + (Z / 0.048) ** 2) * (1 + (Z / 0.32) ** 2) *
                                                   (1 + (Z / 1.35) ** 2))


def _shock_speed(R, yield_mt, c0):
    return c0 * np.sqrt(1.0 + 6.0 / 7.0 * _overpressure(R, yield_mt))       # Rankine-Hugoniot, gamma 1.4


def _front_table(t0, yield_mt, c0, r_max):
    """(radius, time) of the blast front from a burst at t0, out to r_max metres."""
    dr = 2.0
    r = np.arange(0.0, r_max + dr, dr)
    tr = t0 + np.concatenate([[0.0], np.cumsum(dr / _shock_speed(r[:-1] + dr / 2, yield_mt, c0))])
    return r, tr


# ---------------------------------------------------------------- what the front does to the city

def _react_static(ctx, centre, arrive_at, push=1.0):
    """Buildings topple or crumble, trees and poles bend over, parked cars are thrown, as the front reaches each one
    (pushed away from `centre`). Returns [(t, ob, away, h, w, d)] for every building hit."""
    rnd = ctx.rng("react_static")
    react_r = ctx.E.get("react_radius_m", 6000.0)
    fps = ctx.fps
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))
    hit = []
    for ob in ctx.info["static"]:
        name = ob.name
        if not name.startswith(("bldg", "tree", "lamp", "signal", "parked")):
            continue
        p = Vector((ob.location.x, ob.location.y, 0.0))
        if (p - cam).length > react_r:
            continue
        ta = arrive_at(p.x, p.y)
        if not math.isfinite(ta) or ta > ctx.t[-1]:
            continue
        away = p - Vector((centre.x, centre.y, 0.0))
        if away.length < 1e-3:
            continue
        away.normalize()
        axis = Vector((0.0, 0.0, 1.0)).cross(away).normalized()
        f0 = ctx.f(ta)
        base = Vector(ob.location)
        if name.startswith("bldg"):
            w, d, h = ob.scale
            ext = 0.5 * (abs(away.x) * w + abs(away.y) * d)
            pivot = base + away * ext
            topple = rnd.random() < (0.45 if h > 30 else 0.25) * push
            ang_end = math.radians(rnd.uniform(55, 84) if topple else rnd.uniform(4, 14))
            sink = 1.0 if topple else rnd.uniform(0.12, 0.35)
            dur = rnd.uniform(1.4, 2.6) * (1.0 + h / 220.0)
            ob.keyframe_insert("location", frame=f0 - 1)
            ob.keyframe_insert("rotation_euler", frame=f0 - 1)
            ob.keyframe_insert("scale", frame=f0 - 1)
            for u, a, s in ((0.12, 0.08, 1.0), (0.45, 0.28, 0.97), (1.0, 1.0, sink)):
                q = Quaternion(axis, a * ang_end)
                ob.location = pivot + q @ (base - pivot)
                ob.rotation_euler = q.to_euler()
                ob.scale = (w, d, h * s)
                fr = f0 + max(1, int(round(u * dur * fps)))
                for path in ("location", "rotation_euler", "scale"):
                    ob.keyframe_insert(path, frame=fr)
            ob.location, ob.rotation_euler, ob.scale = base, (0, 0, 0), (w, d, h)
            rf.set_interpolation(ob, "BEZIER")
            hit.append((ta, ob, away, h, w, d))
        else:
            rot0 = Quaternion((0, 0, 1), ob.rotation_euler.z)
            car = name.startswith("parked")
            ang = math.radians(rnd.uniform(60, 95) if car else rnd.uniform(35, 85))
            shove = away * (rnd.uniform(8, 30) if car else 0.0)
            ob.keyframe_insert("location", frame=f0 - 1)
            ob.keyframe_insert("rotation_euler", frame=f0 - 1)
            for u, a, pp in ((0.35, 0.5, 0.4), (1.1, 1.0, 1.0)):
                q = Quaternion(axis, a * ang)
                ob.location = base + shove * pp + Vector((0, 0, 1.4 * math.sin(math.pi * pp) if car else 0.0))
                ob.rotation_euler = (q @ rot0).to_euler()
                ob.keyframe_insert("location", frame=f0 + int(round(u * fps)))
                ob.keyframe_insert("rotation_euler", frame=f0 + int(round(u * fps)))
            ob.location, ob.rotation_euler = base, rot0.to_euler()
            rf.set_interpolation(ob, "BEZIER")
    for ta, *_ in hit:
        ctx.event("collapse", ta)
    return hit


def _movers(ctx, centre, arrive_at, face=None):
    """People stop and turn to face the threat, then run (spec "people": {"stop_at", "run_at", "run_mps"}), cars
    brake to a stop ("traffic"), and both are thrown when the front reaches them. face: a point people turn to."""
    E, rnd = ctx.E, ctx.rng("movers")
    t_last = float(ctx.t[-1])
    for ob, p0, v in ctx.info["movers"]:
        person = ob.name.startswith("person")
        S = E.get("people" if person else "traffic", {})
        stop_at, stop_s = S.get("stop_at"), float(S.get("stop_s", 1.0 if person else 3.0))
        x0, y0, z = p0[0], p0[1], ob.location.z
        rot = ob.rotation_euler.copy()
        run_at = S.get("run_at") if person else None
        if run_at is not None:
            run_at = float(run_at) + rnd.uniform(0.0, float(S.get("run_spread_s", 3.0)))
            vv = Vector((v[0], v[1], 0.0))
            vdir = vv.normalized() if vv.length > 1e-6 else Vector((0.0, -1.0, 0.0))
            away0 = Vector((x0 - centre.x, y0 - centre.y, 0.0))
            run_dir = vdir if vdir.dot(away0) >= 0 else -vdir          # along the pavement, away from the threat
            run_v = float(S.get("run_mps", 3.6)) * rnd.uniform(0.8, 1.2)

        def walk(t):
            s = t
            if stop_at is not None and t > stop_at:
                u = min(t - stop_at, stop_s)
                s = stop_at + u - u * u / (2 * stop_s)
            return Vector((x0 + v[0] * s, y0 + v[1] * s, z))

        def at(t):
            if run_at is None or t <= run_at:
                return walk(t)
            u = t - run_at
            return walk(run_at) + run_dir * run_v * (u - 0.3 * (1 - math.exp(-u / 0.3)))

        ta = arrive_at(*at(t_last).xy)
        ta = arrive_at(*at(min(ta, t_last)).xy) if math.isfinite(ta) else ta
        if stop_at is None and not (math.isfinite(ta) and ta <= t_last):
            continue                       # nothing changes for this one
        ob.animation_data_clear()          # (also drops the walking bob)
        times = [0.0]
        if stop_at is not None and stop_at < t_last:
            times += [stop_at + stop_s * k / 4 for k in range(5)]
        end = ta if math.isfinite(ta) and ta <= t_last else t_last
        if run_at is not None and run_at < end:
            times += [run_at, run_at + 0.3, run_at + 0.8]
        times = sorted({round(x, 3) for x in times if x < end} | {round(end, 3)})
        for tt in times:
            ob.location = at(tt)
            ob.keyframe_insert("location", frame=ctx.f(tt))
        if person and stop_at is not None and face is not None and stop_at < end:
            p = at(stop_at)
            yaw = math.atan2(-(face.x - p.x), face.y - p.y)
            ob.rotation_euler = rot
            ob.keyframe_insert("rotation_euler", frame=ctx.f(stop_at + 0.3))
            ob.rotation_euler = (rot.x, rot.y, yaw)
            ob.keyframe_insert("rotation_euler", frame=ctx.f(min(stop_at + 1.2, end)))
            rot = ob.rotation_euler.copy()
        if run_at is not None and run_at < end:
            ob.rotation_euler = rot
            ob.keyframe_insert("rotation_euler", frame=ctx.f(run_at))
            ob.rotation_euler = (rot.x, rot.y, math.atan2(-run_dir.x, run_dir.y))
            ob.keyframe_insert("rotation_euler", frame=ctx.f(min(run_at + 0.35, end)))
            rot = ob.rotation_euler.copy()
        if math.isfinite(ta) and ta <= t_last:
            p = at(ta)
            away = Vector((p.x - centre.x, p.y - centre.y, 0.0)).normalized()
            ob.rotation_euler = rot
            ob.keyframe_insert("rotation_euler", frame=ctx.f(ta))
            dist = rnd.uniform(12, 40) if person else rnd.uniform(8, 28)
            for u, k, lift in ((0.45, 0.55, 1.0), (0.9, 1.0, 0.0)):
                ob.location = p + away * dist * k + Vector((0, 0, lift * rnd.uniform(2, 7)))
                ob.keyframe_insert("location", frame=ctx.f(ta + u))
            ob.rotation_euler = (rnd.uniform(-2.5, 2.5), rnd.uniform(-2.5, 2.5), rot.z + rnd.uniform(-2, 2))
            ob.keyframe_insert("rotation_euler", frame=ctx.f(ta + 0.9))
        rf.set_interpolation(ob, "LINEAR")


def _collapse_dust(ctx, hit, near_m=1800.0, max_n=90, color=(0.50, 0.43, 0.35), rise=1.0, name="collapse_dust"):
    """Dust billowing out of the collapsing buildings nearest to you (or, with a white colour and more rise, the
    spray thrown up where water hits them)."""
    rnd = ctx.rng(name)
    mat = _smoke_mat(name, color=color, glow=(1.0, 0.5, 0.2), noise_scale=3.0, fill=0.16)
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))
    near = [c for c in hit if (Vector((c[1].location.x, c[1].location.y, 0)) - cam).length < near_m]
    near = sorted(near, key=lambda c: (Vector((c[1].location.x, c[1].location.y, 0)) - cam).length)[:max_n]
    for ta, ob, away, h, w, d in near:
        size = max(w, d, h * 0.6)
        x, y = ob.location.x, ob.location.y
        puffs = [((rnd.uniform(-0.45, 0.45), rnd.uniform(-0.45, 0.45), rnd.uniform(0.0, 0.5)),
                  (rnd.uniform(0.5, 0.9),) * 2 + (rnd.uniform(0.4, 0.7),)) for _ in range(6)]
        p = _no_shadow(rf.add_object(name, _billow_mesh(name, mat, puffs, rnd, flat_base=-0.05), ctx.col["city"],
                                     (x, y, 0.0)))
        p["fx"] = 0.0
        p["heat"] = 0.0
        f0 = ctx.f(ta)
        for u, s, a in ((0.0, 0.05, 0.0), (0.5, 0.7, 1.0), (2.5, 1.5, 1.0), (8.0, 2.4, 0.8)):
            p.scale = (size * s, size * s, size * s * rise)
            p.location = (x + away.x * size * s * 0.5, y + away.y * size * s * 0.5, 0.0)
            p["fx"] = a
            fr = f0 + int(round(u * ctx.fps))
            p.keyframe_insert("scale", frame=fr)
            p.keyframe_insert("location", frame=fr)
            p.keyframe_insert('["fx"]', frame=fr)
        _key_vis(p, [(f0, ctx.nf + 2)])


def _rel_yaw(ctx, x, y):
    d = Vector((x - ctx.cam_pos.x, y - ctx.cam_pos.y, 0.0))
    return (math.degrees(math.atan2(d.x, d.y)) - ctx.heading + 180) % 360 - 180


def _by_side(ctx, cand, times, sides, width=13.0):
    """Order candidates so that the one used at times[i] lies near the view direction the spec's "sides"
    ([[t, yaw_deg], ...]: from time t on, prefer that side) asks for at that moment."""
    if not sides:
        return cand
    sides = sorted(sides)
    rnd = ctx.rng("sides")
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))
    left = sorted(cand, key=lambda ob: (Vector((ob.location.x, ob.location.y, 0.0)) - cam).length *
                  rnd.uniform(0.6, 1.6))
    out = []
    for tt in times:
        yaw_c = next((sd[1] for sd in reversed(sides) if sd[0] <= tt), sides[0][1])
        pick = next((ob for ob in left if abs(_rel_yaw(ctx, ob.location.x, ob.location.y) - yaw_c) < width), None)
        pick = pick or (left[0] if left else None)
        if pick is None:
            break
        left.remove(pick)
        out.append(pick)
    return out + left


def _fires(ctx, t_flash, arrive_at):
    """Fires lit by the flash across the city: a glow on the roof and a smoke column that grows and leans, until the
    front reaches it and blows it out."""
    rnd = ctx.rng("fires")
    Fi = {"count": 18, "from": t_flash + 0.5, "until": t_flash + 24.0, "min_m": 450.0, "max_m": 2600.0,
          **ctx.E.get("fires", {})}
    Fi["count"] = int(Fi["count"])
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))

    def ok(ob):
        d = Vector((ob.location.x, ob.location.y, 0)) - cam
        rel = (math.degrees(math.atan2(d.x, d.y)) - ctx.heading + 180) % 360 - 180
        # none in the middle of the view, where a plume would hide the threat coming down the avenue
        return Fi["min_m"] < d.length < Fi["max_m"] and not (abs(rel) < 9 and d.length < 2600)

    cand = [ob for ob in ctx.info["static"] if ob.name.startswith("bldg") and ob.scale[2] > 14 and ok(ob)]
    rnd.shuffle(cand)
    cand = _by_side(ctx, cand, [Fi["from"] + (Fi["until"] - Fi["from"]) * (i / max(1, int(Fi["count"]) - 1)) ** 1.5
                                for i in range(int(Fi["count"]))], Fi.get("sides"))
    smoke = _smoke_mat("fire_smoke", color=(0.11, 0.10, 0.095), glow=(1.0, 0.33, 0.06), noise_scale=5.0, fill=0.07,
                       glow_pow=9.0)
    ember_mat = _glow_mat("ember", (1.0, 0.40, 0.08), 14.0, edge=0.6)
    t = ctx.t
    n = int(Fi["count"])
    wind = math.radians(rnd.uniform(0, 360))
    for i, ob in enumerate(cand[:n]):
        t0 = Fi["from"] + (Fi["until"] - Fi["from"]) * (i / max(1, n - 1)) ** 1.5 + rnd.uniform(-0.4, 0.4)
        t_out = arrive_at(ob.location.x, ob.location.y)
        f_out = ctx.f(t_out + 0.3) if math.isfinite(t_out) else ctx.nf + 2
        w = min(ob.scale[0], ob.scale[1])
        base = (ob.location.x + rnd.uniform(-0.2, 0.2) * ob.scale[0],
                ob.location.y + rnd.uniform(-0.2, 0.2) * ob.scale[1], ob.location.z + ob.scale[2])
        mb = rf.MeshBuilder()
        for _ in range(4):
            mb.ico((rnd.uniform(-0.6, 0.6), rnd.uniform(-0.6, 0.6), 0), (rnd.uniform(0.3, 0.6),) * 2 + (0.25,), 1, 0,
                   jitter=0.3, rnd=rnd)
        ember = _no_shadow(rf.add_object("ember", mb.build("ember", [ember_mat]), ctx.col["city"], base))
        ember.scale = (w * 0.45,) * 3
        ember["fx"] = 0.0
        a = np.clip(t - t0, 0, None)
        flick = 0.8 + 0.12 * np.sin(t * 11 + i * 1.7) + 0.08 * np.sin(t * 23 + i)
        ctx.key(ember, '["fx"]', 0, (t >= t0) * np.clip(a / 2.0, 0, 1) * flick)
        _key_vis(ember, [(ctx.f(t0), f_out)])
        # the plume: narrow at the roof, widening and leaning downwind as it rises (heights in units of its top)
        lean = rnd.uniform(0.25, 0.5)
        puffs = []
        for k in range(18):
            z = (k + 0.5) / 18
            rr = 0.05 + 0.2 * z ** 0.8
            puffs.append(((lean * z ** 1.5 + rnd.uniform(-0.3, 0.3) * rr, rnd.uniform(-0.3, 0.3) * rr, z),
                          (rr * rnd.uniform(0.8, 1.25), rr * rnd.uniform(0.8, 1.25), rr * 0.75)))
        col = _no_shadow(rf.add_object("smoke_plume", _billow_mesh("smoke_plume", smoke, puffs, rnd), ctx.col["city"], base))
        col.rotation_euler = (0, 0, wind + math.radians(rnd.uniform(-15, 15)))
        col["fx"] = 0.0
        col["heat"] = 0.0
        top = np.clip(a / 18.0, 0, 1) ** 0.6 * rnd.uniform(70, 170) + 0.1
        for ax in range(3):
            ctx.key(col, "scale", ax, top)
        ctx.key(col, '["fx"]', 0, (t >= t0) * np.clip(a / 2.5, 0, 1) * 0.9)
        ctx.key(col, '["heat"]', 0, (t >= t0) * 0.5)
        _key_vis(col, [(ctx.f(t0 + 0.3), f_out)])
        ctx.event("fires", t0)


def _quake_sway(ctx, t_q, radius=650.0, dur=6.0):
    """The ground shaking: trees, street lamps and traffic signals rock, dying away over a few seconds."""
    rnd = ctx.rng("quake")
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))
    fps = ctx.fps
    for ob in ctx.info["static"]:
        if not ob.name.startswith(("tree", "lamp", "signal")):
            continue
        if (Vector((ob.location.x, ob.location.y, 0.0)) - cam).length > radius:
            continue
        r0 = ob.rotation_euler.copy()
        amp = math.radians(rnd.uniform(2.0, 4.5) if ob.name.startswith("tree") else rnd.uniform(1.5, 3.5))
        f, ph1, ph2 = rnd.uniform(1.3, 2.6), rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
        ob.keyframe_insert("rotation_euler", frame=ctx.f(t_q) - 1)
        for fr in range(ctx.f(t_q), ctx.f(t_q + dur) + 1, 2):
            a = (fr - 1) / fps - t_q
            k = amp * min(1.0, a / 0.3) * math.exp(-a / 2.2)
            ob.rotation_euler = (r0.x + k * math.sin(2 * math.pi * f * a + ph1),
                                 r0.y + k * 0.7 * math.sin(2 * math.pi * f * 1.13 * a + ph2), r0.z)
            ob.keyframe_insert("rotation_euler", frame=fr)
        ob.rotation_euler = r0
        ob.keyframe_insert("rotation_euler", frame=ctx.f(t_q + dur) + 2)
        rf.set_interpolation(ob, "BEZIER")


def _sparks(ctx, arrive_at):
    """Transformers blowing on rooftops (fire and the shaking short them out): a blue-white flash that lights the
    walls round it for a moment. spec "sparks": {"times": [s, ...], "sides": [[t, yaw], ...], "min_m", "max_m"}."""
    S = ctx.E.get("sparks", {})
    times = [float(x) for x in S.get("times", [])]
    if not times:
        return
    rnd = ctx.rng("sparks")
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))
    lo, hi = float(S.get("min_m", 250.0)), float(S.get("max_m", 1500.0))
    cand = [ob for ob in ctx.info["static"] if ob.name.startswith("bldg") and
            lo < (Vector((ob.location.x, ob.location.y, 0.0)) - cam).length < hi and
            abs(_rel_yaw(ctx, ob.location.x, ob.location.y)) < 40]
    rnd.shuffle(cand)
    cand = _by_side(ctx, cand, times, S.get("sides"))
    mat = _glow_mat("spark", (0.62, 0.84, 1.0), 45.0, edge=0.7)
    for t0, ob in zip(times, cand):
        if arrive_at(ob.location.x, ob.location.y) < t0:
            continue
        w, d, h = ob.scale
        pos = (ob.location.x + rnd.choice((-0.45, 0.45)) * w, ob.location.y + rnd.choice((-0.45, 0.45)) * d,
               ob.location.z + h + 1.0)
        mb = rf.MeshBuilder()
        mb.ico((0, 0, 0), (1, 1, 1), 2, 0, jitter=0.3, rnd=rnd)
        sp = _no_shadow(rf.add_object("spark", mb.build("spark", [mat]), ctx.col["city"], pos))
        sp.scale = (rnd.uniform(2.5, 5.0),) * 3
        sp["fx"] = 0.0
        light = bpy.data.lights.new("spark_light", "POINT")
        light.color = (0.62, 0.82, 1.0)
        _set(light, shadow_soft_size=1.0, use_shadow=False)
        lamp = bpy.data.objects.new("spark_light", light)
        ctx.col["city"].objects.link(lamp)
        lamp.location = pos
        flick = [(0.0, 0.0), (0.03, 1.0), (0.09, 0.25), (0.14, 1.3), (0.22, 0.4), (0.3, 0.9), (0.42, 0.0)]
        for dt, v in flick:
            fr = ctx.f(t0 + dt)
            sp["fx"] = v
            sp.keyframe_insert('["fx"]', frame=fr)
            light.energy = 6.0e4 * v
            light.keyframe_insert("energy", frame=fr)
        light.energy = 0.0
        light.keyframe_insert("energy", frame=ctx.f(t0) - 1)
        rf.set_interpolation(light, "LINEAR")
        _key_vis(sp, [(ctx.f(t0), ctx.f(t0 + 0.45))])
        ctx.event("sparks", t0)


def _window_glass(ctx, centre, arrive_at, near_m=330.0, max_b=28):
    """The windows of the buildings nearest to you burst outward as the front reaches them, floor after floor,
    glass flying towards you. The panes sit over the windows (the city_balcony window grid) until then."""
    rnd = ctx.rng("glass")
    cam = ctx.cam_pos
    cam2 = Vector((cam.x, cam.y, 0.0))
    mat = rf.make_material("window_glass", (0.30, 0.37, 0.44), rough=0.05, metallic=0.85,
                           emission=((0.55, 0.62, 0.68), 0.25), glitch=False)
    _set(mat, use_backface_culling=False)
    blds = [ob for ob in ctx.info["static"] if ob.name.startswith("bldg") and ob.scale[2] > 7.5 and
            (Vector((ob.location.x, ob.location.y, 0.0)) - cam2).length < near_m and
            abs(_rel_yaw(ctx, ob.location.x, ob.location.y)) < 45]          # the ones in front of you
    blds.sort(key=lambda ob: (Vector((ob.location.x, ob.location.y, 0.0)) - cam2).length)
    n_b = 0
    for ob in blds[:max_b]:
        ta = arrive_at(ob.location.x, ob.location.y)
        if not math.isfinite(ta) or ta > ctx.t[-1]:
            continue
        w, d, h = ob.scale
        cx, cy, z0 = ob.location
        x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2
        tower = ob.get("tower", 0.0) > 0.5
        lo_x, lo_y = (0.06, 0.10) if tower else (0.18, 0.28)
        faces = []
        if cam.y < y0:
            faces.append(((0, -1), y0, x0, x1))
        elif cam.y > y1:
            faces.append(((0, 1), y1, x0, x1))
        if cam.x < x0:
            faces.append(((-1, 0), x0, y0, y1))
        elif cam.x > x1:
            faces.append(((1, 0), x1, y0, y1))
        verts, ends, floor_of = [], [], []
        floors = int((z0 + h) // 3.4)
        for (nx, ny), at, u0, u1 in faces:
            nrm = Vector((nx, ny, 0.0))
            along = Vector((abs(ny), abs(nx), 0.0))
            for cu in range(int(math.floor(u0 / 3.2)), int(math.ceil(u1 / 3.2))):
                ua, ub = 3.2 * (cu + lo_x), 3.2 * (cu + 1 - lo_x)
                if ua < u0 + 0.3 or ub > u1 - 0.3:
                    continue
                for fl in range(2, floors):
                    za, zb = 3.4 * (fl + lo_y), 3.4 * (fl + 0.88)
                    if za < 4.2 or zb > z0 + h - 0.4:
                        continue

                    def pt(u, z):
                        base = Vector((u, at, z)) if nx == 0 else Vector((at, u, z))
                        return base + nrm * 0.06
                    um, zm = rnd.uniform(ua + 0.3, ub - 0.3), rnd.uniform(za + 0.3, zb - 0.3)
                    corners = [(ua, za), (ub, za), (ub, zb), (ua, zb)]
                    for k in range(4):                          # four shards meeting at a random point
                        tri = [pt(*corners[k]), pt(*corners[(k + 1) % 4]), pt(um, zm)]
                        c = (tri[0] + tri[1] + tri[2]) / 3
                        fly = nrm * rnd.uniform(14, 40) + along * rnd.uniform(-7, 7) + \
                            Vector((0, 0, rnd.uniform(-1.0, 4.0) - rnd.uniform(4.0, 8.5)))
                        spin = Quaternion(Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))).normalized(),
                                          rnd.uniform(2, 10))
                        for v in tri:
                            verts.append(v)
                            ends.append(c + fly + spin @ (v - c))
                            floor_of.append(fl)
        if not verts:
            continue
        mb = rf.MeshBuilder()
        mb.verts = [tuple(v) for v in verts]
        mb.faces = [(i, i + 1, i + 2) for i in range(0, len(verts), 3)]
        mb.mats = [0] * len(mb.faces)
        g = _no_shadow(rf.add_object("window_glass", mb.build("window_glass", [mat]), ctx.col["city"]))
        g.shape_key_add(name="Basis")
        top = max(floor_of)
        bands = {}
        for i, fl in enumerate(floor_of):
            bands.setdefault((top - fl) // 2, []).append(i)
        for band, idx in sorted(bands.items()):
            sk = g.shape_key_add(name=f"burst_{band}")
            for i in idx:
                sk.data[i].co = ends[i]
            t0 = ta + 0.04 + 0.035 * band                       # floor after floor, from the top down
            sk.value = 0.0
            sk.keyframe_insert("value", frame=ctx.f(t0))
            sk.value = 1.0
            sk.keyframe_insert("value", frame=ctx.f(t0 + 1.3))
        rf.set_interpolation(g.data.shape_keys, "LINEAR")
        _key_vis(g, [(1, ctx.f(ta + 0.04 + 0.035 * max(bands) + 1.3))])
        ctx.event("windows", ta)
        n_b += 1
    return n_b


def _debris(ctx, centre, arrive):
    """As it hits you: glass, grit and chunks flying past the balcony at wind speed."""
    rnd = ctx.rng("debris")
    cam = ctx.cam_pos
    away = (Vector((cam.x, cam.y, 0)) - Vector((centre.x, centre.y, 0))).normalized()
    side = Vector((away.y, -away.x, 0.0))
    mats = [rf.make_material("debris_grit", (0.30, 0.26, 0.22), rough=0.9, glitch=False),
            rf.make_material("debris_glass", (0.55, 0.60, 0.65), rough=0.15, metallic=0.4, glitch=False)]
    mb = rf.MeshBuilder()
    end = []
    for _ in range(360):
        d = rnd.uniform(3, 45)
        p = cam - away * d + side * rnd.uniform(-1, 1) * (d * 0.7 + 3) + Vector((0, 0, rnd.uniform(-14, 9)))
        s = rnd.uniform(0.04, 0.5) * (1 + d / 30)
        m = 0 if rnd.random() < 0.65 else 1
        b = len(mb.verts)
        mb.box(p.x - s * 0.5, p.y - s * 0.3, p.z - s * 0.08, p.x + s * 0.5, p.y + s * 0.3, p.z + s * 0.08, m)
        fly = away * rnd.uniform(35, 70) + side * rnd.uniform(-12, 12) + Vector((0, 0, rnd.uniform(-6, 10)))
        spin = Quaternion(Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))).normalized(),
                          rnd.uniform(2, 9))
        for vi in range(b, len(mb.verts)):
            v = Vector(mb.verts[vi])
            end.append(tuple(p + fly + spin @ (v - p)))
    ob = _no_shadow(rf.add_object("debris", mb.build("debris", mats), ctx.col["life"]))
    ob.shape_key_add(name="Basis")
    sk = ob.shape_key_add(name="blown")
    for k, co in enumerate(end):
        sk.data[k].co = co
    f0 = ctx.f(arrive - 0.05)
    sk.value = 0.0
    sk.keyframe_insert("value", frame=f0)
    sk.value = 1.0
    sk.keyframe_insert("value", frame=f0 + int(0.8 * ctx.fps))
    _key_vis(ob, [(f0, ctx.nf + 2)])


def _balcony_hit(ctx, centre, arrive):
    """Your mug goes flying when the front hits."""
    mug = bpy.data.objects.get("mug")
    if not mug:
        return
    cam = ctx.cam_pos
    away = (Vector((cam.x, cam.y, 0)) - Vector((centre.x, centre.y, 0))).normalized()
    f0 = ctx.f(arrive)
    base = Vector(mug.location)
    mug.keyframe_insert("location", frame=f0 - 1)
    mug.keyframe_insert("rotation_euler", frame=f0 - 1)
    mug.location = base + away * 5.0 + Vector((0, 0, 1.2))
    mug.rotation_euler = (2.5, 1.0, mug.rotation_euler.z + 2.0)
    mug.keyframe_insert("location", frame=f0 + int(0.5 * ctx.fps))
    mug.keyframe_insert("rotation_euler", frame=f0 + int(0.5 * ctx.fps))
    mug.location = base
    rf.set_interpolation(mug, "LINEAR")


def _front_times(ctx, arrive_at):
    """When the front crosses the mountains and downtown (for writing the lines)."""
    for key, prefix in (("mountains", "mountain_"), ("downtown", "bldg")):
        obs = [ob for ob in ctx.info["static"] if ob.name.startswith(prefix)]
        if key == "downtown":
            obs = [ob for ob in obs if ob.get("tower", 0.0) > 0.5]
        ts = [arrive_at(ob.location.x, ob.location.y) for ob in obs]
        ts = [x for x in ts if math.isfinite(x)]
        if ts:
            ctx.times[key] = round(float(np.median(ts)), 2)


# ---------------------------------------------------------------- camera

def _dir_angles(ctx, vecs):
    """(yaw, pitch) in degrees, relative to the world camera, for direction vectors (N x 3)."""
    v = np.asarray(vecs, float)
    yaw = np.degrees(np.arctan2(v[:, 0], v[:, 1])) - ctx.heading
    yaw = (yaw + 180.0) % 360.0 - 180.0
    pitch = np.degrees(np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1]))) - ctx.pitch
    return yaw, pitch


def _camera(ctx, shake_deg, targets=None, knock=None):
    """Your head. spec "look": [[t, yaw, pitch], ...] or [[t, "target", yaw_offset, pitch_offset], ...] with a named
    target that is followed as it moves ("ahead", "street", and what the threat adds: "meteor", "burst", "cloud",
    "front", "downtown", ...); smoothstep-eased between keys, so a key 0.25 s after another is a flinch and one 5 s
    later a slow turn. "zoom": [[t, lens_mm], ...]. Plus shake (degrees per frame) and, at `knock` (seconds), being
    thrown back by the blast: the camera jolts back and down, tips up and rolls, then partly recovers."""
    E = ctx.E
    cam = ctx.cam
    base = Vector(cam.rotation_euler)
    t = ctx.t
    n = len(t)
    named = {"ahead": (np.zeros(n), np.zeros(n)), "street": (np.zeros(n), np.full(n, -16.0))}
    for name, vecs in (targets or {}).items():
        named[name] = _dir_angles(ctx, vecs)
    keys = []
    for k in E.get("look", []):
        if len(k) > 1 and isinstance(k[1], str):
            if k[1] not in named:
                raise ValueError(f"look: unknown target {k[1]!r} (targets here: {', '.join(sorted(named))})")
            y, pt = named[k[1]]
            keys.append((float(k[0]), y + (k[2] if len(k) > 2 else 0.0), pt + (k[3] if len(k) > 3 else 0.0)))
        else:
            keys.append((float(k[0]), np.full(n, float(k[1])), np.full(n, float(k[2]))))
    yaw, pit = np.zeros(n), np.zeros(n)
    if keys:
        keys.sort(key=lambda kk: kk[0])
        yaw, pit = keys[0][1].copy(), keys[0][2].copy()
        for (ta, ya, pa), (tb, yb, pb) in zip(keys, keys[1:]):
            m = t >= ta
            u = _smooth((t - ta) / max(tb - ta, 1e-6))
            yaw = np.where(m, ya + (yb - ya) * u, yaw)
            pit = np.where(m, pa + (pb - pa) * u, pit)
    rng = np.random.default_rng(E.get("seed", 7))
    ph = rng.uniform(0, 6.28, 6)
    jx = np.sin(t * 13.7 + ph[0]) + 0.6 * np.sin(t * 23.1 + ph[1]) + 0.35 * np.sin(t * 41.3 + ph[2])
    jz = np.sin(t * 11.9 + ph[3]) + 0.6 * np.sin(t * 19.7 + ph[4]) + 0.35 * np.sin(t * 37.9 + ph[5])
    hand = 0.05 * np.sin(t * 0.9 + ph[0]) + 0.035 * np.sin(t * 1.7 + ph[1])        # breathing, a hand-held drift
    shake = shake_deg + _curve([tuple(p) for p in E.get("shake", [])], t)
    roll = np.zeros(n)
    if knock is not None:
        a = np.clip(t - knock, 0, None)
        hit = (t >= knock) * (1 - np.exp(-a / 0.07))
        settle = 1.0 - 0.55 * _smooth((a - 0.25) / 0.8)
        pit = pit + 22.0 * hit * settle
        yaw = yaw + 6.0 * hit * settle
        roll = 11.0 * hit * settle
        fwd = Vector((math.sin(math.radians(ctx.heading)), math.cos(math.radians(ctx.heading)), 0.0))
        back = 0.55 * hit * (1 - 0.3 * _smooth((a - 0.25) / 0.8))          # thrown back against the doorway
        p0 = Vector(cam.location)
        for k, (off, down) in enumerate(((fwd.x, 0.0), (fwd.y, 0.0), (0.0, 1.0))):
            ctx.key(cam, "location", k, p0[k] - off * back - down * 0.25 * hit)
    ctx.key(cam, "rotation_euler", 0, base.x + np.radians(pit + shake * jx * 0.5 + hand))
    ctx.key(cam, "rotation_euler", 1, base.y + np.radians(roll + shake * 0.25 * np.sin(t * 17.3 + ph[2])))
    ctx.key(cam, "rotation_euler", 2, base.z + np.radians(-yaw + shake * jz * 0.5 + 0.7 * hand))
    if E.get("zoom"):
        ctx.key(cam.data, "lens", -1, _eased(E["zoom"], t, 1, cam.data.lens))


# ---------------------------------------------------------------- METEOR

def _meteor(ctx):
    E = ctx.E
    B, M = E["burst"], E.get("meteor", {})
    F = {"dust_height_m": 900.0, "dust_lag_m": 100.0, "c0": 343.0, **E.get("front", {})}
    t = ctx.t
    t_b, h_b = float(B["at"]), float(B["altitude_m"])
    yield_mt = float(B.get("yield_mt", 50.0))
    burst = ctx.ground_point(B["distance_m"], B.get("azimuth_deg", 0.0), h_b)
    G = Vector((burst.x, burst.y, 0.0))
    cam = ctx.cam_pos
    slant = (burst - cam).length
    x_cam = (Vector((cam.x, cam.y, 0.0)) - G).length

    # ---- the meteor's straight path at its entry speed, from where it starts to glow to the burst
    t_on = float(M.get("appear", 0.0))
    speed = float(M.get("speed_mps", 18000.0))
    alt0 = float(M.get("from_altitude_m", 100000.0))
    path = speed * (t_b - t_on)
    drop = alt0 - h_b
    if path <= drop:
        raise ValueError(f"meteor: {speed:.0f} m/s for {t_b - t_on:.1f} s covers {path / 1000:.0f} km, less than the "
                         f"{drop / 1000:.0f} km drop; start it earlier or higher, or make it faster")
    hor = math.sqrt(path * path - drop * drop)
    a_tr = math.radians(ctx.heading + B.get("azimuth_deg", 0.0) + M.get("track_deg", 10.0))
    S = burst + Vector((hor * math.sin(a_tr), hor * math.cos(a_tr), drop))
    tau = np.clip((t - t_on) / (t_b - t_on), 0.0, 1.0)
    P = np.array(S)[None, :] + (np.array(burst) - np.array(S))[None, :] * tau[:, None]
    ctx.times.update({"appear": t_on, "flash": t_b})
    print(f"[approach] meteor {path / 1000:.0f} km at {speed / 1000:.1f} km/s ({speed * MPH:,.0f} mph), entry angle "
          f"{math.degrees(math.asin(drop / path)):.1f} deg, burst {slant / 1000:.1f} km from you "
          f"({x_cam / 1000:.1f} km over the ground, {h_b / 1000:.1f} km up), {yield_mt:g} Mt")

    bright, flare = _meteor_head(ctx, P, t_on, t_b)
    _trail(ctx, S, burst, t_on, t_b, tau)
    _burst(ctx, burst, t_b)

    # ---- the blast wave
    r, tr = _front_table(t_b, yield_mt, F["c0"], slant + 6000.0)
    R = np.where(t >= t_b, np.interp(t, tr, r), 0.0)
    arrive = float(np.interp(slant, r, tr))
    quake = float(np.interp(h_b, r, tr)) + x_cam / SEISMIC

    def arrive_at(px, py):
        return float(np.interp(math.hypot(math.hypot(px - G.x, py - G.y), h_b), r, tr, right=float("inf")))

    ctx.times.update({"quake": round(quake, 2), "arrive": round(arrive, 2)})
    ctx.event("flash", t_b)
    ctx.event("quake", quake)
    ctx.event("arrive", arrive)
    _dust_front(ctx, G, np.sqrt(np.maximum(R * R - h_b * h_b, 0.0)), F)
    hit = _react_static(ctx, G, arrive_at)
    _front_times(ctx, arrive_at)
    _movers(ctx, G, arrive_at, face=burst)
    _collapse_dust(ctx, hit)
    _fires(ctx, t_b, arrive_at)
    _quake_sway(ctx, quake)
    _sparks(ctx, arrive_at)
    _window_glass(ctx, G, arrive_at)
    _debris(ctx, G, arrive)
    _balcony_hit(ctx, G, arrive)
    _meteor_light(ctx, t_b, burst, P, bright, flare, arrive + F["dust_lag_m"] / F["c0"], t_on)

    # ---- your head: a flinch at the flash, the ground shaking, the blast
    a = np.clip(t - t_b, 0, None)
    shake = 0.5 * np.exp(-a / 0.5) * (t >= t_b)                                        # the flinch
    q = np.clip(t - quake, 0, None)
    shake += 0.55 * _smooth(q / 0.4) * np.exp(-q / 4.0) * (t >= quake)                 # the ground arrives first
    togo = np.maximum(slant - R, 0.0)
    shake += 0.5 * np.clip(1.0 - togo / 1500.0, 0, 1) ** 2 * (t < arrive)              # buildings falling nearby
    shake += 3.2 * np.exp(-np.clip(t - arrive, 0, None) / 0.5) * (t >= arrive)         # it hits you
    _camera(ctx, shake, _meteor_targets(ctx, P, burst, G, np.sqrt(np.maximum(R * R - h_b * h_b, 0.0)), F, x_cam),
            knock=arrive if ctx.E.get("knockback", True) else None)

    return {
        "meteor_alt_m": [float(z) for z in np.where(t < t_b, P[:, 2], h_b)],
        "meteor_mph": [round(speed * MPH)] * ctx.nf,
        "front_m": [float(v) for v in togo],
        "front_mph": [float(v) for v in np.where(t >= t_b, _shock_speed(np.maximum(R, 1.0), yield_mt, F["c0"]) * MPH, 0.0)],
        "front_psi": [float(v) for v in np.where(t >= t_b, _overpressure(np.maximum(R, 1.0), yield_mt) * PSI, 0.0)],
        "eta_s": [float(v) for v in np.maximum(arrive - t, 0.0)],
        "burst_m": [float(slant)] * ctx.nf,
        "cloud_ft": [float(v * FT) for v in _cloud_top(ctx, t_b, h_b)],
    }


def _meteor_targets(ctx, P, burst, G, x, F, x_cam):
    """Things to look at, as directions from you per frame: the meteor, the fireball, the cloud, the dust front
    (the middle of the bank where it crosses your line of sight) and downtown."""
    cam = np.array(ctx.cam_pos)
    t = ctx.t
    C = ctx.E.get("cloud", {})
    top, rise = float(C.get("top_m", 16000.0)), float(C.get("rise_s", 45.0))
    h_b = burst.z
    t_b = float(ctx.E["burst"]["at"])
    grow = np.where(t >= t_b, 1 - (1 - np.clip((t - t_b) / rise, 0, 1)) ** 2, 0.0)
    lift = (top - h_b - 1500.0) * grow
    b = np.array(burst)
    fireball = b[None, :] + np.stack([np.zeros_like(t), np.zeros_like(t), 400.0 + lift * 0.95], 1)
    cloud = b[None, :] + np.stack([np.zeros_like(t), np.zeros_like(t), 600.0 + lift], 1)
    to_g = np.array((G.x - cam[0], G.y - cam[1], 0.0)) / x_cam
    dist = np.maximum(x_cam - x, 1.0) + 350.0
    H = F["dust_height_m"] * (0.45 + 0.55 * _smooth(x / 9000.0))
    front = cam[None, :] + to_g[None, :] * dist[:, None]
    front[:, 2] = 0.42 * H
    downtown = np.array(ctx.info.get("downtown", (250.0, 2400.0, 120.0)))
    return {"meteor": P - cam[None, :], "burst": fireball - cam[None, :], "cloud": cloud - cam[None, :],
            "front": front - cam[None, :], "downtown": np.tile(downtown - cam, (len(t), 1))}


def _meteor_head(ctx, P, t_on, t_b):
    """The glowing head (a hot core in a glare), drawn at VIS metres along your line of sight at its true angular
    size (never smaller than min_size_deg), brightening as it comes, flaring as it breaks up, with fragments
    peeling off. Returns its brightness (0..1) and the flares per frame."""
    M = ctx.E.get("meteor", {})
    t = ctx.t
    cam = np.array(ctx.cam_pos)
    d = P - cam[None, :]
    dist = np.linalg.norm(d, axis=1)
    dirs = d / dist[:, None]
    vis = cam[None, :] + dirs * VIS
    bright = _smooth((t - t_on) / (t_b - t_on)) ** 1.6
    surge = _smooth((t - (t_b - 2.6)) / 2.6) ** 2                     # the last seconds: brighter than the Sun
    flare = np.zeros_like(t)
    for fl in M.get("flares", []):
        flare += np.exp(-np.abs(t - fl) / 0.16) * (t > fl - 0.3)
        ctx.event("flares", fl)
    true_r = 150.0 + 350.0 * bright ** 2 + 300.0 * surge + 400.0 * flare     # the glowing plasma, metres
    min_r = VIS * math.tan(math.radians(M.get("min_size_deg", 0.12)))
    r_vis = np.maximum(true_r * VIS / dist, min_r * (1 + 0.5 * bright))
    glare = 0.45 + 1.2 * bright + 1.8 * surge + 2.2 * flare
    on = [(ctx.f(t_on), ctx.f(t_b) + 1)]
    # a white-hot core in three layers of glare, so it fades smoothly into the sky like a light too bright to look at
    layers = (("meteor_core", _fireball_mat("meteor_core", gain=45.0), 1.0, None),
              ("meteor_glare_1", _glow_mat("meteor_glare_1", (1.0, 0.9, 0.75), 2.2, edge=3.0), 2.4, 1.0),
              ("meteor_glare_2", _glow_mat("meteor_glare_2", (1.0, 0.72, 0.45), 0.55, edge=3.5), 6.0, 1.0),
              ("meteor_glare_3", _glow_mat("meteor_glare_3", (1.0, 0.62, 0.36), 0.12, edge=4.0), 15.0, 0.8))
    for name, mat, mul, k_fx in layers:
        mb = rf.MeshBuilder()
        mb.ico((0, 0, 0), (1, 1, 1), 3, 0)
        ob = _no_shadow(rf.add_object(name, mb.build(name, [mat]), ctx.col["sky"]))
        for k in range(3):
            ctx.key(ob, "location", k, vis[:, k])
            ctx.key(ob, "scale", k, r_vis * mul * (1.0 if k_fx is None else 1.0 + 0.25 * surge))
        if k_fx is None:
            ob["heat"] = 1.0
            ob["phase"] = 0.0
            ctx.key(ob, '["heat"]', 0, np.clip(0.75 + 0.3 * bright + 0.3 * flare, 0, 1.25))
            ctx.key(ob, '["phase"]', 0, t * 3.0)
        else:
            ob["fx"] = 0.0
            ctx.key(ob, '["fx"]', 0, glare * k_fx)
        _key_vis(ob, on)
    # fragments: small glows that split off at each flare and drift away from the head, fading
    frag_mat = _glow_mat("meteor_fragment", (1.0, 0.7, 0.4), 6.0, edge=0.9)
    rnd = ctx.rng("meteor_head")
    for fl in M.get("flares", []):
        for _ in range(3):
            mb = rf.MeshBuilder()
            mb.ico((0, 0, 0), (1, 1, 1), 2, 0)
            ob = _no_shadow(rf.add_object("meteor_fragment", mb.build("meteor_fragment", [frag_mat]), ctx.col["sky"]))
            side = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-0.6, 0.6)))
            dt = np.clip(t - fl, 0, None)
            off = np.array(side)[None, :] * (dt * VIS * math.radians(rnd.uniform(0.25, 0.7)))[:, None]
            pos = vis + off
            for k in range(3):
                ctx.key(ob, "location", k, pos[:, k])
                ctx.key(ob, "scale", k, r_vis * rnd.uniform(0.6, 1.1))
            ob["fx"] = 0.0
            ctx.key(ob, '["fx"]', 0, 2.5 * np.exp(-dt / 1.2) * (t >= fl))
            _key_vis(ob, [(ctx.f(fl), min(ctx.f(fl + 4.0), ctx.f(t_b) + 1))])
    return np.clip(bright + surge, 0, 1.5), flare


def _trail(ctx, S, B, t_on, t_b, tau):
    """The trail: a ribbon along the path as you see it (projected to VIS metres), hot right behind the head and a
    smoke trail left behind that lingers and widens after the burst."""
    cam = ctx.cam_pos
    n = 300
    us = np.linspace(0.0, 1.0, n)
    P = [S + (B - S) * float(u) for u in us]
    Q = [cam + (p - cam).normalized() * VIS for p in P]
    mb = rf.MeshBuilder()
    for i in range(n):
        tng = (Q[min(i + 1, n - 1)] - Q[max(i - 1, 0)]).normalized()
        side = tng.cross((Q[i] - cam).normalized()).normalized()
        w = 1600.0 * VIS / (P[i] - cam).length                       # the smoke trail widens to ~1.6 km (true)
        mb.verts += [tuple(Q[i] - side * w), tuple(Q[i] + side * w)]
    for i in range(n - 1):
        b = 2 * i
        mb.faces.append((b, b + 2, b + 3, b + 1))
        mb.mats.append(0)
    me = mb.build("meteor_trail", [_trail_mat(t_b - t_on)])
    uv = me.uv_layers.new(name="UVMap")
    loop_uv = []
    for poly in me.polygons:
        for li in poly.loop_indices:
            i, s = divmod(me.loops[li].vertex_index, 2)
            loop_uv += [float(us[i]), -1.0 if s == 0 else 1.0]
    uv.data.foreach_set("uv", loop_uv)
    ob = _no_shadow(rf.add_object("meteor_trail", me, ctx.col["sky"]))
    ob["head"] = 0.0
    ob["age_after"] = 0.0
    ctx.key(ob, '["head"]', 0, tau)
    ctx.key(ob, '["age_after"]', 0, np.maximum(ctx.t - t_b, 0.0))
    _key_vis(ob, [(ctx.f(t_on), ctx.nf + 2)])


def _cloud_top(ctx, t_b, h_b):
    C = ctx.E.get("cloud", {})
    top, rise = float(C.get("top_m", 16000.0)), float(C.get("rise_s", 45.0))
    s = np.clip((ctx.t - t_b) / rise, 0, 1)
    return np.where(ctx.t >= t_b, h_b + 1500.0 + (top - h_b - 1500.0) * (1 - (1 - s) ** 2), 0.0)


def _burst(ctx, Bp, t_b):
    """The fireball, the shock's condensation shell, and the cloud that rises and spreads (a billowing cap over a
    dusty stem), modelled in true metres round the burst and drawn through a proxy at VIS metres."""
    rnd = ctx.rng("burst")
    t = ctx.t
    C = ctx.E.get("cloud", {})
    top, rise, rad = float(C.get("top_m", 16000.0)), float(C.get("rise_s", 45.0)), float(C.get("radius_m", 7000.0))
    h_b = Bp.z
    emp = _proxy(ctx, "burst_proxy", Bp)
    a = np.clip(t - t_b, 0, None)
    after = t >= t_b
    grow = 1 - (1 - np.clip(a / rise, 0, 1)) ** 2
    lift = (top - h_b - 1500.0) * grow
    # fireball
    mb = rf.MeshBuilder()
    mb.ico((0, 0, 0), (1, 1, 1), 4, 0)
    fb = _no_shadow(rf.add_object("fireball", mb.build("fireball", [_fireball_mat("burst_fireball", gain=14.0,
                                                                                    additive=True)]), ctx.col["sky"]))
    fb.parent = emp
    radius = np.where(after, 2400.0 * (1 - np.exp(-a / 0.5)) + 30.0 * a, 1.0)
    for k, m in ((0, 1.0), (1, 1.0), (2, 0.9)):
        ctx.key(fb, "scale", k, radius * m)
    ctx.key(fb, "location", 2, 400.0 + lift * 0.95)          # it rises inside the cloud it makes
    fb["heat"] = 0.0
    fb["phase"] = 0.0
    ctx.key(fb, '["heat"]', 0, np.where(after, np.clip(1.2 * np.exp(-a / 4.0) + 0.3 * np.exp(-a / 22.0), 0, 1.2), 0.0))
    ctx.key(fb, '["phase"]', 0, t * 0.3)
    _key_vis(fb, [(ctx.f(t_b), ctx.f(t_b + 45))])
    # condensation shell racing outward with the shock, gone in a few seconds
    mb = rf.MeshBuilder()
    mb.ico((0, 0, 0), (1, 1, 1), 4, 0)
    shell = _no_shadow(rf.add_object("shock_shell", mb.build("shock_shell", [_glow_mat("shock_shell", (0.95, 0.93, 0.9), 1.8, edge=3.5)]),
                                     ctx.col["sky"]))
    shell.parent = emp
    sr = np.where(after, 1200.0 + 5200.0 * (1 - np.exp(-a / 1.3)), 1.0)
    for k in range(3):
        ctx.key(shell, "scale", k, sr)
    shell["fx"] = 0.0
    ctx.key(shell, '["fx"]', 0, np.where(t >= t_b + 0.3, np.exp(-(a - 0.3) / 1.0), 0.0))
    _key_vis(shell, [(ctx.f(t_b + 0.3), ctx.f(t_b + 4.5))])
    # the cloud
    smoke = _smoke_mat("burst_cloud", color=(0.19, 0.16, 0.14), glow=(1.0, 0.36, 0.08), noise_scale=2.6, fill=0.08,
                       haze=0.25, shade_low=0.5, bump=1.0, evolve=True)
    cap_puffs = []
    for _ in range(40):
        ang = rnd.uniform(0, 6.28)
        rr = rnd.uniform(0.1, 1.0) ** 0.6
        cap_puffs.append(((math.cos(ang) * rr, math.sin(ang) * rr, rnd.uniform(-0.2, 0.35) + 0.25 * (1 - rr)),
                          (rnd.uniform(0.28, 0.5),) * 2 + (rnd.uniform(0.25, 0.42),)))
    for _ in range(26):                                # the rolling ring under the cap's rim
        ang = rnd.uniform(0, 6.28)
        cap_puffs.append(((math.cos(ang) * 0.95, math.sin(ang) * 0.95, rnd.uniform(-0.45, -0.25)),
                          (rnd.uniform(0.2, 0.3),) * 3))
    cap = _no_shadow(rf.add_object("cloud_cap", _billow_mesh("cloud_cap", smoke, cap_puffs, rnd, subdiv=3), ctx.col["sky"]))
    cap.parent = emp
    stem_puffs = []
    for z in np.linspace(0.02, 0.96, 22):
        w = 0.42 - 0.16 * min(z / 0.4, 1.0) + 0.1 * max(0.0, (z - 0.8) / 0.2)      # wide at the foot and the top
        k = w * rnd.uniform(0.8, 1.15)
        stem_puffs.append(((rnd.uniform(-0.12, 0.12), rnd.uniform(-0.12, 0.12), z), (k, k, k * 0.3)))
    stem = _no_shadow(rf.add_object("cloud_stem", _billow_mesh("cloud_stem", smoke, stem_puffs, rnd), ctx.col["sky"]))
    stem.parent = emp
    cap_z = np.where(after, 600.0 + lift, 0.0)
    ctx.key(cap, "location", 2, cap_z)
    for k, v in ((0, 1800.0 + (rad - 1800.0) * grow ** 0.8), (1, 1800.0 + (rad - 1800.0) * grow ** 0.8),
                 (2, 1500.0 + 2600.0 * grow)):
        ctx.key(cap, "scale", k, np.where(after, v, 1.0))
    cap["fx"] = 0.0
    cap["heat"] = 0.0
    cap["phase"] = 0.0
    ctx.key(cap, '["phase"]', 0, t * 0.012)
    ctx.key(cap, '["fx"]', 0, np.clip((t - t_b - 1.0) / 2.5, 0, 1))
    ctx.key(cap, '["heat"]', 0, np.where(after, 1.3 * np.exp(-np.clip(a - 1.0, 0, None) / 4.5) + 0.03, 0.0))
    ctx.key(stem, "location", 2, np.full_like(t, -h_b))
    ctx.key(stem, "scale", 2, np.maximum(cap_z + h_b, 1.0))
    sw = np.where(after, 900.0 + 2200.0 * grow, 1.0)
    ctx.key(stem, "scale", 0, sw)
    ctx.key(stem, "scale", 1, sw)
    stem["fx"] = 0.0
    stem["heat"] = 0.0
    stem["phase"] = 0.0
    ctx.key(stem, '["phase"]', 0, t * 0.03)
    ctx.key(stem, '["fx"]', 0, np.clip((t - t_b - 5.0) / 9.0, 0, 1) * 0.9)
    ctx.key(stem, '["heat"]', 0, np.where(after, 0.3 * np.exp(-np.clip(a - 5, 0, None) / 6.0), 0.0))
    _key_vis(cap, [(ctx.f(t_b + 0.8), ctx.nf + 2)])
    _key_vis(stem, [(ctx.f(t_b + 4.5), ctx.nf + 2)])


def _dust_front(ctx, centre, x, F, start_m=500.0):
    """The front near you: a towering bank of billowing dust (the 100-200 mph wind behind the shock lifts the
    ground's dust and the wreckage) along the front's arc, riding F["dust_lag_m"] behind the shock's radius on the
    ground (x per frame), so what the shock hits is seen breaking a moment before the dust swallows it. The arc's
    radius is your distance from `centre`; its height grows as it spreads. Dithered, so buildings disappear into it
    and it engulfs you at the end."""
    rnd = ctx.rng("dust_front")
    cam = Vector((ctx.cam_pos.x, ctx.cam_pos.y, 0.0))
    to_cam = cam - Vector((centre.x, centre.y, 0.0))
    R0 = to_cam.length
    a_cam = math.atan2(to_cam.y, to_cam.x)
    H = F["dust_height_m"]
    half = min(7500.0 / R0, 0.6)
    color = F.get("dust_color", (0.36, 0.28, 0.20))
    mat = _smoke_mat("dust_front", color=color, glow=(1.0, 0.5, 0.2), noise_scale=1 / 45.0, fill=0.08, haze=0.45,
                     shade_low=0.5, bump=1.4, dark=0.32, detail=4.0, evolve=True)
    mat_close = _smoke_mat("dust_front_close", color=color, glow=(1.0, 0.5, 0.2), noise_scale=1 / 14.0, fill=0.08,
                           haze=0.6, shade_low=0.5, bump=1.6, dark=0.3, detail=5.0, evolve=True)
    close, near, far = [], [], []                      # by distance from your line of sight: finer meshes up close
    n_cols = int(2 * half * R0 / 120.0)
    for i in range(n_cols):
        a = a_cam - half + 2 * half * (i + rnd.random()) / n_cols
        lateral = (a - a_cam) * R0
        s = a * R0
        var = (0.8 + 0.2 * math.sin(s / 900.0 + 1.3) * math.sin(s / 2300.0 + 0.4)) * rnd.uniform(0.85, 1.15)
        dest = close if abs(lateral) < 500 else near if abs(lateral) < 2500 else far
        if dest is close:
            # the skirt: small billows rolling low along the street ahead of the bank
            for _ in range(10):
                r = rnd.uniform(8, 22)
                b = a + rnd.uniform(-0.5, 0.5) * 120.0 / R0
                rr = R0 + rnd.uniform(-60, 4)
                close.append(((rr * math.cos(b), rr * math.sin(b), r * rnd.uniform(0.2, 1.4)), (r * 1.3, r * 1.3, r)))
        # a wedge: a low skirt at the very front rising to the full height ~650 m behind it, so what it hits is seen
        # for a moment before the dust swallows it
        d = rnd.uniform(0, 25)
        while d < 900:
            u = _smooth(np.array(d / 650.0)).item()
            h_d = H * (0.012 + 0.988 * u) * var
            r0 = 24 + 114 * u
            z = 0.0
            while z < h_d:
                r = r0 * rnd.uniform(0.7, 1.3) * (1.0 + 0.5 * z / H)
                b = a + rnd.uniform(-0.5, 0.5) * 120.0 / R0
                rr = R0 - d - rnd.uniform(0, 0.6) * r
                dest.append(((rr * math.cos(b), rr * math.sin(b), z + r * 0.5), (r * 1.25, r * 1.25, r)))
                z += r * rnd.uniform(0.9, 1.3)
            d += r0 * rnd.uniform(1.1, 1.6)
    d = to_cam.normalized()
    x = np.asarray(x, float) - float(F.get("dust_lag_m", 100.0))
    loc = np.array((centre.x, centre.y, 0.0))[None, :] + np.array(d)[None, :] * (x - R0)[:, None]
    on = np.nonzero(x > start_m)[0]
    for name, puffs, sub, m in (("dust_front_close", close, 3, mat_close), ("dust_front_near", near, 2, mat),
                                ("dust_front_far", far, 1, mat)):
        if not puffs:
            continue
        ob = _no_shadow(rf.add_object(name, _billow_mesh(name, m, puffs, rnd, subdiv=sub, flat_base=0.0),
                                      ctx.col["city"]))
        for k in range(2):
            ctx.key(ob, "location", k, loc[:, k])
        ctx.key(ob, "scale", 2, 0.45 + 0.55 * _smooth(x / 9000.0))
        ob["fx"] = 1.0
        ob["heat"] = 0.0
        ob["phase"] = 0.0
        ctx.key(ob, '["phase"]', 0, ctx.t * 22.0)                 # the billows boil upward at ~20 m/s
        if len(on):
            _key_vis(ob, [(int(on[0]) + 1, ctx.nf + 2)])
        else:
            ob.hide_render = True
    # the low clouds over the city vanish into it as it passes under them
    for ob in ctx.info["static"]:
        if ob.name.startswith("cloud_") and ob.hide_render is False:
            along = (Vector((ob.location.x, ob.location.y, 0.0)) - Vector((centre.x, centre.y, 0.0))).dot(d)
            hit = np.nonzero(x >= along)[0]
            if len(hit):
                _key_vis(ob, [(1, int(hit[0]) + 1 + int(0.4 * ctx.fps))])
    print(f"[approach] dust front: {len(close) + len(near) + len(far)} billows along {2 * half * R0 / 1000:.1f} km, "
          f"{H:.0f} m high")


def _meteor_light(ctx, t_b, Bp, P, bright, flare, arrive, t_on):
    """The light: the meteor's glare growing, the flash, the fireball's orange afterglow, the dust in the air
    (`arrive`: when the dust reaches you)."""
    t = ctx.t
    cam = ctx.cam_pos
    dust_k = float(ctx.E.get("light", {}).get("dust", 1.0))
    a = np.clip(t - t_b, 0, None)
    after = t >= t_b
    flash = np.where(after, np.exp(-a / 0.6), 0.0)
    glow_l = np.where(after, np.exp(-a / 10.0), 0.0)
    dust = np.where(after, _smooth((t - t_b - 4.0) / 40.0), 0.0) * dust_k       # dust and smoke in the air, 0..1
    near = _smooth((t - (arrive - 12.0)) / 12.0)                                 # the wall closing in
    w_fire = np.clip(glow_l * 1.2, 0, 1)
    # sky: it stays blue overhead; the horizon warms after the flash and browns with the dust
    hz = _mix(dc.HORIZON, (1.0, 0.76, 0.55), 0.7 * w_fire)
    md = _mix(dc.MID, (0.78, 0.62, 0.55), 0.45 * w_fire)
    zn = _mix(dc.ZENITH, (0.26, 0.30, 0.55), 0.3 * w_fire)
    for arr, dcol, k in ((hz, (0.72, 0.58, 0.44), 0.55), (md, (0.52, 0.52, 0.58), 0.35), (zn, (0.16, 0.24, 0.48), 0.25)):
        arr[:] = arr * (1 - dust[:, None] * k) + np.array(dcol)[None, :] * dust[:, None] * k
    ctx.key_world("SkyHorizon", hz, rgb=True)
    ctx.key_world("SkyMid", md, rgb=True)
    ctx.key_world("SkyZenith", zn, rgb=True)
    pre = (t >= t_on) * (t < t_b) * (0.15 * bright + 0.5 * flare)
    ctx.key_world("SkyGain", 1.0 + 5.0 * flash + pre - 0.15 * dust - 0.2 * near)
    # the threat's glow follows the meteor, then the burst
    dirs = P - np.array(cam)[None, :]
    dirs /= np.linalg.norm(dirs, axis=1)[:, None]
    dirs[after] = np.array((Bp - cam).normalized())
    nt = ctx.world.node_tree
    for k in range(3):
        rf.key_series(nt, f'nodes["ThreatDir"].inputs[{k}].default_value', -1, ctx.frames, dirs[:, k])
    ctx.key_world("ThreatGain", np.where(after, 12.0 * flash + 1.4 * glow_l + 0.45 * dust,
                                         (t >= t_on) * (0.1 + 0.6 * bright ** 2 + 1.5 * flare)))
    ctx.key_world("ThreatWidth", np.where(after, 0.14 + 0.8 * flash + 0.3 * (1 - glow_l), 0.05 + 0.07 * bright))
    ctx.key_world("ThreatColor", np.where(after[:, None], _mix((1.0, 0.95, 0.85), (1.0, 0.45, 0.15), 1 - flash),
                                          np.array((1.0, 0.8, 0.55))[None, :]), rgb=True)
    # the air: warmer after the flash, dustier over time, thicker as the wall closes in
    hcol = _mix((0.70, 0.76, 0.85), (0.92, 0.66, 0.46), 0.6 * w_fire)
    hcol = hcol * (1 - dust[:, None] * 0.7) + np.array((0.55, 0.44, 0.34))[None, :] * dust[:, None] * 0.7
    hcol = _mix_rows(hcol, (0.36, 0.29, 0.21), _smooth((t - arrive + 0.12) / 0.25))      # brown fog as it hits
    look.key_scene_prop(ctx.scene, "rf_haze_col", ctx.frames, hcol)
    look.key_scene_prop(ctx.scene, "rf_haze_sun", ctx.frames, _mix((1.0, 0.86, 0.66), (1.0, 0.6, 0.3), np.clip(w_fire + 0.5 * dust, 0, 1)))
    haze0 = ctx.info.get("haze_m", 5000.0)
    engulf = _smooth((t - arrive + 0.12) / 0.25)                                 # inside the dust
    look.key_scene_prop(ctx.scene, "rf_haze_dist", ctx.frames,
                        (haze0 * (1 - 0.35 * dust) * (1 - 0.25 * near) + 600.0) * (1 - 0.996 * engulf))
    # the lamps: the sun reddens a little in the smoke; the meteor and the burst light the city from in front
    sun = ctx.info.get("sun")
    if sun:
        e0 = sun.data.energy
        c0 = np.array(sun.data.color)
        ctx.key(sun.data, "energy", -1, e0 * (1 - 0.25 * dust) * (1 - 0.15 * near))
        cols = _mix(c0, (1.0, 0.7, 0.48), np.clip(0.7 * dust, 0, 1))
        for k in range(3):
            ctx.key(sun.data, "color", k, cols[:, k])
    light = bpy.data.lights.new("ThreatLight", "SUN")
    light.angle = math.radians(3.0)
    _set(light, use_shadow=True)
    lamp = bpy.data.objects.new("ThreatLight", light)
    ctx.col["sky"].objects.link(lamp)
    lamp.rotation_euler = (-(Bp - cam).normalized()).to_track_quat("-Z", "Y").to_euler()
    pre_e = (t >= t_on) * (t < t_b) * (0.1 + 6.0 * np.minimum(bright, 1.0) ** 4 + 6.0 * np.clip(bright - 1.0, 0, None) + 5.0 * flare)
    ctx.key(light, "energy", -1, np.where(after, 60.0 * flash + 3.0 * glow_l, pre_e))
    lc = np.where(after[:, None], _mix((1.0, 0.97, 0.92), (1.0, 0.5, 0.2), 1 - flash), np.array((1.0, 0.86, 0.66))[None, :])
    for k in range(3):
        ctx.key(light, "color", k, lc[:, k])


# ---------------------------------------------------------------- WAVE

def _wave_mat():
    """Sea water on the wave: deep teal at the foot turning glassy green where light shines through its thin top,
    a band of churning white water along the foot, foam streaks drawn up the face, and white water on the lip and
    over the back. obj["phase"] moves the streaks, obj["inv_h"] = 1 / its height in metres."""
    mat, nt, out = _new_mat("wave_water")
    tc = nt.node("ShaderNodeTexCoord")
    obj = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], obj.inputs[0])
    gz = nt.math("MINIMUM", nt.math("MAXIMUM", obj.outputs["Z"], 0.0), 1.1)        # 0 at the foot, 1 at the crest
    back = nt.math("DIVIDE", nt.math("SUBTRACT", obj.outputs["Y"], 0.1), 0.3, clamp=True)   # 0 on the face, 1 behind
    streak = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", obj.outputs["X"], nt.math("MULTIPLY", _attr(nt, "inv_h"), 5.0)), streak.inputs[0])
    nt.links.new(nt.math("ADD", nt.math("MULTIPLY", obj.outputs["Z"], 3.0), _attr(nt, "phase")), streak.inputs[1])
    nt.links.new(nt.math("MULTIPLY", obj.outputs["Y"], 3.0), streak.inputs[2])
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 2.5
    n.inputs["Detail"].default_value = 9.0
    n.inputs["Roughness"].default_value = 0.66
    nt.links.new(streak.outputs[0], n.inputs["Vector"])
    churn = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(nt.math("MULTIPLY", obj.outputs["X"], nt.math("MULTIPLY", _attr(nt, "inv_h"), 14.0)), churn.inputs[0])
    nt.links.new(nt.math("ADD", nt.math("MULTIPLY", obj.outputs["Z"], 14.0), nt.math("MULTIPLY", _attr(nt, "phase"), 3.0)),
                 churn.inputs[1])
    nt.links.new(nt.math("MULTIPLY", obj.outputs["Y"], 14.0), churn.inputs[2])
    n2 = nt.node("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 1.0
    n2.inputs["Detail"].default_value = 6.0
    nt.links.new(churn.outputs[0], n2.inputs["Vector"])
    streaks = nt.math("POWER", nt.math("DIVIDE", nt.math("SUBTRACT", n.outputs["Fac"], 0.5), 0.22, clamp=True), 1.6)
    foot = nt.math("SUBTRACT", 1.0, nt.math("DIVIDE", nt.math("SUBTRACT", gz, 0.06), 0.2, clamp=True))
    lip = nt.math("DIVIDE", nt.math("SUBTRACT", nt.math("ADD", gz, nt.math("MULTIPLY", n2.outputs["Fac"], 0.25)), 0.78), 0.12,
                  clamp=True)
    white = nt.math("MAXIMUM", foot, lip)
    white = nt.math("MULTIPLY", white, nt.math("ADD", 0.45, n2.outputs["Fac"]))
    white = nt.math("MAXIMUM", white, nt.math("MULTIPLY", streaks, nt.math("ADD", 0.15, nt.math("MULTIPLY", gz, 0.6))))
    white = nt.math("MAXIMUM", white, nt.math("MULTIPLY", back, nt.math("POWER", n2.outputs["Fac"], 2.0)))
    white = nt.math("MINIMUM", white, 1.0)
    water = nt.ramp(gz, [(0.0, (0.03, 0.06, 0.06)), (0.45, (0.025, 0.09, 0.095)), (0.8, (0.05, 0.22, 0.2)),
                         (1.0, (0.08, 0.3, 0.26))])
    b = nt.node("ShaderNodeBsdfPrincipled")
    nt.links.new(nt.mix_color(white, water, (0.86, 0.9, 0.92, 1.0)), b.inputs["Base Color"])
    nt.links.new(nt.math("ADD", 0.06, nt.math("MULTIPLY", white, 0.8)), b.inputs["Roughness"])
    bump = nt.node("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.5
    nt.links.new(nt.math("ADD", n.outputs["Fac"], nt.math("MULTIPLY", n2.outputs["Fac"], 0.5)), bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    thin = nt.math("MULTIPLY", nt.math("DIVIDE", nt.math("SUBTRACT", gz, 0.5), 0.35, clamp=True),
                   nt.math("SUBTRACT", 1.0, white))
    b.inputs["Emission Color"].default_value = (0.08, 0.5, 0.42, 1.0)
    nt.links.new(nt.math("MULTIPLY", nt.math("MULTIPLY", thin, nt.math("SUBTRACT", 1.0, back)), 0.55),
                 b.inputs["Emission Strength"])
    nt.links.new(rf.scene_haze(nt, b.outputs[0], 1.0), out.inputs["Surface"])
    _set(mat, use_backface_culling=False)
    return mat


def _wave_mesh(name, mat, width=26000.0, seg=520):
    """The wave's cross-section swept along local X, travelling towards local -Y (you): the foot at y = 0, a
    concave face that curls forward into a lip hanging over it at height ~1, a back slope, then the flood behind it,
    0.45 high, that keeps everything it has passed under water."""
    prof = [(0.0, 0.0), (-0.02, 0.06), (-0.03, 0.16), (-0.02, 0.30), (0.0, 0.44), (0.02, 0.58), (0.02, 0.70),
            (-0.02, 0.80), (-0.09, 0.89), (-0.18, 0.95), (-0.27, 0.96), (-0.33, 0.91), (-0.34, 0.85),
            (-0.29, 0.93), (-0.2, 1.0), (-0.08, 1.04), (0.06, 1.05), (0.25, 1.02), (0.5, 0.95), (0.9, 0.82),
            (1.5, 0.66), (2.4, 0.53), (3.6, 0.47), (6.0, 0.45), (40.0, 0.45)]
    mb = rf.MeshBuilder()
    n = len(prof)
    for x in np.linspace(-width / 2, width / 2, seg + 1):
        for y, z in prof:
            mb.verts.append((float(x), y, z))
    for i in range(seg):
        for j in range(n - 1):
            a, b = i * n + j, (i + 1) * n + j
            mb.faces.append((a, a + 1, b + 1, b))
            mb.mats.append(0)
    return mb.build(name, [mat], smooth=True)


def _mist_mat(name, H):
    """Mist: a white veil whose transparency is a billowing noise in metres (it boils upward by obj["phase"]),
    densest at the bottom and fading out at the top. obj["fx"] fades it."""
    mat, nt, out = _new_mat(name)
    tc = nt.node("ShaderNodeTexCoord")
    obj = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], obj.inputs[0])
    gen = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], gen.inputs[0])
    v = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(obj.outputs["X"], v.inputs[0])
    nt.links.new(nt.math("SUBTRACT", obj.outputs["Z"], _attr(nt, "phase")), v.inputs[1])
    nt.links.new(obj.outputs["Y"], v.inputs[2])
    n = nt.node("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 1.0 / (0.12 * H)
    n.inputs["Detail"].default_value = 8.0
    n.inputs["Roughness"].default_value = 0.6
    nt.links.new(v.outputs[0], n.inputs["Vector"])
    z = gen.outputs["Z"]
    fade = nt.math("MULTIPLY", nt.math("POWER", nt.math("SUBTRACT", 1.0, z), 1.6), nt.math("DIVIDE", z, 0.08, clamp=True))
    a = nt.math("MULTIPLY", nt.math("DIVIDE", nt.math("SUBTRACT", n.outputs["Fac"], 0.38), 0.3, clamp=True), fade)
    a = nt.math("MULTIPLY", a, _attr(nt, "fx"))
    b = nt.node("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.86, 0.9, 0.92, 1.0)
    b.inputs["Roughness"].default_value = 1.0
    fill = nt.node("ShaderNodeVectorMath", operation="SCALE")
    nt.links.new(_attr(nt, "rf_haze_col", "VIEW_LAYER"), fill.inputs[0])
    fill.inputs["Scale"].default_value = 0.35
    nt.links.new(fill.outputs["Vector"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.0
    nt.links.new(_cutout(nt, rf.scene_haze(nt, b.outputs[0], 0.8), nt.math("MINIMUM", a, 0.9)), out.inputs["Surface"])
    _set(mat, use_backface_culling=False)
    return mat


def _wave_spray(ctx, H, width=26000.0):
    """The mist blown off the crest: three veils, one behind the other, standing on the lip (modelled for the full
    height H; scale them by the wave's height / H)."""
    mat = _mist_mat("wave_mist", H)
    obs = []
    for i, (y, z0, z1) in enumerate(((-0.36, 0.78, 1.55), (-0.2, 0.85, 1.75), (0.0, 0.92, 1.95))):
        mb = rf.MeshBuilder()
        mb.verts += [(-width / 2, y * H, z0 * H), (width / 2, y * H, z0 * H), (width / 2, y * H, z1 * H),
                     (-width / 2, y * H, z1 * H)]
        mb.faces.append((0, 1, 2, 3))
        mb.mats.append(0)
        obs.append(_no_shadow(rf.add_object(f"wave_mist_{i}", mb.build(f"wave_mist_{i}", [mat]), ctx.col["city"])))
    return obs


def _wave(ctx):
    E = ctx.E
    Wv = E["wave"]
    t = ctx.t
    cam = ctx.cam_pos
    hd = math.radians(ctx.heading)
    fwd = Vector((math.sin(hd), math.cos(hd), 0.0))
    t0, d0 = float(Wv.get("start_at", 4.0)), float(Wv.get("from_m", 9000.0))
    H = float(Wv.get("height_m", 300.0))
    v_sea, v_city = float(Wv.get("speed_mps", 70.0)), float(Wv.get("city_speed_mps", 40.0))
    shore = ctx.info.get("shore_y")
    if shore is None:
        raise ValueError("the wave needs a sea: add \"coast\": {\"shore_y\": 3000} to the world")
    shore_d = (shore - cam.y) / max(fwd.y, 0.2)
    # its distance from you along your view (it slows when it reaches the shore), and its height (it rises as the
    # sea gets shallower)
    d = np.zeros_like(t)
    cur = d0
    for i, tt in enumerate(t):
        if tt > t0:
            cur -= (v_sea if cur > shore_d else v_city) / ctx.fps
        d[i] = max(cur, 0.0)
    arrive = float(t[np.argmax(d <= 0.0)]) if (d <= 0).any() else float(t[-1] + d[-1] / v_city)
    hgt = H * (0.4 + 0.6 * _smooth((d0 - d) / max(d0 - shore_d, 1.0))) * (t >= t0)
    t_shore = float(t[np.argmax(d <= shore_d)]) if (d <= shore_d).any() else None
    ctx.times.update({"appear": t0, "shore": t_shore, "arrive": round(arrive, 2)})
    ctx.event("arrive", arrive)
    if t_shore is not None:
        ctx.event("shore", t_shore)
    print(f"[approach] wave {H:.0f} m high from {d0 / 1000:.1f} km at {v_sea:.0f} m/s ({v_sea * MPH:.0f} mph), "
          f"{v_city:.0f} m/s ashore; shore {shore_d / 1000:.1f} km from you")
    wave = rf.add_object("wave", _wave_mesh("wave", _wave_mat()), ctx.col["city"])
    sprays = _wave_spray(ctx, H)
    pos = np.array(cam)[None, :] + np.array(fwd)[None, :] * d[:, None]
    for ob in [wave] + sprays:
        ob.rotation_euler = (0.0, 0.0, -hd)
        for k in range(2):
            ctx.key(ob, "location", k, pos[:, k])
        ctx.key(ob, "location", 2, np.full_like(t, -1.0))
        _key_vis(ob, [(ctx.f(t0), ctx.nf + 2)])
    for k in (1, 2):
        ctx.key(wave, "scale", k, np.maximum(hgt, 1.0))
        for ob in sprays:
            ctx.key(ob, "scale", k, np.maximum(hgt / H, 0.001))
    wave["phase"] = 0.0
    wave["inv_h"] = 0.01
    ctx.key(wave, '["phase"]', 0, -t * 0.5)
    ctx.key(wave, '["inv_h"]', 0, 1.0 / np.maximum(hgt, 1.0))
    for ob in sprays:
        ob["fx"] = 0.0
        ob["phase"] = 0.0
        ctx.key(ob, '["fx"]', 0, 0.9 * _smooth((t - t0) / 4.0))
        ctx.key(ob, '["phase"]', 0, t * 0.09 * H)          # the mist boils up off the lip
    sea = ctx.info.get("sea")
    if sea is not None and Wv.get("drawback_at") is not None:
        db = float(Wv["drawback_at"])
        ctx.key(sea, "location", 2, -np.clip((t - db) / 6.0, 0, 1) * 8.0)
        ctx.times["drawback"] = db

    def arrive_at(px, py):
        along = (px - cam.x) * fwd.x + (py - cam.y) * fwd.y
        reached = np.nonzero(d <= along)[0] if along <= d0 else []
        return float(t[reached[0]]) if len(reached) and t[reached[0]] > t0 else float("inf")

    ahead = cam + fwd * (d0 + 60000.0)
    hit = _react_static(ctx, ahead, arrive_at)
    _collapse_dust(ctx, hit, near_m=2500.0, max_n=70, color=(0.82, 0.86, 0.88), rise=2.2, name="impact_spray")
    _front_times(ctx, arrive_at)
    _movers(ctx, ahead, arrive_at, face=cam + fwd * d0)
    _debris(ctx, ahead, arrive)
    _balcony_hit(ctx, ahead, arrive)
    # the light goes green-grey and dim under the wall of water
    gloom = 0.6 * _smooth((t - t0) / 25.0) + 0.4 * _smooth((t - (arrive - 10)) / 10.0)
    ctx.key_world("SkyHorizon", _mix(dc.HORIZON, (0.50, 0.58, 0.55), gloom), rgb=True)
    ctx.key_world("SkyMid", _mix(dc.MID, (0.38, 0.47, 0.50), gloom), rgb=True)
    ctx.key_world("SkyZenith", _mix(dc.ZENITH, (0.16, 0.22, 0.27), gloom), rgb=True)
    ctx.key_world("SkyGain", 1.0 - 0.35 * gloom)
    engulf = _smooth((t - arrive + 0.1) / 0.25)
    look.key_scene_prop(ctx.scene, "rf_haze_col", ctx.frames,
                        _mix_rows(_mix((0.70, 0.76, 0.85), (0.44, 0.53, 0.53), gloom), (0.05, 0.16, 0.15), engulf))
    look.key_scene_prop(ctx.scene, "rf_haze_dist", ctx.frames,
                        (ctx.info.get("haze_m", 5000.0) * (1 - 0.5 * gloom) + 250.0) * (1 - 0.996 * engulf))
    sun = ctx.info.get("sun")
    if sun:
        ctx.key(sun.data, "energy", -1, sun.data.energy * (1 - 0.55 * gloom))
    shake = 1.0 * np.clip(1 - d / 2000.0, 0, 1) ** 2 * (t < arrive)
    shake += 3.2 * np.exp(-np.clip(t - arrive, 0, None) / 0.5) * (t >= arrive)
    crest = np.array(cam)[None, :] + np.array(fwd)[None, :] * (d + 0.3 * hgt)[:, None]
    crest[:, 2] = 0.9 * hgt
    _camera(ctx, shake, {"wave": crest - np.array(cam)[None, :]},
            knock=arrive if ctx.E.get("knockback", True) else None)
    speed = np.where(d > shore_d, v_sea, v_city) * (t >= t0) * (d > 0)
    return {"front_m": [float(v) for v in d], "front_mph": [float(v * MPH) for v in speed],
            "eta_s": [float(v) for v in np.maximum(arrive - t, 0.0)], "wave_ft": [float(v * FT) for v in hgt]}


# ---------------------------------------------------------------- entry point

def _add_streaks(scene, threshold=8.0, strength=0.35):
    """Star-shaped glare on only the brightest pixels (the meteor's core, the flash), after the bloom."""
    tree = scene.node_tree
    comp = next((n for n in tree.nodes if n.type == "COMPOSITE"), None)
    if comp is None or not comp.inputs["Image"].links:
        return
    src = comp.inputs["Image"].links[0].from_socket
    st = tree.nodes.new("CompositorNodeGlare")
    _set(st, glare_type="STREAKS", quality="HIGH", streaks=6, angle_offset=math.radians(18), fade=0.93,
         threshold=threshold, mix=strength - 1.0)
    for name, val in (("Threshold", threshold), ("Strength", strength), ("Streaks", 6),
                      ("Streaks Angle", math.radians(18)), ("Fade", 0.93), ("Iterations", 3), ("Saturation", 0.6)):
        if name in st.inputs:
            try:
                st.inputs[name].default_value = val
            except (TypeError, AttributeError):
                pass
    tree.links.new(src, st.inputs["Image"])
    tree.links.new(st.outputs["Image"], comp.inputs["Image"])


def apply(spec, info):
    if "scene" not in info or "collections" not in info:
        raise ValueError("effects.approach needs the disaster_city world (\"world\": {\"type\": \"disaster_city\"})")
    ctx = Ctx(spec, info)
    near, far = ctx.E.get("clip", [0.25, 32000.0])
    ctx.cam.data.clip_start = near
    ctx.cam.data.clip_end = far
    look.add_bloom(ctx.scene, threshold=1.2, size=8, mix=-0.6)
    threat = ctx.E["threat"]
    if threat == "meteor":
        _add_streaks(ctx.scene)
    if threat == "meteor":
        series = _meteor(ctx)
    elif threat == "wave":
        series = _wave(ctx)
    else:
        raise ValueError(f"unknown threat {threat!r} (meteor or wave)")
    times = {k: round(float(v), 2) for k, v in ctx.times.items() if v is not None}
    series.update({"fps": ctx.fps, "frames": ctx.nf, "events": ctx.events, "times": times})
    print("[approach] times " + ", ".join(f"{k} {v:.2f}" for k, v in sorted(times.items(), key=lambda kv: kv[1])))
    return series
