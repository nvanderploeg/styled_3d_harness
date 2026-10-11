# Guides for a level

How a package maps onto the harness's three guide layers, and what each guide needs for a level built from modules. The `art-guide` skill writes them, and this file says what goes in.

## Layers

| the package's | goes in |
|---|---|
| the game's style, the games it borrows from, the contract | world |
| the level's or segment's landscape, colours, corridors, light, references | zone |
| how block-out pieces become art: construction from kit data, forms, the piece table | one set per family: gameplay, decor, backdrop, each dressing family |

- **A corridor variant of one zone,** such as a cave stretch, is a parallel swatch rung (`cave_top` beside `top`) and a material set the engine swaps. It is not a new zone.
- **Sea, foam and sky** are the engine's. Name their values in prose so the ladder can be compared with them, never as swatches: they break the value limits, and no mesh zone uses them.

## World guide

- **Ranked pillars:**
  1. *Faithful to the block-out* (CONTRACT.md).
  2. *Readable*: a top is the lightest, flattest, cleanest large surface around it and lands by its value alone. Only a take-off lip carries a mark, a quiet one, and nothing out of reach wears a top's colours.
  3. *Modular*: caps on stacks of bodies, placed from a table.
  4. The style's own pillars.
  5. *Natural before built*, when the world has it.
- **Natural before built names the tells of a made thing,** so lanes and gates can look for them:
  - square sections or right angles that read
  - parallel faces
  - even courses or bond seams
  - stepped rectangular edges
  - straight, unbroken edges
  - uniform fills, and sizes or spacing that repeat
  - rounded bars
  - a silhouette that is only its collision's

  Every send-back on one level was one of these, and every one passed every numeric check. A level whose every piece passed still read as regular: unbroken edges and repeated measures were what the requester saw first.
- **Shape**:
  - cap and body
  - sharp lips, broken edges: a lip edge is straight and exact; every other top edge chips and wanders within `edge_variance_m`, with deeper breaks down the band, cut in planes and never rounded
  - steep below at every scale, and no break leaves a ledge
  - bodies inside the footprint
  - the block-out as collision
  - the additions rule and flight envelopes
  - one oversized chamfer
  - a minimum facet size
  - high to low: detail on a high mesh, reduced to the budget with tops and lips kept exact, baked to a normal and an occlusion map
  - varied by noise: Perlin noise for sizes and spacing that drift, Worley cells for columns, plates and cracks. Noise picks a planned plane or size; it never jitters a vertex

  The contract's keys are in CONTRACT.md.
- **Painting, engine-lit:**
  - Materials hold the surface's colour and none of the light.
  - One shared tiling material per zone, triplanar in world space at `shape.tile_m`. Each module adds its own normal and occlusion maps on its UVs.
  - Layered noise at several scales, plus a world-space variation over `shape.macro_m` that hides the tile. Nothing finer than `shape.paint_min_m`.
  - Weathered by exposure: rock facing the sky above the spray is dry and paler, rock in joints, hollows and caves damp and darker, from the world normal, the occlusion map and height. Never a sun direction.
  - Wet by world height in the shader.
  - Values alone carry the read from body to top.

  Set `texture_mode: "pbr"` and `materials: "shared"`.
- **Budgets per module class:** cap, body (one segment), decor, dressing and backdrop. A budget bounds the low mesh, and reduced static rock is mostly triangles, so the static classes set `limits.max_tri_ratio` to 1. `texture_size` sets the module's normal and occlusion maps. A class's `limits.albedo_luma` caps the value of what sits near routes, so additions stay a step under the tops.

## Zone guide

Build the palette as a value ladder:

1. Compute luma (Rec. 601) and saturation for every measured colour first.
2. Drop the shadow and lit extremes, since photos carry their light. Build the albedo ladder on the mid values.
3. Order the zones by where they sit on a piece: wet, side, crust, top. Space the rungs about 25–30 luma apart, with every touching pair clearing `min_zone_contrast` plus 6.
4. Give the body material a damp and a dry rung from the measured colours, such as a deep and a grey basalt. Exposure blends between them. The palest dry rung stays under the tops less `min_zone_contrast`.
5. Set the take-off lip mark a few luma above the top, under `min_zone_contrast` on purpose, painted as a decal. A rim around every top reads as a painted curb at game distance, and even a quiet one makes every platform look alike.
6. Check that the sea's value sits between the sides and the tops.

- **Name each swatch for its material.** A swatch named for light (`foliage_lit`) invites painted light in an engine-lit world, so call it `foliage_dry`.
- **`painted_light` only tints the review sheets** in an engine-lit world. The guide says so.
- **`wet` is the shader's target, not a zone.** The zone sets the waterline and `wet_m`.

## Set guides

- **Construction from data.** `kit.data` names the extract. The set says how each block-out piece becomes modules: families from the shape fit, cap classes, body forms, origins, the placement table and slugs (MODULES.md).
- **Name the failure look.** For every rule a number can't hold, say what breaking it looks like on a sheet, such as "anything that reads as masonry breaks *Natural before built*". Naming the look fixed a piece in one round. Naming only the rule didn't.
- **State shapes, not only sizes.** A joint given as a depth and an angle came out as cushions. "A step: a crisp edge and a short underside above, one chamfer below" came out as drums.
- **Every default names its fallback.** A rule written as "prefer X where it fits, else Y within Z" survives the piece where X is impossible.
- **Never loosen a world rule.** `pipeline/asset art` rejects a looser limit, but it can't read prose or `kit` values. Before granting art beyond collision or a closer placement, check the grant against the world's additions and envelope rules. An exception is a waiver for the requester to decide (CONTRACT.md).
- **Measure; don't copy the plan.** Re-measure the block-out rather than copying the catalogue's numbers. Catalogues get wall depths and crown shapes wrong.

## Pitfalls

- **Top-level keys.** `art.py` accepts only the top-level keys in ART.md's *Rules*, so painting measurements go under `shape` (`shape.paint_min_m`, `shape.tile_m`).
- **Repeated keys.** One guide may set a key in several json blocks only when their nested keys differ.
