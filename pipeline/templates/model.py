"""Model stage: build the asset mesh from an empty scene. Runs with `asset` predefined."""
import bmesh
import bpy
from mathutils import Vector

import modeling as m

H = asset.spec["height_m"] or 1.0

# One block per part: build it from quads, then put every face in a zone.
body = m.lathe("body", [(0.3 * H, 0.0), (0.32 * H, 0.5 * H), (0.3 * H, H)], segments=24)
m.zone(body, "main")

# Primitives work too; keep their quads and apply nothing by hand — finalize applies modifiers.
# bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, H + 0.1))
# lid = bpy.context.active_object
# lid.modifiers.new("bevel", "BEVEL").segments = 2
# m.zone(lid, "trim")

m.finalize(asset, [body])  # joins parts, welds, origin to bottom centre, smooth-by-angle
m.unwrap(asset)            # seams on hard edges plus any marked, even texel density, packed
# m.make_high(asset, **asset.art.get("make_high", {}))  # rounded-edge twin for normal/AO bakes
