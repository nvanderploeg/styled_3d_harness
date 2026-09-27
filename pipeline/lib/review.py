import math
import os
import tempfile

import bpy
import numpy as np
from mathutils import Matrix, Vector

import imgio
import material
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
        print(f"review: {out}  (tiles: {', '.join(SHEETS['model'])})")
        print(f"review: {a.path('review', 'model_uv.png')}  (grey islands, red overlap, white edges)")
    elif stage == "rig":
        tiles, frames = rig_tiles(a, scene, cam)
        print(f"review: {out}  (three-quarter view at rig_test frames {frames})")
    else:
        tiles = texture_tiles(a, stage, scene, cam)
        print(f"review: {out}  (tiles: {', '.join(SHEETS['texture'])})")
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
    save_sheet(tiles, out, cols=2 if textured else 4)
    per = "lit, unlit" if textured else "one tile each"
    print(f"review: {out}  (shots: {', '.join(s['name'] for s in shots)}; {per})")


def bounds(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = []
    for o in objs:
        ev = o.evaluated_get(dg)
        pts += [ev.matrix_world @ Vector(c) for c in ev.bound_box]
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


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


def aim(cam, lo, hi, view, pad=1.08):
    direction, ortho = VIEWS[view]
    d = Vector(direction).normalized()
    center = (lo + hi) / 2
    radius = (hi - lo).length / 2 or 1.0
    right, up = look(cam, d)
    if ortho:
        cam.data.type = "ORTHO"
        half = (hi - lo) / 2
        extent = max(sum(abs(half[i] * right[i]) for i in range(3)),
                     sum(abs(half[i] * up[i]) for i in range(3)))
        cam.data.ortho_scale = 2 * extent * pad
        dist = radius * 4
    else:
        cam.data.type = "PERSP"
        cam.data.lens = 50
        dist = radius / math.sin(cam.data.angle / 2) * pad
    cam.location = center + d * dist
    cam.data.clip_start = dist * 0.01
    cam.data.clip_end = dist * 4


def render(scene):
    path = os.path.join(tempfile.mkdtemp(), "tile.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return imgio.read(path)


def blank(size=TILE):
    t = np.zeros((size, size, 4), np.float32)
    t[..., 3] = 1
    return t


def save_sheet(tiles, path, cols=4):
    rows = math.ceil(len(tiles) / cols)
    tiles = tiles + [blank(tiles[0].shape[0])] * (rows * cols - len(tiles))
    # Image rows run bottom-up; lay tiles out top-down so the sheet reads left-to-right, top-to-bottom.
    grid = np.concatenate([np.concatenate(tiles[r * cols:(r + 1) * cols], axis=1) for r in reversed(range(rows))], axis=0)
    imgio.write(grid, path, "sRGB")


def workbench(scene, color_type="MATERIAL", light="STUDIO"):
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = light
    sh.color_type = color_type
    sh.show_cavity = light != "FLAT"
    scene.world.color = (0.18, 0.18, 0.2)


def wire_overlay(a, obj):
    """A dark wireframe twin of obj that follows its modifiers, so topology reads over the shading."""
    wire = obj.copy()
    wire.name = f"{obj.name}_wire"
    bpy.context.scene.collection.objects.link(wire)
    dark = bpy.data.materials.new("wire")
    dark.diffuse_color = (0.02, 0.02, 0.02, 1)
    for slot in wire.material_slots:
        slot.link = "OBJECT"
        slot.material = dark
    mod = wire.modifiers.new("wire", "WIREFRAME")
    mod.thickness = 0.0025 * a.size()
    mod.use_even_offset = True
    mod.use_replace = True
    mod.offset = 1
    return wire


def model_tiles(a, scene, cam):
    workbench(scene)
    low, high = a.mesh, a.high
    wire = wire_overlay(a, low)
    lo, hi = bounds([low])
    tiles = []
    for v in SHEETS["model"][:-1]:
        aim(cam, lo, hi, v)
        tiles.append(render(scene))
    if high:
        low.hide_render = wire.hide_render = True
        high.hide_render = False
        aim(cam, lo, hi, "three_quarter")
        tiles.append(render(scene))
    return tiles


def rig_tiles(a, scene, cam):
    workbench(scene)
    arm, obj = a.armature, a.mesh
    act = bpy.data.actions["rig_test"]
    arm.animation_data_create().action = act
    wire_overlay(a, obj)
    scene.frame_set(int(act.frame_range[0]))
    lo, hi = bounds([obj])
    pad = (hi - lo) * 0.25
    lo, hi = lo - pad, hi + pad
    f0, f1 = act.frame_range
    frames = sorted({int(round(f)) for f in np.linspace(f0, f1, 8)})
    tiles = []
    for f in frames:
        scene.frame_set(f)
        aim(cam, lo, hi, "three_quarter", pad=1.0)
        tiles.append(render(scene))
    return tiles, frames


def texture_tiles(a, stage, scene, cam):
    obj = a.mesh
    obj.data.materials.clear()
    obj.data.materials.append(material.baked(a, stage))
    eevee(scene)
    lo, hi = bounds([obj])
    tiles = []
    for v in SHEETS["texture"][:-1]:
        aim(cam, lo, hi, v)
        tiles.append(render(scene))
    workbench(scene, color_type="TEXTURE", light="FLAT")
    aim(cam, lo, hi, "three_quarter")
    tiles.append(render(scene))
    return tiles


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
