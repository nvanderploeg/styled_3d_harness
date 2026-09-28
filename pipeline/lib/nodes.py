"""Shader-node shorthand for zone materials. Every builder returns an output socket to wire onward."""
from types import SimpleNamespace

import bpy
from mathutils import Vector


class Tree:
    def __init__(self, mat):
        mat.use_nodes = True
        self.mat, self.nt = mat, mat.node_tree
        self.p = next(n for n in self.nt.nodes if n.type == "BSDF_PRINCIPLED")
        self._x = -300

    def node(self, kind, **inputs):
        n = self.nt.nodes.new(kind)
        n.location = (self._x, 0)
        self._x -= 40
        for k, v in inputs.items():
            if hasattr(n, k) and not k[0].isupper():
                setattr(n, k, v)
            else:
                self.set(n.inputs[k], v)
        return n

    def set(self, socket, value):
        if isinstance(value, bpy.types.NodeSocket):
            self.nt.links.new(value, socket)
        elif hasattr(socket.default_value, "__len__") and not hasattr(value, "__len__"):
            socket.default_value = [value] * len(socket.default_value)
        elif hasattr(socket.default_value, "__len__") and len(value) < len(socket.default_value):
            socket.default_value = tuple(value) + (1.0,)
        else:
            socket.default_value = value

    def out(self, base=None, roughness=None, metallic=None, normal=None):
        """Wire values or sockets into the Principled BSDF."""
        for name, v in (("Base Color", base), ("Roughness", roughness), ("Metallic", metallic), ("Normal", normal)):
            if v is not None:
                self.set(self.p.inputs[name], v)

    # --- sources

    def coords(self, space="Object"):
        return self.node("ShaderNodeTexCoord").outputs[space]

    def noise(self, scale=5.0, detail=4.0, roughness=0.5, distortion=0.0, vector=None):
        n = self.node("ShaderNodeTexNoise", Scale=scale, Detail=detail, Roughness=roughness, Distortion=distortion)
        if vector is not None:
            self.set(n.inputs["Vector"], vector)
        return n.outputs["Fac"]

    def voronoi(self, scale=5.0, feature="F1", vector=None):
        n = self.node("ShaderNodeTexVoronoi", feature=feature, Scale=scale)
        if vector is not None:
            self.set(n.inputs["Vector"], vector)
        return n.outputs["Distance"]

    def wave(self, scale=5.0, distortion=4.0, detail=3.0, bands_direction="Z", vector=None):
        n = self.node("ShaderNodeTexWave", bands_direction=bands_direction, Scale=scale,
                      Distortion=distortion, Detail=detail)
        if vector is not None:
            self.set(n.inputs["Vector"], vector)
        return n.outputs["Fac"]

    def image(self, path, colorspace="sRGB", vector=None, projection="FLAT", blend=0.2):
        """An image texture; projection BOX tiles it across the surface by object coordinates."""
        n = self.node("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.image.colorspace_settings.name = colorspace
        n.projection = projection
        n.projection_blend = blend
        if vector is not None:
            self.set(n.inputs["Vector"], vector)
        return n.outputs["Color"]

    def ao(self, distance=0.2, samples=16):
        return self.node("ShaderNodeAmbientOcclusion", samples=samples, Distance=distance).outputs["AO"]

    def edges(self, radius=0.01, sharpness=20.0):
        """0 on flat surface and in concave creases, rising to 1 on convex edges within radius."""
        return self._folds(radius, sharpness)[0]

    def _folds(self, radius, sharpness):
        """(convex, concave) edge masks sharing one set of probe nodes. Where two shells intersect, the
        seam is concave."""
        bevel = self.node("ShaderNodeBevel", samples=8, Radius=radius)
        geo = self.node("ShaderNodeNewGeometry")
        dot = self.math_v("DOT_PRODUCT", bevel.outputs["Normal"], geo.outputs["Normal"])
        bend = self.math("MULTIPLY", self.math("SUBTRACT", 1.0, dot), sharpness, clamp=True)
        # Occlusion inside the solid marks a convex edge, occlusion outside a concave one; keep both probes.
        inside, outside = (self.node("ShaderNodeAmbientOcclusion", inside=flag, only_local=True, samples=32,
                                     Distance=radius * 4).outputs["AO"] for flag in (True, False))
        sign = self.math("SUBTRACT", outside, inside)
        # A convex edge faces open air. At an intersection the inside probe also hits the other shell's
        # buried faces, so the sign alone reads the seam as convex.
        open_air = self.map_range(outside, 0.85, 0.97)
        convex = self.math("MULTIPLY", self.map_range(sign, 0.0, 0.03), open_air)
        concave = self.math("MAXIMUM", self.map_range(sign, 0.0, -0.03), self.math("SUBTRACT", 1.0, open_air))
        return self.math("MULTIPLY", bend, convex), self.math("MULTIPLY", bend, concave)

    def attribute(self, name):
        """A mesh attribute as a value, such as the face tag `modeling.sharpen` leaves (1 on tagged faces)."""
        return self.node("ShaderNodeAttribute", attribute_type="GEOMETRY", attribute_name=name).outputs["Fac"]

    def height(self, lo=0.0, hi=1.0):
        """0 at z=lo rising to 1 at z=hi (object space, metres)."""
        z = self.node("ShaderNodeSeparateXYZ")
        self.set(z.inputs["Vector"], self.coords())
        return self.map_range(z.outputs["Z"], lo, hi)

    # --- operators

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        return n.outputs[0]

    def math_v(self, op, a, b=(0, 0, 0)):
        n = self.node("ShaderNodeVectorMath", operation=op)
        self.set(n.inputs[0], a)
        self.set(n.inputs[1], b)
        return n.outputs["Value" if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else "Vector"]

    def map_range(self, value, from_lo=0.0, from_hi=1.0, to_lo=0.0, to_hi=1.0):
        n = self.node("ShaderNodeMapRange", clamp=True)
        for k, v in (("Value", value), ("From Min", from_lo), ("From Max", from_hi), ("To Min", to_lo), ("To Max", to_hi)):
            self.set(n.inputs[k], v)
        return n.outputs["Result"]

    def ramp(self, fac, stops, interpolation="LINEAR"):
        """Colour ramp from [(position, (r, g, b)), ...]."""
        n = self.node("ShaderNodeValToRGB")
        cr = n.color_ramp
        cr.interpolation = interpolation
        while len(cr.elements) > 1:
            cr.elements.remove(cr.elements[-1])
        cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
        for pos, col in stops[1:]:
            cr.elements.new(pos).color = (*col, 1)
        self.set(n.inputs["Fac"], fac)
        return n.outputs["Color"]

    def mix(self, a, b, fac, blend="MIX", data_type="RGBA"):
        """a to b by fac. data_type is RGBA (with blend modes), FLOAT or VECTOR."""
        kind = {"RGBA": "Color", "FLOAT": "Float", "VECTOR": "Vector"}[data_type]
        n = self.node("ShaderNodeMix", data_type=data_type, blend_type=blend, clamp_result=data_type == "RGBA")
        sock = {s.identifier: s for s in n.inputs}
        self.set(sock["Factor_Float"], fac)
        self.set(sock[f"A_{kind}"], a)
        self.set(sock[f"B_{kind}"], b)
        return next(s for s in n.outputs if s.identifier == f"Result_{kind}")

    def bump(self, height, strength=0.3, distance=0.01):
        n = self.node("ShaderNodeBump", Strength=strength, Distance=distance)
        self.set(n.inputs["Height"], height)
        return n.outputs["Normal"]

    # --- stylized patterns (object space, metres)

    def xyz(self, vec):
        n = self.node("ShaderNodeSeparateXYZ")
        self.set(n.inputs["Vector"], vec)
        return n.outputs["X"], n.outputs["Y"], n.outputs["Z"]

    def band(self, d, width, soft=0.003):
        """1 where distance d <= width, fading to 0 over soft: turns a distance field into a painted line.
        width may be a node output, for a line that swells and thins."""
        outer = self.math("ADD", width, soft) if isinstance(width, bpy.types.NodeSocket) else width + soft
        return self.map_range(d, width, outer, 1.0, 0.0)

    def warp(self, vec, scale, amount):
        """vec pushed by up to amount/2 metres of noise, so ruled patterns wobble like hand-laid stone."""
        col = self.noise(scale=scale, detail=2, vector=vec).node.outputs["Color"]
        offset = self.math_v("MULTIPLY", self.math_v("SUBTRACT", col, (0.5, 0.5, 0.5)), (amount, amount, amount))
        return self.math_v("ADD", vec, offset)

    def cell_random(self, *coords):
        """0–1 random value that is constant per cell id (block, course, slab)."""
        c = self.node("ShaderNodeCombineXYZ")
        for sock, v in zip(c.inputs, coords):
            self.set(sock, v)
        w = self.node("ShaderNodeTexWhiteNoise")
        self.set(w.inputs["Vector"], c.outputs["Vector"])
        return w.outputs["Value"]

    def brush(self, col, vec, strength=0.06, scale=30.0):
        """Low-contrast stroke texture multiplied over col: the painted surface."""
        stroke = self.map_range(self.noise(scale=scale, detail=2, vector=vec), 0.3, 0.7, 1 - strength, 1 + strength)
        return self.mix(col, stroke, 1.0, blend="MULTIPLY")

    def by_facing(self, down, side, up):
        """Colour chosen by surface facing: flat facets (fractures, rock) read as solid painted planes."""
        facing = self.map_range(self.xyz(self.node("ShaderNodeNewGeometry").outputs["Normal"])[2], -1.0, 1.0)
        return self.ramp(facing, [(0.0, down), (0.5, side), (1.0, up)])

    def slabs(self, vec, per_metre, key=None, bevel=0.014, jitter=(3.0, 0.035)):
        """Irregular paving in the XY plane. Returns .grout (metres to the nearest joint), .lit / .dark
        (the same, shifted toward / away from key's XY, for a lit and a shadowed rim beside each joint)
        and .tint (0–1 per slab)."""
        p = self.warp(self.math_v("MULTIPLY", vec, (1, 1, 0)), *jitter)

        def cells(v, feature):
            n = self.node("ShaderNodeTexVoronoi", voronoi_dimensions="2D", feature=feature, Scale=per_metre)
            self.set(n.inputs["Vector"], v)
            return n

        def edge(v):
            return self.math("DIVIDE", cells(v, "DISTANCE_TO_EDGE").outputs["Distance"], per_metre)

        out = SimpleNamespace(grout=edge(p), lit=None, dark=None)
        if key is not None:
            norm = (key[0] ** 2 + key[1] ** 2) ** 0.5
            k = (key[0] / norm * bevel, key[1] / norm * bevel, 0.0)
            out.lit, out.dark = edge(self.math_v("ADD", p, k)), edge(self.math_v("SUBTRACT", p, k))
        out.tint = self.map_range(self.math("ADD", cells(p, "F1").outputs["Color"], 0.0), 0.3, 0.7)
        return out

    def courses(self, vec, bottoms, top, block, stagger=0.07, jitter=0.03):
        """Running-bond block courses on walls, measured along x + y (axis-aligned walls).
        bottoms are the courses' lower z in metres; top closes the last course and is not a joint.
        Returns .vertical / .horizontal (metres to the nearest joint), .block and .course (ids),
        .v (0 at a course's bottom, 1 at its top) and .top (1 on the top course)."""
        x, y, zz = self.xyz(vec)
        along = self.math("ADD", x, y)
        along = self.math("ADD", along, self.math("MULTIPLY", self.math("SUBTRACT", self.noise(
            scale=4, detail=1, vector=vec), 0.5), jitter))

        def fold(xs):
            acc = xs[-1]
            for x_ in reversed(xs[:-1]):
                acc = self.math("ADD", x_, acc)
            return acc

        ends = list(bottoms[1:]) + [top]
        above = [self.math("GREATER_THAN", zz, c) for c in bottoms[1:]]
        if above:
            course = fold(above)
            lo = self.math("ADD", bottoms[0], fold([self.math("MULTIPLY", a, bottoms[i + 1] - bottoms[i])
                                                    for i, a in enumerate(above)]))
            hi = self.math("ADD", ends[0], fold([self.math("MULTIPLY", a, ends[i + 1] - ends[i])
                                                 for i, a in enumerate(above)]))
        else:
            course, lo, hi = 0.0, bottoms[0], top
        v = self.math("DIVIDE", self.math("SUBTRACT", zz, lo), self.math("SUBTRACT", hi, lo))
        u = self.math("DIVIDE", self.math("ADD", along, self.math("MULTIPLY", course, block * 0.5 + stagger)), block)
        vertical = self.math("ADD", self.math("MULTIPLY", self.math("ABSOLUTE", self.math(
            "SUBTRACT", self.math("FRACT", u), 0.5)), -block), block * 0.5)
        on_top = self.math("GREATER_THAN", hi, top - 0.01)
        horizontal = self.math("MINIMUM", self.math("SUBTRACT", zz, lo),
                               self.math("ADD", self.math("SUBTRACT", hi, zz), on_top))
        return SimpleNamespace(vertical=vertical, horizontal=horizontal, block=self.math("FLOOR", u),
                               course=course, v=v, top=on_top)

    def cracks(self, vec, key, per_metre=3.0, width=0.0035, lip_width=0.003, lip=0.008,
               coverage=(0.5, 0.58), jitter=(12.0, 0.025)):
        """Branching cracks as (crack, lip) masks: paint the crack dark and the lip light, the
        hand-painted crack. The lip is the crack shifted `lip` metres away from key.
        coverage is the noise window that switches cracks on; raise its low end for fewer."""
        p = self.warp(vec, *jitter)
        norm = sum(k * k for k in key) ** 0.5
        shift = tuple(lip * c / norm for c in key)

        def dist(v):
            return self.math("DIVIDE", self.voronoi(scale=per_metre, feature="DISTANCE_TO_EDGE", vector=v), per_metre)

        on = self.map_range(self.noise(scale=2.5, detail=1, vector=vec), *coverage)
        crack = self.math("MULTIPLY", self.band(dist(p), width, 0.002), on)
        crack_lip = self.math("MULTIPLY", self.band(dist(self.math_v("ADD", p, shift)), lip_width, 0.002), on)
        return crack, crack_lip

    # --- stylized lighting, baked into the albedo

    def painted_light(self, base, key=(0.4, -0.5, 0.75), wrap=0.35, shadow=(0.55, 0.55, 0.75),
                      light=(1.08, 1.04, 0.95), ao_distance=0.15, top=(0.0, 1.0), top_strength=0.15,
                      edge_radius=0.0, edge_strength=0.35, edge_color=None, normal=None):
        """base lit by a fixed key light with hue-shifted shadows, AO, a top-down gradient and
        optional edge paint — the hand-painted look. top is the (lo, hi) z range of the gradient.
        Within edge_radius, convex edges move edge_strength of the way to edge_color; concave creases
        and the seams where shells intersect lose the key light and sink a further edge_strength into
        the shadow colour, so they read darker than both faces they join. edge_color (linear RGB) None is the
        zone's lit colour lifted halfway to the light tint. normal (a node output, such as `bump`'s) replaces the
        surface normal the key light reads."""
        n = normal if normal is not None else self.node("ShaderNodeNewGeometry").outputs["Normal"]
        lam = self.math_v("DOT_PRODUCT", n, tuple(Vector(key).normalized()))
        lit = self.map_range(lam, -wrap, 1.0)
        lit = self.math("MULTIPLY", lit, self.ao(ao_distance))
        if edge_radius > 0:
            convex, concave = self._folds(edge_radius, 20.0)
            lit = self.math("MULTIPLY", lit, self.math("SUBTRACT", 1.0, concave))
        dark = self.mix(base, shadow, 1.0, blend="MULTIPLY")
        bright = self.mix(base, light, 1.0, blend="MULTIPLY")
        col = self.mix(dark, bright, lit)
        grad = self.map_range(self.height(*top), 0, 1, 1 - top_strength, 1 + top_strength * 0.3)
        col = self.mix(col, grad, 1.0, blend="MULTIPLY")
        if edge_radius > 0:
            rim = self.mix(bright, light, 0.5) if edge_color is None else edge_color
            col = self.mix(col, rim, self.math("MULTIPLY", convex, edge_strength))
            sunk = self.mix(col, shadow, 1.0, blend="MULTIPLY")
            col = self.mix(col, sunk, self.math("MULTIPLY", concave, edge_strength))
        return col


def tree(mat):
    return Tree(mat)


def srgb(hex_or_rgb):
    """Linear RGB for a colour picked by eye: '#8a5a3b' or (138, 90, 59). Shader sockets take linear values."""
    if isinstance(hex_or_rgb, str):
        h = hex_or_rgb.lstrip("#")
        hex_or_rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(((c / 255) / 12.92) if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4
                 for c in hex_or_rgb)
