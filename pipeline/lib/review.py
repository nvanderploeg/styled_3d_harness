import math
import os
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

import imgio
import material
import rigging
import uvmath

TILE = 512
SHOT = 768
VIEWS = {
    "front": ((0, -1, 0), True),
    "right": ((1, 0, 0), True),
    "back": ((0, 1, 0), True),
    "left": ((-1, 0, 0), True),
    "top": ((0, 0, 1), True),
    "three_quarter": ((1, -1, 0.7), False),
    "three_quarter_back": ((-1, 1, 0.7), False),
    "front_right_low": ((1, -0.55, 0.3), False),
}
SHEETS = {
    "model": ["front", "right", "back", "left", "top", "three_quarter", "three_quarter_back", "high"],
    "texture": ["front", "right", "back", "left", "top", "three_quarter", "three_quarter_back", "unlit"],
}


def run(a, stage):
    scene = bpy.context.scene
    scene.render.resolution_x = scene.render.resolution_y = TILE
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("review")
    cam = bpy.data.objects.new("review_cam", bpy.data.cameras.new("review_cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    for o in scene.objects:
        o.hide_render = o.type not in {"MESH", "CAMERA"} or o == a.high

    out = a.path("review", f"{stage}.png")
    if stage == "model":
        tiles = model_tiles(a, scene, cam)
        uv_layout(a, a.path("review", "model_uv.png"))
        names = SHEETS["model"] if a.high else SHEETS["model"][:-1]
        print(f"review: {out}  (tiles: {', '.join(names)})")
        print(f"review: {a.path('review', 'model_uv.png')}  (grey islands, red overlap, white edges)")
    elif stage == "rig":
        tiles, frames = rig_tiles(a, scene, cam)
        print(f"review: {out}  (three-quarter view at each rig_test pose, frames {frames}; shots at rest)")
    elif stage == "animate":
        tiles, rows = animate_tiles(a, scene, cam)
        save_sheet(tiles, out)
        print(f"review: {out}  (one row per clip, from the front right: "
              f"{'; '.join(f'{n} frames {fs}' for n, fs in rows)})")
        return
    else:
        tiles = texture_tiles(a, stage, scene, cam)
        print(f"review: {out}  (tiles: {', '.join(SHEETS['texture'])})")
        maps_sheet(a, stage)
    save_sheet(tiles, out)
    shot_sheet(a, stage, scene, cam)


def shot_sheet(a, stage, scene, cam):
    """review/<stage>_shots.png from asset.json `shots`: framed close-ups and gameplay cameras.
    Texture stages render each shot lit, then unlit."""
    shots = a.spec.get("shots") or []
    if not shots:
        return
    scene.render.resolution_x = scene.render.resolution_y = SHOT
    textured = stage.startswith("texture")
    tiles = []
    for s in shots:
        place(cam, Vector(s["target"]), Vector(s.get("from", (1, -1, 0.7))), s["distance"], s.get("lens", 50))
        if textured:
            eevee(scene)
            tiles.append(render(scene))
            workbench(scene, color_type="TEXTURE", light="FLAT")
        tiles.append(render(scene))
    out = a.path("review", f"{stage}_shots.png")
    save_sheet(tiles, out, cols=2 if textured else min(4, len(tiles)))
    per = "lit, unlit" if textured else "one tile each"
    print(f"review: {out}  (shots: {', '.join(s['name'] for s in shots)}; {per})")


def posed_points(obj):
    """(n, 3) world positions of obj's deformed vertices at the current frame."""
    me = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3) @ np.array(obj.matrix_world.to_3x3()).T + np.array(obj.matrix_world.translation)


def look(cam, d):
    """Point cam back along d (target → camera), keeping world Z up; straight-down views keep +Y up."""
    f = -d.normalized()
    up = Vector((0, 1, 0)) if abs(f.z) > 0.999 else Vector((0, 0, 1))
    r = f.cross(up).normalized()
    cam.rotation_euler = Matrix((r, r.cross(f), -f)).transposed().to_euler()
    return r, r.cross(f)


def place(cam, target, direction, distance, lens=50):
    """Perspective camera `distance` metres from target along direction."""
    cam.data.type = "PERSP"
    cam.data.lens = lens
    cam.location = target + direction.normalized() * distance
    look(cam, direction)
    cam.data.clip_start = distance * 0.01
    cam.data.clip_end = distance * 10


def aim(cam, pts, view, pad=1.08):
    """Frame the (n, 3) world points pts from view, so the outermost just fits."""
    direction, ortho = VIEWS[view]
    d = Vector(direction).normalized()
    right, up = look(cam, d)
    right, up, dn = np.array(right), np.array(up), np.array(d)
    x, y = pts @ right, pts @ up
    center = Vector(right * (x.min() + x.max()) / 2 + up * (y.min() + y.max()) / 2 + dn * (pts @ dn).mean())
    rel = pts - np.array(center)
    x, y, z = rel @ right, rel @ up, rel @ dn
    radius = float(np.linalg.norm(rel, axis=1).max()) or 1.0
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 2 * max(np.abs(x).max(), np.abs(y).max()) * pad
        dist = radius * 4
    else:
        cam.data.type = "PERSP"
        cam.data.lens = 50
        tan = math.tan(cam.data.angle / 2)
        dist = float((np.maximum(np.abs(x), np.abs(y)) * pad / tan + z).max())
    cam.location = center + d * dist
    cam.data.clip_start = dist * 0.01
    cam.data.clip_end = dist * 4


def render(scene):
    path = os.path.join(tempfile.mkdtemp(), "tile.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return imgio.read(path)


GUTTER = 6
PAPER = (0.5, 0.5, 0.5, 1)


def blank(size=TILE):
    t = np.empty((size, size, 4), np.float32)
    t[:] = PAPER
    return t


def save_sheet(tiles, path, cols=4):
    """Tiles left to right, top to bottom, on grey paper with a gutter between them."""
    rows = math.ceil(len(tiles) / cols)
    h, w = tiles[0].shape[:2]
    grid = np.empty((rows * h + (rows - 1) * GUTTER, cols * w + (cols - 1) * GUTTER, 4), np.float32)
    grid[:] = PAPER
    for i, t in enumerate(tiles):
        r, c = divmod(i, cols)
        y = (rows - 1 - r) * (h + GUTTER)   # image rows run bottom-up
        x = c * (w + GUTTER)
        grid[y:y + h, x:x + w] = t
    imgio.write(grid, path, "sRGB")


def workbench(scene, color_type="MATERIAL", light="STUDIO"):
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = light
    sh.color_type = color_type
    sh.show_cavity = light != "FLAT"
    sh.show_specular_highlight = False
    scene.world.color = (0.18, 0.18, 0.2)


def wire_overlay(a, obj):
    """A dark wireframe twin of obj that follows its modifiers, so topology reads over the shading. Lines thin
    where edges are short, so a dense face stays visible between them."""
    wire = obj.copy()
    wire.data = obj.data.copy()
    wire.name = f"{obj.name}_wire"
    bpy.context.scene.collection.objects.link(wire)
    dark = bpy.data.materials.new("wire")
    dark.diffuse_color = (0.02, 0.02, 0.02, 1)
    for slot in wire.material_slots:
        slot.link = "OBJECT"
        slot.material = dark
    me = wire.data
    ends = np.empty(len(me.edges) * 2, np.int32)
    me.edges.foreach_get("vertices", ends)
    ends = ends.reshape(-1, 2)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lengths = np.linalg.norm(co[ends[:, 0]] - co[ends[:, 1]], axis=1)
    total = np.bincount(ends.ravel(), np.repeat(lengths, 2), len(co))
    count = np.maximum(np.bincount(ends.ravel(), minlength=len(co)), 1)
    thickness = 0.0025 * a.size()
    scale = np.clip(0.12 * total / count / thickness, 0.1, 1.0)
    group = wire.vertex_groups.new(name="wire_scale")
    for i, w in enumerate(scale):
        group.add([i], float(w), "REPLACE")
    mod = wire.modifiers.new("wire", "WIREFRAME")
    mod.thickness = thickness
    mod.vertex_group = group.name
    mod.thickness_vertex_group = 0.0
    mod.use_even_offset = True
    mod.use_replace = True
    mod.offset = 1
    return wire


def model_tiles(a, scene, cam):
    workbench(scene)
    low, high = a.mesh, a.high
    wire = wire_overlay(a, low)
    pts = posed_points(low)
    tiles = []
    for v in SHEETS["model"][:-1]:
        aim(cam, pts, v)
        tiles.append(render(scene))
    if high:
        low.hide_render = wire.hide_render = True
        high.hide_render = False
        aim(cam, pts, "three_quarter")
        tiles.append(render(scene))
        low.hide_render = wire.hide_render = False
        high.hide_render = True
    return tiles


AXES = ((1, 0, 0, 1), (0, 0.8, 0, 1), (0.1, 0.3, 1, 1))


def socket_markers(a):
    """An axis tripod at each attachment point, riding its bone and drawn over the mesh: X red, Y (along
    the bone) green, Z blue."""
    arm = a.armature
    size = 0.06 * a.size()
    out = []
    for name in (n for n in rigging.SOCKETS if n in arm.data.bones):
        me = bpy.data.meshes.new(f"marker_{name}")
        bm = bmesh.new()
        for axis, color in enumerate(AXES):
            me.materials.append(_flat(f"marker_axis_{axis}", color))
            lo, hi = [-0.06 * size] * 3, [0.06 * size] * 3
            hi[axis] = size
            cube = bmesh.ops.create_cube(bm, size=1.0)["verts"]
            for v in cube:
                v.co = [lo[i] if v.co[i] < 0 else hi[i] for i in range(3)]
            for f in {f for v in cube for f in v.link_faces}:
                f.material_index = axis
        bm.to_mesh(me)
        bm.free()
        obj = bpy.data.objects.new(me.name, me)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent, obj.parent_type, obj.parent_bone = arm, "BONE", name
        obj.location = (0, -arm.data.bones[name].length, 0)
        obj.show_in_front = True
        out.append(obj)
    return out


def _flat(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def rig_tiles(a, scene, cam):
    """One tile per rig_test key, each framed on its own posed mesh, then the armature back at rest."""
    workbench(scene)
    arm, obj = a.armature, a.mesh
    act = bpy.data.actions["rig_test"]
    arm.animation_data_create().action = act
    wire_overlay(a, obj)
    socket_markers(a)
    frames = sorted({int(round(k.co.x)) for fc in act.fcurves for k in fc.keyframe_points})
    tiles = []
    for f in frames:
        scene.frame_set(f)
        aim(cam, posed_points(obj), "three_quarter")
        tiles.append(render(scene))
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis = Matrix()
    scene.frame_set(1)
    return tiles, frames


def animate_tiles(a, scene, cam, per_clip=4):
    """Per clip, a row of per_clip frames from its first to its last, all framed alike, with the spec's
    props in grey. Textured by the latest texture stage."""
    import animation
    arm, obj = a.armature, a.mesh
    tex = a.latest("texture")
    if tex:
        obj.data.materials.clear()
        obj.data.materials.append(material.baked(a, tex))
        eevee(scene)
    else:
        workbench(scene)
    grey = bpy.data.materials.new("prop")
    grey.diffuse_color = (0.35, 0.35, 0.37, 1)
    grey.use_nodes = True
    grey.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = grey.diffuse_color
    boxes = animation.props(a)
    for b in boxes:
        b.data.materials.append(grey)
    arm.animation_data_create()
    rows = []
    for name, c in animation.settings(a)["clips"].items():
        rows.append((name, sorted({int(round(f)) for f in np.linspace(1, c["frames"], per_clip)})))
    pts = [posed_points(b) for b in boxes]
    for name, frames in rows:
        arm.animation_data.action = bpy.data.actions[name]
        for f in frames:
            scene.frame_set(f)
            pts.append(posed_points(obj))
    pts = np.concatenate(pts)
    tiles = []
    for name, frames in rows:
        arm.animation_data.action = bpy.data.actions[name]
        for f in frames:
            scene.frame_set(f)
            aim(cam, pts, "front_right_low")
            tiles.append(render(scene))
        tiles += [blank()] * (per_clip - len(frames))
    return tiles, rows


def texture_tiles(a, stage, scene, cam):
    obj = a.mesh
    obj.data.materials.clear()
    obj.data.materials.append(material.baked(a, stage))
    eevee(scene)
    pts = posed_points(obj)
    tiles = []
    for v in SHEETS["texture"][:-1]:
        aim(cam, pts, v)
        tiles.append(render(scene))
    workbench(scene, color_type="TEXTURE", light="FLAT")
    aim(cam, pts, "three_quarter")
    tiles.append(render(scene))
    return tiles


def maps_sheet(a, stage):
    """review/<stage>_maps.png: the baked maps flat, as the engine reads them."""
    tiles, names = [], []
    orm = a.texture(stage, "orm")
    for name, path, channel in (("albedo", a.texture(stage, "albedo"), None), ("occlusion", orm, 0),
                                ("roughness", orm, 1), ("metallic", orm, 2),
                                ("normal", a.texture(stage, "normal"), None)):
        if not os.path.exists(path):
            continue
        img = imgio.read(path)
        if channel is not None:
            img = np.concatenate([np.repeat(img[..., channel:channel + 1], 3, axis=2), img[..., 3:]], axis=2)
        step = max(1, img.shape[0] // TILE)
        tiles.append(img[::step, ::step])
        names.append(name)
    if not tiles:
        return
    out = a.path("review", f"{stage}_maps.png")
    save_sheet(tiles, out, cols=len(tiles))
    print(f"review: {out}  (maps: {', '.join(names)})")


def eevee(scene):
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 32
    w = scene.world
    if not (w.use_nodes and any(n.type == "TEX_ENVIRONMENT" for n in w.node_tree.nodes)):
        world_hdri(scene)


def world_hdri(scene):
    root = os.path.join(bpy.utils.system_resource("DATAFILES"), "studiolights", "world")
    hdri = os.path.join(root, "courtyard.exr")
    w = scene.world
    w.use_nodes = True
    nt = w.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(hdri)
    bg = nt.nodes["Background"]
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    # Light with the HDRI, but show the camera a flat backdrop.
    backdrop = nt.nodes.new("ShaderNodeBackground")
    backdrop.inputs["Color"].default_value = (0.18, 0.18, 0.2, 1)
    path = nt.nodes.new("ShaderNodeLightPath")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(path.outputs["Is Camera Ray"], mix.inputs[0])
    nt.links.new(bg.outputs["Background"], mix.inputs[1])
    nt.links.new(backdrop.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes["World Output"].inputs["Surface"])


def uv_layout(a, path, res=1024):
    me = a.mesh.data
    tri_uv, _ = uvmath.triangles(me)
    cov = uvmath.raster(tri_uv, res)
    img = np.zeros((res, res, 4), np.float32)
    img[..., 3] = 1
    img[..., :3] = 0.08
    img[cov == 1, :3] = 0.35
    img[cov > 1, :3] = (0.8, 0.1, 0.1)
    segs = uvmath.uv_edges(me) * (res - 1)
    for p, q in segs:
        n = int(np.ceil(np.abs(q - p).max())) + 1
        t = np.linspace(0, 1, n)[:, None]
        pts = np.rint(p + (q - p) * t).astype(int).clip(0, res - 1)
        img[pts[:, 1], pts[:, 0], :3] = 0.95
    imgio.write(img, path, "sRGB")
