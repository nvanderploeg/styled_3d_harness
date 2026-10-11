# The gameplay contract

The block-out is the collision the game plays on. The art dresses it and never changes what a runner can do. This file turns a package's contract into guide rules, code and checks.

## In the world guide

The contract holds for the whole game: the controller's walkable angle, and play matched to the centimetre. It is the world guide's top pillar, *Faithful to the block-out*, ranked above readability, and its numbers go in `shape` and `scale`:

| key | holds | starting value |
|---|---|---|
| `shape.top_tolerance_m` | a placed top's height against the block-out's | 0.01 |
| `shape.edge_variance_m` | a top's outline against its block-out edge, away from lips. Along a lip the outline is exact, within 1 cm. | 0.15 |
| `shape.walkable_deg` | the steepest face the character stands on | the package's |
| `shape.side_deg` | the shallowest any upward face below a top may be, at every scale | walkable + 3 |
| `shape.cap_scale`, `shape.body_scale_z` | the tweak ranges every module must survive | [0.85, 1.15], [0.8, 2.0] |
| `shape.side_out_m`, `shape.side_in_m` | a body's side against the block-out's | 0.0, 1.0 |
| `shape.foothold_m` | the widest standable face an addition may show within reach | 1.0 |
| `shape.gap_clear_m`, `shape.approach_m` | how far a gap corridor is widened, and how far a flight envelope runs past the lips | 2.0, 15.0 |
| `scale.reach_m`, `scale.reach_up_m` | how near a route counts as within reach: plan distance, and height above its tops | the longest jump; 3.0 |
| `scale.submerged_m` | how far a stack goes under the water | 3.0 |

Ask the collision question once (SKILL.md, step 2). When the block-out stays the collision, modules carry no colliders, a designer's tweak to a module is made to its block-out piece too, and the contract is measured against the block-out as placed.

## Angles hold at the scale extremes

A designer will scale caps in plan and bodies in height. Lowering z by its lowest scale and stretching plan by its highest shrinks a face's slope tangent by `z_min / plan_max`. Build every upward face below a top at `atan(tan(side_deg) × plan_max / z_min)` or steeper. With a 60° side, plan up to 1.15 and z down to 0.8, that is 68.1°, so chamfers sit at 69–72°. A flare scaled 1.15 in plan alone needs 63.5° to stay at 60°.

Evaluate the contract over the scale grid (each extreme and 1, on each axis), never only as built.

## In code, not on sheets

A sheet can't show a 2° slope error or a 5 cm drift. Every generator carries a `contract()` that runs in every build and raises when:

- a top isn't flat and at its height
- an outline is off a lip, or off another edge by more than the edge variance
- an upward face below a top is shallower than `side_deg` anywhere on the scale grid
- a side leaves `side_out_m` / `side_in_m` of the block-out

The assembler places every cap and stack from the placement table and measures the result against the block-out: the worst lip, the worst other edge, and heights.

The contract runs on the low mesh, after `modeling.reduce`: reduction keeps tops and lips exact, and the contract proves it.

When floating point breaks a rule at its boundary (63.4999° against 63.5°), step the geometry back 0.1 mm. Never loosen the rule.

## Broken edges

A lip edge is a straight line exact to the block-out. Every other top edge may break, inside the contract:

- **Into the top.** A chip or a wandering outline cuts into the top by no more than `edge_variance_m`. That variance is the requester's call: it is how far the art may stray from the collision away from the lips.
- **Down the band.** Deeper breaks go down the side, where the block-out allows sculpting.
- **No ledges.** A break's floor faces down or is as steep as a side.
- **Lips by class.** A cap keeps straight every edge that is a lip on any member of its class.

## Additions

An addition is anything the block-out doesn't have: a crest above a decor top, an infill, a shelf, every piece of dressing, a backdrop. It leaves every run as it is:

- **No collision.**
- **Outside every flight envelope.** A jump's gap corridor is the hull of its two lip edges, widened by `gap_clear_m`, at any height and down through the water. Its flight envelope is that corridor carried `approach_m` back over the take-off top and as far on over the landing. `tools/routes.py` builds both.
- **No foothold within reach.** Within `reach_m` in plan and `reach_up_m` above a route's top, no exposed upward face shallower than `walkable_deg` holds a disk `foothold_m` wide. Measure the bare geometry, not face roles: a joint the next row covers is not a ledge.
- **Never closer or lower.** The block-out's own decor never moves closer to a route, and never lower.
- **Closed stays closed.** A volume the block-out closes, such as a cave, stays closed. Cast rays up and out from inside it, and require every ray to hit art.

Measure each rule's clear area before choosing densities or sites. On one level the envelopes covered five of eleven decor crests, and the dressing ended up on decor feet, the shore band and the backdrop.

## Placing additions

The contract is the placement tool's accept test.

- **Accept test.** A scattered piece that fails any rule above is dropped, never nudged until it passes.
- **Seat on the art.** Seat pieces on the art, not the block-out, since decor art stands proud of its block-out.
- **Pose data.** Each dressing lane writes its pieces' allowed poses and tilt margins as data, and the placement tool reads them.
- **Deterministic.** Placement is deterministic: the same inputs give the same file.
- **Locked rows.** Rows a designer edits by hand are `locked`, and a rerun keeps them.

## Art beyond collision

Where collision is thin, such as a frame of posts and a lintel, art that hugs it reads as built. Give the art room only where collision allows. Outer faces and crowns may grow as rock with no collision, while the opening the runner passes through and every lip stay exact. Before a set rule grants growth, check it against the additions rule. Growth inside a flight envelope is a contract change: a one-way door for the requester.

## Waivers

When the requester accepts art that breaks a rule, the waiver is data the contract reads: `"waived": [{"slug": ..., "rule": ...}]` beside the placement. The contract still measures a waived rule and reports it. It never fails it and never skips it silently. It refuses a waiver that names a rule the piece doesn't break, or a slug that isn't placed.

A module that would need a waiver is built and sheeted but left unplaced (`"proposes": <slug>` in its kit notes) until the requester decides. Ask with the sheet, its options as small diagrams, and your recommendation.

## Defaults that depend on a view

Write a view-dependent default, such as where a backdrop volcano reads or what the finish looks at, as an angle from a named eye: a bearing and elevation from a top, at runner height. Raycast the assembled scene from that eye before choosing. Decor and vaults close more lines than the plan shows. Once a transform found by search is approved, pin it in the kit, so a rerun can't search it away.
