"""Animation clips on a rigged asset: keyed poses, feet held to the ground, and the stand-in props a clip is
performed against. A pose maps bone name → (x, y, z) Euler degrees in the bone's local space, or
{"rot": (x, y, z), "loc": (x, y, z)} for a bone that also moves (metres, bone-local); unlisted bones rest."""
import math

import bpy
from mathutils import Euler, Quaternion, Vector

FPS = 30
MAX_SLIDE = 0.01
MAX_SINK = 0.02


def settings(a):
    """The spec's `animations`: fps, max_slide, max_sink, props by name, and clips by name in spec order."""
    spec = a.spec.get("animations") or {}
    return {"fps": spec.get("fps", FPS), "max_slide": spec.get("max_slide", MAX_SLIDE),
            "max_sink": spec.get("max_sink", MAX_SINK),
            "props": spec.get("props", {}), "clips": {c["name"]: c for c in spec.get("clips", [])}}


def apply(arm, pose):
    """Put the armature in pose."""
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        v = pose.get(pb.name, (0, 0, 0))
        rot, loc = (v.get("rot", (0, 0, 0)), v.get("loc", (0, 0, 0))) if isinstance(v, dict) else (v, (0, 0, 0))
        pb.rotation_euler = [math.radians(r) for r in rot]
        pb.location = loc
    bpy.context.view_layer.update()


def _with_rot(v, rot):
    return {**v, "rot": rot} if isinstance(v, dict) else rot


def _local_rot(arm, pb, matrix):
    m = arm.convert_space(pose_bone=pb, matrix=matrix, from_space="POSE", to_space="LOCAL")
    return tuple(math.degrees(x) for x in m.to_euler("XYZ"))


def reach(a, pose, targets):
    """pose with each bone in targets {bone: world point} placed by turning its two parent bones (upper arm
    and forearm, thigh and shin) so the bone's head lands on the point. The middle joint bends the way the
    pose already bends it, so key the elbow or knee pre-bent toward where it should point."""
    arm = a.armature
    apply(arm, pose)
    solved, rigs = dict(pose), []
    for bone, at in targets.items():
        mid = arm.pose.bones[bone].parent
        target = bpy.data.objects.new(f"reach_{bone}", None)
        bpy.context.scene.collection.objects.link(target)
        target.location = at
        ik = mid.constraints.new("IK")
        ik.target, ik.chain_count, ik.use_tail = target, 2, True
        rigs.append((target, mid, ik))
    bpy.context.view_layer.update()
    for _, mid, _ in rigs:
        for pb in (mid.parent, mid):
            solved[pb.name] = _with_rot(solved.get(pb.name, (0, 0, 0)), _local_rot(arm, pb, pb.matrix))
    for target, mid, ik in rigs:
        mid.constraints.remove(ik)
        bpy.data.objects.remove(target)
    apply(arm, solved)
    return solved


def plant(a, pose, feet, flat=True):
    """pose with each foot's head, the ankle, held where it is at rest by `reach`; with flat, each foot also
    turns back to its rest orientation. For a deep bend key the thighs and shins pre-bent and turned out, so
    the knees track over the feet. Use it on every key where a foot stays on the ground."""
    arm = a.armature
    solved = reach(a, pose, {f: arm.data.bones[f].head_local for f in feet})
    if flat:
        for foot in feet:
            pb = arm.pose.bones[foot]
            want = arm.data.bones[foot].matrix_local.copy()
            want.translation = pb.matrix.translation
            solved[foot] = _with_rot(solved.get(foot, (0, 0, 0)), _local_rot(arm, pb, want))
        apply(arm, solved)
    return solved


def clip(a, name, keys):
    """Action `name` from keys [(frame, pose)], the first at frame 1 and the last at the clip's `frames`.
    Every key is a whole pose. The clip's `planted` feet are planted on every frame, so they hold between
    keys too. The action replaces any of that name and is kept with a fake user."""
    arm = a.armature
    s = settings(a)
    bpy.context.scene.render.fps = s["fps"]
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data_create().action = act
    moving = {b for _, pose in keys for b, v in pose.items() if isinstance(v, dict) and "loc" in v}
    for frame, pose in keys:
        apply(arm, pose)
        for pb in arm.pose.bones:
            pb.keyframe_insert("rotation_euler", frame=frame)
            if pb.name in moving:
                pb.keyframe_insert("location", frame=frame)
    feet = s["clips"].get(name, {}).get("planted", [])
    legs = {b for f in feet for b in (f, arm.pose.bones[f].parent.name, arm.pose.bones[f].parent.parent.name)}
    if feet:
        solved = {}
        for frame in range(int(keys[0][0]), int(keys[-1][0]) + 1):
            bpy.context.scene.frame_set(frame)
            solved[frame] = plant(a, current(arm), feet)
            arm.animation_data.action = act
        # Settle the reassigned action now, or the first key's update re-evaluates it over that key's pose.
        bpy.context.view_layer.update()
        for frame, pose in solved.items():
            apply(arm, pose)
            for b in legs:
                arm.pose.bones[b].keyframe_insert("rotation_euler", frame=frame)
    arm.animation_data.action = None
    bpy.context.scene.frame_set(1)
    apply(arm, {})
    return act


def sample(keys, frames):
    """Whole poses for frames 1..frames through keys [(frame, pose)], for adding per-frame motion such as
    overlap before passing every frame to `clip`. Rotations blend as quaternions, so keys from `reach` or
    `plant` and keys posed by hand turn the short way; every channel eases into its keys without overshoot."""
    xs = [f for f, _ in keys]
    parts = [{b: _split(v) for b, v in p.items()} for _, p in keys]
    bones = {b for p in parts for b in p}
    out = [{} for _ in range(frames)]
    for b in bones:
        rots = [p.get(b, ((0, 0, 0), (0, 0, 0)))[0] for p in parts]
        locs = [p.get(b, ((0, 0, 0), (0, 0, 0)))[1] for p in parts]
        quats, prev = [], None
        for r in rots:
            q = Euler([math.radians(x) for x in r], "XYZ").to_quaternion()
            if prev is not None and q.dot(prev) < 0:
                q.negate()
            quats.append(q)
            prev = q
        last = None
        for f in range(1, frames + 1):
            q = Quaternion([_ease(xs, [qq[i] for qq in quats], f) for i in range(4)]).normalized()
            e = q.to_euler("XYZ", last) if last is not None else q.to_euler("XYZ")
            last = e
            rot = tuple(math.degrees(x) for x in e)
            loc = tuple(_ease(xs, [l[i] for l in locs], f) for i in range(3))
            out[f - 1][b] = {"rot": rot, "loc": loc} if any(loc) else rot
    return out


def spring(drive, delay, hz=1.6, damping=0.45, fps=FPS):
    """drive (one value per frame) followed `delay` frames late and loose: an underdamped spring, for a
    hanging part's overlap. Add the difference from drive to the part's own channel."""
    w, dt = 2 * math.pi * hz, 1 / fps
    x, v, out = drive[0], 0.0, []
    for f in range(len(drive)):
        target = drive[max(0, f - delay)]
        for _ in range(4):
            acc = w * w * (target - x) - 2 * damping * w * v
            v += acc * dt / 4
            x += v * dt / 4
        out.append(x)
    return out


def _split(v):
    return (tuple(v.get("rot", (0, 0, 0))), tuple(v.get("loc", (0, 0, 0)))) if isinstance(v, dict) \
        else (tuple(v), (0, 0, 0))


def _ease(xs, ys, x):
    """Fritsch–Carlson monotone cubic through (xs, ys) at x."""
    n = len(xs)
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    d = [(ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i]) for i in range(n - 1)]
    m = [0.0] + [0.0 if d[i - 1] * d[i] <= 0 else
                 3 * (d[i - 1] + d[i]) / ((2 * d[i] + d[i - 1]) / d[i - 1] + (d[i] + 2 * d[i - 1]) / d[i])
                 for i in range(1, n - 1)] + [0.0]
    k = max(i for i in range(n - 1) if xs[i] <= x)
    h = xs[k + 1] - xs[k]
    t = (x - xs[k]) / h
    return ((2 * t ** 3 - 3 * t ** 2 + 1) * ys[k] + (t ** 3 - 2 * t ** 2 + t) * h * m[k]
            + (-2 * t ** 3 + 3 * t ** 2) * ys[k + 1] + (t ** 3 - t ** 2) * h * m[k + 1])


def current(arm):
    """The armature's pose as a pose dict."""
    pose = {}
    for pb in arm.pose.bones:
        rot = tuple(math.degrees(x) for x in pb.rotation_euler)
        pose[pb.name] = {"rot": rot, "loc": tuple(pb.location)} if pb.location.length > 0 else rot
    return pose


def pose_at(act, frame):
    """{(data_path, index): value} for every channel of act at frame."""
    return {(fc.data_path, fc.array_index): fc.evaluate(frame) for fc in act.fcurves}


def props(a):
    """Box objects for the spec's props, for review and contact: {"size": [x, y, z], "at": [x, y, z]} with
    `at` the box's bottom centre. The caller removes them."""
    out = []
    for name, p in settings(a)["props"].items():
        me = bpy.data.meshes.new(f"prop_{name}")
        (sx, sy, sz), (x, y, z) = p["size"], p["at"]
        corners = [Vector((x + dx * sx / 2, y + dy * sy / 2, z + dz * sz))
                   for dx in (-1, 1) for dy in (-1, 1) for dz in (0, 1)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        me.from_pydata(corners, [], faces)
        obj = bpy.data.objects.new(f"prop_{name}", me)
        bpy.context.scene.collection.objects.link(obj)
        out.append(obj)
    return out
