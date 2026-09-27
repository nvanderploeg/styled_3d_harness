# PBR: surface, not lighting

The albedo is the surface colour under flat, even light. Everything view-dependent goes into the other maps, and the engine lights the result.

- **Photo sources.** For each ref photo of a material, `photo.prepare(src, dst)` crops it, evens out its lighting and makes it tile. Then `photo.derive` gives a height and a roughness image from it. Put these into the zone recipe with `z.image(path, projection="BOX", vector=<object coords scaled to the pattern size>)`, using `colorspace="Non-Color"` for height and roughness.
- **Delight until flat.** If the prepared image still shows a light direction (one side brighter, cast shadows), raise `delight`. Then check the albedo range warning after the build: a PBR albedo outside 30–243 sRGB has lighting baked in.
- **Procedural where no photo fits.** Build the pattern from `noise`, `wave` and `voronoi`, sized in metres from the card.
- **Normal detail** comes from the recipe's height through `z.bump(height, strength, distance)` into `normal=`. Keep `strength` at 0.3 or below; bump reads as shading, and too much looks like baked-in lighting. Large bevels come from `make_high`, and the bake merges both.
- **Roughness carries the specular story.** Worn or polished spots are smoother, dust and dirt rougher, and water streaks smoother still. Drive them from the same wear masks as the albedo so the maps agree.
- **Metal.** Metallic is 1 where the metal is bare, 0 wherever paint, rust or dirt covers it, and in between only along the border.
- **Maps.** Bake with `ao_in_orm=True` and `normal=True`.
