"""Inventory every object of a block-out FBX: discovery's first read of an unknown level package.

    blender --background --factory-startup --python blockout_inventory.py -- <fbx> <out.json> [--walkable-deg 57]

Reads the FBX (imported with Blender's defaults: metres, Z up). Writes <out.json>:

- `objects`: per object its `name`, `path` in the hierarchy (root first), `type`, `parent`, world transform
  (`location`, `rotation_deg` XYZ Euler, `scale`) and, for a mesh, its world `bbox` [min, max], `verts`, `faces`,
  `tris`, `loose_parts`, `sides` (polygon side count -> faces), `kinds` (faces per class by world normal: `top`
  within walkable_deg of up, `side`, `under` facing down, `bottom` the flat base), `top_z` (distinct heights of
  flat top faces, cm), `up_slopes_deg` (slope of every upward face that is not flat -> faces), `materials`,
  `uv_layers`, and `colour_layers`: name, domain, data type and `top_colours`, the colours of its top faces
  (rounded to 0.01, as stored: linear floats) -> faces, with `mixed` counting faces whose corners differ.
- `groups`: every object with children, its path, its children's types and the meshes beneath it.
- `colour_layers`: per layer name, its domains and types, and each top colour's faces and objects over the
  whole file.
- `materials`: per material its viewport colour and Principled base colour.

Prints the groups with their mesh counts, the meshes in no group, and every colour layer with its colours.
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blockout_mesh as bm  # noqa: E402

FLAT_DEG = 0.05
UNIFORM_TOL = 0.01


def r(v, n=3):
    return [round(float(c), n) for c in v]


def loose_parts(me):
    """How many connected pieces the mesh is made of."""
    parent = list(range(len(me.vertices)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in me.edges:
        a, b = find(e.vertices[0]), find(e.vertices[1])
        if a != b:
            parent[a] = b
    return len({find(v.index) for v in me.vertices})


def colour_key(cols):
    c = bm.uniform(cols, UNIFORM_TOL)
    return "mixed" if c is None else "(" + ", ".join(f"{x:.2f}" for x in c) + ")"


def mesh_record(o, walkable_deg):
    me = o.data
    mw = o.matrix_world
    nm = bm.world_normals(o)
    vs = [mw @ v.co for v in me.vertices]
    if not vs:
        return {"verts": 0, "faces": 0, "tris": 0}
    zmin = min(v.z for v in vs)
    kinds, sides, top_z, slopes = Counter(), Counter(), set(), Counter()
    top_polys = []
    for p in me.polygons:
        n = (nm @ p.normal).normalized()
        kind = bm.face_kind(n, (mw @ p.center).z, zmin, walkable_deg)
        kinds[kind] += 1
        sides[len(p.vertices)] += 1
        up = bm.up_angle(n)
        if kind == "top":
            top_polys.append(p)
            if up < FLAT_DEG:
                top_z.add(round((mw @ p.center).z, 2))
        if FLAT_DEG <= up < 90.0 - FLAT_DEG:
            slopes[round(up, 1)] += 1
    layers = []
    for a in me.color_attributes:
        tops = Counter(colour_key(bm.face_colours(a, p)) for p in top_polys)
        layers.append({"name": a.name, "domain": a.domain, "type": a.data_type,
                       "top_colours": dict(tops.most_common())})
    return {"bbox": [r([min(v[i] for v in vs) for i in range(3)]), r([max(v[i] for v in vs) for i in range(3)])],
            "verts": len(me.vertices), "faces": len(me.polygons),
            "tris": sum(len(p.vertices) - 2 for p in me.polygons), "loose_parts": loose_parts(me),
            "sides": {str(k): v for k, v in sorted(sides.items())}, "kinds": dict(kinds),
            "top_z": sorted(top_z), "up_slopes_deg": {str(k): v for k, v in sorted(slopes.items())},
            "materials": [m.name for m in me.materials if m], "uv_layers": [u.name for u in me.uv_layers],
            "colour_layers": layers}


def object_record(o, walkable_deg):
    loc, rot, scale = o.matrix_world.decompose()
    rec = {"name": o.name, "path": bm.path(o), "type": o.type, "parent": o.parent.name if o.parent else None,
           "location": r(loc), "rotation_deg": r([math.degrees(a) for a in rot.to_euler()], 2), "scale": r(scale)}
    if o.type == "MESH":
        rec.update(mesh_record(o, walkable_deg))
    return rec


def groups(objects):
    """Every object with children: its path, its children's types and the meshes anywhere beneath it."""
    out = {}
    for o in objects:
        if not o.children:
            continue
        below = [c for c in o.children_recursive if c.type == "MESH"]
        out[o.name] = {"path": bm.path(o), "children": dict(Counter(c.type for c in o.children)),
                       "meshes": len(below), "tris": sum(sum(len(p.vertices) - 2 for p in c.data.polygons)
                                                         for c in below)}
    return dict(sorted(out.items(), key=lambda kv: kv[1]["path"]))


def colour_summary(records):
    """Per colour layer name: domains, types, and each top colour's faces and objects over the whole file."""
    out = defaultdict(lambda: {"domains": set(), "types": set(), "colours": defaultdict(lambda: [0, 0])})
    for rec in records:
        for layer in rec.get("colour_layers", []):
            s = out[layer["name"]]
            s["domains"].add(layer["domain"])
            s["types"].add(layer["type"])
            for c, n in layer["top_colours"].items():
                s["colours"][c][0] += n
                s["colours"][c][1] += 1
    return {name: {"domains": sorted(s["domains"]), "types": sorted(s["types"]),
                   "colours": {c: {"faces": f, "objects": k}
                               for c, (f, k) in sorted(s["colours"].items(), key=lambda kv: -kv[1][0])}}
            for name, s in out.items()}


def materials():
    out = {}
    for m in bpy.data.materials:
        base = None
        if m.use_nodes and m.node_tree:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED":
                    base = r(n.inputs["Base Color"].default_value)
        out[m.name] = {"diffuse": r(m.diffuse_color), "base_color": base}
    return out


def main():
    argv = bm.args(sys.argv)
    fbx, out = argv[0], argv[1]
    walkable_deg = float(argv[argv.index("--walkable-deg") + 1]) if "--walkable-deg" in argv else 57.0
    bm.load(fbx)
    objects = sorted(bpy.data.objects, key=bm.path)
    records = [object_record(o, walkable_deg) for o in objects]
    data = {"source": fbx, "units": "metres, Blender Z up (FBX imported with Blender's defaults)",
            "walkable_deg": walkable_deg, "groups": groups(objects), "colour_layers": colour_summary(records),
            "materials": materials(), "objects": records}
    with open(out, "w") as f:
        json.dump(data, f, indent=1)

    meshes = [rec for rec in records if rec["type"] == "MESH"]
    print(f"{len(records)} objects, {len(meshes)} meshes, {sum(m['tris'] for m in meshes)} tris -> {out}")
    print("groups (path: children by type; meshes beneath, tris):")
    for name, g in data["groups"].items():
        depth = g["path"].count("/")
        kids = ", ".join(f"{n} {t.lower()}" for t, n in g["children"].items())
        print(f"  {'  ' * depth}{name}: {kids}; {g['meshes']} meshes, {g['tris']} tris")
    leaves = [rec for rec in meshes if rec["parent"] is None
              or data["groups"][rec["parent"]]["children"].get("EMPTY", 0)]
    if leaves:
        print("meshes beside groups (siblings of empties, or at the root):")
        for rec in leaves:
            print(f"  {rec['path']}: {rec['tris']} tris, bbox {rec['bbox'][0]} - {rec['bbox'][1]}")
    print("colour layers (top faces by colour, as stored):")
    for name, s in data["colour_layers"].items():
        print(f"  {name} ({'/'.join(s['domains'])}, {'/'.join(s['types'])}):")
        for c, n in s["colours"].items():
            print(f"    {c}: {n['faces']} faces on {n['objects']} objects")
    sides = Counter()
    for m in meshes:
        for k, v in m["sides"].items():
            sides[int(k)] += v
    slopes = Counter()
    for m in meshes:
        for k, v in m["up_slopes_deg"].items():
            slopes[round(float(k))] += v
    print(f"polygon sides: {dict(sorted(sides.items()))}")
    print(f"upward slopes (deg, rounded: faces): {dict(sorted(slopes.items()))}")


main()
