"""Shared Blender helpers for the pipeline (runs inside Blender 4.5). Imported everywhere as `rf`."""
import math

import bmesh
import bpy

HAZE_COLOR = (0.70, 0.76, 0.85, 1.0)
HAZE_DIST = 5000.0
HAZE_MAX = 0.85
HAZE_SCENE = False      # look.init_haze() turns this on: haze then follows the rf_haze_* scene properties


# ---------------------------------------------------------------- scene setup

def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                 bpy.data.worlds, bpy.data.actions, bpy.data.curves):
        for d in list(coll):
            coll.remove(d)


def new_collection(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def setup_render(scene, spec, build_dir):
    fps = spec["fps"]
    scene.render.fps = fps
    scene.frame_start = 1
    scene.frame_end = int(round(spec["render_until"] * fps))
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = 1080
    scene.render.resolution_y = 1920
    scene.render.resolution_percentage = 100
    R = spec.get("render", {})
    scene.render.use_motion_blur = bool(R.get("motion_blur", False))
    if scene.render.use_motion_blur:
        scene.render.motion_blur_shutter = R.get("shutter", 0.5)
        # low depth scale stops fast backgrounds bleeding onto foreground objects (the camera-locked car)
        for prop, val in (("motion_blur_max", 64), ("motion_blur_steps", 1),
                          ("motion_blur_depth_scale", R.get("blur_depth_scale", 0.0))):
            try:
                setattr(scene.eevee, prop, val)
            except AttributeError:
                pass
    scene.render.film_transparent = False
    scene.eevee.taa_render_samples = R.get("samples", 16)
    for prop, val in (("shadow_pool_size", "1024"), ("shadow_resolution_scale", R.get("shadow_scale", 1.0))):
        try:
            setattr(scene.eevee, prop, val)
        except (AttributeError, TypeError):
            pass
    scene.render.image_settings.file_format = "JPEG"
    scene.render.image_settings.quality = 92
    scene.render.filepath = str(build_dir / "frames" / "f_")
    scene.render.use_overwrite = False  # lets an interrupted render resume where it stopped
    scene.render.use_placeholder = True
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try:
            scene.view_settings.look = look
            break
        except TypeError:
            continue


def set_interp(kind):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind


def all_fcurves(idblock):
    """All F-curves animating an ID (object, world node tree...), with 4.4+ slotted actions."""
    ad = getattr(idblock, "animation_data", None)
    if not ad or not ad.action:
        return []
    try:
        from bpy_extras import anim_utils
        cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
        if cb is not None:
            return list(cb.fcurves)
    except Exception:
        pass
    try:
        return list(ad.action.fcurves)
    except Exception:
        return []


def get_fcurve(obj, data_path, index=0):
    for fc in all_fcurves(obj):
        if fc.data_path == data_path and fc.array_index == index:
            return fc
    return None


def key_series(idblock, data_path, index, frames, values, interp="LINEAR"):
    """Bake one F-curve with a value per frame (much faster than keyframe_insert per frame).

    keyframe_insert() on the first frame creates the F-curve (and the 4.4+ action slot); the rest are bulk-added.
    For a custom property use data_path '["name"]' and index 0.
    """
    try:
        idblock.keyframe_insert(data_path, index=index, frame=frames[0])
    except TypeError:  # scalar property (custom props, lens...): Blender wants index -1
        idblock.keyframe_insert(data_path, index=-1, frame=frames[0])
    fc = next(f for f in all_fcurves(idblock) if f.data_path == data_path and f.array_index == max(index, 0))
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(frames))
    fc.keyframe_points.foreach_set("co", [c for f, v in zip(frames, values) for c in (float(f), float(v))])
    for kp in fc.keyframe_points:
        kp.interpolation = interp
    fc.update()
    return fc


def set_interpolation(idblock, kind, data_path=None):
    """keyframe_insert() ignores the user default, so set interpolation on the keys explicitly."""
    for fc in all_fcurves(idblock):
        if data_path is None or fc.data_path == data_path:
            for kp in fc.keyframe_points:
                kp.interpolation = kind


def add_sine(obj, data_path, index, amplitude, period_frames, phase=0.0):
    fc = get_fcurve(obj, data_path, index)
    if fc is None:
        return False
    m = fc.modifiers.new("FNGENERATOR")
    m.function_type = "SIN"
    m.amplitude = amplitude
    m.phase_multiplier = 2 * math.pi / period_frames
    m.phase_offset = phase
    m.use_additive = True
    return True


def add_noise(obj, data_path, index, strength, scale, frame_range=None, blend=0):
    fc = get_fcurve(obj, data_path, index)
    if fc is None:
        return False
    m = fc.modifiers.new("NOISE")
    m.strength = strength
    m.scale = scale
    m.phase = hash((obj.name, data_path, index, strength)) % 1000
    if frame_range:
        m.use_restricted_range = True
        m.frame_start, m.frame_end = frame_range
        m.blend_in = blend
    return True


# ---------------------------------------------------------------- meshes

class MeshBuilder:
    """Accumulates low-poly primitives into one mesh with per-face material indices."""

    def __init__(self):
        self.verts, self.faces, self.mats = [], [], []

    def box(self, x0, y0, z0, x1, y1, z1, mat=0):
        b = len(self.verts)
        self.verts += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                       (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        for q in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self.faces.append(tuple(b + i for i in q))
            self.mats.append(mat)

    def cyl(self, cx, cy, z0, z1, r, seg=8, mat=0, r_top=None):
        rt = r if r_top is None else r_top
        b = len(self.verts)
        for rad, z in ((r, z0), (rt, z1)):
            for k in range(seg):
                a = 2 * math.pi * k / seg
                self.verts.append((cx + rad * math.cos(a), cy + rad * math.sin(a), z))
        for k in range(seg):
            k2 = (k + 1) % seg
            self.faces.append((b + k, b + k2, b + seg + k2, b + seg + k))
            self.mats.append(mat)
        self.faces.append(tuple(b + seg + k for k in range(seg)))
        self.mats.append(mat)
        self.faces.append(tuple(b + k for k in reversed(range(seg))))
        self.mats.append(mat)

    def ico(self, center, radii, subdiv=1, mat=0, jitter=0.0, rnd=None):
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        bm.verts.ensure_lookup_table()
        bm.verts.index_update()
        b = len(self.verts)
        for v in bm.verts:
            s = 1.0 + (rnd.uniform(-jitter, jitter) if (jitter and rnd) else 0.0)
            self.verts.append((center[0] + v.co.x * radii[0] * s,
                               center[1] + v.co.y * radii[1] * s,
                               center[2] + v.co.z * radii[2] * s))
        for f in bm.faces:
            self.faces.append(tuple(b + v.index for v in f.verts))
            self.mats.append(mat)
        bm.free()

    def cyl_x(self, cx, cy, cz, r, half_w, seg=16, mat=0, cap_mat=None):
        """Cylinder whose axis runs along X (wheels)."""
        b = len(self.verts)
        for x in (cx - half_w, cx + half_w):
            for k in range(seg):
                a = 2 * math.pi * k / seg
                self.verts.append((x, cy + r * math.cos(a), cz + r * math.sin(a)))
        for k in range(seg):
            k2 = (k + 1) % seg
            self.faces.append((b + k, b + seg + k, b + seg + k2, b + k2))
            self.mats.append(mat)
        cm = mat if cap_mat is None else cap_mat
        self.faces.append(tuple(b + seg + k for k in range(seg)))
        self.mats.append(cm)
        self.faces.append(tuple(b + k for k in reversed(range(seg))))
        self.mats.append(cm)

    def loft(self, sections, mat_fn, cap=True, cap_mat=0):
        """Connect closed cross-sections [(y, [(x, z), ...]), ...] (same point count) into a solid.

        mat_fn(section_index, point_index) -> material index for the quad that starts there.
        """
        n = len(sections[0][1])
        b = len(self.verts)
        for y, pts in sections:
            for x, z in pts:
                self.verts.append((x, y, z))
        for s in range(len(sections) - 1):
            for k in range(n):
                k2 = (k + 1) % n
                self.faces.append((b + s * n + k, b + s * n + k2, b + (s + 1) * n + k2, b + (s + 1) * n + k))
                self.mats.append(mat_fn(s, k))
        if cap:
            self.faces.append(tuple(b + k for k in range(n)))
            self.mats.append(cap_mat)
            last = (len(sections) - 1) * n
            self.faces.append(tuple(b + last + k for k in reversed(range(n))))
            self.mats.append(cap_mat)

    def build(self, name, materials, fix_normals=False, smooth=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.verts, [], self.faces)
        for m in materials:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", self.mats)
        if fix_normals:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(me)
            bm.free()
        if smooth:
            me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.update()
        return me


def add_object(name, mesh, collection, location=(0, 0, 0), scale=(1, 1, 1), rotation_z=0.0):
    ob = bpy.data.objects.new(name, mesh)
    ob.location = location
    ob.scale = scale
    ob.rotation_euler = (0.0, 0.0, rotation_z)
    collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- materials

def _sock(coll, identifier, name=None, typ=None):
    for s in coll:
        if s.identifier == identifier:
            return s
    for s in coll:
        if s.name == name and s.type == typ:
            return s
    raise KeyError(identifier)


class NodeTree:
    """Small wrapper to keep node-graph code readable."""

    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def node(self, typ, **props):
        nd = self.nodes.new(typ)
        for k, v in props.items():
            setattr(nd, k, v)
        return nd

    def feed(self, sock, value):
        if isinstance(value, (int, float)):
            sock.default_value = value
        elif isinstance(value, tuple):
            sock.default_value = value
        else:
            self.links.new(value, sock)

    def math(self, op, a, b=None, clamp=False):
        nd = self.nodes.new("ShaderNodeMath")
        nd.operation = op
        nd.use_clamp = clamp
        self.feed(nd.inputs[0], a)
        if b is not None:
            self.feed(nd.inputs[1], b)
        return nd.outputs[0]

    def band(self, x, lo, hi):
        """1.0 where lo < x < hi."""
        return self.math("MULTIPLY", self.math("GREATER_THAN", x, lo), self.math("LESS_THAN", x, hi))

    def mix_color(self, fac, a, b):
        nd = self.nodes.new("ShaderNodeMix")
        nd.data_type = "RGBA"
        self.feed(_sock(nd.inputs, "Factor_Float", "Factor", "VALUE"), fac)
        self.feed(_sock(nd.inputs, "A_Color", "A", "RGBA"), a)
        self.feed(_sock(nd.inputs, "B_Color", "B", "RGBA"), b)
        return _sock(nd.outputs, "Result_Color", "Result", "RGBA")

    def ramp(self, fac, stops, constant=False):
        nd = self.nodes.new("ShaderNodeValToRGB")
        cr = nd.color_ramp
        cr.interpolation = "CONSTANT" if constant else "LINEAR"
        els = cr.elements
        while len(els) > len(stops):
            els.remove(els[-1])
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops):
            el.position = pos
            el.color = col if len(col) == 4 else (*col, 1.0)
        self.feed(nd.inputs[0], fac)
        return nd.outputs[0]

    def object_random(self):
        return self.node("ShaderNodeObjectInfo").outputs["Random"]

    def object_color(self):
        return self.node("ShaderNodeObjectInfo").outputs["Color"]


def rgba(c):
    return c if len(c) == 4 else (c[0], c[1], c[2], 1.0)


def make_material(name, base, rough=0.85, metallic=0.0, emission=None, haze=1.0, glitch=True):
    """Principled surface + aerial-perspective haze + per-object 'missing texture' glitch flash.

    `base` is an RGB tuple or a callable(nt) returning a color socket.
    Objects can drive the flash with a custom property obj["glitch"] (0..1).
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    bsdf = nt.node("ShaderNodeBsdfPrincipled")
    nt.feed(bsdf.inputs["Base Color"], base(nt) if callable(base) else rgba(base))
    nt.feed(bsdf.inputs["Roughness"], rough(nt) if callable(rough) else rough)
    bsdf.inputs["Metallic"].default_value = metallic
    if emission:
        bsdf.inputs["Emission Color"].default_value = rgba(emission[0])
        bsdf.inputs["Emission Strength"].default_value = emission[1]
    shader = bsdf.outputs[0]

    if haze > 0 and HAZE_SCENE:
        shader = scene_haze(nt, shader, haze)
    elif haze > 0:
        cam = nt.node("ShaderNodeCameraData")
        f = nt.math("DIVIDE", cam.outputs["View Distance"], -HAZE_DIST)
        f = nt.math("EXPONENT", f)
        f = nt.math("SUBTRACT", 1.0, f)
        f = nt.math("MULTIPLY", f, HAZE_MAX * haze)
        em = nt.node("ShaderNodeEmission")
        em.inputs["Color"].default_value = HAZE_COLOR
        em.inputs["Strength"].default_value = 1.0
        mix = nt.node("ShaderNodeMixShader")
        nt.links.new(f, mix.inputs[0])
        nt.links.new(shader, mix.inputs[1])
        nt.links.new(em.outputs[0], mix.inputs[2])
        shader = mix.outputs[0]

    if glitch:
        attr = nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name="glitch")
        geo = nt.node("ShaderNodeNewGeometry")
        cam2 = nt.node("ShaderNodeCameraData")
        # squares stay roughly the same size on screen (~1.4 degrees) whatever the distance
        k = nt.math("DIVIDE", 40.0, nt.math("MAXIMUM", cam2.outputs["View Distance"], 0.3))
        scaled = nt.node("ShaderNodeVectorMath", operation="SCALE")
        nt.links.new(geo.outputs["Position"], scaled.inputs[0])
        nt.links.new(k, scaled.inputs["Scale"])
        chk = nt.node("ShaderNodeTexChecker")
        chk.inputs["Scale"].default_value = 1.0
        chk.inputs["Color1"].default_value = (1.0, 0.0, 1.0, 1.0)
        chk.inputs["Color2"].default_value = (0.0, 0.0, 0.0, 1.0)
        nt.links.new(scaled.outputs["Vector"], chk.inputs["Vector"])
        em2 = nt.node("ShaderNodeEmission")
        em2.inputs["Strength"].default_value = 1.4
        nt.links.new(chk.outputs["Color"], em2.inputs["Color"])
        mix2 = nt.node("ShaderNodeMixShader")
        nt.links.new(attr.outputs["Fac"], mix2.inputs[0])
        nt.links.new(shader, mix2.inputs[1])
        nt.links.new(em2.outputs[0], mix2.inputs[2])
        shader = mix2.outputs[0]

    nt.links.new(shader, out.inputs["Surface"])
    return mat


def scene_haze(nt, shader, amount=1.0):
    """Aerial haze driven by scene properties (see look.py): 1 - exp(-d / rf_haze_dist), capped at rf_haze_max,
    coloured from rf_haze_col towards rf_haze_sun when looking into the sun. Returns the hazed shader socket."""
    def attr(name):
        return nt.node("ShaderNodeAttribute", attribute_type="VIEW_LAYER", attribute_name=name)
    cam = nt.node("ShaderNodeCameraData")
    f = nt.math("DIVIDE", cam.outputs["View Distance"], nt.math("MULTIPLY", attr("rf_haze_dist").outputs["Fac"], -1.0))
    f = nt.math("SUBTRACT", 1.0, nt.math("EXPONENT", f))
    f = nt.math("MULTIPLY", f, nt.math("MULTIPLY", attr("rf_haze_max").outputs["Fac"], amount))
    geo = nt.node("ShaderNodeNewGeometry")
    dot = nt.node("ShaderNodeVectorMath", operation="DOT_PRODUCT")
    nt.links.new(geo.outputs["Incoming"], dot.inputs[0])
    nt.links.new(attr("rf_sun_dir").outputs["Vector"], dot.inputs[1])
    # Incoming points back at the camera, so looking into the sun gives dot = -1
    toward = nt.math("POWER", nt.math("MAXIMUM", nt.math("MULTIPLY", dot.outputs["Value"], -1.0), 0.0), 5.0)
    col = nt.mix_color(toward, attr("rf_haze_col").outputs["Color"], attr("rf_haze_sun").outputs["Color"])
    em = nt.node("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    mix = nt.node("ShaderNodeMixShader")
    nt.links.new(f, mix.inputs[0])
    nt.links.new(shader, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    return mix.outputs[0]


def make_grid_material(name, color=(0.55, 0.55, 0.58), fade=180.0):
    """Editor-style void grid: thin lines every 1 m and bolder every 10 m, fading with distance."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    geo = nt.node("ShaderNodeNewGeometry")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Position"], sep.inputs[0])

    def lines(period, width):
        acc = None
        for axis in ("X", "Y"):
            fr = nt.math("FRACT", nt.math("DIVIDE", sep.outputs[axis], period))
            edge = nt.math("MAXIMUM", nt.math("LESS_THAN", fr, width), nt.math("GREATER_THAN", fr, 1.0 - width))
            acc = edge if acc is None else nt.math("MAXIMUM", acc, edge)
        return acc

    g = nt.math("MAXIMUM", nt.math("MULTIPLY", lines(1.0, 0.02), 0.35), lines(10.0, 0.004))
    cam = nt.node("ShaderNodeCameraData")
    fall = nt.math("EXPONENT", nt.math("DIVIDE", cam.outputs["View Distance"], -fade))
    g = nt.math("MULTIPLY", g, fall)
    em = nt.node("ShaderNodeEmission")
    em.inputs["Color"].default_value = rgba(color)
    nt.links.new(g, em.inputs["Strength"])
    transp = nt.node("ShaderNodeBsdfTransparent")
    mix = nt.node("ShaderNodeMixShader")
    nt.links.new(g, mix.inputs[0])
    nt.links.new(transp.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------- sky

def setup_sky_world(scene, void_color=(0.16, 0.16, 0.17)):
    """Gradient sky with a dark void below the horizon. Node 'SkyOff' (0 = sky, 1 = flat void) can be keyframed."""
    world = bpy.data.worlds.new("RF_World")
    scene.world = world
    world.use_nodes = True
    nt = NodeTree(world.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputWorld")
    bg = nt.node("ShaderNodeBackground")
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    z = sep.outputs["Z"]
    sky = nt.ramp(z, [(0.0, (0.80, 0.83, 0.88)), (0.06, (0.58, 0.69, 0.86)),
                      (0.30, (0.33, 0.50, 0.82)), (1.0, (0.17, 0.32, 0.72))])
    below = nt.math("LESS_THAN", z, -0.004)
    sky = nt.mix_color(below, sky, (0.010, 0.011, 0.015, 1.0))
    off = nt.node("ShaderNodeValue", name="SkyOff", label="SkyOff")
    off.outputs[0].default_value = 0.0
    col = nt.mix_color(off.outputs[0], sky, rgba(void_color))
    nt.links.new(col, bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs[0], out.inputs["Surface"])
    return world


def add_sun(collection, heading_deg=215.0, elevation_deg=38.0, energy=4.0):
    light = bpy.data.lights.new("Sun", "SUN")
    light.energy = energy
    light.angle = math.radians(1.5)
    light.color = (1.0, 0.95, 0.88)
    try:
        light.use_shadow = True
    except AttributeError:
        pass
    sun = bpy.data.objects.new("Sun", light)
    # Sun object points down -Z; tilt it toward the requested elevation, then spin to the heading it comes from.
    sun.rotation_euler = (math.radians(90.0 - elevation_deg), 0.0, math.radians(-heading_deg + 180.0))
    collection.objects.link(sun)
    return sun


def add_camera(collection, location, heading_deg, pitch_deg, lens_mm):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = lens_mm
    cam_data.sensor_width = 36.0
    cam_data.sensor_fit = "AUTO"
    cam_data.clip_start = 0.05
    cam_data.clip_end = 20000.0
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = location
    cam.rotation_euler = (math.radians(90.0 + pitch_deg), 0.0, math.radians(-heading_deg))
    collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam
