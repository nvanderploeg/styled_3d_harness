"""Base texture stage: one flat colour, roughness and metalness per zone, baked with AO. Runs with `asset` predefined."""
import bpy

import bake
from nodes import srgb, tree

ZONES = {
    # zone: (sRGB colour, roughness, metallic 0 or 1), for each zone the art guides' palette leaves out
    "main": ("#8a5a3b", 0.8, 0.0),
}
for name, (colour, roughness, metallic) in asset.zone_table(ZONES).items():
    tree(bpy.data.materials[f"zone_{name}"]).out(srgb(colour), roughness, metallic)

bake.bake(asset, "texture_base")
