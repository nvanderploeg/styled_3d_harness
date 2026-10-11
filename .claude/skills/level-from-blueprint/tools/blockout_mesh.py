"""Blender helpers the block-out tools share: import an FBX, walk an object's hierarchy, class a face by its world
normal, read a face's vertex colours. Imported by blockout_inventory.py, blockout_extract.py and piece_views.py;
runs only inside Blender.
"""
import math

import bpy

BOTTOM_DEG = 179.0


def args(argv):
    """The arguments after Blender's `--`."""
    return argv[argv.index("--") + 1:] if "--" in argv else []


def load(fbx):
    """An empty scene holding the FBX, imported with Blender's defaults (metres, Z up)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=fbx)


def ancestors(o):
    """o's parents, nearest first."""
    out, p = [], o.parent
    while p is not None:
        out.append(p)
        p = p.parent
    return out


def path(o):
    """o's place in the hierarchy, root first, names joined by '/'."""
    return "/".join(reversed([o.name] + [p.name for p in ancestors(o)]))


def up_angle(n):
    """Degrees between a unit normal and world up: 0 faces straight up, 180 straight down."""
    return math.degrees(math.acos(max(-1.0, min(1.0, n.z))))


def face_kind(n, cz, zmin, walkable_deg):
    """'top' (walkable: within walkable_deg of up), 'bottom' (the flat base at the mesh's lowest height), 'under'
    (facing down), else 'side'. n is the face's unit world normal, cz its centre's height, zmin the mesh's."""
    up = up_angle(n)
    if up < walkable_deg:
        return "top"
    if up > BOTTOM_DEG and abs(cz - zmin) < 1e-3:
        return "bottom"
    if n.z < -1e-3:
        return "under"
    return "side"


def world_normals(o):
    """The matrix that takes o's local normals to world."""
    return o.matrix_world.to_3x3().inverted().transposed()


def face_colours(layer, poly):
    """The colour (r, g, b) at each corner of poly, as the layer stores it (Blender's linear floats)."""
    if layer.domain == "CORNER":
        return [tuple(layer.data[li].color[:3]) for li in poly.loop_indices]
    return [tuple(layer.data[vi].color[:3]) for vi in poly.vertices]


def uniform(cols, tol):
    """The mean of cols when every channel of every corner lies within tol of it, else None."""
    mean = tuple(sum(c[i] for c in cols) / len(cols) for i in range(3))
    if all(max(abs(c[i] - mean[i]) for i in range(3)) < tol for c in cols):
        return mean
    return None
