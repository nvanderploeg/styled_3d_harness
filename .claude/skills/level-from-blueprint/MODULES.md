# Modules

The gameplay set as modules a designer tweaks without new art, and the kits that build them. Decor, backdrop and dressing sets follow the same pattern with forms of their own.

## Anatomy

- **Cap.** The gameplay surface. Its zones are the top and the band under its edge. The band runs `top_band_m` deep, vertical or flared as the block-out is. Its lip edges are straight and exact. Every other edge chips and wanders within `edge_variance_m`, with deeper breaks down the band. The cap's origin is the centre of the band's foot, and its top centre sits a band height above it.
- **Body segment.** A slice of rock below the cap, with the same outline top and bottom, starting and ending on a joint, so segments stack in any order. Its origin is its footprint's centre, not its bounds' centre: an asymmetric colonnade shifts its bounds by a quarter metre, and the stack misaligns.
- **Stack.** Segments from the cap down to `submerged_m` under the water. Every segment is scaled alike in z within `body_scale_z`, with the segment count that keeps the scale nearest 1. Scaling only the lowest segment pushes drums out of range on tall pieces.
- **Zones and two maps.** With `materials: "shared"`, a module carries its mesh zones, which the engine paints from the shared library ([MATERIALS.md](MATERIALS.md)), plus its own normal and occlusion maps from the `bake` stage.
- **High first.** Each module is built as a high mesh with its chips, joint relief and bevels, then reduced to its budget with `modeling.reduce`, its tops and lips kept exact. The `bake` stage carries the high's detail onto the low, with one `ao_distance` for the whole set so occlusion matches across stacked modules. The contract runs on the low mesh.

## Classes from the shape fit

- **Cap classes.** A cap class is one shape at a base size, straight or flared, and it serves every top within `cap_scale` of its size on each axis. Cover the tops greedily: most members first, sizes on a 0.25 m grid, exact block-out sizes first. On one level, 15 classes covered 38 tops. Seven classes served a single top, mostly for odd flares.
- **Flares.** A flared class can't be taller than any member's flare. A flare narrower than `chamfer_m` becomes a straight band, since it can't be cut as one facet. A band shorter than `facet_min_m` extends to it.
- **Slopes.** Each (ramp, rise) pair is its own class. A slope class is scaled across its width only, since a scale along it changes the slope.
- **Welds.** A top that fits no shape gets a cap of its own. Its rim follows the whole outline, it is cut in quads across the branch root, and it sits on the bodies of the classes its parts fit.
- **Lips by class.** One cap class serves tops whose lips sit on different edges. A cap keeps straight every edge that is a lip on any member of its class, and breaks the rest. When that leaves a member with no broken edge in view of its runs, split the class by lip layout.
- **Thin frames.** Posts and a lintel at a finish are one module that matches the frame, dressed as a piece of the zone (CONTRACT.md, *Art beyond collision*).

## Segment height per form

Derive a form's segment height from its joint-spacing rule and the z-scale range together. Then test it against every stack height in the placement table, not only the lead's.

On one level, columns read as single shafts with joints 4–6 m apart as placed. Single-drum segments 5 m tall, with z in [0.8, 1.2], fit every stack of 8 m or more. Segments 8 m tall left stacks between 12 and 16 m with no valid count.

## Placement table

The table is the deliverable beside the meshes. Per block-out piece it holds:

- the cap class, the top centre, the rotation about Z and the plan scale per axis
- its segments from the top down, each with its variant, top height and z scale
- its lips, taken from the extract, each marked take-off or landing from the routes, for cameras and the contract
- a lip-mark decal for each take-off lip. The mark is per placement, since a cap class serves tops with different lips.
- sections for frames and welds

A designer's tweak edits these numbers in the engine, and makes the same change to the block-out piece, which stays the collision. Rows edited by hand are marked `locked`, so a rerun keeps them. Write only built slugs into the table, plus a to-do list: a table that names variants nobody built breaks assembly. Build every variant of a form a class uses, placed or not, so a raised top has a longer stack ready.

## Kit files per set

| file | does |
|---|---|
| `<set>.py` | the generator: module geometry from its parameters, and `contract()` |
| `<set>_place.py` | the placement table from the extract, deterministic |
| `<set>_assemble.py` | places every module from the table, runs the contract on the result, writes a file per corridor |
| `<set>_batch.py` | builds every module the table needs, skips approved ones, fails on any CHANGED `verify`, and reruns in seconds |
| `<set>_preview.py` | one sheet per class: the cap, its bodies and every placed instance with materials, from the gameplay camera |
| `<set>_notes.md` | commands, coverage, decisions and frictions: the handoff to the next agent |

A later set's kit imports the gameplay kit and wraps it. It never edits it.

A preview camera looks across a lip it can see clearly. A camera placed without checking can sit inside a neighbouring piece.

## Generating geometry

- **Noise fields.** Draw variation from noise rather than uniform chance:
  - Perlin noise (fBm) for sizes, heights, joint spacing and how densely chips gather, so they drift across a piece instead of repeating
  - Worley cells for column sections (columnar basalt cracks into near-Voronoi cells), lava plates and crack networks

  Seed every field from the module's parameters, so it rebuilds identically.
- **Big planned planes.** Build from big planned planes, and let noise choose which plane, size or angle, never where a vertex goes. Random fracture planes always left edges under the facet minimum, and jittered vertices bend flat faces.
- **Chips.** A chip at a broken edge is one or two flat fracture planes. It cuts into the top no deeper than `edge_variance_m`, and down the band as far as the set allows. Its floor faces down or stays as steep as a side, so it leaves no ledge.
- **Bites.** A bite on an edge is one flat fracture plane across a face's full width, giving a trapezoid outline. Never a notch that narrows to a point.
- **Small pieces.** A small piece sits in a size window, between the minimum facet at the bottom of its scale range and the foothold width at the top (0.59–0.8 m on one level). Check that the kit's ranges fit that window before generating. At 0.5 m facets, a 1 m shrub is one ring and a top.
- **Fills.** A naive fill of a long outline gives 179.99° corners and 0.002° triangles. Use a constrained fill with a minimum corner rule, and keep the model check's corner limit passing.
- **Budget.** Detail lives on the high mesh, and `modeling.reduce` brings the low to its budget, so the generator never trims detail to fit. Kept tops and lips and every zone border stay exact, so their triangles count in full: keep those outlines lean. Check the reduced low against the contract and the sheets: when reduction flattens a break the silhouette needs, keep it with the top and lips.
- **Panel walls.** A wall of panels with one skin shows sky through its joints from somewhere. Put a hidden core slab inside it.
- **Lightmap UVs.** With every facet its own lightmap island, UV coverage lands near 0.3. Set the limit in the brief.

## The test article

The test article is the lead piece. Its brief holds:

- `tools/piece_views.py` renders of the piece among its neighbours and the water
- a crop of the plan around it
- the reference photos it needs, converted to PNG in `refs/` and marked internal in `asset.json`
- its top outline and height, in both the block-out's frame and the piece's own (the block-out's, less the bottom centre)
- the end the run starts from, each lip and its difficulty, the flare levels, the water level, and the placement offset
- the objects on its top that aren't part of it, such as markers

Its shots are:

- the gameplay camera, from behind the start along the run
- a close-up across a lip
- a view at the waterline

The lead piece's agent writes the generator and its contract. On one level that took about 45 minutes and 450k tokens; the variants are cheap after it. Ask the agent to dry-run the generator over every other member of the family without writing assets. The pieces it refuses are the plan's work list.
