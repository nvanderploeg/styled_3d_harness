# The asset contract

Every pipeline skill reads and writes assets in this shape. The build script is the source of truth;
every `.blend` is its output.

## Layout

```
assets/<slug>/
  asset.json             the spec — every stage reads it
  refs/                  reference images
  build/<stage>.py       what a stage does; edit this, never the .blend
  <stage>.blend          a stage's output, rebuilt from the previous stage's .blend + its script
  review/<stage>.png     contact sheet of renders
  review/<stage>_shots.png  the asset's `shots`, framed close-ups and gameplay cameras
  review/<stage>.json    the check report
  textures/<stage>/      <slug>_albedo.png (sRGB), <slug>_orm.png, <slug>_normal.png (Non-Color)
  export/<slug>.glb      the deliverable, plus export/textures/
```

Stages run in order `model → rig → texture_base → texture_ref`. `rig` is skipped when `rig` is `"none"`.
Each build opens the nearest upstream stage's `.blend`, runs `build/<stage>.py`, and saves `<stage>.blend`.
Rebuilding a stage makes every later stage stale. `status` shows this; rebuild the stale stages in order.
When `_kit` code or the spec (`asset.json`, its art guides' rules, the limits in force) changes after a stage
was built, `status` says so. Run `verify` on that stage. IDENTICAL re-checks the stage under the current spec
and, if it passes, clears the flag. CHANGED means the stage must be rebuilt and reviewed again.

## Art guides

An asset's `art` field names its chain of art guides in `assets/_art/`: its world's look, its zone's mood, and
its set's construction and palette. Their rules feed the spec (`texture_mode`, the limits) and the build
scripts (palette swatches, and the arguments of `painted_light`, `brush` and `make_high`). The format and merge
rules are in [ART.md](ART.md), and `pipeline/asset art <slug>` prints an asset's chain.

## Sets and `_kit`

Pieces that belong together (a platform set, a wall kit, a family of props) share a set guide, and share code
in `assets/_kit/`.
The geometry generator and the zone recipes live there, and each piece's build script is one call with its own
parameters. Kit modules are importable from every build script. Seed any randomness from the piece's own
parameters, so each piece rebuilds to the same result. Before accepting any change to kit code, run `verify` on
every approved piece that uses it.

## asset.json

| field | meaning | default |
|---|---|---|
| `brief` | what the asset is, in the user's words plus any decisions | `""` |
| `refs` | paths under `refs/`, each with what it shows | `[]` |
| `art` | the art guide chain: `"<world>"`, `"<world>/<zone>"` or `"<world>/<zone>/<set>"` (ART.md) | none: no guides |
| `rig` | `"none"`, `"humanoid"`, or `"custom: <skeleton in words>"` | `"none"` |
| `texture_mode` | `"stylized"` (lighting painted into albedo) or `"pbr"` (engine lights it) | the world guide's, else chosen from the refs |
| `tri_budget` | triangle ceiling for the low mesh | `3000` |
| `texture_size` | square map size in px, a power of two | `1024` |
| `height_m` | real-world height in metres (Z extent) | none |
| `shots` | extra review cameras: `{"name", "target": [x,y,z], "from": [dx,dy,dz], "distance": m, "lens": mm}` | `[]` |
| `limits` | overrides for check thresholds, each set deliberately and named in `brief` | `{}` |

Budget guide, when the world guide has no `budgets`: small prop 300–1.5k tris at 512–1k, hero prop 1.5k–5k at
1k–2k, character 5k–20k at 2k.

`limits` keys: `max_tri_ratio` 0.15, `allow_open` false, `uv_overlap_ok` false, `min_uv_coverage` 0.35,
`texel_density_tolerance` 2.0, `texel_density_px_per_m` none (a `[min, max]` range), `min_zone_contrast` 20
(luma between neighbouring zones in the base texture), `albedo_luma` none (a `[min, max]` range for each
zone's mean albedo luma), `max_saturation` none (for each zone's mean albedo), `max_influences` 4,
`max_bones` 80. The art guides set defaults over these, and `asset.json` overrides both. `albedo_luma` and
`max_saturation` skip accent swatches; they FAIL at `texture_ref` and WARN at `texture_base`.

## Scene conventions

- Metres, Z up. The asset's front faces −Y, which is Blender's front view.
- Origin at the bottom centre of the bounds. Object transforms are identity.
- The mesh object is named `<slug>`. The optional bake source is `<slug>_high`, and the armature is `<slug>_rig`. No other objects.
- Every face belongs to a zone: a material named `zone_<name>` (`zone_wood`, `zone_iron`, `zone_skin`). The texture stages paint zones, and export replaces them with one baked material.

## Commands

```
pipeline/asset new <slug>             create the folder and a default asset.json
pipeline/asset build <slug> <stage>   build, then check, then render the review sheet (exit 0 = check passed)
pipeline/asset check <slug> <stage>   re-run the check only
pipeline/asset review <slug> <stage>  re-render the sheet only
pipeline/asset verify <slug> <stage>  rebuild into scratch space, diff against the saved stage, re-check it
                                      (exit 0 = IDENTICAL and the check passes)
pipeline/asset status <slug>          pass / FAIL / stale / not built, per stage
pipeline/asset compare <stage> <slug>...  zone luma of each piece against the first (exit 0 = consistent)
pipeline/asset art [<slug> | <chain>]  every chain, or one asset's or chain's guides, palette and rules (ART.md)
pipeline/asset export <slug>          glTF (.glb) from the latest texture stage, re-imported and verified
```

`$BLENDER` overrides the Blender binary (default `~/opt/blender/blender`, 4.5 LTS). `$ASSETS_DIR` overrides `assets/`.

## Build scripts

Start from `pipeline/templates/<stage>.py`. The script runs inside Blender with `asset` (an `Asset`) predefined and
`pipeline/lib` and `assets/_kit` importable. `asset.art` holds the merged art rules, `asset.swatch(name)` one
palette swatch, and `asset.zone_table(local)` every zone's colour, roughness and metallic. The helper modules document themselves; read the docstrings of the
ones a stage uses:

- `modeling`: `lathe`, `mesh_object`, `quadify`, `footprint_outline`, `zone`, `finalize`, `sharpen`, `unwrap`,
  `make_high`
- `rigging`: `section`, `build`, `bind`, `clean`, `rigid`, `test_action`
- `nodes`: `tree(mat)` for shader-node shorthand, plus `srgb` for picking colours by eye. Its stylized patterns
  are `slabs`, `courses`, `cracks`, `by_facing`, `brush` and `painted_light`, built from `band`, `warp` and
  `cell_random`
- `bake`: `bake` turns zone materials into the stage's maps
- `photo`: `prepare` and `derive` turn reference photos into tileable sources

## Review sheets

Tiles read left to right, top to bottom.

- `model`: front, right, back, left, top, three-quarter, three-quarter back, high mesh. Zones are coloured and the wireframe is overlaid. `model_uv.png`: grey islands, red overlap.
- `rig`: three-quarter view across the frames of the `rig_test` action.
- `texture_*`: lit by an HDRI, in the order front, right, back, left, top, three-quarter, three-quarter back, then unlit albedo.
- The top tile looks straight down with +Y (the back) at the top of the image.
- `<stage>_shots.png`: one tile per shot. Texture stages give two per shot, lit then unlit. Sheet tiles run
  at about 150 px/m on a 3 m asset, so add a shot for anything smaller than a hand: joints, lips, creases, the
  gameplay camera.

Texture checks report `zone_luma` and `zone_saturation`, each zone's mean albedo brightness and saturation.
`compare` reads `zone_luma` across a set.
