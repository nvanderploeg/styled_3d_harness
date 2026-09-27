---
name: texture-from-reference
description: Texture a game asset to match reference images, either hand-painted stylized with the lighting baked in or a full PBR set (albedo, normal, roughness, metallic, AO) from photos. Use when the user supplies texture or style references, or wants detailed, realistic or hand-painted textures.
---

# Texture From Reference

You rebuild each zone's surface as a shader-node recipe that matches the references, then bake it to the asset's final maps. Read `pipeline/ASSET.md` first; it defines the asset folder, the scene conventions and the commands. Read `pipeline/MATERIALS.md` for value ranges.

This stage builds on `texture_base.blend`. If that stage isn't built, run the `texture-base` skill first; its zone values are this stage's starting palette.

## 1. Pick the branch

`texture_mode` in `asset.json` decides it. When it's unset, painted or illustrated refs mean `"stylized"` and photographs mean `"pbr"`. Write the choice back to `asset.json`. Then read the branch file now:

- `stylized` → [STYLIZED.md](STYLIZED.md): lighting, AO and highlights painted into the albedo.
- `pbr` → [PBR.md](PBR.md): an unlit albedo plus normal, roughness, metallic and AO; the engine does the lighting.

## 2. Read the references into recipe cards

Read every reference image. Write one card per zone:

- **Palette.** 3–5 sRGB hex values (shadow, mid, light, accent), each picked from a named ref.
- **Pattern.** What repeats (grain, planks, scales, weave), its size in metres on this asset, and which way it runs.
- **Wear.** Where the surface breaks up (edges, cavities, top, bottom, contact points) and what it breaks up into.
- **Response.** A roughness range and a metallic value, from MATERIALS.md, with the ref's own sheen overriding it.

Done when every zone from the model check's `zones` metric has a card, and every value on it traces to a ref or to MATERIALS.md.

## 3. Build the recipes

Copy `pipeline/templates/texture_ref.py` to `build/texture_ref.py` and read the docstrings in `pipeline/lib/nodes.py` and `pipeline/lib/bake.py`. Build one recipe per card, following your branch file. Reach for the pattern helpers before hand-wiring nodes: `slabs` (paving), `courses` (block walls), `cracks`, `by_facing`, `brush`. For a piece of a set, the recipes live in `assets/_kit/` and every piece calls them unchanged.

**Drive patterns from object coordinates.** They are in metres and continuous across UV seams. UV coordinates rotate with every packed island and break at every seam, so use them only for a pattern that must follow one island, and check the direction on the sheet.

## 4. Build and compare

Add `shots` to `asset.json` for what the sheet tiles are too small to judge: close-ups of seams, lips, corners and damage, plus the gameplay camera. Run `pipeline/asset build <slug> texture_ref`, fix every `FAIL`, and read `review/texture_ref.png` and `review/texture_ref_shots.png` side by side with each reference. Use the tile at the ref's angle, and the unlit tile for stylized refs. For each zone, list what differs, **squint** first (value masses, then hue, then pattern scale, then wear placement), and fix the largest difference first. Rebuild and compare again.

Done when the check passes and the difference list for every zone holds only detail that the map resolution can't carry. For a set, `pipeline/asset compare texture_ref <lead> <piece>...` also reads `CONSISTENT`, or each piece it flags has a reason you can name.
