"""Rig stage: skeleton, skin weights, and the rig_test action. Runs on model.blend with `asset` predefined."""
import rigging

H = asset.mesh.dimensions.z

# Joint positions come from evidence: rigging.section() pinches and the model review sheet.
# for z in (0.25 * H, 0.5 * H, 0.75 * H): print(z, rigging.section(asset, "z", z))

bones = [
    {"name": "root", "head": (0, 0, 0), "tail": (0, 0, 0.1 * H), "deform": False},
    {"name": "spine", "head": (0, 0, 0.1 * H), "tail": (0, 0, 0.6 * H), "parent": "root"},
    # {"name": "arm.L", "head": (...), "tail": (...), "parent": "spine"},   # .L bones mirror to .R
]
rigging.build(asset, bones)
rigging.bind(asset)  # skip=[...] names the extra chain bones, which rigging.chain weights below
# rigging.rigid(asset, "lid", "trim")  # solid parts: one bone, full weight
# rigging.chain(asset, ["beard_1", "beard_2"], "beard")  # hanging parts: blended along their own chain
rigging.test_action(asset, [
    {"spine": (30, 0, 0)},   # each pose: bone → (x, y, z) degrees, bone-local
    {"spine": (-30, 0, 0)},
    {"spine": (0, 45, 0)},
])
