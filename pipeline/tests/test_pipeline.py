"""Pipeline invariants (pipeline/ASSET.md), run inside Blender:
    ~/opt/blender/blender --background --factory-startup --python pipeline/tests/test_pipeline.py
"""
import contextlib
import io
import json
import math
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
import rigging  # noqa: E402
import animation  # noqa: E402

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


# --- rigging

def test_a_chain_blends_a_hanging_part_from_its_parent_to_its_tip():
    """A beard hanging below a head bone on a two-bone chain. At the chin it follows the head, at the tip
    it follows the last bone, and between them each vertex splits its weight between two neighbours."""
    clear_scene()
    a = new_asset("beardy", rig="humanoid")
    obj = mesh_object("beardy", {"skin": [((-0.1, -0.1, 1.0), (0.1, 0.1, 1.2))],
                                 "beard": [((-0.05, -0.15, 0.6), (0.05, -0.1, 1.0))]})
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    beard = [f for f in bm.faces if f.material_index == 1]
    bmesh.ops.subdivide_edges(bm, edges=list({e for f in beard for e in f.edges if abs(e.verts[0].co.z - e.verts[1].co.z) > 0.1}),
                              cuts=7, use_grid_fill=True)
    bm.to_mesh(obj.data)
    bm.free()
    rigging.build(a, [
        {"name": "root", "head": (0, 0, 0), "tail": (0, 0, 0.1), "deform": False},
        {"name": "head", "head": (0, 0, 1.0), "tail": (0, 0, 1.2), "parent": "root"},
        {"name": "beard_1", "head": (0, -0.12, 1.0), "tail": (0, -0.12, 0.8), "parent": "head"},
        {"name": "beard_2", "head": (0, -0.12, 0.8), "tail": (0, -0.12, 0.6), "parent": "beard_1"},
    ], mirror=False)
    rigging.rigid(a, "head", "skin")
    rigging.chain(a, ["beard_1", "beard_2"], "beard")
    groups = {g.index: g.name for g in obj.vertex_groups}

    def weights(v):
        return {groups[g.group]: round(g.weight, 3) for g in v.groups if g.weight > 1e-4}

    beard_verts = sorted((v for v in obj.data.vertices if v.co.y < -0.099 and v.co.z < 0.999),
                         key=lambda v: -v.co.z)
    assert weights(beard_verts[-1]) == {"beard_2": 1.0}, weights(beard_verts[-1])
    chin = [v for v in obj.data.vertices if v.co.y < -0.099 and abs(v.co.z - 1.0) < 1e-4]
    assert chin and all(weights(v) == {"head": 1.0} for v in chin), [weights(v) for v in chin]
    for v in beard_verts:
        w = weights(v)
        assert len(w) <= 2 and abs(sum(w.values()) - 1) < 1e-3, w
    mid = [weights(v) for v in beard_verts if abs(v.co.z - 0.8) < 1e-3]
    assert mid and all(w == {"beard_1": 0.5, "beard_2": 0.5} for w in mid), mid



# --- animation

LEGS = {"clips": [], "props": {}}


def biped(**animations):
    """A box biped on hips, thighs, shins and feet, with animations as its spec's `animations`."""
    clear_scene()
    a = new_asset("walker", rig="humanoid", animations=animations)
    parts = {"hips": ((-0.15, -0.1, 0.5), (0.15, 0.1, 0.9))}
    for side, x in (("L", 0.1), ("R", -0.1)):
        parts[f"thigh.{side}"] = ((x - 0.05, -0.06, 0.29), (x + 0.05, 0.04, 0.5))
        parts[f"shin.{side}"] = ((x - 0.05, -0.06, 0.07), (x + 0.05, 0.04, 0.28))
        parts[f"foot.{side}"] = ((x - 0.05, -0.16, 0.0), (x + 0.05, 0.04, 0.06))
    mesh_object("walker", {"body": list(parts.values())})
    rigging.build(a, [
        {"name": "root", "head": (0, 0, 0), "tail": (0, 0, 0.1), "deform": False},
        {"name": "hips", "head": (0, 0, 0.5), "tail": (0, 0, 0.7), "parent": "root"},
        {"name": "thigh.L", "head": (0.1, 0, 0.5), "tail": (0.1, -0.02, 0.28), "parent": "hips"},
        {"name": "shin.L", "head": (0.1, -0.02, 0.28), "tail": (0.1, 0, 0.06), "parent": "thigh.L"},
        {"name": "foot.L", "head": (0.1, 0, 0.06), "tail": (0.1, -0.14, 0.02), "parent": "shin.L"},
    ])
    obj = a.mesh
    obj.modifiers.new("rig", "ARMATURE").object = a.armature
    for bone, (lo, hi) in parts.items():
        rigging.rigid(a, bone, lambda co, lo=lo, hi=hi: all(lo[i] - 1e-4 <= co[i] <= hi[i] + 1e-4 for i in range(3)))
    return a


def animate_report(a):
    r = checks.Report()
    checks.animate_checks(a, r)
    return r


SQUAT = {"hips": {"rot": (0, 0, 0), "loc": (0, -0.12, 0)}}   # an upright hips bone's local Y is world Z
FEET = ["foot.L", "foot.R"]


def test_a_planted_clip_holds_its_feet_while_the_hips_drop():
    a = biped(clips=[{"name": "squat", "frames": 20, "loop": True, "planted": FEET}])
    animation.clip(a, "squat", [(1, {}), (10, SQUAT), (20, {})])
    r = animate_report(a)
    assert not r.fails, r.fails
    assert r.metrics["planted_slide_m"]["squat"] <= 0.001, r.metrics
    a.armature.animation_data.action = bpy.data.actions["squat"]
    bpy.context.scene.frame_set(10)
    assert a.armature.pose.bones["hips"].head.z < 0.4, "the hips never dropped"


def test_a_planted_clip_keys_its_first_frame_from_its_first_pose():
    # The last key pre-bends the knees, as a deep sit does to steer the solve; frame 1 must not inherit them.
    a = biped(clips=[{"name": "sit", "frames": 20, "planted": FEET}])
    bent = {**SQUAT, "thigh.L": (-40, 0, 0), "shin.L": (60, 0, 0), "thigh.R": (-40, 0, 0), "shin.R": (60, 0, 0)}
    animation.clip(a, "sit", [(1, {}), (20, bent)])
    r = animate_report(a)
    assert not r.fails, r.fails
    act = bpy.data.actions["sit"]
    thigh = act.fcurves.find('pose.bones["thigh.L"].rotation_euler', index=0)
    assert abs(thigh.evaluate(1)) < 1e-3, f"frame 1 thigh keyed at {math.degrees(thigh.evaluate(1)):.1f}°"


def test_the_check_holds_planted_feet_loops_and_hand_offs():
    a = biped(clips=[{"name": "sink", "frames": 20, "loop": True, "to": "rise"}, {"name": "rise", "frames": 10}])
    animation.clip(a, "sink", [(1, {}), (20, SQUAT)])
    a.spec["animations"]["clips"][0]["planted"] = FEET   # keyed before its feet were planted
    animation.clip(a, "rise", [(1, {"hips": (10, 0, 0)}), (10, {})])
    bpy.data.actions["sink"].fcurves.find('pose.bones["hips"].scale', index=0) or \
        bpy.data.actions["sink"].fcurves.new('pose.bones["hips"].scale', index=0).keyframe_points.insert(1, 1.0)
    fails = "\n".join(animate_report(a).fails)
    assert "slides a planted bone" in fails and "below the ground" in fails, fails
    assert "loop 'sink' ends away from its start" in fails, fails
    assert "ends away from the first frame of 'rise'" in fails, fails
    assert "scales hips" in fails, fails


def test_only_a_rigged_asset_with_clips_has_an_animate_stage():
    clip = {"clips": [{"name": "idle", "frames": 30, "loop": True}]}
    assert "animate" in new_asset("a1", rig="humanoid", animations=clip).stages()
    assert "animate" not in new_asset("a2", rig="humanoid").stages()
    assert "animate" not in new_asset("a3", animations=clip).stages()


def test_clips_change_only_the_animate_stage_fingerprint():
    before = new_asset("a1", rig="humanoid")
    after = new_asset("a1", rig="humanoid", animations={"clips": [{"name": "idle", "frames": 30}]})
    assert after.fingerprint("rig") == before.fingerprint("rig")
    assert after.fingerprint("texture_ref") == before.fingerprint("texture_ref")
    assert after.fingerprint("animate") != before.fingerprint("animate")


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
