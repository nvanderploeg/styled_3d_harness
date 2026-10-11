---
name: model-asset
description: Model a game-ready 3D asset in Blender with clean quad topology and UVs. Use when the user wants a 3D model, mesh or prop made, or a model's topology or UVs fixed.
---

# Model Asset

You write a Blender build script that makes the asset's low-poly mesh from nothing: quad-dominant, UV'd, zoned, at real-world scale. Read `pipeline/ASSET.md` first. It defines the asset folder, the scene conventions and the commands, and this skill assumes all of it.

## 1. Spec

If `assets/<slug>/` doesn't exist, run `pipeline/asset new <slug>`. Fill `asset.json` from the request: `brief`, `refs` (copy the images into `refs/`), `art`, `rig`, `height_m`, and `budget_class` from the world guide's `budgets`. When the guides have no budgets, set `tri_budget` and `texture_size` from the budget guide in ASSET.md.

Settle `texture_size` now. `unwrap` pads islands in pixels at that size, so changing it later means rebuilding the model.

Read every reference image, and every guide `pipeline/asset art <slug>` lists: the world's shape language and scale, the zone's shape and wear, the set's construction and `kit` measurements. Done when `asset.json` has a real height, a budget, and a brief a stranger could model from.

## 2. Plan the silhouette

Write the part list before any code. For each part give its shape, how you'll build it (lathe, extruded bmesh, a primitive plus modifiers), its zone, and its share of the tri budget. Spend triangles on **silhouette**: a loop earns its place by changing the outline in some view, by carrying a bend the rig will make, or by bounding a zone. Detail that doesn't reach the silhouette goes to the textures. Shape and size each part by the guides: their proportions, taper, lean and sag, their `scale` sizes, and the set's `kit` measurements.

When the spec has a `head_tri_budget` (every humanoid does), the head is budgeted apart: its parts share `head_tri_budget` and the rest share `tri_budget`. The head is the skull and face and what grows from or rides on them (hair, ears, a beard, a hat); the neck is body. Spend the head's triangles where the face reads: brow, nose, jaw, the eye sockets and mouth, and the ears and hair outline.

The guides' smallest facet sets the smallest part. Before planning a small piece, work out what it can show at that size: at 0.5 m facets, a 1 m shrub is one ring and a top.

Done when every visible feature of the brief and refs belongs to a part, every shape rule in the guides is either in the plan or named as not applying, and the budget shares add up to no more than `tri_budget`, and the head's to no more than `head_tri_budget`.

## 3. Build and iterate

Copy `pipeline/templates/model.py` to `build/model.py` and read the docstrings in `pipeline/lib/modeling.py`. Write the parts, zone every face, mark the head's faces with `head` when the spec has a head budget, then call `finalize` and `unwrap`. Add `make_high` when the asset has hard edges that would read better rounded in the normal map.

**High first**, for static rock and anything whose detail the budget can't hold: build the detailed mesh as `<slug>_high`, mark the faces that must stay exact (a gameplay top, a jump lip) with `modeling.keep`, and call `modeling.reduce` to make the low mesh at the budget. Mark them before `finalize`, and keep their outlines no denser than the budget allows: kept faces and zone borders never move, so their triangles count in full. Then `unwrap` the low, and skip `make_high`: the mesh you reduced from is the high. It is the bake source, for a shared asset's `bake` stage or a baked asset's texture stages, so the detail reaches the low through its normal map. Spend the high's polygons on what a bake can carry: chips, joint relief, narrow bevels. Take the variation from noise fields (Perlin noise for sizes and spacing that drift, Worley cells for cells and cracks) picking among planned planes, never from jittered vertices.

For a piece of a set, write the geometry as a function of the piece's parameters in `assets/_kit/` (ASSET.md, *Sets*). `build/model.py` is then one call to it. A guide rule the sheet can't show (an outline matched to a source mesh, a minimum slope, a tolerance) goes in a check the function runs and raises on, at both ends of any scale range the piece must survive.

Add `shots` to `asset.json` for what the sheet tiles are too small to judge: the gameplay camera, joints, damaged edges. Take the gameplay camera from the refs, or else the brief. With neither, frame the asset as a third-person camera would see it, about 4 m back and 30° above, and report that camera as a judgement call.

Run `pipeline/asset build <slug> model`. Fix every `FAIL`, and every `WARN` too unless you can say why it's harmless for this asset. Then read `review/model.png`, `review/model_uv.png` and `review/model_shots.png` and hold them to the rules below and the guides' shape rules. For each reference, compare its silhouette to the matching tile.

Done when the check passes, every rule below holds in the sheets, and for each view you can say in one line how it matches the brief. Anything you can't match is a named gap, not a silent one.

## Topology rules

- **Quads.** No n-gons. Triangles only where the surface is flat and never bends. A cap or a pole goes where nothing deforms or highlights. A reduced static mesh is the exception: `reduce` leaves triangles, and its budget class's `limits.max_tri_ratio` allows them.
- **Edge flow follows form.** Loops ring cylinders and limbs and run along creases. A spiral or a loop that dead-ends in the middle of a surface means the part was built wrong: rebuild it rather than patching.
- **Deforming meshes** (`rig` is not `"none"`): at least three loops across every joint the rig will bend, spaced evenly and perpendicular to the bend. Anything that bends is one connected surface. Model in the rest pose the rig expects: a humanoid faces −Y in an A-pose, or a T-pose when the request or a guide names one (rig-asset's HUMANOID.md). A part that will swing on its own bones (a beard, a cloak, a hat tip) takes three loops across it at each joint of its chain, like a limb.
- **Static meshes** may be separate intersecting shells (bands over a barrel, a buckle on a strap). Each shell is closed, and that's cheaper than merging them.
- **Even density.** Within a part, neighbouring quads stay roughly square and similar in size unless curvature asks for more loops. A loop still has to earn its place by the silhouette rule, so a flat part may be a few large quads.
- **No slivers.** A fill across a long outline needs a triangulation that keeps every corner open. The check fails a corner under `limits.min_corner_deg`, or a vertex lying on a straight side.

## Damage rules

Damage means crumble, chips, breaks and wear cut into the mesh. The zone and set guides say how much of it and where; these rules say how.

- **Decisive bites.** Use about one bite per metre of damaged edge. Each bite is large, with flat fracture planes meeting at hard edges and a step or ledge where material is missing. Per-vertex noise and smooth dents read as melted clay. Mark the fracture creases with `sharpen` so they shade as facets.
- **Planned planes.** Plan each bite's planes, then let a noise field choose which one a bite takes and where bites gather, never where a vertex goes. Free random planes leave edges shorter than the guides' smallest facet. A plane that clips a corner runs across the face's full width, so its outline is a trapezoid, never a notch narrowing to a point.
- **Seen from the side.** A bite drops the top edge too, not only its outline from above, so it reads from the gameplay camera.
- **Clear of what gameplay needs.** An edge the player relies on (a jump edge, a doorway, a socket) stays straight and square for a stated margin. Write the margin in `brief`.
- **Corners fold.** A bite beside a convex corner folds the faces there unless its neighbours move with it. Check the top tile and the shots for folded or sliver quads at every corner.

## UV rules

- **Seams** go on hard edges (`unwrap` marks these) and where they'll be seen least: bottoms, backs, insides, under overlapping parts. A cylinder gets one seam on its least visible side (`lathe`'s `seam_deg`), and a round part with few sides goes in `finalize`'s `smooth` so its sides aren't seamed as hard edges. Mark any extra seam in the script (`edge.seam = True` in bmesh) before `unwrap`.
- **Texel density** stays uniform; the check enforces it. Scale an island up only for a deliberate reason, and record it in `limits.texel_density_tolerance` and `brief`. When the limits in force carry a `texel_density_px_per_m` band, pick `texture_size` to land in it.
- **Coverage.** When many small parts leave UV coverage under `limits.min_uv_coverage`, `unwrap`'s `pad_px` may drop to 4 at a `texture_size` of 512 or less. If it still falls short, lower `limits.min_uv_coverage` in `asset.json` and report it as a judgement call.
- **Overlap** (stacked or mirrored islands) only when the brief accepts identical texturing on both sides. Set `limits.uv_overlap_ok` to allow it.
