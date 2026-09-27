# styled_3d_harness

Claude Code skills that make game-ready 3D assets in Blender, from a brief and reference images to a verified glTF.

| skill | invoked | does |
|---|---|---|
| `/make-asset` | by you | runs the whole pipeline for one asset, one stage agent at a time, gating each stage |
| `model-asset` | by Claude or you | low-poly mesh with clean quad topology, zones and UVs |
| `rig-asset` | by Claude or you | deform skeleton, skin weights and a `rig_test` action |
| `texture-base` | by Claude or you | flat material per zone, baked with AO |
| `texture-from-reference` | by Claude or you | stylized (painted light) or PBR maps matched to references |
| `art-guide` | by Claude or you | the world, zone or set art guide that assets of one game follow |

Every stage is a Blender build script under `assets/<slug>/build/`. `pipeline/asset build` runs it, checks the result
against hard limits, and renders a review sheet. See [pipeline/ASSET.md](pipeline/ASSET.md) for the asset contract.

## Setup

Blender 4.5 LTS at `~/opt/blender/blender`, or set `$BLENDER`. Baking uses the GPU (OptiX or CUDA) when there is one.

```
pipeline/asset new crate
pipeline/asset build crate model
pipeline/asset status crate
pipeline/asset export crate      # assets/crate/export/crate.glb
```

## Art guides

Assets that must look like one game follow a chain of art guides in `assets/_art/`: the world's look, a zone's
mood, and a set's construction and palette. [pipeline/ART.md](pipeline/ART.md) defines the format, and
`pipeline/templates/art/` holds a worked example in the style of World of Warcraft's Duskwood.

```
pipeline/asset art                                    # every chain
pipeline/asset art azeroth/duskwood/human_village     # one chain's guides in reading order, its palette and rules
```

## Sets

Sets of pieces share a set guide, and their generator and recipes in `assets/_kit/`. Two commands keep them honest:

```
pipeline/asset verify castle_platform_cross texture_ref     # rebuild in scratch space, diff against the approved stage
pipeline/asset compare texture_ref castle_platform_straight castle_platform_cross   # zone brightness across the set
```

## Tests

```
~/opt/blender/blender --background --factory-startup --python pipeline/tests/test_art.py
```
