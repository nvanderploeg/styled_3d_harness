"""Pipeline invariants (pipeline/ASSET.md), run inside Blender:
    ~/opt/blender/blender --background --factory-startup --python pipeline/tests/test_pipeline.py
"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import traceback

ROOT = tempfile.mkdtemp(prefix="pipeline_test_")
os.environ["ASSETS_DIR"] = ROOT
HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "..", "templates", "art")
sys.path.insert(0, os.path.join(HERE, "..", "lib"))

import bmesh  # noqa: E402
import bpy  # noqa: E402
import numpy as np  # noqa: E402

import asset as asset_mod  # noqa: E402
import checks  # noqa: E402
import imgio  # noqa: E402
import nodes  # noqa: E402
import review  # noqa: E402

PLACES = {"world_art.md": "azeroth", "zone_art.md": "azeroth/duskwood",
          "set_art.md": "azeroth/duskwood/human_village"}


def install_examples():
    shutil.rmtree(asset_mod.ART, ignore_errors=True)
    for name, where in PLACES.items():
        os.makedirs(os.path.join(asset_mod.ART, where), exist_ok=True)
        shutil.copy(os.path.join(EXAMPLES, f"{name}.example"), os.path.join(asset_mod.ART, where, name))


def new_asset(slug, **spec):
    d = os.path.join(ROOT, slug)
    os.makedirs(os.path.join(d, "build"), exist_ok=True)
    with open(os.path.join(d, "asset.json"), "w") as f:
        json.dump({"slug": slug, **spec}, f)
    return asset_mod.Asset(slug)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def rejects(fn, words):
    try:
        fn()
    except SystemExit as e:
        assert words in str(e.code), f"expected '{words}' in: {e.code}"
        return
    raise AssertionError(f"expected a rejection mentioning '{words}'")


def box(bm, lo, hi):
    """An axis-aligned closed box from corner lo to corner hi, added to bm."""
    geom = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    for v in geom:
        v.co = [lo[i] if v.co[i] < 0 else hi[i] for i in range(3)]


def mesh_object(name, boxes_by_zone):
    """One mesh object whose shells are boxes, each box's faces in its zone."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for i, (zone, boxes) in enumerate(boxes_by_zone.items()):
        me.materials.append(bpy.data.materials.get(f"zone_{zone}") or bpy.data.materials.new(f"zone_{zone}"))
        for lo, hi in boxes:
            before = set(bm.faces)
            box(bm, lo, hi)
            for f in set(bm.faces) - before:
                f.material_index = i
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def status_lines(a):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        asset_mod.status(a)
    return dict(line.split(None, 1) for line in out.getvalue().splitlines())


# --- budget classes

def test_a_budget_class_supplies_its_budget_and_limits():
    a = new_asset("dwarf", art="azeroth", budget_class="character")
    assert a.spec["tri_budget"] == 12000 and a.spec["texture_size"] == 2048
    # The class band sits above the world's [160, 320]; it replaces it rather than failing to tighten it.
    assert a.limits["texel_density_px_per_m"] == [480, 960]


def test_asset_json_overrides_its_budget_class():
    a = new_asset("dwarf", art="azeroth", budget_class="character", tri_budget=6000,
                  limits={"texel_density_px_per_m": [400, 900]})
    assert a.spec["tri_budget"] == 6000 and a.spec["texture_size"] == 2048
    assert a.limits["texel_density_px_per_m"] == [400, 900]


def test_an_unknown_budget_class_is_rejected():
    rejects(lambda: new_asset("dwarf", art="azeroth", budget_class="vehicle"), "vehicle")
    rejects(lambda: new_asset("crate", budget_class="small_prop"), "none")


def test_a_new_spec_leaves_the_budget_to_its_class():
    with contextlib.redirect_stdout(io.StringIO()):
        asset_mod.new("barrel")
    with open(os.path.join(ROOT, "barrel", "asset.json")) as f:
        spec = json.load(f)
    assert "tri_budget" not in spec and "texture_size" not in spec and "budget_class" in spec


def test_naming_a_budget_class_changes_the_fingerprint_only_through_its_values():
    plain = new_asset("crate", art="azeroth").fingerprint()
    assert new_asset("crate", art="azeroth", budget_class=None).fingerprint() == plain
    same = new_asset("crate", art="azeroth", budget_class="large_prop", tri_budget=2000, texture_size=1024)
    assert same.fingerprint() == new_asset("crate", art="azeroth", tri_budget=2000, texture_size=1024).fingerprint()


# --- kit staleness

def test_kit_modules_follow_imports_through_the_kit():
    kit = asset_mod.KIT
    write(os.path.join(kit, "walls.py"), "import stone\nimport math\n")
    write(os.path.join(kit, "stone.py"), "from paint import ramp\n")
    write(os.path.join(kit, "paint.py"), "import os\n")
    write(os.path.join(kit, "roofs.py"), "")
    script = os.path.join(ROOT, "piece", "build", "model.py")
    write(script, "import walls\nimport bpy\n")
    found = [os.path.basename(p) for p in asset_mod.kit_modules(script)]
    assert found == ["paint.py", "stone.py", "walls.py"], found


def test_status_flags_only_the_kit_modules_a_stage_imports():
    kit = asset_mod.KIT
    write(os.path.join(kit, "walls.py"), "")
    write(os.path.join(kit, "roofs.py"), "")
    a = new_asset("piece")
    write(a.script("model"), "import walls\n")
    write(a.blend("model"), "")
    built = os.path.getmtime(a.blend("model"))
    write(a.path("review", "model.json"), json.dumps({"pass": True, "built": built, "spec": a.fingerprint(),
                                                      "fail": []}))
    later = built + 10
    os.utime(os.path.join(kit, "roofs.py"), (later, later))
    assert status_lines(a)["model"] == "pass", status_lines(a)
    os.utime(os.path.join(kit, "walls.py"), (later, later))
    assert "_kit (walls.py) changed" in status_lines(a)["model"]


def test_a_recheck_of_the_same_build_keeps_its_verify_stamp():
    clear_scene()
    a = new_asset("crate")
    mesh_object("crate", {"wood": [((-0.5, -0.5, 0), (0.5, 0.5, 1))]})
    write(a.blend("model"), "")
    write(a.path("review", "model.json"), json.dumps({"built": os.path.getmtime(a.blend("model")),
                                                      "verified": 123.0}))
    with contextlib.redirect_stdout(io.StringIO()):
        checks.run(a, "model")
    assert a.report("model")["verified"] == 123.0
    time.sleep(0.01)
    write(a.blend("model"), "rebuilt")
    with contextlib.redirect_stdout(io.StringIO()):
        checks.run(a, "model")
    assert "verified" not in a.report("model")


# --- zone contrast

def test_neighbours_include_shells_that_intersect_or_rest_on_each_other():
    clear_scene()
    obj = mesh_object("table", {
        "top": [((-0.5, -0.3, 0.8), (0.5, 0.3, 1.0))],
        "leg": [((-0.45, -0.25, 0.0), (-0.35, -0.15, 0.85))],   # pushed into the top
        "cloth": [((-0.2, -0.2, 1.0), (0.2, 0.2, 1.01))],       # resting on it
        "crate": [((2.0, 2.0, 0.0), (2.5, 2.5, 0.5))],          # standing apart
    })
    assert checks.neighbours(obj) == [("cloth", "top"), ("leg", "top")], checks.neighbours(obj)


# --- review sheets

def test_model_review_leaves_the_low_mesh_showing_for_the_shots():
    clear_scene()
    a = new_asset("crate")
    mesh_object("crate", {"wood": [((-0.5, -0.5, 0), (0.5, 0.5, 1))]})
    mesh_object("crate_high", {"wood": [((-0.5, -0.5, 0), (0.5, 0.5, 1))]})
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new("review")
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    real = review.render
    review.render = lambda scene: None
    try:
        review.model_tiles(a, scene, cam)
    finally:
        review.render = real
    assert not a.mesh.hide_render and a.high.hide_render


# --- painted light

def test_edge_paint_lights_convex_edges_and_darkens_intersections():
    """A block with a leg pushed up into it, seen from the front. The block's lower front edge is convex,
    and the line where the leg enters the block is an intersection seam: it must read concave, never lit."""
    clear_scene()
    obj = mesh_object("probe", {"main": [((-0.5, -0.5, 0.8), (0.5, 0.5, 1.2)),
                                         ((-0.1, -0.1, 0.0), (0.1, 0.1, 1.0))]})
    mat = obj.data.materials[0]
    t = nodes.tree(mat)
    convex, concave = t._folds(0.02, 20.0)
    rgb = t.node("ShaderNodeCombineXYZ")
    t.set(rgb.inputs[0], convex)
    t.set(rgb.inputs[1], concave)
    emit = t.node("ShaderNodeEmission")
    t.set(emit.inputs["Color"], rgb.outputs[0])
    t.nt.links.new(emit.outputs[0], next(n for n in t.nt.nodes if n.type == "OUTPUT_MATERIAL").inputs[0])

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64
    scene.cycles.device = "CPU"
    scene.world = bpy.data.worlds.new("black")
    scene.world.color = (0, 0, 0)
    scene.view_settings.view_transform = "Standard"
    res = 400
    scene.render.resolution_x = scene.render.resolution_y = res
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1.6
    cam.location = (0, -5, 0.6)
    cam.rotation_euler = (np.pi / 2, 0, 0)
    scene.camera = cam
    out = os.path.join(ROOT, "folds.png")
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    img = imgio.read(out)

    def at(x, z):
        return img[int((z + 0.2) / 1.6 * res), int((x + 0.8) / 1.6 * res), :2]

    block_edge, seam, face, leg_edge = at(0.3, 0.806), at(0.0, 0.794), at(0.3, 1.0), at(0.096, 0.4)
    assert block_edge[0] > 0.5, f"convex block edge not lit: {block_edge}"
    assert leg_edge[0] > 0.5, f"convex leg edge not lit: {leg_edge}"
    assert seam[0] < 0.15, f"intersection seam lit as convex: {seam}"
    assert seam[1] > 0.3, f"intersection seam not concave: {seam}"
    assert face.max() < 0.1, f"flat face carries edge paint: {face}"


def main():
    failed = 0
    only = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    for name, fn in [(n, f) for n, f in globals().items() if n.startswith("test_")]:
        if only and not any(o in name for o in only):
            continue
        clear_scene()
        shutil.rmtree(ROOT, ignore_errors=True)
        os.makedirs(ROOT)
        install_examples()
        try:
            fn()
            print(f"PASS {name}")
        except (Exception, SystemExit):
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    shutil.rmtree(ROOT, ignore_errors=True)
    print(f"{failed} failed" if failed else "all passed")
    sys.exit(1 if failed else 0)


main()
