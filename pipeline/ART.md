# Art guides

Art direction in three layers, so assets made by different agents, months apart, still belong together. Every
pipeline skill reads the guides of the asset it works on.

| layer | file | owns | for example |
|---|---|---|---|
| world | `<world>/world_art.md` | the game's look: shape language, painting technique, scale, budgets | chunky, hand-painted |
| zone | `<world>/<zone>/zone_art.md` | a region's mood: palette, value key, light, wear | Duskwood: dark, haunted |
| set | `<world>/<zone>/<set>/set_art.md` | a family of assets: construction, materials, kit numbers, pieces | Darkshire's timber houses |

Each layer refines the one above: a zone sets its mood with the world's technique, and a set picks its materials
from the zone's palette. A *zone* here is a region of the game; the `zone_<name>` materials of a mesh are called
*mesh zones* in this file.

## Layout

```
assets/_art/
  <world>/world_art.md
  <world>/<zone>/zone_art.md
  <world>/<zone>/<set>/set_art.md
  .../refs/                      the images a guide names, beside it
```

An asset joins a chain with `"art": "<world>"`, `"<world>/<zone>"` or `"<world>/<zone>/<set>"` in `asset.json`,
and follows only the guides on that chain. Each world is one game's look, so several games can share one
`assets/` folder.

```
pipeline/asset art                            every chain in assets/_art/
pipeline/asset art <slug>                     the asset's guides in reading order, its palette, every rule in force
pipeline/asset art <chain> [--sheet <png>]    the same for a chain; the sheet draws each swatch, dark to light,
                                              as shadow, base and lit under the chain's light, then as grey
```

Worked examples in the style of World of Warcraft live in `pipeline/templates/art/`: `world_art.md.example`,
`zone_art.md.example` (Duskwood) and `set_art.md.example` (Darkshire's human village). Each names the path it
belongs at under `assets/_art/azeroth/`.

## Format

A guide is Markdown. The prose carries the rules a reviewer judges on a sheet, and each measurable rule sits in a
fenced `json` block under the section it belongs to. The pipeline reads only the json blocks and joins all of
a guide's blocks into one object. A key set in two blocks of one guide is an error.

Sections, in order:

- **world**: Style (one line), Pillars (ranked), Shape, Painting, Materials, Scale and budgets, References
- **zone**: Mood (one line), Story, Palette and value, Light, Shape, Wear, Motifs, References
- **set**: Set (one line), Construction, Materials, Shape, Damage, Pieces, References

## Rules

| key | usual layer | holds | read by |
|---|---|---|---|
| `texture_mode` | world | `"stylized"` or `"pbr"`, for assets whose `asset.json` leaves it unset | the texture stages |
| `limits` | any | defaults for the `asset.json` limits listed in ASSET.md | checks |
| `palette` | zone, set | swatches by name: `{"color": "#rrggbb", "roughness", "metallic", "accent", "touches"}` | `asset.zone_table`, `asset.swatch`, checks |
| `painted_light`, `brush`, `make_high` | world, zone | keyword arguments for the helper of that name | build scripts |
| `budgets` | world | per asset class: `tri_budget`, `texture_size`, and any `limits` | an asset's `budget_class` |
| `scale` | world | reference sizes in metres: a character, a door, a storey | model-asset |
| `shape` | any | the measurements behind the shape and wear rules: lean, sag, taper | model-asset |
| `kit` | set | the measurements the set's `_kit` code builds from: grid, module sizes, sections | kit code |

- **Swatches.** A mesh zone `zone_<name>` takes the swatch `<name>`. `texture_base` bakes it as it is, and
  `texture_ref` builds that zone's ramp around it. A swatch that no mesh zone names (fog, sky) is a colour
  for recipes to paint with, through `asset.swatch(name)`. `roughness` defaults to 0.8 and `metallic` to 0.
- **Accents.** A swatch with `"accent": true` (lamplight, magic, heraldry) may leave the value and saturation
  limits. Keep accents few; they are where the eye goes first.
- **Touching.** `touches` names the swatches this one shares an edge with on one mesh: a frame and its plaster, a
  door and its hinges. A colour painted over another inside one zone, like moss on a roof, is not a touch. Declare
  a pair on either swatch, or on the lower guide's when the two come from different guides. `pipeline/asset art`
  rejects a pair closer than `limits.min_zone_contrast`.
- **Value key.** `limits.albedo_luma` `[min, max]` bounds each mesh zone's mean albedo luma (sRGB, 0–255), and
  `limits.max_saturation` bounds its HSV saturation. The texture checks FAIL on both at `texture_ref` and WARN
  at `texture_base`.

## Merging

The chain merges world, then zone, then set, then the asset's own `asset.json`:

- Objects merge key by key. Any other value in a later guide replaces the earlier one.
- A later guide's `limits` only tighten: a `min_*` rises, a `max_*` falls, and a `[lo, hi]` range narrows.
  `pipeline/asset art` rejects a guide that loosens one.
- Every swatch that is not an accent sits inside the merged value and saturation limits, and every touching
  pair clears the merged `min_zone_contrast`.
- The `limits` in `asset.json` override the guides for that one asset, as an exception named in its `brief`.
- A changed json rule marks the chain's built stages `spec changed`, and `verify` rebuilds and re-checks them.
  Prose marks nothing, so review the chain's assets against changed prose at their next rebuild.

## Writing a guide

The `art-guide` skill writes and revises guides, and holds the rules for writing one.
