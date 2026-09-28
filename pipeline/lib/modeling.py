import contextlib
import io
import math
import re
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

PALETTE = [
    (0.80, 0.52, 0.33, 1), (0.45, 0.62, 0.80, 1), (0.60, 0.78, 0.45, 1),
    (0.85, 0.75, 0.40, 1), (0.70, 0.50, 0.75, 1), (0.50, 0.75, 0.72, 1),
]


def zone_material(name):
    """The `zone_<name>` material, created with a distinct viewport colour for review renders."""
    mname = f"zone_{name}"
    mat = bpy.data.materials.get(mname)
    if mat is None:
        mat = bpy.data.materials.new(mname)
        mat.use_nodes = True
        zones = [m for m in bpy.data.materials if m.name.startswith("zone_")]
        mat.diffuse_color = PALETTE[(len(zones) - 1) % len(PALETTE)]
    return mat


def zone(obj, name, faces=None):
    """Assign faces (all when None; else polygon indices) of obj to zone `name`."""
    mat = zone_material(name)
    slots = [s.material for s in obj.material_slots]
    if mat not in slots:
        obj.data.materials.append(mat)
        slots.append(mat)
    idx = slots.index(mat)
    polys = obj.data.polygons
    for i in (range(len(polys)) if faces is None else faces):
        polys[i].material_index = idx
    return mat


def bake_modifiers(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    obj.modifiers.clear()
    old, obj.data = obj.data, me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def bake_transform(obj):
    bpy.context.view_layer.update()
    mw = obj.matrix_world.copy()
    obj.parent = None
    obj.data.transform(mw)
    obj.matrix_world = Matrix.Identity(4)


def finalize(asset, parts, sharp_angle=35, smooth=()):
    """Join parts into the one asset mesh: modifiers and transforms applied, welded,
    normals outward, smooth-by-angle shading, origin at bottom centre. Edges inside the zones in smooth stay
    soft at any angle, for low-sided round parts (an 8-sided limb turns 45° per edge). The move that puts it there is
    printed and kept as asset.shift: add it to a point in the parts' coordinates to find it on the mesh."""
    for o in parts:
        if o.type != "MESH":
            raise ValueError(f"{o.name} is not a mesh")
        bake_modifiers(o)
        bake_transform(o)
    base = parts[0]
    if len(parts) > 1:
        with bpy.context.temp_override(active_object=base, selected_editable_objects=parts):
            bpy.ops.object.join()
    base.name = base.data.name = asset.slug

    me = base.data
    bm = bmesh.new()
    bm.from_mesh(me)
    size = max((max(v.co[i] for v in bm.verts) - min(v.co[i] for v in bm.verts)) for i in range(3))
    eps = size * 1e-5
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=eps)
    bmesh.ops.dissolve_degenerate(bm, dist=eps, edges=bm.edges)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lo = Vector([min(v.co[i] for v in bm.verts) for i in range(3)])
    hi = Vector([max(v.co[i] for v in bm.verts) for i in range(3)])
    asset.shift = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
    bmesh.ops.translate(bm, verts=bm.verts, vec=asset.shift)
    if asset.shift.length > eps:
        print(f"finalize: moved the mesh by {tuple(round(c, 4) for c in asset.shift)} m to the bottom centre")
    bm.to_mesh(me)
    bm.free()

    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    soft = {i for i, m in enumerate(me.materials) if m and m.name[5:] in smooth}
    if soft:
        zones = {}
        for p in me.polygons:
            for ek in p.edge_keys:
                zones.setdefault(ek, set()).add(p.material_index)
        sharp = me.attributes["sharp_edge"].data
        for e in me.edges:
            if zones.get(e.key, set()) <= soft:
                sharp[e.index].value = False

    for o in list(bpy.data.objects):
        if o not in (base,) and o.name != f"{asset.slug}_high":
            bpy.data.objects.remove(o)
    return base


def unwrap(asset, seams_from_sharp=True, pad_px=8):
    """Seams on sharp edges (plus any already marked), angle-based unwrap,
    uniform texel density, packed with pad_px of padding at the asset's texture size."""
    obj = asset.mesh
    me = obj.data
    if seams_from_sharp:
        bm = bmesh.new()
        bm.from_mesh(me)
        for e in bm.edges:
            if not e.smooth or e.is_boundary:
                e.seam = True
        bm.to_mesh(me)
        bm.free()
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    margin = 2 * pad_px / asset.spec["texture_size"]
    printed = _printed(lambda: _edit(obj, lambda: (
        bpy.ops.uv.unwrap(method="ANGLE_BASED", margin=margin),
        bpy.ops.uv.average_islands_scale(),
        bpy.ops.uv.pack_islands(rotate=True, margin=margin),
    )))
    failed = re.search(r"failed to solve (\d+) of (\d+) island", printed)
    if failed:
        raise SystemExit(f"unwrap failed to solve {failed[1]} of {failed[2]} UV islands, which keep stale UVs: "
                         "open every closed smooth shell with seams (a tube along its length, a ball pole to pole)")


def _printed(fn):
    """Run fn and return what it printed, echoing it; operator reports print there."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        fn()
    sys.stdout.write(out.getvalue())
    return out.getvalue()


def _edit(obj, fn):
    bpy.context.view_layer.objects.active = obj
    for o in bpy.context.view_layer.objects:
        o.select_set(o == obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.context.scene.tool_settings.use_uv_select_sync = True
    try:
        fn()
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")


def make_high(asset, bevel=0.02, segments=3, angle=35, sharp_zones=()):
    """`<slug>_high`: the low mesh with edges bending more than `angle` degrees rounded, the source for
    normal and AO bakes. bevel is the rounding width in metres, so edges match across assets of any size.
    Edges of the zones in sharp_zones (blades, spikes) stay sharp. Flat faces keep flat normals."""
    low = asset.mesh
    old = asset.high
    if old:
        bpy.data.objects.remove(old)
    high = low.copy()
    high.data = low.data.copy()
    high.name = high.data.name = f"{asset.slug}_high"
    bpy.context.scene.collection.objects.link(high)
    me = high.data
    me.shade_smooth()
    if "sharp_edge" in me.attributes:
        me.attributes.remove(me.attributes["sharp_edge"])
    keep = {i for i, m in enumerate(me.materials) if m and m.name[5:] in sharp_zones}
    bm = bmesh.new()
    bm.from_mesh(me)
    weight = bm.edges.layers.float.new("bevel_weight_edge")
    for e in bm.edges:
        faces = e.link_faces
        bend = len(faces) == 2 and e.calc_face_angle() > math.radians(angle)
        e[weight] = 1.0 if bend and not any(f.material_index in keep for f in faces) else 0.0
    bm.to_mesh(me)
    bm.free()
    mod = high.modifiers.new("bevel", "BEVEL")
    mod.width = bevel
    mod.segments = segments
    mod.limit_method = "WEIGHT"
    mod.harden_normals = True
    bake_modifiers(high)
    return high


def mesh_object(name, bm):
    """Link a new object built from bm (which is freed)."""
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def quadify(bm, faces):
    """Replace faces (n-gons, fans) with a quad-dominant fill."""
    tris = bmesh.ops.triangulate(bm, faces=faces, quad_method="BEAUTY", ngon_method="BEAUTY")["faces"]
    bmesh.ops.join_triangles(bm, faces=tris, angle_face_threshold=math.pi, angle_shape_threshold=math.pi)


def lathe(name, profile, segments=16, loop=False, seam_deg=0.0):
    """Revolve profile [(radius, z), ...] around Z into a quad mesh, with seams marked for a clean unwrap.
    The seam down its length runs at seam_deg around Z from +X; put it where the camera sees least.
    loop=False: an open profile, capped with a quad grid at each end whose radius is non-zero
    (segments a multiple of 4 gives an all-quad cap).
    loop=True: a closed cross-section, giving a ring (bands, rims, tyres)."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        rings.append([bm.verts.new((r * math.cos(math.radians(seam_deg) + 2 * math.pi * i / segments),
                                    r * math.sin(math.radians(seam_deg) + 2 * math.pi * i / segments), z))
                      for i in range(segments)])
    pairs = list(zip(rings, rings[1:])) + ([(rings[-1], rings[0])] if loop else [])
    for lo, hi in pairs:
        for i in range(segments):
            j = (i + 1) % segments
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bm.edges.get((lo[0], hi[0])).seam = True
    if loop:
        for i in range(segments):
            bm.edges.get((rings[0][i], rings[0][(i + 1) % segments])).seam = True
    else:
        for ring, (r, z) in ((rings[0], profile[0]), (rings[-1], profile[-1])):
            if r > 0:
                _cap(bm, ring, r, z)
                for i in range(segments):
                    bm.edges.get((ring[i], ring[(i + 1) % segments])).seam = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mesh_object(name, bm)


def _cap(bm, ring, r, z):
    n = len(ring)
    if n == 4:
        bm.faces.new(ring)
        return
    if n % 4:
        quadify(bm, [bm.faces.new(ring)])
        return
    k = n // 4
    s = 0.55 * r
    a0 = math.atan2(ring[0].co.y, ring[0].co.x)
    c, sn = math.cos(a0), math.sin(a0)
    grid = {}
    for i in range(k + 1):
        for j in range(k + 1):
            x, y = -1 + 2 * i / k, -1 + 2 * j / k
            gx, gy = s * x * math.sqrt(1 - y * y / 2), s * y * math.sqrt(1 - x * x / 2)
            grid[i, j] = bm.verts.new((gx * c - gy * sn, gx * sn + gy * c, z))
    for i in range(k):
        for j in range(k):
            bm.faces.new((grid[i, j], grid[i + 1, j], grid[i + 1, j + 1], grid[i, j + 1]))
    border = ([grid[i, 0] for i in range(k)] + [grid[k, j] for j in range(k)] +
              [grid[i, k] for i in range(k, 0, -1)] + [grid[0, j] for j in range(k, 0, -1)])
    ang = [math.atan2(v.co.y, v.co.x) for v in border]
    shift = min(range(n), key=lambda o: abs(math.remainder(ang[o] - a0, 2 * math.pi)))
    border = border[shift:] + border[:shift]
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((border[i], border[j], ring[j], ring[i]))


def footprint_outline(cells):
    """Outline of a set of unit lattice cells (lower-left corners) as one counter-clockwise loop of
    lattice points. Grid-based level pieces (floors, platforms, walls) start from this."""
    step = {}
    for i, j in cells:
        for (a, b), nb in ((((i, j), (i + 1, j)), (i, j - 1)),
                           (((i + 1, j), (i + 1, j + 1)), (i + 1, j)),
                           (((i + 1, j + 1), (i, j + 1)), (i, j + 1)),
                           (((i, j + 1), (i, j)), (i - 1, j))):
            if nb not in cells:
                if a in step:
                    raise ValueError(f"footprint outline touches itself at {a}")
                step[a] = b
    start = min(step)
    loop, q = [start], step[start]
    while q != start:
        loop.append(q)
        q = step[q]
    if len(loop) != len(step):
        raise ValueError("footprint must be one piece without holes")
    return loop


def sharpen(obj, angle=20, tag=None, zones=None):
    """Mark edges bending more than `angle` degrees sharp where a neighbouring face is tagged: a face int
    layer `tag` or a zone in `zones`; angle 0 hardens every bend around them. Broken stone, chipped wood and
    cut facets then shade as flat planes while the rest stays smooth. The `tag` layer stays on the mesh for
    texture recipes (`Tree.attribute`)."""
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    layer = bm.faces.layers.int[tag] if tag else None
    idx = {i for i, m in enumerate(me.materials) if zones and m and m.name[5:] in zones}
    limit = math.radians(angle)

    def tagged(f):
        return (layer is not None and f[layer]) or f.material_index in idx

    for e in bm.edges:
        if len(e.link_faces) == 2 and any(tagged(f) for f in e.link_faces) and e.calc_face_angle() > limit:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()
