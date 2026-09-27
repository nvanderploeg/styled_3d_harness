"""Reference texture stage: one node recipe per zone, baked to albedo/ORM/normal. Runs with `asset` predefined."""
import bpy

import bake
import photo
from nodes import srgb, tree

STYLIZED = asset.spec["texture_mode"] == "stylized"

z = tree(bpy.data.materials["zone_main"])
pos = z.coords("Object")                     # metres; seamless across UV seams
streaks = z.math_v("MULTIPLY", pos, (1, 1, 0.1))   # stretch along Z for vertical grain
grain = z.noise(scale=30, detail=6, vector=streaks)
base = z.ramp(grain, [(0.2, srgb("#5a3520")), (0.5, srgb("#8a5a3b")), (0.9, srgb("#b07a4e"))])
rough = z.map_range(grain, 0, 1, 0.9, 0.7)
if STYLIZED:
    z.out(z.painted_light(base, top=(0, asset.mesh.dimensions.z), edge_radius=0.01), rough, 0.0)
else:
    # src = photo.prepare(asset.path("refs", "wood.jpg"), asset.path("refs", "wood_tile.png"))
    # h, r = photo.derive(src, asset.path("refs", "wood_h.png"), asset.path("refs", "wood_r.png"))
    # base = z.image(src, projection="BOX", vector=z.math_v("MULTIPLY", pos, (2, 2, 2)))
    z.out(base, rough, 0.0, normal=z.bump(grain, strength=0.2))

bake.bake(asset, "texture_ref", normal=True, ao_in_orm=not STYLIZED, samples=64 if STYLIZED else 32)
