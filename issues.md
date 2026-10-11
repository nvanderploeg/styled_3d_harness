# Open issues

Friction found by the battle-test workers, the rig, texture and animate agents, and review.

## Checks

- **`compare` drifts with lighting.** Zone luma leaves out down-facing faces, but it still moves with painted light and a part's height, so set pieces can flag or pass for reasons unrelated to the material.
- **UV padding isn't pixels.** Packed islands end up about 0.9 × `pad_px` apart, and the ratio drifts with the layout. `margin_method` (SCALED, ADD or FRACTION) makes no difference in 4.5, so a fix has to measure the packed gap.
- **Model rebuilds aren't deterministic with Bevel.** Face order and loop starts vary, so UVs move and `verify` reads CHANGED.
- **Texel density wobbles.** It varied 139.1–139.7 px/m across rebuilds that `verify` called IDENTICAL.
- **Hovering isn't caught.** The animate check fails a mesh below the ground, but not a seated body floating above it.
- **Hem chains aren't checked.** HUMANOID.md asks for front and back chains on a hem below the hips, and nothing enforces it. The dwarf's knee-length tunic has none, so seated it stands as a stiff tube.
- **No balance check.** The animate check can't tell when the body's weight leaves its support, and pops are only a WARN, since a fast strike can come close to the threshold.
- **Guides can loosen each other in prose.** `pipeline/asset art` compares limits only. A set's prose or `kit` value can grant what a world rule forbids, such as art growing into a jump's flight envelope, and nothing flags it.
- **Export ignores "changed since".** `export` accepts a stage whose status reads spec, data or module changes since its check.
- **Approval hashes follow the snapshot.** Any change to what `verify.snapshot` covers invalidates every approval. A float sitting on the hash's 6-decimal rounding boundary could also flip a hash; not seen yet.
- **Data Blender opens itself isn't tracked.** A build's `inputs` hold files Python opens. Images and linked libraries loaded through `bpy` don't show.

## Review sheets

- **Tiles have no labels.** Sheets list their tiles in the printed line only, since there's no text drawing in background Blender without a font path.
- **Lit tiles double the light.** Texture tiles light a stylized albedo with an HDRI on top of the painted light. Which light matches the game is a style decision the guides don't make.
- **Shots use fixed coordinates.** A proportion change means hand-editing every shot in `asset.json`.
- **No level view.** Sheets show one asset. A level's read (columns stacking into blocks from far cameras, the start and finish views) is judged on renders each kit makes of its own assembly.
- **The high mesh stays at rest.** `<slug>_high` isn't rigged, so any custom posed render shows it frozen over the posed mesh.

## Skills and docs

- **No value key without a guide.** A texture stage now fails when `texture_mode` is unset, but a guide-less stylized asset still has no `albedo_luma` or `max_saturation`, so those checks never fire.
- **No pivot other than the bottom centre.** `finalize` now reports and keeps its move (`asset.shift`), but the origin check rules out a pivot the engine wants elsewhere, like a lamppost's pole under a side arm.
- **Bone heat on a squat torso.** A thigh can reach the ribs. `rigging.mirror` fixes the asymmetry, but nothing says how to pull a thigh's reach back below the belt.
- **Installed guides predate the example fixes.** `assets/_art/azeroth` still has "north faces", "large pieces" and unsized "real size" rules, and the dwarf kit's shoulder width pulls against Dun Morogh's squat ratio.
- **Example set slugs.** The Darkshire pieces are `darkshire_*` in a set folder named `human_village`, and nothing says how set pieces are named.

## Helpers

- **`lathe` flat caps leave sharp rims.** A cap meets the side at a hard 90°, with no option to round or dome it.
- **No character modelling helpers.** Rings on other axes, loop bridging and caps were each written by hand.
- **Planting pulls feet home.** `animation.clip` plants a clip's planted feet at their standing spots, so an idle whose feet rest elsewhere (a cross-legged sit) can't plant them. The dwarf's animate script passes `clip` a spec without them.
- **`courses` works only on axis-aligned walls.**
- **The bake cage is fixed.** `bake.detail` extrudes its ray cage by 2% of the asset's size. A low that strays further from its high, near a deep chip, can catch inverted normals; only the normal map's mean is checked.
- **Slow UV packing.** `modeling.unwrap` turns on `use_uv_select_sync`, and with it `uv.pack_islands(rotate=True)` takes 20 s or more on a plain cube; without it, packing is instant. Changing it moves every built asset's UVs.
- **`painted_light` has no thin-part exclusion** for STYLIZED.md's small-facet rule.
- **Olive patches in normal bakes.** The WoW butcher table's texture_ref normal map has patches of strongly tilted normals on some long plank faces, both before and after the `make_high` change. The cage likely reaches a neighbouring plank.

## Environment

- **Skills load from the main checkout.** An agent in a worktree runs the main checkout's `.claude/skills`, so a skill edit in the worktree goes untested.
- **Worktree shell guard.** The worktree sandbox refused compound shell commands, which slowed every agent.
- **Level tools test against one package.** `level-from-blueprint/tools/test_tools.py` checks the tools against la montée's block-out and kit, so it runs only from that project.

## Assets built before the latest checks

- **Every built stage, again.** `materials` and `min_corner_deg` joined the spec fingerprint, so every built stage reads `spec changed` until `verify` clears it. A report written before approvals has no snapshot: `check` or `verify` the stage before `approve`.
- **Every built stage.** `status` now flags `pipeline/lib` changes, and this round touched most modules, so each approved stage needs `verify`.
- **Warcraft butcher table.** Its texture_ref now fails the shell-aware contrast check: planks against timber, and the cleaver's iron against the planks.
- **WoW dwarf.** Its animate stage now fails `max_sink`: the tunic's back hem, weighted rigidly to the hips, sinks 3.8–4.6 cm into the seat (HUMANOID.md now asks for hem chains).
- **Castle platforms.** Their texture_ref will verify CHANGED, because the edge highlight now takes the zone's colour.
