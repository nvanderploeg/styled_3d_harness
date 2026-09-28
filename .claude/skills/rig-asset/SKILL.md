---
name: rig-asset
description: Rig a modeled game asset in Blender with a deform skeleton, skin weights and a test action. Use when the user wants a model rigged, skinned or weighted, or its deformation fixed.
---

# Rig Asset

You write a build script that gives the model a game skeleton: deform bones only, at most four influences per vertex, and one root. The script also adds a `rig_test` action that bends every joint. Read `pipeline/ASSET.md` first. It defines the asset folder, the scene conventions and the commands.

The rig builds on `model.blend`. If the model is failing or stale (`pipeline/asset status <slug>`), fix it first. A rig can't rescue topology that has no loops at the joints.

## 1. Find the joints

Set `rig` in `asset.json` if it's `"none"`. For a humanoid, read [HUMANOID.md](HUMANOID.md) now; its required bones replace the ones you would design, its *Extra bones* section says when a part gets a chain of its own, and its *Attachment points* are the sockets every humanoid carries.

Locate every pivot from evidence. `rigging.section(asset, axis, value)` cuts the mesh and returns each island's centre and size: a limb is an island, and a joint is where its size pinches. Cross-check each pivot on `review/model.png`. A joint sits at the centre of the limb's cross-section, where the loops the model put there bunch up.

Done when every bone has a head and tail you can justify with a section or a visible feature.

## 2. Build, bind, exercise

Copy `pipeline/templates/rig.py` to `build/rig.py` and read the docstrings in `pipeline/lib/rigging.py`.

- **Skeleton.** One non-deforming root at the origin, with every other bone below it. Bones run along the limb's centreline. Name paired bones `.L` / `.R` and let `build` mirror the `.L` side. Set the roll so that each joint's main bend is a rotation about its local X.
- **Weights.** Call `bind` for automatic weights, `rigid` for solid parts that must move as one piece (wheels, lids, plates), and `chain` for parts that hang on a chain of their own (beards, cloaks, tails). On a symmetric mesh, finish with `mirror`, since bone heat weights the two sides unevenly on squat or wide bodies.
- **Test action.** `test_action` with poses that take every joint to the far end of its expected range and back. Include twist on anything that twists. A pose the rig will never make in game proves nothing.

## 3. Build and review

Run `pipeline/asset build <slug> rig` and fix every `FAIL`. Then read `review/rig.png` frame by frame and look for:

- **Collapse.** A joint pinches thin or folds flat (candy-wrapper on twist).
- **Stragglers.** Vertices left behind that stretch into spikes.
- **Bleed.** A part moves with a bone it doesn't belong to, such as a leg with the other leg or a sleeve with the torso.
- **Wrong axis.** A joint bends sideways or backwards.
- **Sockets.** On a humanoid, each attachment point's tripod sits where HUMANOID.md puts it and points its green Y and blue Z the way the table says, in every frame. Add a `shots` entry on a hand when the sheet is too small to show the grip inside it.

Fix a weight problem in the script (`rigid`, a bone moved to its true pivot, or an added bone) and rebuild. Done when the check passes and every frame shows clean bends at every joint.
