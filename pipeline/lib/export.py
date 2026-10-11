import json
import os
import shutil

import bpy

import animation
import bake
import material
import rigging


def export(a):
    order = a.stages()
    if a.shared:
        last = order[-1]
        if last == "bake" and not os.path.exists(a.blend("bake")):
            last = order[-2]
        tex = "bake" if order.index(last) >= order.index("bake") else None
    else:
        tex = a.latest("texture")
        if tex is None:
            raise SystemExit("nothing to export — no texture stage is built")
        last = "animate" if a.animated else tex
    for s in order[: order.index(last) + 1]:
        rep = a.report(s)
        if not os.path.exists(a.blend(s)) or not rep or not rep["pass"] \
                or rep.get("built") != os.path.getmtime(a.blend(s)):
            raise SystemExit(f"stage '{s}' has not passed its check — run: pipeline/asset build {a.slug} {s}")

    bpy.ops.wm.open_mainfile(filepath=a.blend(last))
    clips = list(animation.settings(a)["clips"]) if a.animated else []
    for act in list(bpy.data.actions):
        if act.name not in clips:
            bpy.data.actions.remove(act)
    obj, arm = a.mesh, a.armature
    if a.high:
        bpy.data.objects.remove(a.high)
        bpy.context.view_layer.update()
    if a.shared:
        zones = [m.name for m in obj.data.materials]
        maps = {k: a.texture(tex, k) for k in ("normal", "occlusion")} if tex else {}
        for m in obj.data.materials:
            material.preview(m, a.swatch(m.name[5:]), **maps)
    else:
        zones = None
        obj.data.materials.clear()
        obj.data.materials.append(material.baked(a, tex))
    bake.triangulate(obj)
    if arm:
        arm.animation_data.action = None
        for pb in arm.pose.bones:
            pb.matrix_basis.identity()

    out_dir = a.path("export")
    os.makedirs(out_dir, exist_ok=True)
    glb = os.path.join(out_dir, f"{a.slug}.glb")
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (obj, arm))
    bpy.ops.export_scene.gltf(
        filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
        export_animations=bool(clips), export_animation_mode="ACTIONS", export_force_sampling=True,
        export_def_bones=False, export_tangents=True, export_image_format="AUTO",
    )
    if tex:
        tex_out = os.path.join(out_dir, "textures")
        os.makedirs(tex_out, exist_ok=True)
        for f in os.listdir(a.textures(tex)):
            shutil.copy2(os.path.join(a.textures(tex), f), tex_out)

    ok = verify(a, glb, clips, zones, maps=bool(tex))
    print(f"export {glb}: {'PASS' if ok else 'FAIL'}")
    if not ok:
        os.remove(glb)
        raise SystemExit("exported file failed verification and was removed")


def verify(a, glb, clips=(), zones=None, maps=False):
    """Re-import the file into an empty scene and confirm what an engine will see: one baked, textured
    material, or with zones, exactly those zone materials, each with the bake's normal and occlusion textures
    when maps and no texture otherwise, and never a colour texture."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    shapes = {pb.custom_shape for arm in arms for pb in arm.pose.bones}
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o not in shapes]
    fails = []
    if len(meshes) != 1:
        fails.append(f"{len(meshes)} meshes in the file, expected 1")
    else:
        me = meshes[0].data
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        print(f"  tris: {tris}  materials: {[m.name for m in me.materials]}")
        budget = a.spec["tri_budget"] + (a.spec.get("head_tri_budget") or 0)
        if tris > budget:
            fails.append(f"{tris} tris exceeds the tri budget {budget}")
        if zones is not None:
            found = sorted(m.name for m in me.materials)
            if found != sorted(zones):
                fails.append(f"materials {found}, expected the zones {sorted(zones)}")
            want = {"normalTexture", "occlusionTexture"} if maps else set()
            for m in gltf(glb).get("materials", []):
                has = {k for k in (*m, *m.get("pbrMetallicRoughness", {})) if k.endswith("Texture")}
                if has != want:
                    fails.append(f"{m['name']} carries {sorted(has) or 'no textures'}, expected "
                                 f"{sorted(want) or 'none'}")
        elif len(me.materials) != 1:
            fails.append(f"{len(me.materials)} materials, expected 1")
        elif not any(n.type == "TEX_IMAGE" for n in me.materials[0].node_tree.nodes):
            fails.append("material carries no textures")
    if a.rigged:
        if len(arms) != 1:
            fails.append(f"{len(arms)} armatures, expected 1")
        elif meshes and not any(m.type == "ARMATURE" for m in meshes[0].modifiers):
            fails.append("mesh is not skinned to the armature")
        else:
            print(f"  bones: {len(arms[0].data.bones)}")
            if a.spec["rig"] == "humanoid":
                missing = [n for n in rigging.SOCKETS if n not in arms[0].data.bones]
                if missing:
                    fails.append(f"attachment points missing from the file: {missing}")
    found = sorted(act.name for act in bpy.data.actions)
    if clips or found:
        print(f"  animations: {found}")
    if sorted(clips) != found:
        fails.append(f"animations {found}, expected {sorted(clips)}")
    print(f"  size: {os.path.getsize(glb) / 1e6:.2f} MB")
    for f in fails:
        print(f"FAIL {f}")
    return not fails


def gltf(glb):
    """The JSON chunk of a .glb: what an engine reads before any buffer."""
    with open(glb, "rb") as f:
        head = f.read(20)
        return json.loads(f.read(int.from_bytes(head[12:16], "little")))
