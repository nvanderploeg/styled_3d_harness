# Delivery and look builds

## Look build

A look build is a quick scene of the assembled level that the requester can open, made at each checkpoint and kept separate from the delivery. It has:

- simple world-space triplanar materials, with each module's normal and occlusion maps once they are baked
- a switch that shows the block-out collision
- a few cameras: start, finish and overview

Offer it early. On one level, the requester asked "I just want to look at it" before the package was done.

In Godot, run the editor headless with `XDG_CONFIG_HOME`, `XDG_DATA_HOME` and `XDG_CACHE_HOME` set to absolute paths in the project. Otherwise it writes into the user's home.

## Manifest

One manifest gathers every placement table:

- **Adapters.** One adapter per table schema flattens a table into rows: instance id, slug, layer, corridor, position, rotation, scale, material set and waived rules. A table in an unknown schema is skipped, and the manifest says why.
- **Both frames.** Rows are in Blender's frame (Z up) and the engine's. For Unity from Blender:

  | | Unity |
  |---|---|
  | position | (−x, z, −y) |
  | yaw | −rot_z |
  | scale | (sx, sz, sy) |
- **Instance ids.** An id is the name the assembly gives its object, so every row traces to an assembled corridor.
- **Approval state:**

  | list | holds | in the package |
  |---|---|---|
  | modules | approved and placed | yes |
  | spares | approved but unplaced | yes |
  | pending | placed but unapproved | yes, flagged |
- **Data layers.** Layers with no mesh ship as data: decals (the take-off lip marks among them), flocks and effect emitters.

## Round trip

Prove the engine frame without the engine:

1. Read each module's export the way the engine's importer does: units, the handedness mirror, winding.
2. Rebuild every corridor from the manifest.
3. Compare it with the assembled corridor vertex by vertex. Both sides go through the same reader, so its convention cancels out.
4. Check the winding of mirrored instances.

On one level the round trip covered 411 instances, with a worst error of 38.7 µm.

## Package

The zip has no top folder. It holds:

- each module's file, by layer, with its normal and occlusion maps
- the manifest
- the material library and shader spec
- the block-out, as the collision
- the assembled corridors, for reference
- an importer: an editor script that builds the scene and prefabs

A guard refuses any reference image.

Lanes rewrite their tables while you pack, so build every derived file (the corridor files and the manifest) from the tables in one pass.

## Pack early and often

Start the delivery lane before the last meshes land, and pack after every gate. Each pack surfaces:

- placed but unapproved modules, as pending
- an approval mistake, as a whole family pending
- a contract failure in one lane caused by another, before that lane reports
