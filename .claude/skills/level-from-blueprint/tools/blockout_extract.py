"""Extract every piece of a block-out FBX into the construction data the level's kit generators read.

    blender --background --factory-startup --python blockout_extract.py -- <fbx> <out.json> [--water Z]
        [--group-pattern ROLE=REGEX ...] [--object-pattern ROLE=REGEX ...] [--corridor-pattern REGEX]
        [--lip-layer Col] [--walkable-deg 57] [--palette NAME=R,G,B ...] [--plain white,grey,black]
        [--lip-match 0.06] [--colour-tol 0.06]

Pieces are the meshes beneath a group whose name matches a role pattern (`re.match`, nearest group wins; default
`gameplay=^Gameplay\\b` and `decor=^Decor\\b`), plus any mesh whose own name matches an object pattern (none by
default). A piece's corridor is the first group above it whose name matches --corridor-pattern; its first
capture group is the corridor's name (default `^(C\\d+) - `).

Writes <out.json>: `source`, `units`, `water_z`, `walkable_deg`, `roles` and `corridor_pattern` as given,
`lip_layer`, `palette` (name -> rgb), `lip_colours` (every cluster of uniform top-face colours: `rgb`, `faces`,
`ring_faces`, `pieces`, the `nearest` palette name, its `distance` (largest channel difference) and `lip`, true when
it marks lips), `mixed_top_faces`, and `pieces` (sorted by name). Per piece, in world metres, Blender Z up:

- `corridor`, `role`, `bbox` [min, max], `bottom_centre` (the bbox's centre at its lowest height), `tris`;
- `verts`, `faces` (vertex indices), `kinds`: `top` (walkable: within walkable_deg of up), `side` (steeper, facing
  up or sideways), `under` (facing down), `bottom` (the flat base);
- `tops`: one per connected region of top faces: its `faces`, `outline` (the region's outer boundary, as vertex
  indices), `flat`, `z` (the outline's highest point), `ring_faces` (top faces with an edge on the outline: where
  a block-out draws its inset lip ring) and `lips` (`face`, `colour`): faces whose every corner lies within
  --lip-match of a palette colour not in --plain, named by that colour.

Colours are compared as Blender stores them (`.color`: scene-linear floats). Prints the lip colour clusters, then
one line per piece: corridor, role, tris and its tops.
"""
import json
import os
import re
import sys
from collections import defaultdict

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blockout_mesh as bm  # noqa: E402

PALETTE = {"blue": (0.1, 0.35, 1.0), "cyan": (0.0, 0.85, 0.95), "green": (0.15, 0.85, 0.15),
           "orange": (1.0, 0.55, 0.0), "yellow": (1.0, 0.85, 0.1), "red": (1.0, 0.2, 0.2),
           "magenta": (1.0, 0.2, 1.0), "white": (1.0, 1.0, 1.0), "grey": (0.5, 0.5, 0.5), "black": (0.0, 0.0, 0.0)}
DEFAULTS = {"water": None, "group_pattern": ["gameplay=^Gameplay\\b", "decor=^Decor\\b"], "object_pattern": [],
            "corridor_pattern": "^(C\\d+) - ", "lip_layer": "Col", "walkable_deg": 57.0, "palette": [],
            "plain": "white,grey,black", "lip_match": 0.06, "colour_tol": 0.06}
MULTI = {"group_pattern", "object_pattern", "palette"}


def options(argv):
    """(fbx, out, options) from the arguments after `--`; repeatable options collect a list, and a repeatable
    option given on the command line replaces its default list."""
    pos, opt, given = [], json.loads(json.dumps(DEFAULTS)), set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--"):
            key = a[2:].replace("-", "_")
            if key not in DEFAULTS:
                raise SystemExit(f"unknown option {a}")
            val = argv[i + 1]
            if key in MULTI:
                if key not in given:
                    opt[key] = []
                    given.add(key)
                opt[key].append(val)
            else:
                opt[key] = val
            i += 2
        else:
            pos.append(a)
            i += 1
    if len(pos) != 2:
        raise SystemExit("usage: blockout_extract.py -- <fbx> <out.json> [options]")
    for key in ("walkable_deg", "lip_match", "colour_tol"):
        opt[key] = float(opt[key])
    opt["water"] = None if opt["water"] is None else float(opt["water"])
    return pos[0], pos[1], opt


def pairs(items):
    """'role=regex' strings as [(role, compiled regex)], in order."""
    out = []
    for s in items:
        role, _, rx = s.partition("=")
        out.append((role, re.compile(rx)))
    return out


def palette(extra):
    """PALETTE with the 'name=r,g,b' entries added or replaced."""
    pal = dict(PALETTE)
    for s in extra:
        name, _, rgb = s.partition("=")
        pal[name] = tuple(float(c) for c in rgb.split(","))
    return pal


def role_of(o, group_roles, object_roles):
    """The role o plays, or None: its own name's pattern first, then its nearest matching group."""
    for role, rx in object_roles:
        if rx.match(o.name):
            return role
    for p in bm.ancestors(o):
        for role, rx in group_roles:
            if rx.match(p.name):
                return role
    return None


def corridor_of(o, rx):
    """The first capture group (else the whole match) of the nearest group above o matching rx, or None."""
    for p in bm.ancestors(o):
        m = rx.match(p.name)
        if m:
            return m.group(1) if m.groups() else m.group(0)
    return None


def nearest(cols, pal):
    """(name, distance) of the palette colour nearest every corner of a face: distance is the largest channel
    difference over the corners."""
    best = None
    for name, ref in pal.items():
        d = max(max(abs(c[i] - ref[i]) for i in range(3)) for c in cols)
        if best is None or d < best[1]:
            best = (name, d)
    return best


class Clusters:
    """Uniform top-face colours grouped within tol on every channel, and a count of the faces whose corners differ,
    for the header."""

    def __init__(self, tol):
        self.tol, self.items, self.mixed = tol, [], 0

    def add(self, rgb, ring, piece):
        for c in self.items:
            if max(abs(rgb[i] - c["rgb"][i]) for i in range(3)) < self.tol:
                break
        else:
            c = {"rgb": rgb, "sum": [0.0, 0.0, 0.0], "faces": 0, "ring_faces": 0, "pieces": set()}
            self.items.append(c)
        c["faces"] += 1
        c["ring_faces"] += int(ring)
        c["pieces"].add(piece)
        c["sum"] = [s + x for s, x in zip(c["sum"], rgb)]

    def rows(self, pal, plain, match):
        """Each cluster, most faces first, named by its nearest palette colour; a lip when within match of a
        colour not in plain."""
        out = []
        for c in sorted(self.items, key=lambda c: -c["faces"]):
            rgb = tuple(s / c["faces"] for s in c["sum"])
            name, d = nearest([rgb], pal)
            out.append({"rgb": [round(x, 3) for x in rgb], "faces": c["faces"], "ring_faces": c["ring_faces"],
                        "pieces": len(c["pieces"]), "nearest": name, "distance": round(d, 3),
                        "lip": d < match and name not in plain})
        return out


def regions(faces, kinds):
    """Connected regions of top faces, with the edge -> faces map they were found with."""
    adj = defaultdict(set)
    edge_faces = defaultdict(list)
    for fi, f in enumerate(faces):
        for a, b in zip(f, f[1:] + f[:1]):
            edge_faces[tuple(sorted((a, b)))].append(fi)
    for fs in edge_faces.values():
        tops = [f for f in fs if kinds[f] == "top"]
        for a in tops:
            for b in tops:
                if a != b:
                    adj[a].add(b)
    seen, out = set(), []
    for fi, k in enumerate(kinds):
        if k != "top" or fi in seen:
            continue
        stack, region = [fi], []
        seen.add(fi)
        while stack:
            f = stack.pop()
            region.append(f)
            for g in adj[f]:
                if g not in seen:
                    seen.add(g)
                    stack.append(g)
        out.append(region)
    return out, edge_faces


def on_outline(a, b, region, edge_faces):
    """Whether edge (a, b) bounds the region: only one of its faces lies in it."""
    return sum(1 for g in edge_faces[tuple(sorted((a, b)))] if g in region) == 1


def ring_of(region, faces, edge_faces):
    """The region's faces with an edge on its outline."""
    return [f for f in region
            if any(on_outline(a, b, region, edge_faces) for a, b in zip(faces[f], faces[f][1:] + faces[f][:1]))]


def top_record(region, faces, verts, edge_faces, lips):
    """A top region's outline, flatness, height, ring faces and lips."""
    boundary = {}
    for f in region:
        fv = faces[f]
        for a, b in zip(fv, fv[1:] + fv[:1]):
            if on_outline(a, b, region, edge_faces):
                boundary[a] = b
    loop = []
    if boundary:
        start = next(iter(boundary))
        v = start
        while True:
            loop.append(v)
            v = boundary[v]
            if v == start or len(loop) > len(boundary):
                break
    zs = [verts[v][2] for v in loop]
    ring = ring_of(region, faces, edge_faces)
    return {"faces": sorted(region), "outline": loop, "flat": max(zs) - min(zs) < 1e-3 if zs else False,
            "z": round(max(zs), 3) if zs else None, "ring_faces": sorted(ring),
            "lips": [{"face": f, "colour": lips[f]} for f in sorted(region) if f in lips]}


def piece_record(o, role, corridor, opt, pal, plain, clusters):
    """One piece's record; its top faces' colours go into clusters."""
    me = o.data
    mw = o.matrix_world
    nm = bm.world_normals(o)
    col = me.color_attributes.get(opt["lip_layer"])
    verts = [[round(c, 4) for c in (mw @ v.co)] for v in me.vertices]
    zmin = min(v[2] for v in verts)
    faces, kinds, colours = [], [], {}
    for p in me.polygons:
        n = (nm @ p.normal).normalized()
        kind = bm.face_kind(n, (mw @ p.center).z, zmin, opt["walkable_deg"])
        faces.append(list(p.vertices))
        kinds.append(kind)
        if kind == "top" and col is not None:
            colours[p.index] = bm.face_colours(col, p)
    found, edge_faces = regions(faces, kinds)
    ring = {f for region in found for f in ring_of(region, faces, edge_faces)}
    lips = {}
    for fi, cols in colours.items():
        mean = bm.uniform(cols, opt["colour_tol"])
        if mean is None:
            clusters.mixed += 1
        else:
            clusters.add(mean, fi in ring, o.name)
        name, d = nearest(cols, pal)
        if d < opt["lip_match"] and name not in plain:
            lips[fi] = name
    tops = [top_record(region, faces, verts, edge_faces, lips) for region in found]
    xs, ys = [v[0] for v in verts], [v[1] for v in verts]
    return {"corridor": corridor, "role": role,
            "bbox": [[round(min(xs), 3), round(min(ys), 3), round(zmin, 3)],
                     [round(max(xs), 3), round(max(ys), 3), round(max(v[2] for v in verts), 3)]],
            "bottom_centre": [round((min(xs) + max(xs)) / 2, 4), round((min(ys) + max(ys)) / 2, 4), round(zmin, 4)],
            "tris": sum(len(f) - 2 for f in faces),
            "verts": verts, "faces": faces, "kinds": kinds, "tops": tops}


def main():
    fbx, out, opt = options(bm.args(sys.argv))
    group_roles, object_roles = pairs(opt["group_pattern"]), pairs(opt["object_pattern"])
    corridor_rx = re.compile(opt["corridor_pattern"])
    pal = palette(opt["palette"])
    plain = {s for s in opt["plain"].split(",") if s}
    bm.load(fbx)
    clusters, pieces, skipped = Clusters(opt["colour_tol"]), {}, []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        role = role_of(o, group_roles, object_roles)
        if role is None or not o.data.vertices:
            skipped.append(o.name)
            continue
        pieces[o.name] = piece_record(o, role, corridor_of(o, corridor_rx), opt, pal, plain, clusters)
    rows = clusters.rows(pal, plain, opt["lip_match"])
    data = {"source": fbx, "units": "metres, Blender Z up (FBX imported with Blender's defaults)",
            "water_z": opt["water"], "walkable_deg": opt["walkable_deg"],
            "roles": {"groups": opt["group_pattern"], "objects": opt["object_pattern"]},
            "corridor_pattern": opt["corridor_pattern"], "lip_layer": opt["lip_layer"],
            "palette": {k: list(v) for k, v in pal.items()}, "lip_colours": rows, "mixed_top_faces": clusters.mixed,
            "pieces": dict(sorted(pieces.items()))}
    with open(out, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    by_role = defaultdict(int)
    for p in pieces.values():
        by_role[p["role"]] += 1
    print(f"{len(pieces)} pieces ({', '.join(f'{n} {r}' for r, n in sorted(by_role.items()))}) -> {out}")
    print(f"meshes in no role: {', '.join(sorted(skipped)) or 'none'}")
    print(f"top-face colour clusters on layer {opt['lip_layer']!r} ({clusters.mixed} top faces mixed):")
    for row in rows:
        mark = "LIP" if row["lip"] else "   "
        print(f"  {mark} {row['nearest']:8} d={row['distance']:.3f} rgb={row['rgb']} faces={row['faces']} "
              f"ring={row['ring_faces']} pieces={row['pieces']}")
    for name, p in data["pieces"].items():
        tops = ", ".join(f"z={t['z']}{'' if t['flat'] else ' slope'} lips={[lip['colour'] for lip in t['lips']]}"
                         for t in p["tops"])
        print(f"{p['corridor']} {p['role']:8} {name:20} tris={p['tris']:4} tops: {tops}")


main()
