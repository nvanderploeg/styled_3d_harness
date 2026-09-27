# Stylized: lighting painted in

The albedo is the finished image. The engine may render it unlit, so every shadow, highlight and gradient the refs show goes into the albedo.

- **Light with `painted_light`.** Every zone gets the same `key` direction and `top` range (the asset's height), so the whole asset agrees on where the light comes from. Its shadow and light tints are hue-shifted: cool shadows and warm lights, unless the refs say otherwise. In a set, `key` is one constant in the kit. The light is baked in each piece's own frame, so it turns with the piece in a level, and faces turned toward the key read slightly brighter.
- **Convex edges catch light, concave creases hold shadow.** `painted_light` highlights only convex edges and darkens creases. Any line you paint along an edge yourself must obey the same rule. Check every inner corner in a shot.
- **Gameplay reads first.** The zone the player must spot stays the brightest, cleanest read in the finished albedo, as it was in the base texture.
- **Shape before texture.** Big value shapes come first: the top-lit gradient, AO in the crevices, and edge highlights (`edge_radius` of about 1% of the asset's size). Pattern (`noise`, `wave`, `voronoi` through a `ramp` of the card's palette) sits under them and stays lower in contrast than the lighting.
- **Posterize like the refs.** For banded cel-style refs, use `ramp(..., interpolation="CONSTANT")` with the card's 3–5 colours. For soft painterly refs, use `LINEAR` and low noise detail.
- **Brush texture.** Use `brush`: a low-contrast stroke texture at 2–5 cm, multiplied over the lit colour.
- **Fractures and broken surfaces.** Give each facet one solid tone chosen by facing (`by_facing`: down darkest, up lightest), clearly darker than the intact surface around it. Paint no edge highlight across small facets, because it washes them into frosted glass. A thin light rim goes only where the break meets the intact surface.
- **Cracks and stains.** A crack is a few decisive branches, each a dark line with a lit lip (`cracks`). Large dark blotches read as camouflage, so keep blotch contrast low and blotches few.
- **Maps.** Bake with `ao_in_orm=False`, and use `samples=64` or more, since the AO and bevel nodes are noisy. Roughness stays at 0.7 or above and metallic at 0 unless the refs show real shine. A stylized normal map carries only broad bevels from `make_high`, never fine bumps, which would fight the painted light.
