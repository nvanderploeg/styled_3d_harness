import contextlib
import heapq
import io
import math
import re
import sys

import bmesh
import bpy
import numpy as np
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


HEAD = "head"


def head(obj, faces=None):
    """Mark faces (all when None; else polygon indices) of obj as the head, which `head_tri_budget` counts:
    the skull and face and what grows from or rides on them (hair, ears, a beard, a hat). The neck is body."""
    me = obj.data
    attr = me.attributes.get(HEAD) or me.attributes.new(HEAD, "BOOLEAN", "FACE")
    for i in (range(len(me.polygons)) if faces is None else faces):
        attr.data[i].value = True


KEEP = "keep"


def keep(obj, faces=None):
    """Mark faces (all when None; else polygon indices) of obj as kept: `reduce` leaves them, their vertices
    and edges exactly as built. Keep what gameplay measures: a walkable top, a jump lip."""
    me = obj.data
    attr = me.attributes.get(KEEP) or me.attributes.new(KEEP, "BOOLEAN", "FACE")
    for i in (range(len(me.polygons)) if faces is None else faces):
        attr.data[i].value = True


def reduce(asset, tris=None, planar_deg=1.0, borders=True, sharp_angle=35):
    """`<slug>`: the detailed mesh reduced to tris triangles (the spec's tri_budget when None), with the
    detailed mesh kept as `<slug>_high`, the bake source. The detailed mesh is `<slug>_high` when the script
    built one, else the finalized `<slug>`.

    Faces within planar_deg of coplanar dissolve first, so flat faces stay flat; edge collapses then remove the
    vertices whose loss costs the shape least, a large face weighing more than small ones. Every vertex of the
    reduced mesh is a vertex of the detailed one. Kept faces (`keep`) keep their vertices and edges bit-exact.
    With borders, every zone border keeps its vertices too, and an open mesh always keeps its rim. The reduced
    mesh carries the zones and no UVs: unwrap it. It may come out triangle-dominant.

    Reduce before bevelling: a bevelled corner has no vertex on its planes, and the low folds."""
    target = tris or asset.spec["tri_budget"]
    high, low = asset.high, asset.mesh
    if high is None:
        if low is None:
            raise SystemExit("reduce needs the detailed mesh: finalize it as the asset mesh, or build <slug>_high")
        low.name = low.data.name = f"{asset.slug}_high"
        high, low = low, None
    if low is not None:
        bpy.data.objects.remove(low)
    low = high.copy()
    low.data = high.data.copy()
    low.name = low.data.name = asset.slug
    bpy.context.scene.collection.objects.link(low)
    me = low.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    before = _tris(me)

    bm = bmesh.new()
    bm.from_mesh(me)
    layer = bm.faces.layers.bool.get(KEEP)

    def kept(f):
        return layer is not None and f[layer]

    kept_tris = sum(len(f.verts) - 2 for f in bm.faces if kept(f))
    if kept_tris > target:
        bm.free()
        raise SystemExit(f"reduce: the kept faces alone are {kept_tris} tris, over the budget {target}; keep "
                         "fewer faces or raise tri_budget")
    fixed_verts = {v for f in bm.faces if kept(f) for v in f.verts}
    fixed_edges = {e for f in bm.faces if kept(f) for e in f.edges}
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(planar_deg), use_dissolve_boundaries=False,
                             verts=[v for v in bm.verts if v not in fixed_verts],
                             edges=[e for e in bm.edges if e not in fixed_edges], delimit={"MATERIAL"})
    quadric = _quadrics(bm)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3 and not kept(f)],
                          quad_method="BEAUTY", ngon_method="BEAUTY")
    locked = {v for f in bm.faces if kept(f) for v in f.verts} | {v for v in bm.verts if v.is_boundary}
    if borders:
        locked |= {v for v in bm.verts if len({f.material_index for f in v.link_faces}) > 1}
    after = _collapse(bm, target, locked, quadric, asset.limits.get("min_corner_deg") or 0.0)
    bmesh.ops.join_triangles(bm, faces=[f for f in bm.faces if len(f.verts) == 3 and not kept(f)],
                             cmp_materials=True, angle_face_threshold=math.radians(planar_deg),
                             angle_shape_threshold=math.radians(40))
    bm.to_mesh(me)
    bm.free()
    if after > target:
        raise SystemExit(f"reduce: {after} tris left, over the budget {target}, without moving the kept faces "
                         f"({kept_tris} tris){' or zone borders' if borders else ''}. Keep fewer faces, give the "
                         "high simpler zone borders, pass borders=False, or raise tri_budget")
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(sharp_angle))
    print(f"reduce: {before} → {after} tris (budget {target}), {kept_tris} of them kept")
    return low


def _tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


def _quadrics(bm):
    """{vertex: 4x4 quadric}: the planes of the faces around each vertex, each weighted by its face's area."""
    bm.normal_update()
    quadric = {v: np.zeros((4, 4)) for v in bm.verts}
    for f in bm.faces:
        n = f.normal
        plane = np.array([n.x, n.y, n.z, -n.dot(f.verts[0].co)])
        q = np.outer(plane, plane) * f.calc_area()
        for v in f.verts:
            quadric[v] += q
    return quadric


def _collapse(bm, target, locked, quadric, min_corner_deg):
    """Merge vertices of bm's triangles into a neighbour, cheapest first, until it holds target triangles or no
    merge is left; the triangles it holds. A merge costs the quadric error of the surviving vertex over the
    planes the two gathered (`_quadrics`). A locked vertex never goes, though a free neighbour may merge into
    it. A merge that would break the surface's topology, turn a face more than 60° or leave a corner under
    min_corner_deg is skipped. The merges run on index lists and reach bm in one weld."""
    bm.verts.index_update()
    bm.faces.index_update()
    verts = list(bm.verts)
    co = [v.co.copy() for v in verts]
    q = [quadric[v] for v in verts]
    lock = {v.index for v in locked}
    faces = {f.index: [v.index for v in f.verts] for f in bm.faces}
    normal = {f.index: f.normal.copy() for f in bm.faces}
    around = [set() for _ in verts]
    for i, vs in faces.items():
        for v in vs:
            around[v].add(i)
    stamp = [0] * len(verts)
    merged, heap, count = {}, [], 0

    def ring(v):
        out = set()
        for f in around[v]:
            vs = faces[f]
            i = vs.index(v)
            out.update((vs[i - 1], vs[(i + 1) % len(vs)]))
        return out

    def push(a, b):
        nonlocal count
        pair = q[a] + q[b]
        for keep, gone in ((a, b), (b, a)):
            if gone not in lock:
                p = np.array((*co[keep], 1.0))
                count += 1
                heapq.heappush(heap, (float(p @ pair @ p), count, keep, gone, stamp[keep], stamp[gone]))

    for e in bm.edges:
        push(e.verts[0].index, e.verts[1].index)
    tris = sum(len(vs) - 2 for vs in faces.values())
    limit = math.cos(math.radians(60))
    while tris > target and heap:
        _, _, keep, gone, sk, sg = heapq.heappop(heap)
        if stamp[keep] != sk or stamp[gone] != sg:
            continue
        turned = _merge(faces, around, co, normal, ring, keep, gone, limit, min_corner_deg)
        if turned is None:
            continue
        for f in around[keep] & around[gone]:
            for v in faces.pop(f):
                if v != gone:
                    around[v].discard(f)
            del normal[f]
        for f, n in turned.items():
            faces[f] = [keep if v == gone else v for v in faces[f]]
            normal[f] = n
            around[keep].add(f)
        around[gone] = set()
        merged[gone] = keep
        q[keep] = q[keep] + q[gone]
        stamp[keep] += 1
        stamp[gone] += 1
        tris -= 2
        for v in ring(keep):
            push(keep, v)

    def final(v):
        while v in merged:
            v = merged[v]
        return v

    if merged:
        bmesh.ops.weld_verts(bm, targetmap={verts[g]: verts[final(g)] for g in merged})
    return sum(len(f.verts) - 2 for f in bm.faces)


def _merge(faces, around, co, normal, ring, keep, gone, limit, min_corner_deg):
    """{face: new normal} for the faces that move when gone merges into keep, or None when the merge would break
    the surface's topology, turn a face's normal by more than acos(limit) or leave a corner under
    min_corner_deg."""
    shared = around[keep] & around[gone]
    if len(shared) != 2 or any(len(faces[f]) != 3 for f in shared):
        return None
    if ring(keep) & ring(gone) != {v for f in shared for v in faces[f]} - {keep, gone}:
        return None
    turned = {}
    for f in around[gone] - shared:
        if len(faces[f]) != 3:
            return None
        pts = [co[keep] if v == gone else co[v] for v in faces[f]]
        n = (pts[1] - pts[0]).cross(pts[2] - pts[0])
        if n.length < 1e-12 or n.normalized().dot(normal[f]) < limit:
            return None
        for i in range(3):
            u, w = pts[i - 1] - pts[i], pts[(i + 1) % 3] - pts[i]
            if u.length == 0 or w.length == 0 or math.degrees(u.angle(w)) < min_corner_deg:
                return None
        turned[f] = n.normalized()
    return turned


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
