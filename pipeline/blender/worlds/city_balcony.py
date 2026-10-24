"""World: a low-poly city seen from a 3rd-floor balcony, looking up an avenue toward a skyline and mountains.

Every object that an effect may show/hide is returned in info["static"] (with obj["rf_ud"] = its distance
from the camera in metres and obj["rf_size"] = its largest dimension) or info["movers"] (cars, people).
"""
import math
import random

import bpy
from mathutils import Vector

import rf_common as rf

PERIOD = 124.0          # block + road
ROAD_HALF = 12.0        # road is 24 m wide
SIDEWALK = 4.0
CITY_LIMIT_Y = 3300.0
FIELD_LIMIT_Y = 3800.0
DOWNTOWN = (250.0, 2400.0, 750.0)   # x, y, radius of the tower cluster
SIGHTLINE_DEG = 3.5                 # ordinary buildings stay below this angle so the skyline and mountains show

WALLS = [(0.32, 0.10, 0.06), (0.55, 0.24, 0.12), (0.62, 0.48, 0.32), (0.78, 0.72, 0.58),
         (0.45, 0.45, 0.45), (0.75, 0.60, 0.28), (0.70, 0.45, 0.40), (0.60, 0.62, 0.66)]


# ---------------------------------------------------------------- materials

def _building_color(nt, relative=False):
    """Window/wall pattern in metres. relative=True measures from the object origin so the pattern stays put on
    buildings that move (and lets obj["shattered"] black the windows out)."""
    geo = nt.node("ShaderNodeNewGeometry")
    pos = nt.node("ShaderNodeSeparateXYZ")
    nrm = nt.node("ShaderNodeSeparateXYZ")
    if relative:
        sub = nt.node("ShaderNodeVectorMath", operation="SUBTRACT")
        nt.links.new(geo.outputs["Position"], sub.inputs[0])
        nt.links.new(nt.node("ShaderNodeObjectInfo").outputs["Location"], sub.inputs[1])
        nt.links.new(sub.outputs["Vector"], pos.inputs[0])
    else:
        nt.links.new(geo.outputs["Position"], pos.inputs[0])
    nt.links.new(geo.outputs["Normal"], nrm.inputs[0])
    tower = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="tower").outputs["Fac"]
    isx = nt.math("GREATER_THAN", nt.math("ABSOLUTE", nrm.outputs["X"]), 0.5)
    u = nt.math("ADD", nt.math("MULTIPLY", pos.outputs["X"], nt.math("SUBTRACT", 1.0, isx)),
                nt.math("MULTIPLY", pos.outputs["Y"], isx))
    z = pos.outputs["Z"]
    vert = nt.math("LESS_THAN", nt.math("ABSOLUTE", nrm.outputs["Z"]), 0.5)
    fx = nt.math("FRACT", nt.math("DIVIDE", u, 3.2))
    fy = nt.math("FRACT", nt.math("DIVIDE", z, 3.4))
    # towers are nearly all glass: widen the window band
    lo_x = nt.math("SUBTRACT", 0.18, nt.math("MULTIPLY", tower, 0.12))
    lo_y = nt.math("SUBTRACT", 0.28, nt.math("MULTIPLY", tower, 0.18))
    wx = nt.math("MULTIPLY", nt.math("GREATER_THAN", fx, lo_x), nt.math("LESS_THAN", fx, nt.math("SUBTRACT", 1.0, lo_x)))
    wy = nt.math("MULTIPLY", nt.math("GREATER_THAN", fy, lo_y), nt.math("LESS_THAN", fy, 0.88))
    upper = nt.math("GREATER_THAN", z, 4.2)
    win = nt.math("MULTIPLY", nt.math("MULTIPLY", wx, wy), nt.math("MULTIPLY", upper, vert))
    # shopfronts on the ground floor
    sx = nt.math("FRACT", nt.math("DIVIDE", u, 6.0))
    shop = nt.math("MULTIPLY", nt.band(sx, 0.08, 0.92), nt.band(z, 0.6, 3.3))
    shop = nt.math("MULTIPLY", shop, vert)
    win = nt.math("MAXIMUM", win, shop)

    rnd = nt.object_random()
    wall = nt.ramp(rnd, [(i / len(WALLS), c) for i, c in enumerate(WALLS)], constant=True)
    wall = nt.mix_color(tower, wall, (0.55, 0.60, 0.66, 1.0))
    ground_floor = nt.math("LESS_THAN", z, 4.2)
    wall_dark = nt.mix_color(0.45, wall, (0.08, 0.08, 0.09, 1.0))
    wall = nt.mix_color(ground_floor, wall, wall_dark)

    cell = nt.math("ADD", nt.math("MULTIPLY", nt.math("FLOOR", nt.math("DIVIDE", u, 3.2)), 7.13),
                   nt.math("MULTIPLY", nt.math("FLOOR", nt.math("DIVIDE", z, 3.4)), 13.7))
    cell = nt.math("ADD", cell, nt.math("MULTIPLY", rnd, 97.0))
    wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="1D")
    nt.links.new(cell, wn.inputs["W"])
    glass = nt.ramp(wn.outputs["Value"], [(0.0, (0.04, 0.05, 0.07)), (0.65, (0.10, 0.13, 0.18)),
                                          (1.0, (0.40, 0.48, 0.58))])
    if relative:
        shattered = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="shattered").outputs["Fac"]
        glass = nt.mix_color(shattered, glass, (0.004, 0.004, 0.005, 1.0))
    col = nt.mix_color(win, wall, glass)
    roof = nt.math("GREATER_THAN", nrm.outputs["Z"], 0.5)
    col = nt.mix_color(roof, col, (0.24, 0.24, 0.25, 1.0))
    nt._win = win
    return col


def _building_rough(nt):
    return nt.math("SUBTRACT", 0.85, nt.math("MULTIPLY", nt._win, 0.65))


def _ramp_from_random(stops):
    return lambda nt: nt.ramp(nt.object_random(), stops)


def make_materials(relative=False):
    M = {}
    M["building"] = rf.make_material("building", lambda nt: _building_color(nt, relative), rough=_building_rough)
    M["asphalt"] = rf.make_material("asphalt", (0.075, 0.075, 0.08), rough=0.92)
    M["sidewalk"] = rf.make_material("sidewalk", (0.45, 0.44, 0.42))
    M["lot"] = rf.make_material("lot", (0.34, 0.33, 0.31))
    M["mark_w"] = rf.make_material("mark_white", (0.85, 0.85, 0.82))
    M["mark_y"] = rf.make_material("mark_yellow", (0.85, 0.62, 0.10))
    M["field"] = rf.make_material("field", _ramp_from_random([(0.0, (0.22, 0.32, 0.14)), (1.0, (0.40, 0.42, 0.20))]))
    M["leaf"] = rf.make_material("leaf", _ramp_from_random([(0.0, (0.08, 0.22, 0.06)), (1.0, (0.22, 0.40, 0.10))]))
    M["trunk"] = rf.make_material("trunk", (0.22, 0.14, 0.08))
    M["metal"] = rf.make_material("metal_dark", (0.07, 0.07, 0.08), rough=0.45, metallic=0.6)
    M["paint"] = rf.make_material("car_paint", lambda nt: nt.object_color(), rough=0.3, metallic=0.4)
    M["glass"] = rf.make_material("glass", (0.03, 0.04, 0.05), rough=0.1)
    M["tire"] = rf.make_material("tire", (0.02, 0.02, 0.02), rough=0.9)
    M["shirt"] = rf.make_material("shirt", lambda nt: nt.object_color())
    M["pants"] = rf.make_material("pants", _ramp_from_random([(0.0, (0.04, 0.05, 0.10)), (0.5, (0.18, 0.18, 0.20)),
                                                               (1.0, (0.40, 0.33, 0.22))]))
    M["skin"] = rf.make_material("skin", _ramp_from_random([(0.0, (0.12, 0.06, 0.035)), (0.5, (0.45, 0.25, 0.15)),
                                                             (1.0, (0.80, 0.55, 0.42))]))
    M["cloud"] = rf.make_material("cloud", (0.95, 0.95, 0.97), rough=1.0, emission=((1, 1, 1), 0.35), haze=0.35)
    M["mountain"] = rf.make_material("mountain", _ramp_from_random([(0.0, (0.12, 0.17, 0.12)), (1.0, (0.22, 0.25, 0.19))]),
                                     haze=0.55)
    M["snow"] = rf.make_material("snow", (0.85, 0.87, 0.9), haze=0.45)
    M["rail"] = rf.make_material("rail", (0.85, 0.85, 0.82), rough=0.5, haze=0.0)
    M["floor"] = rf.make_material("balcony_floor", (0.50, 0.30, 0.20), haze=0.0)
    M["mug"] = rf.make_material("mug", (0.88, 0.88, 0.86), rough=0.25, haze=0.0)
    M["coffee"] = rf.make_material("coffee", (0.05, 0.025, 0.01), rough=0.1, haze=0.0)
    M["sig_red"] = rf.make_material("signal_red", (0.1, 0.0, 0.0), emission=((1.0, 0.05, 0.02), 6.0))
    M["sig_green"] = rf.make_material("signal_green", (0.0, 0.1, 0.0), emission=((0.1, 1.0, 0.3), 5.0))
    return M


# ---------------------------------------------------------------- shared meshes

def _chunk_mesh(M, detailed):
    mb = rf.MeshBuilder()
    ASPH, SIDE, LOT, MW, MY = 0, 1, 2, 3, 4
    h = PERIOD / 2
    mb.box(-h, -h, -0.2, h, h, 0.0, ASPH)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = sorted((sx * ROAD_HALF, sx * h))
            y0, y1 = sorted((sy * ROAD_HALF, sy * h))
            mb.box(x0, y0, 0.0, x1, y1, 0.15, SIDE)
            lx0, lx1 = (x0 + SIDEWALK, x1) if sx > 0 else (x0, x1 - SIDEWALK)
            ly0, ly1 = (y0 + SIDEWALK, y1) if sy > 0 else (y0, y1 - SIDEWALK)
            mb.box(lx0, ly0, 0.15, lx1, ly1, 0.17, LOT)
    if detailed:
        z0, z1 = 0.0, 0.012
        for s in (-1, 1):
            a0, a1 = sorted((s * 17.0, s * h))
            # double yellow centre lines on both roads
            for off in (-0.25, 0.1):
                mb.box(off, a0, z0, off + 0.15, a1, z1, MY)
                mb.box(a0, off, z0, a1, off + 0.15, z1, MY)
            # dashed lane lines
            for lane in (-5.5, 5.5):
                y = a0
                while y + 3 <= a1:
                    mb.box(lane - 0.08, y, z0, lane + 0.08, y + 3, z1, MW)
                    mb.box(y, lane - 0.08, z0, y + 3, lane + 0.08, z1, MW)
                    y += 9
            # crosswalks
            c0, c1 = sorted((s * 13.0, s * 16.5))
            x = -11.0
            while x < 11.0:
                mb.box(x, c0, z0, x + 0.7, c1, z1, MW)
                mb.box(c0, x, z0, c1, x + 0.7, z1, MW)
                x += 1.4
    return mb.build("chunk_city" + ("" if detailed else "_lod"),
                    [M["asphalt"], M["sidewalk"], M["lot"], M["mark_w"], M["mark_y"]])


def _field_mesh(M):
    mb = rf.MeshBuilder()
    h = PERIOD / 2
    mb.box(-h, -h, -0.2, h, h, 0.05, 0)
    return mb.build("chunk_field", [M["field"]])


def _unit_cube(M):
    mb = rf.MeshBuilder()
    mb.box(-0.5, -0.5, 0.0, 0.5, 0.5, 1.0, 0)
    return mb.build("building", [M["building"]])


def _tree_mesh(M, rnd):
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 2.8, 0.18, 6, 0)
    mb.ico((0, 0, 4.4), (1.9, 1.9, 2.3), 1, 1, jitter=0.15, rnd=rnd)
    return mb.build("tree", [M["trunk"], M["leaf"]])


def _lamp_mesh(M):
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 7.0, 0.08, 6, 0)
    mb.box(0, -0.05, 6.9, 1.7, 0.05, 7.0, 0)
    mb.box(1.3, -0.18, 6.75, 1.9, 0.18, 6.92, 0)
    return mb.build("lamp", [M["metal"]])


def _signal_mesh(M):
    mb = rf.MeshBuilder()
    mb.cyl(0, 0, 0, 5.6, 0.1, 6, 0)
    mb.box(0, -0.06, 5.4, 4.5, 0.06, 5.55, 0)
    mb.box(4.2, -0.2, 4.3, 4.55, 0.15, 5.4, 0)
    mb.box(4.25, -0.24, 5.05, 4.5, -0.2, 5.3, 1)
    mb.box(4.25, -0.24, 4.4, 4.5, -0.2, 4.65, 2)
    return mb.build("signal", [M["metal"], M["sig_red"], M["sig_green"]])


def _car_mesh(M):
    mb = rf.MeshBuilder()
    mb.box(-0.9, -2.2, 0.3, 0.9, 2.2, 0.95, 0)
    mb.box(-0.8, -1.2, 0.95, 0.8, 0.9, 1.42, 1)
    mb.box(-0.78, -1.1, 1.42, 0.78, 0.8, 1.48, 0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = sorted((sx * 0.72, sx * 0.95))
            y0, y1 = sorted((sy * 1.15, sy * 1.75))
            mb.box(x0, y0, 0.0, x1, y1, 0.6, 2)
    return mb.build("car", [M["paint"], M["glass"], M["tire"]])


def _bus_mesh(M):
    mb = rf.MeshBuilder()
    mb.box(-1.25, -5.6, 0.4, 1.25, 5.6, 3.1, 0)
    mb.box(-1.27, -5.3, 1.7, 1.27, 5.62, 2.6, 1)
    for sy in (-3.8, 3.8):
        mb.box(-1.3, sy - 0.5, 0.0, 1.3, sy + 0.5, 0.9, 2)
    return mb.build("bus", [M["paint"], M["glass"], M["tire"]])


def _person_mesh(M):
    mb = rf.MeshBuilder()
    mb.box(-0.17, -0.10, 0.0, -0.02, 0.10, 0.86, 1)
    mb.box(0.02, -0.10, 0.0, 0.17, 0.10, 0.86, 1)
    mb.box(-0.21, -0.12, 0.84, 0.21, 0.12, 1.45, 0)
    mb.box(-0.29, -0.07, 0.9, -0.21, 0.07, 1.42, 0)
    mb.box(0.21, -0.07, 0.9, 0.29, 0.07, 1.42, 0)
    mb.ico((0, 0, 1.6), (0.12, 0.12, 0.14), 1, 2)
    return mb.build("person", [M["shirt"], M["pants"], M["skin"]])


# ---------------------------------------------------------------- builder

def build(spec):
    W = spec["world"]
    rnd = random.Random(W.get("seed", 1))
    camspec = W["camera"]
    cam_pos = Vector(camspec["location"])
    heading = camspec["heading_deg"]
    hfov_half = math.degrees(math.atan(18.0 * (1080 / 1920) / camspec["lens_mm"]))
    scene = bpy.context.scene

    col_city = rf.new_collection("City")
    col_life = rf.new_collection("Life")
    col_sky = rf.new_collection("Sky")
    col_near = rf.new_collection("Balcony")

    rf.setup_sky_world(scene)
    rf.add_sun(col_sky, heading_deg=245.0, elevation_deg=36.0, energy=4.2)
    cam = rf.add_camera(col_near, cam_pos, heading, camspec["pitch_deg"], camspec["lens_mm"])

    M = make_materials()
    mesh_chunk = _chunk_mesh(M, True)
    mesh_chunk_lod = _chunk_mesh(M, False)
    mesh_field = _field_mesh(M)
    mesh_cube = _unit_cube(M)
    mesh_tree = _tree_mesh(M, rnd)
    mesh_lamp = _lamp_mesh(M)
    mesh_signal = _signal_mesh(M)
    mesh_car = _car_mesh(M)
    mesh_bus = _bus_mesh(M)
    mesh_person = _person_mesh(M)

    static, movers = [], []

    def heading_of(x, y):
        return math.degrees(math.atan2(x - cam_pos.x, y - cam_pos.y))

    def in_view(x, y, margin=10.0):
        if math.hypot(x - cam_pos.x, y - cam_pos.y) < 70:
            return True
        if y < cam_pos.y - 5:
            return False
        rel = heading_of(x, y) - heading
        return -hfov_half - margin <= rel <= hfov_half + margin

    def rect_in_view(x0, y0, x1, y1, margin=10.0):
        pts = ((x0, y0), (x1, y0), (x0, y1), (x1, y1), ((x0 + x1) / 2, (y0 + y1) / 2))
        return any(in_view(x, y, margin) for x, y in pts)

    def box_dist(x0, y0, z0, x1, y1, z1):
        dx = max(x0 - cam_pos.x, 0.0, cam_pos.x - x1)
        dy = max(y0 - cam_pos.y, 0.0, cam_pos.y - y1)
        dz = max(z0 - cam_pos.z, 0.0, cam_pos.z - z1)
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def register(ob, ud, size):
        ob["rf_ud"] = float(ud)
        ob["rf_size"] = float(size)
        ob["glitch"] = 0.0
        static.append(ob)
        return ob

    # ---- ground chunks
    for i in range(-30, 31):
        for j in range(-1, int(FIELD_LIMIT_Y // PERIOD) + 1):
            cx, cy = PERIOD * i, PERIOD * j
            h = PERIOD / 2
            if not rect_in_view(cx - h, cy - h, cx + h, cy + h, margin=14):
                continue
            d = (Vector((cx, cy, 0.0)) - cam_pos).length
            if cy > CITY_LIMIT_Y:
                mesh = mesh_field
            else:
                mesh = mesh_chunk if d < 900 else mesh_chunk_lod
            ob = rf.add_object(f"chunk_{i}_{j}", mesh, col_city, (cx, cy, 0.0))
            register(ob, d, PERIOD)

    # ---- buildings
    def add_building(x0, y0, x1, y1, height, tower=False):
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ob = rf.add_object("bldg", mesh_cube, col_city, (cx, cy, 0.15), (x1 - x0, y1 - y0, height))
        ob["tower"] = 1.0 if tower else 0.0
        register(ob, box_dist(x0, y0, 0.0, x1, y1, height), max(height, x1 - x0, y1 - y0))
        return ob

    def split(a0, a1, n, gap_max):
        cuts = sorted(rnd.uniform(0.25, 0.75) for _ in range(n - 1)) if n > 1 else []
        edges = [a0] + [a0 + (a1 - a0) * (k + 1) / n + (c - 0.5) * (a1 - a0) / n * 0.6 for k, c in enumerate(cuts)] + [a1]
        out = []
        for k in range(n):
            g = rnd.uniform(0.0, gap_max)
            out.append((edges[k] + (g if k else 0.0), edges[k + 1] - (g if k < n - 1 else 0.0)))
        return out

    for i in range(-30, 31):
        for j in range(-1, int(CITY_LIMIT_Y // PERIOD) + 1):
            bx0, bx1 = PERIOD * i + ROAD_HALF + SIDEWALK, PERIOD * (i + 1) - ROAD_HALF - SIDEWALK
            by0, by1 = PERIOD * j + ROAD_HALF + SIDEWALK, PERIOD * (j + 1) - ROAD_HALF - SIDEWALK
            if not rect_in_view(bx0, by0, bx1, by1, margin=8):
                continue
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            if bx0 < cam_pos.x < bx1 and by0 - 10 < cam_pos.y < by1:
                continue  # the camera's own block is behind us
            d = math.hypot(cx - cam_pos.x, cy - cam_pos.y)
            dd = math.hypot(cx - DOWNTOWN[0], cy - DOWNTOWN[1])
            if dd < DOWNTOWN[2]:
                peak = 90 + 260 * math.exp(-(dd ** 2) / (2 * 380.0 ** 2))
                for (x0, x1) in split(bx0, bx1, 2, 8):
                    for (y0, y1) in split(by0, by1, 2, 8):
                        if rnd.random() < 0.15:
                            continue
                        hgt = peak * rnd.uniform(0.55, 1.15)
                        inset = rnd.uniform(2, 8)
                        add_building(x0 + inset, y0 + inset, x1 - inset, y1 - inset, hgt, tower=True)
                continue
            if d > 400 and rnd.random() < 0.05:
                continue  # the odd empty lot / park
            frontage = abs(cx) < 140
            if d < 650:
                nx, ny, hmin, hmax = 3, 3, 12, 60 if frontage else 42
            elif d < 1500:
                nx, ny, hmin, hmax = 2, 2, 12, 50
            else:
                nx, ny, hmin, hmax = 1, rnd.choice((1, 2)), 10, 40
            for a, (x0, x1) in enumerate(split(bx0, bx1, nx, 3)):
                for b, (y0, y1) in enumerate(split(by0, by1, ny, 3)):
                    if nx == 3 and a == 1 and b == 1:
                        continue  # courtyard
                    near = max(math.hypot(max(x0 - cam_pos.x, 0, cam_pos.x - x1),
                                          max(y0 - cam_pos.y, 0, cam_pos.y - y1)), 1.0)
                    cap = cam_pos.z + near * math.tan(math.radians(SIGHTLINE_DEG))
                    hgt = min(rnd.uniform(hmin, hmax), cap * rnd.uniform(0.75, 1.0))
                    add_building(x0, y0, x1, y1, max(hgt, 8.0))

    # ---- mountains (one mesh each, low-poly crags)
    for k in range(10):
        my = rnd.uniform(3550, 3850)
        h_rel = -18 + k * 7.5 + rnd.uniform(-2, 2)
        mx = cam_pos.x + (my - cam_pos.y) * math.tan(math.radians(heading + h_rel))
        rx, ry, rz = rnd.uniform(700, 1300), rnd.uniform(300, 450), rnd.uniform(500, 1050)
        mb = rf.MeshBuilder()
        mb.ico((0, 0, -rz * 0.2), (rx, ry, rz), 2, 0, jitter=0.12, rnd=rnd)
        if rz > 650:
            mb.ico((0, 0, rz * 0.66), (rx * 0.2, ry * 0.25, rz * 0.15), 1, 1, jitter=0.1, rnd=rnd)
        ob = rf.add_object(f"mountain_{k}", mb.build(f"mountain_{k}", [M["mountain"], M["snow"]]), col_city, (mx, my, 0.0))
        register(ob, box_dist(mx - rx, my - ry, 0, mx + rx, my + ry, rz), 2 * rx)

    # ---- clouds
    for k in range(14):
        dist = rnd.uniform(1100, 3600)
        h_rel = rnd.uniform(-hfov_half - 6, hfov_half + 6)
        a = math.radians(heading + h_rel)
        x, y, z = cam_pos.x + dist * math.sin(a), cam_pos.y + dist * math.cos(a), rnd.uniform(450, 1100)
        mb = rf.MeshBuilder()
        for _ in range(rnd.randint(3, 6)):
            mb.ico((rnd.uniform(-90, 90), rnd.uniform(-40, 40), rnd.uniform(-8, 18)),
                   (rnd.uniform(40, 90), rnd.uniform(30, 60), rnd.uniform(14, 30)), 1, 0, jitter=0.15, rnd=rnd)
        ob = rf.add_object(f"cloud_{k}", mb.build(f"cloud_{k}", [M["cloud"]]), col_sky, (x, y, z), rotation_z=rnd.uniform(0, 3.14))
        register(ob, (Vector((x, y, z)) - cam_pos).length, 180)

    # ---- street furniture
    for side in (-1, 1):
        y = 18.0
        while y < 420:
            x = side * (ROAD_HALF + 1.6)
            if in_view(x, y, 6):
                register(rf.add_object("tree", mesh_tree, col_city, (x, y, 0.15), rotation_z=rnd.uniform(0, 6.28)),
                         box_dist(x - 2, y - 2, 0, x + 2, y + 2, 6.7), 6.7)
            y += rnd.uniform(9, 13)
        y = 20.0
        while y < 420:
            x = side * (ROAD_HALF + 0.6)
            if in_view(x, y, 6):
                register(rf.add_object("lamp", mesh_lamp, col_city, (x, y, 0.15), rotation_z=0.0 if side < 0 else math.pi),
                         box_dist(x - 1.9, y - 0.2, 0, x + 1.9, y + 0.2, 7.0), 7.0)
            y += 32
    for k in range(-6, 12):
        x = 20.0 + k * 11 + rnd.uniform(-2, 2)
        if abs(x) < 18:
            continue
        y = ROAD_HALF + 1.6
        if in_view(x, y, 6):
            register(rf.add_object("tree", mesh_tree, col_city, (x, y, 0.15), rotation_z=rnd.uniform(0, 6.28)),
                     box_dist(x - 2, y - 2, 0, x + 2, y + 2, 6.7), 6.7)
    for (sx, sy, rot) in ((-1, 1, 0.0), (1, -1, math.pi), (1, 1, -math.pi / 2), (-1, -1, math.pi / 2)):
        x, y = sx * (ROAD_HALF + 1.0), sy * (ROAD_HALF + 1.0)
        register(rf.add_object("signal", mesh_signal, col_city, (x, y, 0.15), rotation_z=rot),
                 box_dist(x - 5, y - 5, 0, x + 5, y + 5, 5.6), 5.6)

    # ---- parked cars on the cross street
    palette = [(0.6, 0.02, 0.02), (0.02, 0.05, 0.25), (0.75, 0.75, 0.75), (0.05, 0.05, 0.05),
               (0.9, 0.9, 0.88), (0.85, 0.6, 0.05), (0.1, 0.3, 0.12), (0.3, 0.32, 0.35)]
    for side in (-1, 1):
        x = 22.0
        while x < 300:
            y = side * 9.6
            if in_view(x, y, 4) and rnd.random() < 0.7:
                ob = rf.add_object("parked", mesh_car, col_life, (x, y, 0.0), rotation_z=math.pi / 2)
                ob.color = (*rnd.choice(palette), 1.0)
                register(ob, box_dist(x - 2.2, y - 0.9, 0, x + 2.2, y + 0.9, 1.5), 4.4)
            x += rnd.uniform(6, 9)

    # ---- moving traffic on the avenue (northbound x>0, southbound x<0)
    rf.set_interp("LINEAR")
    fps = spec["fps"]
    n_frames = int(round(spec["render_until"] * fps))
    t_end = (n_frames - 1) / fps
    for lane_x, direction in ((2.75, 1), (8.25, 1), (-2.75, -1), (-8.25, -1)):
        speed = rnd.uniform(10.0, 13.0) * (0.85 if abs(lane_x) > 5 else 1.0)
        y = -150.0 if direction > 0 else -60.0
        while y < 2700:
            y += rnd.uniform(22, 95)
            bus = rnd.random() < 0.1
            ob = rf.add_object("bus" if bus else "car", mesh_bus if bus else mesh_car, col_life,
                               (lane_x, y, 0.0), rotation_z=0.0 if direction > 0 else math.pi)
            ob.color = (*((0.85, 0.65, 0.05) if bus else rnd.choice(palette)), 1.0)
            ob["glitch"] = 0.0
            ob["rf_size"] = 11.0 if bus else 4.4
            v = (0.0, direction * speed, 0.0)
            ob.keyframe_insert("location", frame=1)
            ob.location = (lane_x, y + v[1] * t_end, 0.0)
            ob.keyframe_insert("location", frame=n_frames)
            rf.set_interpolation(ob, "LINEAR", "location")
            movers.append((ob, (lane_x, y, 0.75), v))

    # ---- pedestrians
    shirts = [(0.7, 0.1, 0.1), (0.1, 0.2, 0.6), (0.9, 0.9, 0.9), (0.15, 0.15, 0.15), (0.9, 0.6, 0.1),
              (0.2, 0.5, 0.3), (0.6, 0.3, 0.6), (0.85, 0.75, 0.55), (0.3, 0.6, 0.8)]
    walk_paths = []
    for side in (-1, 1):
        for _ in range(34):
            x = side * (ROAD_HALF + rnd.uniform(0.6, 3.4))
            walk_paths.append(((x, rnd.uniform(-40, 260)), (0.0, rnd.choice((-1, 1)))))
    for _ in range(36):
        y = ROAD_HALF + rnd.uniform(0.6, 3.4)
        walk_paths.append(((rnd.uniform(-90, 170), y), (rnd.choice((-1, 1)), 0.0)))
    for (x, y), (ux, uy) in walk_paths:
        speed = rnd.uniform(1.05, 1.6)
        ob = rf.add_object("person", mesh_person, col_life, (x, y, 0.15),
                           rotation_z=math.atan2(-ux, uy))
        ob.color = (*rnd.choice(shirts), 1.0)
        ob["glitch"] = 0.0
        ob["rf_size"] = 1.8
        s = rnd.uniform(0.92, 1.08)
        ob.scale = (s, s, s)
        v = (ux * speed, uy * speed, 0.0)
        ob.keyframe_insert("location", frame=1)
        ob.location = (x + v[0] * t_end, y + v[1] * t_end, 0.15)
        ob.keyframe_insert("location", frame=n_frames)
        rf.set_interpolation(ob, "LINEAR", "location")
        rf.add_sine(ob, "location", 2, 0.035, fps / (speed * 1.7), rnd.uniform(0, 6.28))
        movers.append((ob, (x, y, 1.0), v))

    # ---- the balcony you are standing on
    rail_y = cam_pos.y + 0.8
    floor_z = cam_pos.z - 1.6
    mb = rf.MeshBuilder()
    mb.box(cam_pos.x - 2.2, rail_y - 0.03, floor_z + 1.0, cam_pos.x + 2.2, rail_y + 0.05, floor_z + 1.06, 0)
    x = cam_pos.x - 2.2
    while x <= cam_pos.x + 2.2:
        mb.box(x - 0.012, rail_y - 0.012, floor_z, x + 0.012, rail_y + 0.012, floor_z + 1.0, 0)
        x += 0.13
    mb.box(cam_pos.x - 2.2, rail_y - 0.02, floor_z + 0.1, cam_pos.x + 2.2, rail_y + 0.02, floor_z + 0.14, 0)
    rail = rf.add_object("railing", mb.build("railing", [M["rail"]]), col_near)
    register(rail, 0.8, 1.0)
    mb = rf.MeshBuilder()
    mb.box(cam_pos.x - 2.3, cam_pos.y - 0.8, floor_z - 0.25, cam_pos.x + 2.3, rail_y + 0.1, floor_z, 0)
    floor = rf.add_object("balcony_floor", mb.build("balcony_floor", [M["floor"]]), col_near)
    register(floor, 1.6, 4.6)
    if W.get("props", {}).get("mug", True):
        mx, my, mz = cam_pos.x - 0.06, rail_y + 0.01, floor_z + 1.06
        mb = rf.MeshBuilder()
        mb.cyl(0, 0, 0, 0.095, 0.042, 14, 0)
        mb.cyl(0, 0, 0.08, 0.088, 0.036, 14, 1)
        mb.box(0.038, -0.008, 0.025, 0.062, 0.008, 0.075, 0)
        mug = rf.add_object("mug", mb.build("mug", [M["mug"], M["coffee"]]), col_near, (mx, my, mz), rotation_z=0.5)
        ud = spec.get("effect", {}).get("last_object_ud", {}).get("mug", 0.75)
        register(mug, ud, 0.1)

    # editor-style grid revealed when everything is gone
    mb = rf.MeshBuilder()
    mb.box(-3000, -3000, -0.01, 3000, 3000, 0.0, 0)
    grid = rf.add_object("void_grid", mb.build("void_grid", [rf.make_grid_material("void_grid")]), col_sky,
                         (cam_pos.x, cam_pos.y, -45.0))
    grid.hide_render = True

    print(f"[city_balcony] static={len(static)} movers={len(movers)}")
    return {"camera": cam, "cam_pos": cam_pos, "static": static, "movers": movers, "grid": grid,
            "world": scene.world}
