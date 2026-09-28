"""Animation clips on a rigged asset: keyed poses, feet held to the ground, and the stand-in props a clip is
performed against. A pose maps bone name → (x, y, z) Euler degrees in the bone's local space, or
{"rot": (x, y, z), "loc": (x, y, z)} for a bone that also moves (metres, bone-local); unlisted bones rest."""
import math

import bpy
from mathutils import Vector

FPS = 30
MAX_SLIDE = 0.01


def settings(a):
    """The spec's `animations`: fps, max_slide, props by name, and clips by name in spec order."""
    spec = a.spec.get("animations") or {}
    return {"fps": spec.get("fps", FPS), "max_slide": spec.get("max_slide", MAX_SLIDE),
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


def plant(a, pose, feet, flat=True):
    """pose with each foot's two parent bones (thigh and shin) turned so the foot's head, the ankle, stays
    where it is at rest; with flat, each foot also turns back to its rest orientation. The solve starts from
    the pose's own thigh and shin, so for a deep bend key them pre-bent and turned out, and the knees track
    over the feet. Use it on every key where a foot stays on the ground."""
    arm = a.armature
    apply(arm, pose)
    solved, rigs = dict(pose), []
    for foot in feet:
        shin = arm.pose.bones[foot].parent
        target = bpy.data.objects.new(f"plant_{foot}", None)
        bpy.context.scene.collection.objects.link(target)
        target.location = arm.data.bones[foot].head_local
        ik = shin.constraints.new("IK")
        ik.target, ik.chain_count, ik.use_tail = target, 2, True
        rigs.append((target, shin, ik))
    bpy.context.view_layer.update()
    for _, shin, _ in rigs:
        for pb in (shin.parent, shin):
            solved[pb.name] = _with_rot(solved.get(pb.name, (0, 0, 0)), _local_rot(arm, pb, pb.matrix))
    for target, shin, ik in rigs:
        shin.constraints.remove(ik)
        bpy.data.objects.remove(target)
    apply(arm, solved)
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
