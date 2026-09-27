import os

import bpy
import numpy as np

import imgio

CHANNELS = {"albedo": ("Base Color", "sRGB"), "roughness": ("Roughness", "Non-Color"),
            "metallic": ("Metallic", "Non-Color")}


def triangulate(obj):
    """The one triangulation shared by bakes and export; a normal map is only valid on the triangles it was baked on."""
    mod = obj.modifiers.get("triangulate") or obj.modifiers.new("triangulate", "TRIANGULATE")
    mod.quad_method = "FIXED"
    mod.ngon_method = "BEAUTY"
    mod.keep_custom_normals = True
    return mod


def use_gpu(scene):
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == kind
            scene.cycles.device = "GPU"
            return kind
    scene.cycles.device = "CPU"
    return "CPU"


def principled(mat):
    nodes = [n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"] if mat.use_nodes else []
    if len(nodes) != 1:
        raise SystemExit(f"{mat.name} must end in exactly one Principled BSDF (found {len(nodes)})")
    return nodes[0]


def bake(a, stage, normal=None, ao_in_orm=True, samples=32, ao_samples=128, ao_distance=0.25):
    """Bake the zone materials on the asset mesh into textures/<stage>/<slug>_{albedo,orm[,normal]}.png.

    normal: None bakes one when a high mesh exists or a zone drives its Normal input.
    ao_in_orm: False writes occlusion as white, for styles that paint AO into the albedo.
    ao_distance: AO ray length in metres. It is absolute so that pieces of a set darken their creases alike."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    print(f"bake: device {use_gpu(scene)}")
    obj, size = a.mesh, a.spec["texture_size"]
    mats = list(obj.data.materials)
    for m in mats:
        principled(m)
    arm = a.armature
    if arm:
        rest, arm.data.pose_position = arm.data.pose_position, "REST"
    tri = triangulate(obj)
    settings = scene.render.bake
    settings.margin = max(4, size // 64)
    settings.margin_type = "EXTEND"
    maps = {}
    try:
        for name, (socket, cs) in CHANNELS.items():
            undo = [_emit(m, socket) for m in mats]
            try:
                maps[name] = _bake(scene, obj, mats, "EMIT", size, cs, samples)
            finally:
                for fn in undo:
                    fn()
        if ao_in_orm:
            scene.world = scene.world or bpy.data.worlds.new("bake")
            scene.world.light_settings.distance = ao_distance
            maps["ao"] = _bake(scene, obj, mats, "AO", size, "Non-Color", ao_samples)
        detail = any(principled(m).inputs["Normal"].links for m in mats)
        if normal or (normal is None and (a.high or detail)):
            maps["normal"] = _normal(scene, a, obj, mats, size, samples, detail)
    finally:
        obj.modifiers.remove(tri)
        if arm:
            arm.data.pose_position = rest

    out = a.textures(stage)
    os.makedirs(out, exist_ok=True)
    imgio.write(maps["albedo"], a.texture(stage, "albedo"), "sRGB")
    ones = np.ones_like(maps["roughness"][..., 0])
    orm = np.stack([maps["ao"][..., 0] if "ao" in maps else ones,
                    maps["roughness"][..., 0], maps["metallic"][..., 0]], axis=-1)
    imgio.write(orm, a.texture(stage, "orm"))
    if "normal" in maps:
        imgio.write(maps["normal"], a.texture(stage, "normal"))
    print(f"bake: wrote {', '.join(['albedo', 'orm'] + (['normal'] if 'normal' in maps else []))} to {out}")


def _emit(mat, socket):
    """Route a Principled input through an Emission shader to the output; returns the undo."""
    nt = mat.node_tree
    src = principled(mat).inputs[socket]
    out = nt.get_output_node("CYCLES")
    prev = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].links else None
    em = nt.nodes.new("ShaderNodeEmission")
    if src.links:
        nt.links.new(src.links[0].from_socket, em.inputs["Color"])
    else:
        v = src.default_value
        em.inputs["Color"].default_value = tuple(v) if hasattr(v, "__len__") else (v, v, v, 1)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])

    def undo():
        nt.nodes.remove(em)
        if prev is not None:
            nt.links.new(prev, out.inputs["Surface"])
    return undo


def _bake(scene, obj, mats, kind, size, colorspace, samples, high=None, extrusion=0.0):
    img = bpy.data.images.new(f"bake_{kind}", size, size, alpha=False)
    img.colorspace_settings.name = colorspace
    added = []
    for m in mats:
        n = m.node_tree.nodes.new("ShaderNodeTexImage")
        n.image = img
        m.node_tree.nodes.active = n
        added.append((m.node_tree, n))
    scene.cycles.samples = samples
    # The high mesh shares the low surface; left visible it occludes every ray the low casts.
    hidden = [o for o in bpy.context.view_layer.objects if o.name.endswith("_high") and o is not high]
    for o in hidden:
        o.hide_render = True
    for o in bpy.context.view_layer.objects:
        o.select_set(o in (obj, high))
    bpy.context.view_layer.objects.active = obj
    try:
        bpy.ops.object.bake(type=kind, use_clear=True, use_selected_to_active=high is not None,
                            cage_extrusion=extrusion, normal_space="TANGENT")
        return imgio.read(img)[..., :3].copy()
    finally:
        for o in hidden:
            o.hide_render = False
        for nt, n in added:
            nt.nodes.remove(n)
        bpy.data.images.remove(img)


def _normal(scene, a, obj, mats, size, samples, detail):
    geo = mat_detail = None
    if a.high:
        geo = _bake(scene, obj, mats, "NORMAL", size, "Non-Color", samples,
                    high=a.high, extrusion=0.02 * a.size())
    if detail or geo is None:
        mat_detail = _bake(scene, obj, mats, "NORMAL", size, "Non-Color", samples)
    if geo is None:
        return mat_detail
    if mat_detail is None:
        return geo
    return rnm(geo, mat_detail)


def rnm(base, detail):
    """Reoriented normal mapping: detail laid over base, both tangent-space maps in 0–1."""
    t = base * 2 + np.array([-1, -1, 0])
    u = detail * np.array([-2, -2, 2]) + np.array([1, 1, -1])
    r = t * (t * u).sum(-1, keepdims=True) / np.maximum(t[..., 2:3], 1e-4) - u
    r /= np.maximum(np.linalg.norm(r, axis=-1, keepdims=True), 1e-6)
    return r * 0.5 + 0.5
