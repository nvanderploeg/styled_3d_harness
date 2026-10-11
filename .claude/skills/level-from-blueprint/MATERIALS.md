# Shared tiling materials

An engine-lit level paints its modules with one tiling material per mesh zone, projected in world space. Modules then scale, rotate and recombine with no stretch and no rebake. The library is a lane of its own. Its generator lives in the kit and reads its swatches from the guides, so a palette change regenerates it.

## What the library holds

- Per material, a tileable albedo and roughness covering `shape.tile_m`, at about 128 px/m.
- An open-air set, plus one set per lighting variant, such as a cave.
- Procedural, periodic textures only. Reference photos are internal, and a texture made from one ships them.
- A macro map: a low-frequency mask tiling once per `shape.macro_m`, sampled top-down in world space, that moves albedo a few percent so the `tile_m` repeat never shows.
- Wetness is the shader's. It blends rock toward wet by world height, up to the zone's waterline plus `wet_m`. Wet rock is darker and smoother, never lighter.
- Exposure is the shader's too. It blends each zone between its damp and dry swatches from the world normal, the module's occlusion map and the height above the spray. Exposure is rock colour, never a sun direction.
- Each module's own normal and occlusion maps come from its `bake` stage, on its UVs. The shared material holds the surface, the module's maps its shape.
- A shader spec ships with the library for the engine: triplanar sampling, the macro, exposure and wet blends, the module maps, the material sets, and lip-mark decals.

## Noise

Build every map from layered noise, each layer sized in metres:

| layer | noise | scale | gives |
|---|---|---|---|
| patches | Perlin fBm, 3–4 octaves | 1–4 m | broad lighter and darker areas |
| cells | Worley (F2 − F1 for edges) | the set's cell size | column heads, lava plates, the joints between them |
| cracks | Worley edges, thresholded thin | 0.5–2 m | crack networks on crust |
| pits | Worley F1, thresholded | 0.25–0.5 m | porous cooled lava |
| warp | Perlin added to the lookup position | about a cell | boundaries that never run straight |

- Stop every octave at `paint_min_m`. Noise below it reads as grain.
- Make noise periodic over the tile (sample it on a torus, or wrap its lattice), so the tile seams vanish.
- Keep the contrast of each layer inside the value limits, and keep tops the cleanest: their cells and patches sit at the lowest contrast in the library.

## Checks

| check | what it holds |
|---|---|
| albedo mean | within 3 luma of its swatch |
| pixel values | every pixel inside the value limits |
| seams | the step across the wrap is never the largest step |
| blur test | no mark smaller than `paint_min_m` |
| 3×3 sheet | the tile repeated as a contact sheet, read for repetition |

## Tiling rules

- **Repetition shows on the 3×3 sheet.** A singular mark on a tile, such as one crack or one big stain, becomes a lattice there. Use many small, varied patches instead of a few big ones, and let the macro map vary them further. Test on a strip as long as the longest module's perimeter.
- **Alternating zones read as a quilt.** Zones that switch facet by facet on one large form read that way. Give the form big areas of one zone instead, such as crust tongues over rock.

## Previews in Blender

- **Build the world-space triplanar by hand.** Blender's box projection mixes object-space normals with world positions, so it stretches on rotated objects.
- **Build each shared node group once per file.** Rebuilding a group's interface unlinks every material built before it, and everything then renders grey. Test it by building two material sets in one scene and checking that every input is still linked.
- **Strip the `.NNN` suffix when mapping materials by name.** Modules appended from several files duplicate material names (`zone_top.001`).
