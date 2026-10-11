# Discovery

What a package holds, how to read it, and the facts every later step needs.

## What a package holds

| kind | usually | pull from it |
|---|---|---|
| block-out | an FBX | every piece's geometry, hierarchy and name, top heights, how jump lips are marked |
| plans | top views of the routes, close-ups per corridor | the routes (the main one and the alternates), each jump's difficulty, heights, which piece is which |
| direction | an art-direction doc, a palette image | the game's style, the level's landscape, notes per corridor, measured colours, what it rules out |
| contract | the README's list of what must not change | top heights and outlines, the walkable angle, no new footholds, decor out of reach, water under jumps clear |
| references | photos | forms, materials and light. Usually internal. |

## Steps

1. Read the README and the direction in full first. They name everything else.
2. Look at every plan and reference image. Convert webp to PNG in your scratch folder first (`convert x.webp -resize '900x900>' x.png`), since it doesn't open directly.
3. Take an inventory of the block-out: groups, objects, face classes, colour layers and the colours on its tops.
   ```
   $BLENDER -b --factory-startup --python <skill>/tools/blockout_inventory.py -- <fbx> <scratch>/inventory.json
   ```
4. Extract it into kit data, the one file every generator reads instead of the FBX: per piece its corridor, role, vertices, faces, face kinds, tops with outlines, lips and bottom centre.
   ```
   $BLENDER -b --factory-startup --python <skill>/tools/blockout_extract.py -- <fbx> assets/_kit/<level>_blockout.json --water <z>
   ```
   - **Roles and corridors.** Both come from the hierarchy, by pattern: `--group-pattern role=regex` and `--corridor-pattern`. A mesh outside every group, such as a vault at the root, takes `--object-pattern decor=^name`. Check the inventory for meshes the extract skipped.
   - **Lip colours.** The extract lists every colour cluster on the tops and names each by its nearest palette colour. Decoding the clusters is your job.
5. Fit the tops to shapes:
   ```
   python3 <skill>/tools/shape_fit.py assets/_kit/<level>_blockout.json
   ```
   A designer's tool made the block-out, so expect a few parametric shapes in a few sizes, and identical tops repeated. The fit is what lets a few module classes cover every top (MODULES.md).
   - It proposes two covers, by shape alone and by shape and flare.
   - `--seed` fixes classes a brief has already named.
6. Pair the lips into jumps:
   ```
   python3 <skill>/tools/routes.py assets/_kit/<level>_blockout.json --start <first piece> --lip-colours <colour>=<difficulty>,... --world-guide <world_art.md> --map <scratch>/routes.png
   ```
   Check every jump against the plans. An unpaired lip or a wrong pair means a misread lip colour, or a jump the plan draws differently.
   - `--start` orients each jump away from the start. The block-out doesn't say which way the run goes.
   - The map has no labels, so read it beside the printed summary.
7. Render pieces in context for briefs and review:
   ```
   $BLENDER -b --factory-startup --python <skill>/tools/piece_views.py -- <fbx> <extract> <piece> <outdir>
   ```
   It renders an overview, a view level with the water, and the gameplay camera behind the take-off lip. Each camera is placed where the fewest objects block its view.
8. Look for prior work on the same game: other chains in `assets/_art`, and older guides elsewhere. The newer package wins where they conflict. Record each conflict.
9. Audit the block-out (below).

`<skill>` is this skill's folder, `.claude/skills/level-from-blueprint`.

## Facts to establish

- Units and axes: metres and Z up after import, and the engine conventions the FBX was exported with.
- Whether objects sit at the origin with world-space vertices. If so, the art keeps the block-out's orientation and the placements carry the offsets.
- The water or death plane, and how far pieces reach below it.
- Gameplay against decor: the hierarchy's groups, per corridor.
- Compound names (`a+b`): pieces welded into one mesh.
- How lips are marked, for example an inset ring on every top whose lip segments carry vertex colours, and what each colour means. Decode the colours against the plans' difficulties. When the package doesn't say, your reading is a judgement call for the designers to confirm.
- The slopes present: sides, chamfers, ramps and gentle slopes, against the walkable angle.
- How each piece is lit: open sky, under a closed vault (a cave material set), at night.
- Objects that aren't pieces, such as markers, spawn cubes and corridor helpers sitting on tops. Briefs name them as not part of a piece.
- Tiny tops, under about 1 m² or thinner than about 1.2 m. These are frame members or markers, not landings. Find out what they are, such as a finish gate or a railing, before modelling them.

## Audit the block-out

Some things the block-out does can't be fixed by art. Check for these and list them for the designers:

- **Closed volumes that aren't closed.** A cave vault whose side springs with nothing under it lets light in.
- **Views blocked along a run line.** For example, a finish that faces a wall. Check this before choosing where a backdrop goes.
- **Slivers and tiny faces at welds.** Clean them in the placement step, never in the extract, which stays the collision as exported.
- **Slopes too shallow for scaling.** A taper or flare shallower than the scale-safe angles (CONTRACT.md) leaves the art just inside it.

## Pitfalls

- **Measured colours include their light.** A "shadow" swatch at luma 14 is the engine's job. For an engine-lit world, build the albedo ladder on the mid values (GUIDES.md).
- **An older guide for the same game can contradict the package,** for example painted and organic against flat facets and sharp edges. The package wins, and the conflict goes in the report.
- **Plan images carry no scale.** Check their axes against two pieces' bounding boxes, then crop them by eye.
