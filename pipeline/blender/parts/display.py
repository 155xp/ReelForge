"""Seven-segment number display drawn by a shader (no text objects, so it can change every frame in a render).

The display face spans object-space x in [-width/2, width/2] and z in [0, height]. Object attributes:
  num_lo, num_hi   the value is num_hi * 100000 + num_lo (both exact in float32 up to 2^31)
  ndig             how many digits to light (leading zeros stay dark)
  neg              1 draws a minus sign in front
  glitch           0..1 flickers segments
"""
import bpy

import rf_common as rf

# segment order a b c d e f g; True = lit
DIGITS = ["abcdef", "bc", "abdeg", "abcdg", "bcfg", "acdfg", "acdefg", "abc", "abcdefg", "abcdfg"]
SEGS = "abcdefg"


def _lookup_image():
    img = bpy.data.images.new("seven_seg_lookup", 10, 8, alpha=False, float_buffer=False)
    px = []
    for y in range(8):
        for x in range(10):
            on = y < 7 and SEGS[y] in DIGITS[x]
            px += [1.0 if on else 0.0] * 3 + [1.0]
    img.pixels = px
    img.pack()
    return img


def seven_segment_material(name="floor_display", width=1.6, height=0.22, cells=11, on=(1.0, 0.16, 0.05), mirror=False,
                           off=(0.05, 0.008, 0.006), strength=9.0, thickness=0.13):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = rf.NodeTree(mat.node_tree)
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.node("ShaderNodeOutputMaterial")
    tc = nt.node("ShaderNodeTexCoord")
    sep = nt.node("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    attr = lambda n: nt.node("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=n).outputs["Fac"]
    # 0 at the left edge as the viewer sees it (mirror=True: the face points along +y, so the viewer looks down -y)
    u = nt.math("ADD", nt.math("DIVIDE", sep.outputs["X"], -width if mirror else width), 0.5)
    v = nt.math("DIVIDE", sep.outputs["Z"], height)
    r = nt.math("MULTIPLY", nt.math("SUBTRACT", 1.0, u), cells)                    # cells counted from the right
    k = nt.math("FLOOR", r)                                                        # 0 = ones digit
    lu = nt.math("SUBTRACT", 1.0, nt.math("FRACT", r))                             # 0..1 left to right in a cell
    lv = v
    # italic slant
    lu = nt.math("SUBTRACT", lu, nt.math("MULTIPLY", nt.math("SUBTRACT", lv, 0.5), 0.12))
    hi_sel = nt.math("GREATER_THAN", k, 4.5)
    base = nt.math("ADD", nt.math("MULTIPLY", attr("num_hi"), hi_sel),
                   nt.math("MULTIPLY", attr("num_lo"), nt.math("SUBTRACT", 1.0, hi_sel)))
    e = nt.math("SUBTRACT", k, nt.math("MULTIPLY", hi_sel, 5.0))
    d = nt.math("FLOORED_MODULO", nt.math("FLOOR", nt.math("DIVIDE", nt.math("ADD", base, 0.25),
                                                           nt.math("POWER", 10.0, e))), 10.0)
    ndig = attr("ndig")
    show = nt.math("LESS_THAN", k, nt.math("MAXIMUM", ndig, 1.0))
    minus = nt.math("MULTIPLY", nt.math("MULTIPLY", nt.math("GREATER_THAN", k, nt.math("SUBTRACT", ndig, 0.5)),
                                        nt.math("LESS_THAN", k, nt.math("ADD", ndig, 0.5))), attr("neg"))
    inside = nt.math("MULTIPLY", nt.band(u, 0.0, 1.0), nt.band(v, 0.0, 1.0))
    img = _lookup_image()
    t = thickness
    x0, x1, y0, ym, y1 = 0.2, 0.8, 0.1, 0.5, 0.9

    def hseg(yc):
        return nt.math("MULTIPLY", nt.band(lv, yc - t / 2, yc + t / 2), nt.band(lu, x0 + t * 0.4, x1 - t * 0.4))

    def vseg(xc, ya, yb):
        return nt.math("MULTIPLY", nt.band(lu, xc - t / 2, xc + t / 2), nt.band(lv, ya + t * 0.4, yb - t * 0.4))

    shapes = {"a": hseg(y1), "b": vseg(x1, ym, y1), "c": vseg(x1, y0, ym), "d": hseg(y0), "e": vseg(x0, y0, ym),
              "f": vseg(x0, ym, y1), "g": hseg(ym)}
    lit = None
    every = None
    for s_idx, s in enumerate(SEGS):
        tex = nt.node("ShaderNodeTexImage", interpolation="Closest", extension="EXTEND")
        tex.image = img
        vec = nt.node("ShaderNodeCombineXYZ")
        nt.links.new(nt.math("DIVIDE", nt.math("ADD", d, 0.5), 10.0), vec.inputs[0])
        vec.inputs[1].default_value = (s_idx + 0.5) / 8.0
        nt.links.new(vec.outputs[0], tex.inputs["Vector"])
        sc = nt.node("ShaderNodeSeparateColor")
        nt.links.new(tex.outputs["Color"], sc.inputs[0])
        seg_on = nt.math("MULTIPLY", shapes[s], sc.outputs[0])
        lit = seg_on if lit is None else nt.math("MAXIMUM", lit, seg_on)
        every = shapes[s] if every is None else nt.math("MAXIMUM", every, shapes[s])
    lit = nt.math("MULTIPLY", lit, show)
    lit = nt.math("MAXIMUM", lit, nt.math("MULTIPLY", shapes["g"], minus))
    # glitch: random cells flicker on and off
    wn = nt.node("ShaderNodeTexWhiteNoise", noise_dimensions="2D")
    gv = nt.node("ShaderNodeCombineXYZ")
    nt.links.new(k, gv.inputs[0])
    nt.links.new(nt.math("FLOOR", nt.math("MULTIPLY", attr("phase"), 30.0)), gv.inputs[1])
    nt.links.new(gv.outputs[0], wn.inputs["Vector"])
    flick = nt.math("MULTIPLY", attr("glitch"), nt.math("GREATER_THAN", wn.outputs["Value"], 0.55))
    lit = nt.math("ABSOLUTE", nt.math("SUBTRACT", lit, nt.math("MULTIPLY", flick, every)))
    lit = nt.math("MULTIPLY", lit, inside)
    ghost = nt.math("MULTIPLY", nt.math("MULTIPLY", every, inside), 0.35)          # unlit segments faintly visible
    col = nt.mix_color(lit, nt.mix_color(ghost, (0.0, 0.0, 0.0, 1.0), rf.rgba(off)), rf.rgba(on))
    em = nt.node("ShaderNodeEmission")
    nt.links.new(col, em.inputs["Color"])
    nt.links.new(nt.math("ADD", 0.4, nt.math("MULTIPLY", lit, strength)), em.inputs["Strength"])
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return mat


def number_attrs(value):
    """(num_lo, num_hi, ndig, neg) for an integer value."""
    v = int(value)
    neg = 1.0 if v < 0 else 0.0
    a = abs(v)
    return float(a % 100000), float(a // 100000), float(max(1, len(str(a)))), neg
