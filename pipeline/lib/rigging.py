import math

import bmesh
import bpy
from mathutils import Vector

# Humanoid attachment points, socket → the bone it rides: keep in step with rig-asset HUMANOID.md.
SOCKETS = {"socket_hand.L": "hand.L", "socket_hand.R": "hand.R", "socket_helm": "head", "socket_cloak": "chest"}


def section(a, axis="z", value=0.0):
    """Islands where the plane axis=value cuts the mesh: [(centre, size)] as Vectors, sorted along x.
    Use it to find joint positions — a limb is an island, a joint is where its size pinches."""
    i = "xyz".index(axis)
    no = Vector([1.0 if k == i else 0.0 for k in range(3)])
    bm = bmesh.new()
    bm.from_mesh(a.mesh.data)
    res = bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:],
                                 plane_co=no * value, plane_no=no)
    cut = {v for v in res["geom_cut"] if isinstance(v, bmesh.types.BMVert)}
    islands, seen = [], set()
    for v in cut:
        if v in seen:
            continue
        stack, isl = [v], []
        seen.add(v)
        while stack:
            u = stack.pop()
            isl.append(u.co.copy())
            for e in u.link_edges:
                w = e.other_vert(u)
                if w in cut and w not in seen:
                    seen.add(w)
                    stack.append(w)
        lo = Vector([min(p[k] for p in isl) for k in range(3)])
        hi = Vector([max(p[k] for p in isl) for k in range(3)])
        islands.append(((lo + hi) / 2, hi - lo))
    bm.free()
    return sorted(islands, key=lambda c: c[0].x)


def build(a, bones, mirror=True):
    """Create `<slug>_rig` from bone dicts: name, head, tail, parent (optional), roll in degrees (optional),
    up (optional, in place of roll: a direction the bone's local Z turns toward), deform (default True).
    With mirror, every `.L` bone gets a `.R` twin across X."""
    old = a.armature
    if old:
        bpy.data.objects.remove(old)
    specs = list(bones)
    if mirror:
        for b in bones:
            if b["name"].endswith(".L"):
                m = dict(b, name=b["name"][:-2] + ".R",
                         head=_flip(b["head"]), tail=_flip(b["tail"]), roll=-b.get("roll", 0))
                if "up" in b:
                    m["up"] = _flip(b["up"])
                if b.get("parent", "").endswith(".L"):
                    m["parent"] = b["parent"][:-2] + ".R"
                specs.append(m)
    data = bpy.data.armatures.new(f"{a.slug}_rig")
    arm = bpy.data.objects.new(f"{a.slug}_rig", data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    for s in specs:
        eb = data.edit_bones.new(s["name"])
        eb.head, eb.tail = Vector(s["head"]), Vector(s["tail"])
        eb.roll = math.radians(s.get("roll", 0))
        if "up" in s:
            eb.align_roll(Vector(s["up"]))
        eb.use_deform = s.get("deform", True)
    for s in specs:
        if s.get("parent"):
            eb = data.edit_bones[s["name"]]
            eb.parent = data.edit_bones[s["parent"]]
            eb.use_connect = (eb.head - eb.parent.tail).length < 1e-5
    bpy.ops.object.mode_set(mode="OBJECT")
    data.display_type = "STICK"
    return arm


def _flip(p):
    return (-p[0], p[1], p[2])


def bind(a, max_influences=None, threshold=0.01, skip=()):
    """Parent the mesh to the rig with automatic (bone heat) weights, then clean them. Bones in skip take
    no heat weights, so the extra chains `chain` weights afterwards don't pull on the body."""
    obj, arm = a.mesh, a.armature
    obj.vertex_groups.clear()
    for m in [m for m in obj.modifiers if m.type == "ARMATURE"]:
        obj.modifiers.remove(m)
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (obj, arm))
    bpy.context.view_layer.objects.active = arm
    held = [b for b in arm.data.bones if b.name in skip and b.use_deform]
    for b in held:
        b.use_deform = False
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        clean(a, max_influences, threshold)
    finally:
        for b in held:
            b.use_deform = True


def clean(a, max_influences=None, threshold=0.01):
    """Drop weights below threshold and on non-deform groups, keep the strongest max_influences, normalise.
    A vertex left with no weight takes its nearest weighted neighbour's."""
    obj, arm = a.mesh, a.armature
    limit = max_influences or a.limits["max_influences"]
    deform = {b.name for b in arm.data.bones if b.use_deform}
    groups = {g.index: g for g in obj.vertex_groups}
    empty = []
    for v in obj.data.vertices:
        ws = sorted(((g.weight, g.group) for g in v.groups), reverse=True)
        keep = [(w, gi) for w, gi in ws if groups[gi].name in deform and w >= threshold][:limit]
        for w, gi in ws:
            groups[gi].remove([v.index])
        total = sum(w for w, _ in keep)
        for w, gi in keep:
            groups[gi].add([v.index], w / total, "REPLACE")
        if not keep:
            empty.append(v.index)
    if empty:
        _fill_from_neighbours(obj, empty)
    return len(empty)


def _select(obj, where):
    """Vertex indices in a zone (by name), passing a predicate on the vertex position, or given as a set."""
    if isinstance(where, str):
        slots = [m.name for m in obj.data.materials]
        idx = slots.index(f"zone_{where}")
        return {v for p in obj.data.polygons if p.material_index == idx for v in p.vertices}
    if isinstance(where, (set, frozenset, list, tuple)):
        return set(where)
    return {v.index for v in obj.data.vertices if where(v.co)}


def shell(a, point):
    """Vertex indices of the connected shell holding the vertex nearest point, for rigid or chain:
    a buckle, a clasp or a bead that shares its zone with its neighbours."""
    me = a.mesh.data
    start = min(me.vertices, key=lambda v: (v.co - Vector(point)).length).index
    links = {}
    for e in me.edges:
        i, j = e.vertices
        links.setdefault(i, []).append(j)
        links.setdefault(j, []).append(i)
    found, todo = {start}, [start]
    while todo:
        for j in links.get(todo.pop(), []):
            if j not in found:
                found.add(j)
                todo.append(j)
    return found


def _assign(obj, verts, weights_of):
    """Replace the weights of verts with weights_of(index) → {bone: weight}."""
    for g in obj.vertex_groups:
        g.remove(list(verts))
    for i in verts:
        for bone, w in weights_of(i).items():
            if w > 0:
                (obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)).add([i], w, "REPLACE")


def rigid(a, bone, where):
    """Weight vertices fully to one bone: a zone name, a predicate on the vertex position, or a vertex set
    such as `shell` returns. For parts that move as a solid (wheels, lids, armour plates). It replaces
    earlier weights, so a solid piece inside a chained part (a clasp in a braid) is weighted after `chain`."""
    verts = _select(a.mesh, where)
    _assign(a.mesh, verts, lambda i: {bone: 1.0})
    return len(verts)


def chain(a, bones, where):
    """Weight a hanging part along a chain of connected bones, root first: each vertex blends between the
    two bones whose middles it falls between along the chain, and between the root and the first bone's
    middle it blends into that bone's parent. For beards, cloaks, braids, hat tips and tails.
    where selects vertices as in rigid."""
    obj, arm = a.mesh, a.armature
    verts = _select(obj, where)
    chain_bones = [arm.data.bones[n] for n in bones]
    pts = [b.head_local for b in chain_bones] + [chain_bones[-1].tail_local]
    starts = [0.0]
    for p, q in zip(pts, pts[1:]):
        starts.append(starts[-1] + (q - p).length)
    anchors = [((starts[i] + starts[i + 1]) / 2, n) for i, n in enumerate(bones)]
    parent = chain_bones[0].parent
    if parent:
        anchors.insert(0, (0.0, parent.name))

    def along(co):
        best = None
        for i, (p, q) in enumerate(zip(pts, pts[1:])):
            seg = q - p
            t = min(max((co - p).dot(seg) / seg.length_squared, 0.0), 1.0)
            d = (p + seg * t - co).length
            if best is None or d < best[0]:
                best = (d, starts[i] + t * seg.length)
        return best[1]

    def weights_of(i):
        s = along(obj.data.vertices[i].co)
        if s <= anchors[0][0]:
            return {anchors[0][1]: 1.0}
        for (s0, b0), (s1, b1) in zip(anchors, anchors[1:]):
            if s <= s1:
                w = (s - s0) / (s1 - s0)
                return {b0: 1.0 - w, b1: w}
        return {anchors[-1][1]: 1.0}

    _assign(obj, verts, weights_of)
    return len(verts)


def mirror(a, source="L", tol=0.002):
    """Copy the weights of the `source` side (.L, at +X) onto its mirror image, swapping .L and .R groups,
    so bone heat's lopsided results come out symmetric. Vertices on the centre line keep their weights;
    a vertex with no mirror within tol metres keeps its own."""
    from mathutils.kdtree import KDTree
    obj = a.mesh
    verts = obj.data.vertices
    sign = 1 if source == "L" else -1
    other = "R" if source == "L" else "L"
    kd = KDTree(len(verts))
    for v in verts:
        kd.insert(v.co, v.index)
    kd.balance()

    def swap(name):
        for s, o in ((f".{source}", f".{other}"), (f".{other}", f".{source}")):
            if name.endswith(s):
                return name[:-len(s)] + o
        return name

    names = {g.index: g.name for g in obj.vertex_groups}
    copied = []
    for v in verts:
        if v.co.x * sign >= -tol:
            continue
        _, i, d = kd.find(Vector((-v.co.x, v.co.y, v.co.z)))
        if d > tol:
            continue
        copied.append((v.index, [(swap(names[g.group]), g.weight) for g in verts[i].groups]))
    for idx, weights in copied:
        for g in list(verts[idx].groups):
            obj.vertex_groups[g.group].remove([idx])
        for name, w in weights:
            group = obj.vertex_groups.get(name) or obj.vertex_groups.new(name=name)
            group.add([idx], w, "REPLACE")
    return len(copied)


def _fill_from_neighbours(obj, empty):
    from mathutils.kdtree import KDTree
    verts = obj.data.vertices
    weighted = [v for v in verts if v.groups]
    kd = KDTree(len(weighted))
    for i, v in enumerate(weighted):
        kd.insert(v.co, i)
    kd.balance()
    for idx in empty:
        _, i, _ = kd.find(verts[idx].co)
        for g in weighted[i].groups:
            obj.vertex_groups[g.group].add([idx], g.weight, "REPLACE")


def test_action(a, poses, frames_per_pose=10):
    """`rig_test`: the rest pose at frame 1, then each pose in turn.
    A pose maps bone name → (x, y, z) Euler rotation in degrees, in the bone's local space."""
    arm = a.armature
    old = bpy.data.actions.get("rig_test")
    if old:
        bpy.data.actions.remove(old)
    arm.animation_data_create()
    act = bpy.data.actions.new("rig_test")
    act.use_fake_user = True
    arm.animation_data.action = act
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
    for i, pose in enumerate([{}] + list(poses)):
        frame = 1 + i * frames_per_pose
        for pb in arm.pose.bones:
            rot = pose.get(pb.name, (0, 0, 0))
            pb.rotation_euler = [math.radians(r) for r in rot]
            pb.keyframe_insert("rotation_euler", frame=frame)
    bpy.context.scene.frame_set(1)
    return act
