---
name: texture-base
description: Give a modeled game asset its base texture — a flat colour, roughness and metalness per zone, baked with AO into albedo and ORM maps. Use when the user wants a quick, blockout or base texture, or colours for a model's parts.
---

# Texture Base

You give every zone one flat material read and bake it into the asset's first set of maps. The asset should read correctly at a glance before any detail exists. Read `pipeline/ASSET.md` first; it defines the asset folder, the scene conventions and the commands. Read `pipeline/MATERIALS.md` for value ranges.

## 1. Pick a read per zone

List the zones with `pipeline/asset check <slug> model` (the `zones` metric), and the palette and limits with `pipeline/asset art <slug>`. A zone with a palette swatch of its own name takes that swatch; the template's `zone_table` fills it in. For every other zone, pick an sRGB colour, a roughness and a metallic of 0 or 1 from MATERIALS.md (its stylized rule when `texture_mode` is `"stylized"`), nudged toward the brief and any refs, inside the `albedo_luma` and `max_saturation` limits.

Order the zones into a **value ladder**. The zone gameplay most needs seen (a jump edge, a handle, a hazard) takes the brightest or most contrasting rung. Zones that touch sit clear of `limits.min_zone_contrast` (in `pipeline/asset art <slug>`), at least 6 luma above it, so they separate in value at a squint, not only in hue, and still do once `texture_ref`'s painting pulls them closer. The check measures this: `zone_luma` per zone, and a WARN when neighbours fall under `limits.min_zone_contrast`. Zones are neighbours across a shared edge, where their shells intersect, or where one rests on the other. At `texture_ref` the same gap FAILs.

For a set, every swatch the pieces share lives in the set guide's palette. A zone WARN on a zone that takes its swatch is a guide problem, because changing a swatch changes every asset in the chain: report the zone, its neighbour and both lumas rather than working around it.

Done when every zone has all three values and its rung on the ladder.

## 2. Build and review

Copy `pipeline/templates/texture_base.py` to `build/texture_base.py`, fill in `ZONES` for the zones the palette leaves out, and run `pipeline/asset build <slug> texture_base`. Fix every `FAIL` and every zone `WARN` (contrast, value key, saturation). Then read `review/texture_base.png`:

- **Unlit tile.** Each zone reads as its material, and the whole asset matches the brief's colour story.
- **Lit tiles.** Metallic zones catch the HDRI, the rest don't, and the roughness differences show.
- **AO.** On the occlusion tile of `review/texture_base_maps.png`, it darkens contacts and crevices only: under bands, between parts, in recesses.

Done when the check passes with no zone WARN and all three hold. For a set, `pipeline/asset compare texture_base <lead> <piece>...` also reads `CONSISTENT`.
