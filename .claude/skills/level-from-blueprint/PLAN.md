# Catalogue and plan

One agent writes these while the test article builds, read-only on everything but `assets/_plan/`. They cover the whole level, so every later lane is a slice of them.

## Files

- `assets/_plan/<level>_catalogue.md`:
  - gameplay modules, decor modules, environment (what the engine provides) and dressing
  - placement rules, and new guides and swatches
  - the build plan, the decisions and the open questions
- `assets/_plan/<level>_catalogue.json`: one record per item, with its slug or family, set, build route (`kit_generated`, `make_asset` or `engine`), count, instances, priority and fit with the direction.
- `assets/_plan/<level>_zones.png`: a top view of tops, lips, decor, gap corridors, envelopes, the reach band and dressing areas, drawn on the routes tool's map.

## What the catalogue holds

- **Counts against the block-out:**
  - gameplay meshes and landing tops, against module meshes and placements
  - decor meshes and instances
  - dressing families, meshes and instances
  - a total

  State the trade plainly. Per-piece art makes fewer unique meshes, and any tweak forces a remodel. Modular art makes more meshes, all from one generator run, and a tweak needs no new mesh.
- **Economies as yes/no items** with their mesh deltas, such as folding short flares or skipping spare variants. Never apply one silently. You decide each and log the call.
- **A provisional design for every unfit piece:**
  - flows as wedge caps
  - welds as unique caps
  - a blade of rock as a natural dyke rather than the reference's built blocks
  - a frame as a piece of the zone
- **Dressing filtered by the direction.** Only natural, zone-plausible items that pass the additions rule go in. Ideas the direction rules out are left out, not listed as conflicts: a lighthouse it says isn't there, or ropes and other built things where everything outside a castle is rock.
- **Dressing rules drawn from the contract**, on the map:
  - gap corridors and envelopes
  - buffers around tops
  - the reach band
  - low decor tops within reach
  - occlusion of lips
  - the value cap near routes
- **Findings of the block-out audit** that change the plan (DISCOVERY.md).
- **Questions in two lists:**
  - the requester's: economies, the forms of unfit pieces, a cap on dressing
  - the designers': what a frame is, a lighting gap, a missing neighbour, how lip colours read, the delivery

  Under the run's rules, both lists become defaults with a logged reason unless a question is a one-way door.

## Defaults that carry from level to level

- An unexplained gameplay frame is built as a piece of the zone, such as a natural arch at a finish.
- Vegetation and other natural dressing go anywhere they leave jumps and gameplay alone.
- Additions are allowed when they can't affect completion: they have no collision, stay outside gap corridors and envelopes, and offer no foothold within reach.
- A missing neighbour, such as the crater a segment leads to, becomes a movable placeholder backdrop on the inferred line. It is replaced when the data arrives.
- The delivery is a zip with each module exported on its own, a placement manifest in both frames and the material library. It adds an engine scene or prefab when that engine is available here, and an editor script that builds the scene when it isn't.

## Build plan

Batches with lanes and checkpoints, with lanes split by file ownership. A shape that worked:

| batch | the lane owns | checkpoint |
|---|---|---|
| guides for every new set | `assets/_art/` | every chain accepted |
| the gameplay classes | the gameplay kit | every class sheet; every top assembled within contract |
| the unfit gameplay pieces: flows, welds, frames | the gameplay kit | gameplay complete |
| the decor kit | a kit that wraps the gameplay kit | the decor contract and sheets |
| the backdrop | its kit, plus any rock material it adds | views from the start and the finish |
| dressing sets, a few families per lane, and the dressing materials | their kits | each family's sheet |
| dressing placement | the placement tool | its contract and an overview |
| delivery | the packager | a pack after every gate |

Calibration from one level of about 40 gameplay pieces:

| | cost |
|---|---|
| one set's lane, including a fix round | 0.4–0.9M tokens and 30–90 minutes |
| the whole level | about 6M tokens |

Five lanes at once hit a session usage limit together. Budget lanes against the limit, and stagger the heaviest.

## Repo hygiene

Measure before choosing. Time each regeneration, and compare two runs byte for byte.

- **Keep out of git** quick, deterministic outputs. Each ignore carries its rebuild command beside it as a comment.
- **Commit as a cache** slow but small outputs: solved placements, pose data, contract reports.
- **Commit** everything agent-written: guides, the catalogue, notes and kits.
- **Keep review sheets out.** They are large, and every batch rebuilds them.

Commit each lane as one batch after its gate, on a branch.
