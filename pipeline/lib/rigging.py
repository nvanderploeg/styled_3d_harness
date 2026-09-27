import math

import bmesh
import bpy
from mathutils import Vector


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
    deform (default True). With mirror, every `.L` bone gets a `.R` twin across X."""
    old = a.armature
    if old:
        bpy.data.objects.remove(old)
    specs = list(bones)
    if mirror:
        for b in bones:
            if b["name"].endswith(".L"):
                m = dict(b, name=b["name"][:-2] + ".R",
                         head=_flip(b["head"]), tail=_flip(b["tail"]), roll=-b.get("roll", 0))
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


def bind(a, max_influences=None, threshold=0.01):
    """Parent the mesh to the rig with automatic (bone heat) weights, then clean them."""
    obj, arm = a.mesh, a.armature
    obj.vertex_groups.clear()
    for m in [m for m in obj.modifiers if m.type == "ARMATURE"]:
        obj.modifiers.remove(m)
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (obj, arm))
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    clean(a, max_influences, threshold)


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


def rigid(a, bone, where):
    """Weight vertices fully to one bone: a zone name, or a predicate on the vertex position.
    For parts that move as a solid (wheels, lids, armour plates)."""
    obj = a.mesh
    if isinstance(where, str):
        slots = [m.name for m in obj.data.materials]
        idx = slots.index(f"zone_{where}")
        verts = {v for p in obj.data.polygons if p.material_index == idx for v in p.vertices}
    else:
        verts = {v.index for v in obj.data.vertices if where(v.co)}
    vg = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
    for g in obj.vertex_groups:
        if g != vg:
            g.remove(list(verts))
    vg.add(list(verts), 1.0, "REPLACE")
    return len(verts)


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
