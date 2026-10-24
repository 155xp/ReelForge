"""Effect: everyone on Earth does one thing at the same moment ("What if everyone on Earth jumped at once?").
Use it with worlds/plaza.py (or any world that returns the same info keys).

The story climbs the scales: you alone, the people round you, the square, the city, the country, the whole planet,
with a counter of how many have joined (a gold "joined" glow spreads over the city's streets, the country and the
continents where people actually live). Then a countdown and the synchronized moment: everyone crouches and jumps,
time slows to a near-freeze in the air while the camera tours the scales, and everyone lands together. The
physics comes along: the Earth is pushed back by everyone's push-off, by a tiny exact amount, and returns when they
land (momentum: the centre of mass of Earth plus people never moves).

Spec keys (spec["effect"]), times in video seconds:
  population      the final count (default 8_300_678_395: the UN's projection for mid-2026)
  mean_mass_kg    average body mass of everyone, children included (default 50)
  join            when each scale joins in:
                    "square":  {"from", "to"}         the square's crowd appears, nearest you first
                    "streets": {"from", "to"}         the ring road and the avenues
                    "city":    {"from", "to", "count"}   the city's streets fill out to its edge (count: everyone in
                                                     the city, square and streets included)
                    "country": {"from", "to", "radius_km", "count"}   the gold front spreads to radius_km (count:
                                                     everyone in the country, the city included)
                    "planet":  {"from", "to"}         the front sweeps the globe; the counter follows how many people
                                                     live within it (parts/globe.py), reaching `population`
  where           [[t, "TEXT"], ...] the HUD's "where" line from each time on (series "where")
  countdown       {"ticks": [t, ...], "texts": ["3", "2", "1", "JUMP!"], "go": t} (series "countdown"; the last
                  text shows from "go")
  action          what everyone does:
                    {"type": "jump", "lift_off": t, "height": 0.44 (m), "air": 0.6 (s), "crouch": 0.32, "land": 0.28,
                     "slow_at": t (the slow motion starts), "slow_rate": 0.006 (crowd seconds per video second in
                     the freeze), "ease": 0.3 (s into and out of the freeze), "land_at": t (the feet touch down: the
                     freeze ends just in time), "cheer_after": 0.6 (s after landing the crowd cheers)}
                    {"type": "pose", "pose": "look" | "wave" | "cheer" | "film", "at": t}
  hero            {"hop_at": t | [t, ...], "hop_height": 0.12}  warm-up bounces from you before anyone joins
                  (optional; leave about 0.9 s between bounces)
  glow            [[t, v], ...] the gold "joined" glow (0..1)
  earth           {"show_from": t, "count_for": 3.0}  the series earth_m counts up from 0 over count_for seconds
                  from show_from, then follows the real displacement (back to 0 when everyone lands)
  lod             [near_m, far_m] crowd level-of-detail distances (default [38, 160])
  shots           the camera, as hard-cut shots [{"from", "to", "type", ...}, ...]; types:
                    "keys":   {"keys": [[t, [x, y, z], [tx, ty, tz], lens], ...], "rel": "hero" | "world"}
                              eased moves between keys ("rel": "hero" puts the origin at your feet)
                    "orbit":  {"centre": [x, y, z] | "hero", "radius": [r0, r1], "height": [h0, h1],
                               "az": [a0, a1] (degrees round the centre, 0 = from the south, 90 = from the east),
                               "look_z": z, "lens": mm | [l0, l1]}
                    "climb":  {"over": [x, y], "alt": [a0, a1] (metres, exponential), "back": 0.8 (camera this far
                               south of the point, times its altitude), "ahead": 0.3 (aims this far north, times
                               the altitude), "lens"}
                    "rise":   {"target": [x, y, z] | "hero", "target_to": [dx, dy, dz] (optional: the aim drifts to
                               this offset from you), "alt": [a0, a1], "back": 4.0, "lens"}: a pull-up from street
                              level to looking straight down at the target, keeping it centred
                    "planet": {"alt_km": [a0, a1], "pos": [north_deg, east_deg] (where the camera hangs, as angles
                               from home), "aim": [north_deg, east_deg] (where it looks, on the ground; default the
                               planet's centre), "lens", "roll": deg}: up is the planet's north
                  any shot may add "shake": [[t, deg], ...], "dof": {"fstop": 2.0, "focus": "hero_feet" | metres},
                  "ease": false (linear instead of eased moves)

Returned series (per frame; post/compose.py FORMATS in brackets):
  ready      people who have joined [int_commas]        where      the "where" text [raw]
  countdown  the countdown text [raw]                   in_air     people off the ground [int_commas]
  airtime    time in the air so far, "0.31 s" [raw]     earth_m    Earth's displacement, "0.000000000000031 m" [raw]
  mass_t     tonnes of people in the air [int_commas]   alt_m      camera altitude above the ground [distance_imperial]
  subject_box  your screen box per frame, for "layout": {"avoid_subject": true}
  events     {"cut", "milestone", "pop", "tick", "go", "lift_off", "freeze", "land", "cheer"} seconds for the cue sheet
  times      the key moments (lift_off, apex, freeze, resume, land, ...), also printed in build.log
"""
import math
import random

import numpy as np
from mathutils import Matrix

import camrig
import look
import rf_common as rf
from parts import crowd, globe

G = 9.81
M_EARTH = 5.972e24


def _ss(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _interp(points, t, default=0.0):
    if not points:
        return np.full_like(t, default, dtype=float)
    xs, ys = zip(*points)
    return np.interp(t, xs, ys)


def _pair(v, u):
    """A number, or [a, b] eased by u."""
    if isinstance(v, (int, float)):
        return float(v)
    return float(v[0]) + (float(v[1]) - float(v[0])) * u


def _exp_pair(v, u):
    a, b = float(v[0]), float(v[1])
    return a * (b / a) ** u


class Ctx:
    def __init__(self, spec, info):
        self.spec, self.info = spec, info
        self.E = spec["effect"]
        self.fps = spec["fps"]
        self.nf = int(round(spec["render_until"] * self.fps))
        self.frames = np.arange(1, self.nf + 1)
        self.t = (self.frames - 1) / self.fps
        self.scene = info["scene"]
        self.rnd = random.Random(self.E.get("seed", 5))
        self.events, self.times = {}, {}
        hx, hy = info["hero"]["pos"]
        self.hero = np.array((hx, hy, 0.0))
        self.planet = info["planet"]

    def event(self, name, t):
        self.events.setdefault(name, []).append(round(float(t), 3))

    def key(self, idblock, path, index, values):
        rf.key_series(idblock, path, index, self.frames, values)


# ---------------------------------------------------------------- the crowd's clock and the action

def _rate(t, A, resume_at):
    ease = A.get("ease", 0.3)
    lo = A.get("slow_rate", 0.006)
    s0 = A["slow_at"]
    down = _ss((t - s0) / ease)
    up = _ss((t - resume_at) / ease)
    # ease the logarithm of the rate, so the slow-down reads as one smooth deceleration
    lr = math.log(lo) * down * (1 - up)
    return np.exp(lr)


def crowd_clock(ctx, A):
    """Crowd time per frame for a jump with a near-freeze in the air, solved so the feet touch down at land_at."""
    dt = 1.0 / 600.0
    tt = np.arange(0.0, ctx.spec["render_until"] + 1.0, dt)
    touch = A["lift_off"] + A.get("air", 0.6)

    def clock(resume_at):
        r = _rate(tt, A, resume_at)
        return np.concatenate([[0.0], np.cumsum(r[:-1]) * dt])

    lo, hi = A["slow_at"] + A.get("ease", 0.3), A["land_at"]
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        c = clock(mid)
        if np.interp(A["land_at"], tt, c) > touch:      # still too far along at land_at: freeze for longer
            lo = mid
        else:
            hi = mid
    resume = 0.5 * (lo + hi)
    c = clock(resume)
    return np.interp(ctx.t, tt, c), tt, c, resume


def _hop(local, air, height):
    s = np.clip(local / max(air, 1e-6), 0.0, 1.0)
    return 4.0 * height * s * (1.0 - s) * ((local > 0) & (local < air))


# ---------------------------------------------------------------- the camera

def _planet_dir(north_deg, east_deg):
    n, e = math.radians(north_deg), math.radians(east_deg)
    return np.array([math.sin(e) * math.cos(n), math.sin(n), math.cos(e) * math.cos(n)])


def _shot_pose(ctx, sh, t):
    """(cam, tgt, lens, up, altitude, kind) for shot `sh` at time t."""
    t0, t1 = sh["from"], sh["to"]
    u_lin = min(1.0, max(0.0, (t - t0) / max(t1 - t0, 1e-6)))
    u = u_lin if sh.get("ease") is False else float(_ss(u_lin))
    kind = sh["type"]
    up = np.array((0.0, 0.0, 1.0))
    centre = np.array(ctx.planet["centre"])
    R = ctx.planet["radius"]
    if kind == "keys":
        off = ctx.hero if sh.get("rel", "hero") == "hero" else np.zeros(3)
        keys = [(k[0], np.array(k[1], float) + off, np.array(k[2], float) + off, float(k[3])) for k in sh["keys"]]
        if t <= keys[0][0]:
            a = keys[0]
            cam, tgt, lens = a[1], a[2], a[3]
        elif t >= keys[-1][0]:
            a = keys[-1]
            cam, tgt, lens = a[1], a[2], a[3]
        else:
            for a, b in zip(keys, keys[1:]):
                if a[0] <= t <= b[0]:
                    s = (t - a[0]) / max(b[0] - a[0], 1e-6)
                    s = s if sh.get("ease") is False else float(_ss(s))
                    cam = a[1] + (b[1] - a[1]) * s
                    tgt = a[2] + (b[2] - a[2]) * s
                    lens = a[3] + (b[3] - a[3]) * s
                    break
        alt = float(cam[2])
    elif kind == "orbit":
        c = ctx.hero + np.array((0.0, 0.0, 0.0)) if sh.get("centre", "hero") == "hero" else np.array(sh["centre"], float)
        r = _pair(sh["radius"], u)
        h = _pair(sh["height"], u)
        az = math.radians(_pair(sh["az"], u))
        cam = np.array((c[0] + r * math.sin(az), c[1] - r * math.cos(az), h))
        tgt = np.array((c[0], c[1], sh.get("look_z", c[2])))
        lens = _pair(sh.get("lens", 30.0), u)
        alt = h
    elif kind == "climb":
        x, y = sh.get("over", (0.0, 0.0))
        alt = _exp_pair(sh["alt"], u)
        cam = np.array((x, y - sh.get("back", 0.8) * alt, alt))
        tgt = np.array((x, y + sh.get("ahead", 0.3) * alt, 0.0))
        lens = _pair(sh.get("lens", 30.0), u)
    elif kind == "rise":
        T = ctx.hero + np.array((0.0, 0.0, 1.0)) if sh.get("target", "hero") == "hero" else np.array(sh["target"], float)
        if "target_to" in sh:                                  # the aim drifts (e.g. from you into the crowd)
            T = T + (ctx.hero + np.array(sh["target_to"], float) - T) * u
        alt = _exp_pair(sh["alt"], u)
        back = sh.get("back", 4.0) * (1.0 + 0.02 * alt)
        cam = np.array((T[0], T[1] - back, alt))
        tgt = T.copy()
        lens = _pair(sh.get("lens", 30.0), u)
    elif kind == "planet":
        alt = _exp_pair([a * 1000.0 for a in sh["alt_km"]], u)
        pos = sh.get("pos", [0.0, 0.0])
        pos = [_pair(pos[0], u), _pair(pos[1], u)]
        cam = centre + _planet_dir(*pos) * (R + alt)
        if "aim" in sh:
            aim = sh["aim"]
            tgt = centre + _planet_dir(_pair(aim[0], u), _pair(aim[1], u)) * R
        else:
            tgt = centre.copy()
        lens = _pair(sh.get("lens", 35.0), u)
        up = np.array(ctx.planet["frame"] @ np.array((0.0, 0.0, 1.0)))    # the planet's north, in world terms
    else:
        raise ValueError(f"unknown shot type {kind!r}")
    return np.asarray(cam, float), np.asarray(tgt, float), float(lens), up, float(alt), kind


def _quat(f, r, u):
    m = Matrix(((r[0], u[0], -f[0]), (r[1], u[1], -f[1]), (r[2], u[2], -f[2])))
    return m.to_quaternion()


def camera(ctx):
    """Key the camera per frame from the shot list; returns per-frame altitude, kind, cam, tgt, lens."""
    shots = ctx.E["shots"]
    cam_ob = ctx.info["camera"]
    cam_ob.rotation_mode = "QUATERNION"
    n = ctx.nf
    locs, quats, lenses, alts, kinds, cams, tgts = [], [], [], [], [], [], []
    clip0, clip1, fst, focus = [], [], [], []
    prev_q = None
    last_shot = None
    for i, t in enumerate(ctx.t):
        k = next((j for j, s in enumerate(shots) if s["from"] <= t < s["to"]), len(shots) - 1)
        sh = shots[k]
        if last_shot is not None and k != last_shot:
            ctx.event("cut", sh["from"])
        last_shot = k
        cam, tgt, lens, up, alt, kind = _shot_pose(ctx, sh, t)
        f, r, u = camrig.basis(cam, tgt, up)
        # shake: small rotations, eased by the shot's shake curve
        amp = float(_interp(sh.get("shake", []), np.array([t]))[0]) if sh.get("shake") else 0.0
        if amp > 0:
            jx, jz = camrig.jitter(t, math.radians(amp), (0.3, 1.7, 2.9, 0.8, 2.2, 4.1))
            f = f + r * jx + u * jz
            f /= np.linalg.norm(f)
            r = np.cross(f, up)
            r /= np.linalg.norm(r)
            u = np.cross(r, f)
        roll = math.radians(sh.get("roll", 0.0))
        if roll:
            r, u = r * math.cos(roll) + u * math.sin(roll), u * math.cos(roll) - r * math.sin(roll)
        q = _quat(f, r, u)
        if prev_q is not None and prev_q.dot(q) < 0:
            q.negate()
        prev_q = q
        locs.append(cam)
        quats.append(q)
        lenses.append(lens)
        alts.append(alt)
        kinds.append(kind)
        cams.append(cam)
        tgts.append(tgt)
        dist = float(np.linalg.norm(tgt - cam))
        if kind == "planet":
            R = ctx.planet["radius"]
            clip0.append(max(1000.0, alt * 0.02))
            clip1.append((alt + 2.2 * R) * 1.2)
        else:
            clip0.append(max(0.05, alt * 0.02))
            horizon = math.sqrt(2 * 6.371e6 * max(alt, 1.0))
            clip1.append(max(30_000.0, 3.0 * horizon + 2.0 * alt))
        dof = sh.get("dof")
        if dof:
            fst.append(float(dof.get("fstop", 2.8)))
            fo = dof.get("focus", "target")
            if fo == "hero_feet":
                focus.append(float(np.linalg.norm(ctx.hero + np.array((0.0, 0.0, 0.5)) - cam)))
            elif isinstance(fo, (int, float)):
                focus.append(float(fo))
            else:
                focus.append(dist)
        else:
            fst.append(128.0)
            focus.append(max(dist, 0.1))
    locs = np.array(locs)
    for k in range(3):
        ctx.key(cam_ob, "location", k, locs[:, k])
    qa = np.array([[q.w, q.x, q.y, q.z] for q in quats])
    for k in range(4):
        ctx.key(cam_ob, "rotation_quaternion", k, qa[:, k])
    ctx.key(cam_ob.data, "lens", -1, lenses)
    ctx.key(cam_ob.data, "clip_start", -1, clip0)
    ctx.key(cam_ob.data, "clip_end", -1, clip1)
    cam_ob.data.dof.use_dof = True
    ctx.key(cam_ob.data, "dof.aperture_fstop", -1, fst)
    ctx.key(cam_ob.data, "dof.focus_distance", -1, focus)
    for idb in (cam_ob, cam_ob.data):
        rf.set_interpolation(idb, "CONSTANT")
    return np.array(alts), kinds, np.array(cams), np.array(tgts), np.array(lenses)


def _key_vis(ctx, ob, show):
    """CONSTANT hide_render keys from a per-frame bool array."""
    if ob is None:
        return
    vals = [0.0 if s else 1.0 for s in show]
    ob.hide_render = bool(vals[0])
    ctx.key(ob, "hide_render", -1, vals)
    rf.set_interpolation(ob, "CONSTANT", "hide_render")


# ---------------------------------------------------------------- the story

def apply(spec, info):
    ctx = Ctx(spec, info)
    E = ctx.E
    t = ctx.t
    fps = ctx.fps
    scene = ctx.scene
    pop_total = int(E.get("population", 8_300_678_395))
    mass = float(E.get("mean_mass_kg", 50.0))
    A = dict(E.get("action", {"type": "jump", "lift_off": 1e6}))
    J = E.get("join", {})
    R = ctx.planet["radius"]

    # ---- the crowd's clock and inputs
    if A.get("type", "jump") == "jump":
        A.setdefault("slow_at", A["lift_off"] + 0.12)
        A.setdefault("land_at", A["slow_at"] + 1.0)
        clock, tt, cfine, resume = crowd_clock(ctx, A)
    else:
        clock, resume = t.copy(), None
    air, height = A.get("air", 0.6), A.get("height", 0.44)
    crouch, land = A.get("crouch", 0.32), A.get("land", 0.28)
    lod = E.get("lod", [38.0, 160.0])
    hype_at = 1e6
    if A.get("type", "jump") == "jump":
        hype_at = float(np.interp(A["land_at"], t, clock)) + land + A.get("cheer_after", 0.6)
    crowds = info["crowds"]
    for c in crowds:
        jw = J.get(c["name"], {"from": 0.0, "to": 0.0})
        ob = c["object"]
        crowd.set_input(ob, "Join From", float(jw["from"]))
        crowd.set_input(ob, "Join Span", float(jw["to"] - jw["from"]))
    for ob in info["crowd_objects"]:
        crowd.set_input(ob, "LOD Dist", float(lod[0]))
        crowd.set_input(ob, "LOD Far", float(lod[1]))
        crowd.set_input(ob, "Crouch", float(crouch))
        crowd.set_input(ob, "Land", float(land))
        crowd.set_input(ob, "Hype From", float(hype_at))
        if A.get("type", "jump") == "jump":
            crowd.set_input(ob, "Jump At", float(A["lift_off"]))
            crowd.set_input(ob, "Air", float(air))
            crowd.set_input(ob, "Height", float(height))
        elif A.get("type") == "pose":
            crowd.set_input(ob, "Act At", float(A["at"]))
            crowd.set_input(ob, "Act Pose", float(crowd.POSES.index(A.get("pose", "look"))))
        crowd.key_inputs(ob, ctx.frames, clock=clock)
    # your warm-up bounces (each one needs ~0.85 s: a short crouch, the hop, the landing)
    H = E.get("hero")
    hero_ob = info["hero"]["object"]
    if H and A.get("type", "jump") == "jump":
        hops = H["hop_at"] if isinstance(H["hop_at"], (list, tuple)) else [H["hop_at"]]
        hh = float(H.get("hop_height", 0.12))
        hair = 2.0 * math.sqrt(2.0 * hh / G)
        ja = np.full_like(t, float(hops[0]))
        for h0 in hops:
            ja = np.where(t >= h0 - 0.25, float(h0), ja)
        switch = hops[-1] + hair + 0.6
        before = t < switch
        crowd.key_inputs(hero_ob, ctx.frames,
                         jump_at=np.where(before, ja, A["lift_off"]),
                         height=np.where(before, hh, height), air=np.where(before, hair, air),
                         crouch=np.where(before, 0.2, crouch))
        for h0 in hops:
            ctx.event("hop", h0)

    # ---- how many have joined
    ready = np.ones_like(t)
    for c in crowds:
        jw = J.get(c["name"])
        if not jw:
            continue
        times = jw["from"] + c["order"] * (jw["to"] - jw["from"])
        ready += np.searchsorted(np.sort(times), clock, side="right")
        # pops for the sound: every 0.25 s while people are appearing
        for tp in np.arange(jw["from"], jw["to"], 0.25):
            ctx.event("pop", tp)
    n_flat = 1 + sum(c["n"] for c in crowds)
    r0 = float(info.get("fill_from", 400.0))
    r_city = float(info["city_radius"])
    fill_r = np.zeros_like(t)
    if "city" in J:
        jc = J["city"]
        u = _ss((t - jc["from"]) / (jc["to"] - jc["from"]))
        fill_r = np.where(t >= jc["from"], r0 + (r_city + 700.0 - r0) * u, 0.0)
        area = np.clip((np.minimum(fill_r, r_city) ** 2 - r0 ** 2) / (r_city ** 2 - r0 ** 2), 0.0, 1.0)
        ready += area * max(jc["count"] - n_flat, 0)
        n_city = jc["count"]
    else:
        n_city = n_flat
    globe_a = np.zeros_like(t)
    rk = r_city
    if "country" in J:
        jk = J["country"]
        rk = jk["radius_km"] * 1000.0
        u = _ss((t - jk["from"]) / (jk["to"] - jk["from"]))
        rc = r_city + (rk - r_city) * u
        globe_a = np.where(t >= jk["from"], rc / R, 0.0)
        ready += np.clip((rc ** 2 - r_city ** 2) / (rk ** 2 - r_city ** 2), 0.0, 1.0) * \
            (t >= jk["from"]) * max(jk["count"] - n_city, 0)
        n_country = jk["count"]
    else:
        n_country = n_city
    if "planet" in J:
        jp = J["planet"]
        u = _ss((t - jp["from"]) / (jp["to"] - jp["from"]))
        a = rk / R + (math.pi - rk / R) * u
        globe_a = np.where(t >= jp["from"], a, globe_a)
        home = info["home"]
        share = globe.population_within(a, home[0], home[1], exclude_rad=rk / R)
        ready += np.where(t >= jp["from"], share, 0.0) * max(pop_total - n_country, 0)
        ready = np.where(t >= jp["to"], pop_total, ready)
    ready = np.floor(ready + 1e-6)
    look.key_scene_prop(scene, "rf_time", ctx.frames, clock)               # the fountain's water freezes too
    look.key_scene_prop(scene, "rf_fill_r", ctx.frames, fill_r)
    look.key_scene_prop(scene, "rf_globe_a", ctx.frames, globe_a)
    look.key_scene_prop(scene, "rf_glow", ctx.frames, _interp(E.get("glow", []), t))
    last = 1
    for i in range(len(t)):
        while ready[i] >= last * 10:
            last *= 10
            ctx.event("milestone", t[i])

    # ---- countdown text
    cd = E.get("countdown", {})
    texts, ticks = cd.get("texts", ["3", "2", "1", "JUMP!"]), cd.get("ticks", [])
    countdown = []
    for x in t:
        s = ""
        for k, tk in enumerate(ticks):
            if x >= tk:
                s = texts[min(k, len(texts) - 1)]
        if cd.get("go") is not None and x >= cd["go"]:
            s = texts[-1]
        countdown.append(s)
    for tk in ticks:
        ctx.event("tick", tk)
    if cd.get("go") is not None:
        ctx.event("go", cd["go"])

    # ---- the jump's numbers: people in the air, airtime, Earth's push-back
    if A.get("type", "jump") == "jump":
        local = clock - A["lift_off"]
        airborne = (local > 0) & (local < air)
        in_air = np.where(airborne, pop_total, 0)
        airtime = [f"{min(max(v, 0.0), air):.2f} s" for v in local]
        h_people = _hop(local, air, height)
        earth = pop_total * mass * h_people / M_EARTH
        ec = E.get("earth", {})
        if ec:
            k = _ss((t - ec["show_from"]) / max(ec.get("count_for", 3.0), 1e-6))
            earth = np.where(t >= ec["show_from"], earth * k, earth)
        earth_m = [f"{v:.15f} m" for v in earth]
        mass_t = np.where(airborne, pop_total * mass / 1000.0, 0.0)
        lift = A["lift_off"]
        apex_c = lift + air / 2
        ctx.times.update({"lift_off": lift, "crouch": lift - crouch,
                          "apex": float(np.interp(apex_c, cfine, tt)), "resume": resume,
                          "land": A["land_at"], "cheer": float(np.interp(hype_at, clock, t))})
        rate = np.gradient(clock, t)
        fz = t[np.argmax(rate < A.get("slow_rate", 0.006) * 1.5)] if (rate < A.get("slow_rate", 0.006) * 1.5).any() else lift
        ctx.times["freeze"] = float(fz)
        for k_ in ("lift_off", "freeze", "land", "cheer"):
            ctx.event(k_, ctx.times[k_])
        ctx.times["earth_max_m"] = pop_total * mass * height / M_EARTH
        ctx.times["airtime_s"] = air
    else:
        in_air = np.zeros_like(t)
        airtime = [""] * len(t)
        earth_m = ["0 m"] * len(t)
        mass_t = np.zeros_like(t)

    # ---- the camera, and what is shown at each altitude
    alts, kinds, cams, tgts, lenses = camera(ctx)
    planet_shot = np.array([k == "planet" for k in kinds])
    for ob in info["crowd_objects"]:
        _key_vis(ctx, ob, (alts < 6000.0) & ~planet_shot)
    for ob in info["flat"]:
        _key_vis(ctx, ob, ~planet_shot)
    for ob in info.get("low_clouds", []):
        _key_vis(ctx, ob, (alts < 6_000.0) & ~planet_shot)              # puffs look like popcorn from far above
    _key_vis(ctx, ctx.planet.get("clouds"), alts > 15_000.0)
    _key_vis(ctx, ctx.planet.get("atmosphere"), alts > 100_000.0)
    # the air clears as you climb (a milky haze over everything is the classic flat aerial)
    la = np.log10(np.maximum(alts, 1.5))
    max_mul = np.interp(la, [math.log10(500.0), math.log10(20_000.0)], [1.0, 0.55])
    look.key_air(scene, info["world"], ctx.frames, np.maximum(alts, 1.5), max_mul=max_mul)
    # stars only once properly in space: at 20-80 km up a daylight sky shows none
    stars = np.clip((alts - 80_000.0) / 400_000.0, 0.0, 1.0) * 0.8
    rf.key_series(info["world"].node_tree, 'nodes["StarMix"].outputs[0].default_value', -1, ctx.frames, stars)

    # ---- your box on screen (story lines stay off you)
    boxes = []
    hero_lift = _hop(clock - A.get("lift_off", 1e6), air, height) if A.get("type", "jump") == "jump" else 0 * t
    for i in range(len(t)):
        if planet_shot[i] or alts[i] > 400:
            boxes.append(None)
            continue
        hx, hy = ctx.hero[0], ctx.hero[1]
        z0 = float(hero_lift[i])
        pts = [camrig.project((hx + dx, hy + dy, z0 + dz), cams[i], tgts[i], lenses[i])
               for dx in (-0.35, 0.35) for dy in (-0.35, 0.35) for dz in (0.0, 1.85)]
        if any(p is None for p in pts):
            boxes.append(None)
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        b = [max(min(xs), 0), max(min(ys), 0), min(max(xs), 1080), min(max(ys), 1920)]
        boxes.append([round(v) for v in b] if (b[2] > b[0] and b[3] - b[1] > 110) else None)

    # ---- where
    where = []
    W = E.get("where", [])
    for x in t:
        s = ""
        for tw, txt in W:
            if x >= tw:
                s = txt
        where.append(s)

    tl = ", ".join(f"{k} {v:.2f}" for k, v in ctx.times.items() if isinstance(v, float) and v < 1e5)
    print(f"[everyone] people in the square and streets: {n_flat - 1:,}; Earth's push-back at the apex: "
          f"{pop_total * mass * height / M_EARTH:.3e} m")
    print(f"[everyone] times: {tl}")
    for i, s in enumerate(E["shots"]):
        f0 = int(round(s["from"] * fps))
        f1 = min(int(round(s["to"] * fps)) - 1, len(alts) - 1)
        if 0 <= f0 < len(alts):
            print(f"[everyone] shot {i:2d} {s['from']:5.1f}-{s['to']:5.1f} {s['type']:6s} altitude "
                  f"{alts[f0]:,.0f} -> {alts[max(f0, f1)]:,.0f} m")

    return {"fps": fps, "frames": ctx.nf, "ready": [int(v) for v in ready], "where": where,
            "countdown": countdown, "in_air": [int(v) for v in in_air], "airtime": airtime, "earth_m": earth_m,
            "mass_t": [int(v) for v in mass_t], "alt_m": [float(a) for a in alts], "subject_box": boxes,
            "events": ctx.events, "times": {k: round(float(v), 4) for k, v in ctx.times.items()}}
