# The asset contract

Every pipeline skill reads and writes assets in this shape. The build script is the source of truth;
every `.blend` is its output.

## Layout

```
assets/<slug>/
  asset.json             the spec — every stage reads it
  approved.json          the approved stages and their snapshot hashes; small, so commit it
  refs/                  reference images, PNG or JPEG (convert webp first: agents can't view it)
  build/<stage>.py       what a stage does; edit this, never the .blend
  <stage>.blend          a stage's output, rebuilt from the previous stage's .blend + its script
  review/<stage>.png     contact sheet of renders
  review/<stage>_shots.png  the asset's `shots`, framed close-ups and gameplay cameras
  review/<texture stage>_maps.png  the baked maps flat: albedo, occlusion, roughness, metallic, normal
  review/bake_maps.png   a shared asset's normal and occlusion, flat
  review/<stage>.json    the check report
  textures/<stage>/      <slug>_albedo.png (sRGB), <slug>_orm.png, <slug>_normal.png (Non-Color)
  textures/bake/         <slug>_normal.png, <slug>_occlusion.png (Non-Color): a shared asset's own detail
  export/<slug>.glb      the deliverable, plus export/textures/
```

Stages run in order `model → rig → texture_base → texture_ref → animate`. `rig` is skipped when `rig` is `"none"`,
and `animate` runs only on a rigged asset whose `animations` name clips. An asset whose `materials` are `"shared"`
runs `model → rig → bake → animate` instead: its `bake` stage bakes the normal and occlusion maps the engine lays
over the shared zone materials, on the asset's own UVs. Export skips an unbuilt `bake` when no stage follows it.
Each build opens the nearest upstream stage's `.blend`, runs `build/<stage>.py`, and saves `<stage>.blend`.
Rebuilding a stage makes every later stage stale, and so does an unbuilt stage before it. `status` shows this;
rebuild the stale stages in order.
When a `pipeline/lib` or `_kit` module the stage's build script imports (directly or through other modules),
the spec (`asset.json`, its art guides' rules, the limits in force) or a data file the build read changes after a
stage was built, `status` says so.
Re-running `check` on the same build keeps a stage's verification. Run `verify` on that stage. IDENTICAL re-checks the stage under the current spec
and, if it passes, clears the flag. CHANGED means the stage must be rebuilt and reviewed again. `verify` compares
the mesh with every attribute it carries (vertex colours, custom layers), the rest skeleton, every action's keys,
and a texture or bake stage's maps.

A data file is any file under `assets/` that the build script opens from Python, other than code, `.blend` files,
files the build writes, the asset's own spec and outputs, and its own chain's guides: a kit's placement table,
another chain's guide. A guide counts by its json rules, so prose changes nothing; any other file by its bytes; a
deleted file as changed. Files Blender opens itself, such as images, are not seen.

## Approval

`pipeline/asset approve <slug>` records the last built stage (or `--stage <stage>`) and every stage upstream of it
in `approved.json`: each stage's snapshot hash, its spec fingerprint and the time. It refuses a stage that is not
built or whose status is not a plain `pass`. Once a stage is approved:

- `build` saves only a rebuild that hashes as approved and, for a stage with maps, bakes maps that match the
  saved ones as `verify` reads them. Any other rebuild prints what changed, leaves the saved stage and its maps
  as they were, and exits 1. A clone without `.blend` files rebuilds its approved stages to what was approved.
- `verify` reads CHANGED when the rebuild strays from the approval.
- `status` adds `approved`, or `CHANGED since approval` when the stage's latest check found another snapshot.

To accept a change, revoke the approval, rebuild, review, and approve again. `--revoke --stage <stage>` drops that
stage and every later one; `--revoke` alone drops them all. A pipeline update that changes what the snapshot
covers changes every hash: `verify` each approved stage, then approve it again.

## Art guides

An asset's `art` field names its chain of art guides in `assets/_art/`: its world's look, its zone's mood, and
its set's construction and palette. Their rules feed the spec (`texture_mode`, the limits) and the build
scripts (palette swatches, and the arguments of `painted_light`, `brush` and `make_high`). The format and merge
rules are in [ART.md](ART.md), and `pipeline/asset art <slug>` prints an asset's chain.

## Sets and `_kit`

Pieces that belong together (a platform set, a wall kit, a family of props) share a set guide, and share code
in `assets/_kit/`.
What the pieces share lives there: always the zone recipes, and a geometry generator when they share a shape
(platforms, wall segments) rather than only materials (street props). Each piece's build script calls the kit with
its own parameters. A recipe takes what varies by piece (its height, a seed, a mask's name) as arguments and reads
nothing from another piece's scripts. Kit modules are importable from every build script. Seed any randomness from the piece's own
parameters, so each piece rebuilds to the same result. Approve each finished piece (*Approval*), and before
accepting any change to kit code, run `verify` on every approved piece that uses it: a build that would change one
stops instead of saving.

## asset.json

| field | meaning | default |
|---|---|---|
| `brief` | what the asset is, in the user's words plus any decisions | `""` |
| `refs` | paths under `refs/`, each with what it shows | `[]` |
| `art` | the art guide chain: `"<world>"`, `"<world>/<zone>"` or `"<world>/<zone>/<set>"` (ART.md) | none: no guides |
| `budget_class` | a class in the guides' `budgets`; it supplies `tri_budget`, `head_tri_budget`, `texture_size` and its `limits` | none |
| `rig` | `"none"`, `"humanoid"`, or `"custom: <skeleton in words>"` | `"none"` |
| `texture_mode` | `"stylized"` (lighting painted into albedo) or `"pbr"` (engine lights it) | the world guide's, else chosen from the refs |
| `materials` | `"baked"` (export bakes the zones into one textured material) or `"shared"` (the engine paints each zone with a shared material of its own; the asset bakes only its normal and occlusion, in its `bake` stage) | the world guide's, else `"baked"` |
| `tri_budget` | triangle ceiling for the low mesh, less its head when `head_tri_budget` is set | the budget class's, else `3000` |
| `head_tri_budget` | triangle ceiling for the faces `modeling.head` marks, apart from `tri_budget` | the budget class's, else `tri_budget` on a humanoid, else none |
| `texture_size` | square map size in px, a power of two | the budget class's, else `1024` |
| `height_m` | real-world height in metres (Z extent) | none |
| `shots` | extra review cameras: `{"name", "target": [x,y,z], "from": [dx,dy,dz], "distance": m, "lens": mm}` | `[]` |
| `limits` | overrides for check thresholds, each set deliberately and named in `brief` | `{}` |
| `animations` | the clips the `animate` stage keys (*Animations*) | none |

Budget guide, when the world guide has no `budgets`: small prop 300–1.5k tris at 512–1k, hero prop 1.5k–5k at
1k–2k, character 5k–20k at 2k with a head of about as many again. The head's share is the style's: a world guide
sets it on its character class.

`limits` keys: `max_tri_ratio` 0.15, `allow_open` false, `uv_overlap_ok` false, `min_uv_coverage` 0.35,
`texel_density_tolerance` 2.0, `texel_density_px_per_m` none (a `[min, max]` range), `min_corner_deg` 0.5 (a face
corner under it is a sliver, and one within it of 180° a vertex on a straight side), `min_zone_contrast` 20
(luma between neighbouring zones: across a shared edge, where shells intersect, or where one rests on
another), `albedo_luma` none (a `[min, max]` range for each
zone's mean albedo luma), `max_saturation` none (for each zone's mean albedo), `max_influences` 4,
`max_bones` 80. The art guides set defaults over these, the budget class's `limits` replace them, and
`asset.json` overrides all three. `albedo_luma` and `max_saturation` skip accent swatches. All three zone
limits FAIL at `texture_ref` and WARN at `texture_base`.

## Animations

```json
"animations": {
  "fps": 30, "max_slide": 0.01, "max_sink": 0.02,
  "props": {"seat": {"size": [0.5, 0.45, 0.35], "at": [0, 0.3, 0]}},
  "clips": [
    {"name": "sit_down", "frames": 40, "to": "sit_idle", "planted": ["foot.L", "foot.R"], "brief": "..."},
    {"name": "sit_idle", "frames": 120, "loop": true, "planted": ["foot.L", "foot.R"], "brief": "..."}
  ]
}
```

- **Clips** run from frame 1 to `frames` at `fps` (default 30). The export carries every clip, by name, and no
  other action.
- **Hand-offs.** `loop` ends a clip on its first pose. `from: X` starts it on X's last pose and `to: X` ends it on
  X's first pose, so the engine can cut between them without a pop.
- **Planted** bones hold still in world space for the whole clip, within `max_slide` metres (default 0.01).
  `animation.clip` re-solves each planted foot's leg on every frame.
- **Props** are stand-in boxes, `at` their bottom centre, drawn in the review so contact can be judged: a seat,
  a table edge, a door handle. They are not exported. The mesh may sink into a prop by `max_sink` metres
  (default 0.02), the give of a body resting on it.
- The check also fails a clip that scales a bone, moves a connected bone, or takes the mesh below the ground,
  and warns of a pop: a channel whose speed jumps by more than 20° or 2 cm per frame between two frames.
  Only the `animate` stage reads `animations`, so editing it leaves the other stages' specs unchanged.

## Scene conventions

- Metres, Z up. The asset's front faces −Y, which is Blender's front view.
- Origin at the bottom centre of the bounds. Object transforms are identity.
- The mesh object is named `<slug>`. The optional bake source is `<slug>_high`, and the armature is `<slug>_rig`. No other objects.
- Every face belongs to a zone: a material named `zone_<name>` (`zone_wood`, `zone_iron`, `zone_skin`). The texture stages paint zones, and export replaces them with one baked material.
  A shared asset exports its zones as they are, each a flat preview of its swatch, grey without one, carrying
  the bake stage's normal and occlusion textures once it is built and never a colour texture.
- `zone_<name>.001` is Blender's duplicate of `zone_<name>`, made when a second file brings its own copy. It
  fails the check: give its faces the original.

## Commands

```
pipeline/asset new <slug>             create the folder and a default asset.json
pipeline/asset build <slug> <stage>   build, then check, then render the review sheet (exit 0 = check passed)
pipeline/asset check <slug> <stage>   re-run the check only
pipeline/asset review <slug> <stage>  re-render the sheet only
pipeline/asset verify <slug> <stage>  rebuild into scratch space, diff against the saved stage, re-check it
                                      (exit 0 = IDENTICAL and the check passes)
pipeline/asset status <slug>          pass / FAIL / stale / not built, per stage, and approved or not
pipeline/asset approve <slug>... [--stage <stage>] [--revoke]
                                      approve a stage and those upstream of it, or revoke (*Approval*)
pipeline/asset compare <stage> <slug>...  zone luma of each piece against the first (exit 0 = consistent)
pipeline/asset art [<slug> | <chain>]  every chain, or one asset's or chain's guides, palette and rules (ART.md)
pipeline/asset export <slug>          glTF (.glb) from the latest texture stage, with the animate stage's clips
                                      when there is one, re-imported and verified; a shared asset's from its
                                      last stage, with its zone materials and the bake's maps
```

`$BLENDER` overrides the Blender binary (default `~/opt/blender/blender`, 4.5 LTS). `$ASSETS_DIR` overrides `assets/`.

## Build scripts

Start from `pipeline/templates/<stage>.py`. The script runs inside Blender with `asset` (an `Asset`) predefined and
`pipeline/lib` and `assets/_kit` importable. `asset.art` holds the merged art rules, `asset.swatch(name)` one
palette swatch, and `asset.zone_table(local)` every zone's colour, roughness and metallic. The helper modules document themselves; read the docstrings of the
ones a stage uses:

- `modeling`: `lathe`, `mesh_object`, `quadify`, `footprint_outline`, `zone`, `head`, `keep`, `finalize`,
  `reduce`, `sharpen`, `unwrap`, `make_high`
- `rigging`: `section`, `build`, `bind`, `clean`, `rigid`, `chain`, `shell`, `mirror`, `test_action`
- `animation`: `clip`, `plant`, `reach`, `sample`, `spring`, `apply`, `current`, `pose_at`, `props`, `settings`
- `nodes`: `tree(mat)` for shader-node shorthand, plus `srgb` for picking colours by eye. Its stylized patterns
  are `slabs`, `courses`, `cracks`, `by_facing`, `brush` and `painted_light`, built from `band`, `warp` and
  `cell_random`
- `bake`: `bake` turns zone materials into a texture stage's maps; `detail` bakes a shared asset's normal and
  occlusion
- `photo`: `prepare` and `derive` turn reference photos into tileable sources

### High first

A model may start from the detail. Build the parts as detailed as the bake should show, mark with `modeling.keep`
the faces gameplay measures (a walkable top, a jump lip), `finalize` them, and `reduce` the result to the
budget: the detailed mesh stays as `<slug>_high`, and `<slug>` is its reduction. Kept faces come through
bit-exact, and with `borders` so do zone borders, so build both no denser than the low can afford. Then
`unwrap` the low, and bake: a shared asset's `bake` stage (`bake.detail`), a baked asset's texture stages. The
reduced mesh may be triangle-dominant; allow it with `limits.max_tri_ratio` on the budget classes built this way.
Bevels and cracks go on after `reduce`, on a copy of the low that replaces `<slug>_high`: a bevelled corner has no
vertex on its planes, so a low reduced from a bevelled mesh folds.

## Review sheets

Tiles read left to right, top to bottom.

- `model`: front, right, back, left, top, three-quarter, three-quarter back, high mesh. Zones are coloured and the wireframe is overlaid. `model_uv.png`: grey islands, red overlap.
- `rig`: three-quarter view across the frames of the `rig_test` action. Each attachment point is an axis tripod
  drawn over the mesh: X red, Y (along the bone) green, Z blue.
- `animate`: one row per clip, four frames from first to last, seen from the front right with the props in grey.
- `texture_*`: lit by an HDRI, in the order front, right, back, left, top, three-quarter, three-quarter back, then unlit albedo.
- `bake`: lit by an HDRI in the zones' flat colours under the normal and occlusion maps, in the same seven views,
  then three-quarter without the maps: what the bake adds.
- The top tile looks straight down with +Y (the back) at the top of the image.
- `<stage>_shots.png`: one tile per shot. Texture stages give two per shot, lit then unlit; the bake stage's are
  lit. Sheet tiles run at about 150 px/m on a 3 m asset, so add a shot for anything smaller than a hand: joints,
  lips, creases, the gameplay camera.

Texture checks report `zone_luma` and `zone_saturation`, each zone's mean albedo brightness and saturation.
`compare` reads `zone_luma` across a set.
