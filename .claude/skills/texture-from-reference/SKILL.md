---
name: texture-from-reference
description: Texture a game asset to match reference images and its art guides, either hand-painted with the lighting baked in or PBR from photos. Use when the user supplies texture or style references, or wants detailed, realistic or hand-painted textures.
---

# Texture From Reference

You rebuild each zone's surface as a shader-node recipe that matches the references, then bake it to the asset's final maps. Read `pipeline/ASSET.md` first; it defines the asset folder, the scene conventions and the commands. Read `pipeline/MATERIALS.md` for value ranges.

This stage builds on `texture_base.blend`. If that stage isn't built, run the `texture-base` skill first; its zone values are this stage's starting palette.

## 1. Pick the branch

`texture_mode` in the spec decides it: `asset.json`'s, else the world guide's. When both leave it unset, painted or illustrated refs mean `"stylized"` and photographs mean `"pbr"`; write that choice back to `asset.json`. Then read the branch file now:

- `stylized` → [STYLIZED.md](STYLIZED.md): lighting, AO and highlights painted into the albedo.
- `pbr` → [PBR.md](PBR.md): an unlit albedo plus normal, roughness, metallic and AO; the engine does the lighting.

## 2. Read the references into recipe cards

Read every reference image, and every guide `pipeline/asset art <slug>` lists: the world's painting and material rules, the zone's palette, light and wear, and the set's material notes. Write one card per zone:

- **Palette.** 3–5 sRGB hex values (shadow, mid, light, accent) built around the zone's swatch when the palette has one, each picked from a named ref or guide.
- **Pattern.** What repeats (grain, planks, scales, weave), its size in metres on this asset, and which way it runs.
- **Wear.** Where the surface breaks up (edges, cavities, top, bottom, contact points) and what it breaks up into.
- **Response.** A roughness range and a metallic value, from the swatch or else MATERIALS.md, with the ref's own sheen overriding it.

Done when every zone from the model check's `zones` metric has a card, and every value on it traces to a ref, a guide or MATERIALS.md.

## 3. Build the recipes

Copy `pipeline/templates/texture_ref.py` to `build/texture_ref.py` and read the docstrings in `pipeline/lib/nodes.py` and `pipeline/lib/bake.py`. Build one recipe per card, following your branch file. Reach for the pattern helpers before hand-wiring nodes: `slabs` (paving), `courses` (block walls), `cracks`, `by_facing`, `brush`. For a piece of a set, the recipes live in `assets/_kit/` and every piece calls them unchanged.

**Drive patterns from object coordinates.** They are in metres and continuous across UV seams. UV coordinates rotate with every packed island and break at every seam, so use them only for a pattern that must follow one island, and check the direction on the sheet.

## 4. Build and compare

Add `shots` to `asset.json` for what the sheet tiles are too small to judge: close-ups of seams, lips, corners and damage, plus the gameplay camera. Run `pipeline/asset build <slug> texture_ref`, fix every `FAIL`, and read `review/texture_ref.png` and `review/texture_ref_shots.png` side by side with each reference and the guides. Use the tile at the ref's angle, and the unlit tile for stylized refs. For each zone, list what differs, **squint** first (value masses, then hue, then pattern scale, then wear placement), and fix the largest difference first. Rebuild and compare again.

Done when the check passes, every painting rule in the guides holds on the sheets, and the difference list for every zone holds only detail that the map resolution can't carry. For a set, `pipeline/asset compare texture_ref <lead> <piece>...` also reads `CONSISTENT`, or each piece it flags has a reason you can name.
