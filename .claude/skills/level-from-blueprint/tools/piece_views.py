"""Render one block-out piece highlighted among its neighbours and the water, from cameras derived from its bounds,
its lips and the routes.

    blender --background --factory-startup --python piece_views.py -- <fbx> <extract.json> <piece> <outdir>
        [--routes routes.json] [--water-object water] [--res 1280 720] [--lens 28]

Reads the FBX, blockout_extract.py's json and routes.py's json (computed here from the extract with routes.py's
defaults when --routes is not given). Writes into <outdir>, with Workbench (studio light, cavity):

- `<piece>_overview.png`: from above at three-quarter, 40 degrees down;
- `<piece>_water.png`: level with the water, 1 m over it, looking at the piece's middle height;
- `<piece>_gameplay.png`: a runner's view from behind a take-off lip along its jump line (the piece's own
  take-off first, the easiest such jump; else a jump landing on the piece); with no jump, along the piece's longest
  top axis;
- `<piece>_views.json`: each view's camera (location, target, lens), how it was chosen and the objects in its way.

The overview and water views try 16 bearings and keep the one whose sight lines to points on the piece cross the
fewest other objects (ray casts), three-quarter bearings first on a tie; the gameplay view backs off and rises
until its sight lines to both lips are clear. The piece is orange, other route pieces sand, decor and unassigned
meshes grey, the water blue; lips are drawn as strips in their colours.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import blockout_mesh as bm  # noqa: E402

COLOURS = {"piece": (0.9, 0.5, 0.18, 1), "route": (0.62, 0.57, 0.5, 1), "other": (0.32, 0.32, 0.33, 1),
           "water": (0.2, 0.33, 0.45, 1)}
SKY = (0.46, 0.52, 0.57)
EYE_M = 4.0
OVERVIEW_DEG = 40.0
# Share of the frame's width the piece's plan extent fills.
FILL = 0.6
SENSOR_MM = 36.0
STRIP_M = 0.35
BEARINGS = 16


def options(argv):
    """([fbx, extract, piece, outdir], options) from the arguments after `--`."""
    pos, opt = [], {"routes": None, "water_object": "water", "res": [1280, 720], "lens": 28.0}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--res":
            opt["res"] = [int(argv[i + 1]), int(argv[i + 2])]
            i += 3
        elif a.startswith("--"):
            key = a[2:].replace("-", "_")
            if key not in opt:
                raise SystemExit(f"unknown option {a}")
            opt[key] = float(argv[i + 1]) if key == "lens" else argv[i + 1]
            i += 2
        else:
            pos.append(a)
            i += 1
    if len(pos) != 4:
        raise SystemExit("usage: piece_views.py -- <fbx> <extract.json> <piece> <outdir> [options]")
    return pos, opt


def load_routes(extract_path, routes_path):
    """routes.py's json: read from routes_path, else computed from the extract with routes.py's defaults."""
    if routes_path:
        with open(routes_path) as f:
            return json.load(f)
    import routes
    rt = routes.Routes(extract_path)
    return json.loads(json.dumps(rt.as_json(extract_path), default=lambda o: o.tolist()))


# ---------------------------------------------------------------- scene


def setup_scene(res, piece, pieces, water_name, water_z):
    """Workbench, object colours and a camera; the water object, or a plane at water_z when there is none."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "OBJECT"
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.world = bpy.data.worlds.new("sky")
    sc.world.color = SKY
    water = bpy.data.objects.get(water_name)
    if water is None and water_z is not None:
        me = bpy.data.meshes.new("water")
        s = 2000.0
        me.from_pydata([(-s, -s, water_z), (s, -s, water_z), (s, s, water_z), (-s, s, water_z)], [], [(0, 1, 2, 3)])
        water = bpy.data.objects.new("water", me)
        sc.collection.objects.link(water)
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        if o == water:
            o.color = COLOURS["water"]
        elif o.name == piece:
            o.color = COLOURS["piece"]
        elif o.name in pieces and pieces[o.name].get("role", "gameplay") == "gameplay":
            o.color = COLOURS["route"]
        else:
            o.color = COLOURS["other"]
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.clip_end = 5000.0
    sc.collection.objects.link(cam)
    sc.camera = cam
    return sc, cam, water


def lip_strips(lips, palette):
    """One mesh per lip colour: a thin strip inside each lip edge, just over the top."""
    by = {}
    for lip in lips:
        by.setdefault(lip["colour"], []).append(lip)
    made = []
    for colour, group in by.items():
        verts, faces = [], []
        for lip in group:
            a, b = np.array(lip["a"], float), np.array(lip["b"], float)
            n = np.array(lip["n"] + [0.0], float)
            k = len(verts)
            for p in (a, b, b - n * STRIP_M, a - n * STRIP_M):
                verts.append(tuple(p + [0, 0, 0.03]))
            for p in (a, b, b - n * STRIP_M, a - n * STRIP_M):
                verts.append(tuple(p + [0, 0, 0.15]))
            faces += [(k, k + 1, k + 2, k + 3), (k + 4, k + 7, k + 6, k + 5), (k, k + 4, k + 5, k + 1),
                      (k + 1, k + 5, k + 6, k + 2), (k + 2, k + 6, k + 7, k + 3), (k + 3, k + 7, k + 4, k)]
        me = bpy.data.meshes.new(f"lips_{colour}")
        me.from_pydata(verts, [], faces)
        o = bpy.data.objects.new(f"lips_{colour}", me)
        o.color = tuple(palette.get(colour, (1, 1, 1))) + (1,)
        bpy.context.scene.collection.objects.link(o)
        made.append(o.name)
    return made


# ---------------------------------------------------------------- sight lines


def blockers(sc, cam, point, allowed):
    """Names of the objects not in allowed that the segment from cam to point crosses."""
    dg = bpy.context.evaluated_depsgraph_get()
    origin, target = Vector(cam), Vector(point)
    d = target - origin
    left = d.length
    d.normalize()
    found = set()
    while left > 1e-3:
        hit, loc, _, _, obj, _ = sc.ray_cast(dg, origin, d, distance=left)
        if not hit:
            break
        if obj.name not in allowed:
            found.add(obj.name)
        step = (loc - origin).length + 1e-3
        origin = loc + d * 1e-3
        left -= step
    return found


def score(sc, cam, points, allowed):
    """(sight lines blocked, distinct blockers) from cam to the points."""
    hits = [blockers(sc, cam, p, allowed) for p in points]
    return sum(1 for h in hits if h), sorted(set().union(*hits))


def piece_points(piece):
    """Points on the piece to keep in sight: its tops' outline corners pulled in, their centres, and its bbox's
    centre; with the bbox and that centre."""
    V = np.array(piece["verts"], float)
    pts = []
    for t in piece["tops"]:
        P = V[t["outline"]]
        c = P.mean(axis=0)
        pts.append(c + [0, 0, 0.1])
        pts += [p + (c - p) * min(0.3 / max(np.linalg.norm((c - p)[:2]), 1e-6), 0.5) + [0, 0, 0.1] for p in P]
    lo, hi = np.array(piece["bbox"][0]), np.array(piece["bbox"][1])
    mid = (lo + hi) / 2
    return [tuple(p) for p in pts + [mid]], lo, hi, mid


def long_axis(piece):
    """Unit plan direction of the piece's longest top (or its bbox's longer side), and that top's length along it."""
    V = np.array(piece["verts"], float)
    best = None
    for t in piece["tops"]:
        P = V[t["outline"]][:, :2]
        P = P - P.mean(axis=0)
        _, vecs = np.linalg.eigh(P.T @ P)
        ax = vecs[:, -1]
        span = float(np.ptp(P @ ax))
        if best is None or span > best[1]:
            best = (ax, span)
    if best is None:
        lo, hi = np.array(piece["bbox"][0]), np.array(piece["bbox"][1])
        ext = hi[:2] - lo[:2]
        return (np.array([1.0, 0.0]) if ext[0] >= ext[1] else np.array([0.0, 1.0])), float(ext.max())
    return best


# ---------------------------------------------------------------- views


def fit_dist(extent, lens, floor):
    """Camera distance at which extent spans FILL of the frame's width."""
    return max(floor, extent / FILL / 2 * lens / (SENSOR_MM / 2))


def orbit(sc, points, allowed, target, dist, elev_deg, axis_deg, z=None):
    """The clearest of BEARINGS camera positions round target at dist, elev_deg down (or at height z)."""
    best = None
    for k in range(BEARINGS):
        bearing = axis_deg + 45.0 + k * 360.0 / BEARINGS
        b = math.radians(bearing)
        flat = dist * math.cos(math.radians(elev_deg)) if z is None else dist
        cz = target[2] + dist * math.sin(math.radians(elev_deg)) if z is None else z
        cam = (target[0] + flat * math.cos(b), target[1] + flat * math.sin(b), cz)
        off = abs(((bearing - axis_deg - 45.0) % 90.0 + 45.0) % 90.0 - 45.0)
        blocked, names = score(sc, cam, points, allowed)
        key = (blocked, len(names), off)
        if best is None or key < best[0]:
            best = (key, cam, bearing % 360.0, names, blocked)
    _, cam, bearing, names, blocked = best
    return {"location": cam, "target": tuple(target), "bearing_deg": round(bearing, 1), "blocked_lines": blocked,
            "lines": len(points), "blockers": names}


def pick_jump(name, routes):
    """(take-off lip, landing lip, jump) for the piece: its own easiest take-off first, else a jump landing on it."""
    own = [j for j in routes["jumps"] if piece_of_top(j["from"]) == name]
    onto = [j for j in routes["jumps"] if piece_of_top(j["to"]) == name]
    for group in (own, onto):
        if group:
            j = min(group, key=lambda j: (j["difficulty"] or "~", j["gap_m"], j["name"]))
            return routes["lips"][j["lips"][0]], routes["lips"][j["lips"][1]], j
    return None


def gameplay(sc, name, piece, routes, allowed):
    """A runner's camera behind a take-off lip looking along the jump, backed off and raised until clear."""
    pick = pick_jump(name, routes)
    if pick:
        A, B, j = pick
        a_mid = np.array(A["mid"] + [A["z"]], float)
        b_mid = np.array(B["mid"] + [B["z"]], float)
        d = (b_mid - a_mid)[:2]
        d /= np.linalg.norm(d)
        target = (a_mid + b_mid) / 2 - [0, 0, 1.0]
        points = [tuple(a_mid + [0, 0, 0.3]), tuple(b_mid + [0, 0, 0.3])]
        allow = allowed | {piece_of_top(A["top"]), piece_of_top(B["top"])}
        how = f"behind the take-off lip of {j['name']} ({j['difficulty']}, gap {j['gap_m']} m)"
        tries = [(back, up) for up in (EYE_M, 2 * EYE_M, 4 * EYE_M) for back in (14.0, 9.0, 5.0)]
        base = a_mid
    else:
        ax, span = long_axis(piece)
        lo, hi = np.array(piece["bbox"][0]), np.array(piece["bbox"][1])
        top_z = max((t["z"] for t in piece["tops"]), default=hi[2])
        centre = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, top_z])
        best = None
        for sign in (1, -1):
            d = ax * sign
            cam = centre - np.r_[d * (span / 2 + 12.0), -EYE_M]
            blocked, names = score(sc, tuple(cam), [tuple(centre + [0, 0, 0.1])], allowed | {name})
            if best is None or (blocked, len(names)) < best[0]:
                best = ((blocked, len(names)), d)
        d = best[1]
        target = centre - [0, 0, 1.0]
        points = [tuple(centre + [0, 0, 0.1])]
        allow = allowed | {name}
        how = "along the piece's longest top axis (no jump)"
        tries = [(span / 2 + back, up) for up in (EYE_M, 2 * EYE_M, 4 * EYE_M) for back in (12.0, 8.0, 4.0)]
        base = centre
    best = None
    for back, up in tries:
        cam = base - np.r_[d * back, 0.0] + [0, 0, up]
        blocked, names = score(sc, tuple(cam), points, allow)
        key = (blocked, len(names))
        if best is None or key < best[0]:
            best = (key, cam, names, blocked, back, up)
        if blocked == 0:
            break
    _, cam, names, blocked, back, up = best
    return {"location": tuple(float(c) for c in cam), "target": tuple(float(c) for c in target),
            "how": how, "back_m": back, "up_m": up, "blocked_lines": blocked, "lines": len(points),
            "blockers": names}


def piece_of_top(top_id):
    """The piece of a route top id ('piece#i')."""
    return top_id.rsplit("#", 1)[0]


def shoot(sc, cam, view, lens, path):
    cam.location = Vector(view["location"])
    cam.data.lens = lens
    cam.rotation_euler = (Vector(view["target"]) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def main():
    (fbx, extract_path, name, outdir), opt = options(bm.args(sys.argv))
    with open(extract_path) as f:
        data = json.load(f)
    if name not in data["pieces"]:
        raise SystemExit(f"{name} is not a piece of {extract_path}")
    piece = data["pieces"][name]
    routes = load_routes(extract_path, opt["routes"])
    bm.load(fbx)
    sc, cam, water = setup_scene(opt["res"], name, data["pieces"], opt["water_object"], data.get("water_z"))
    strips = lip_strips(routes["lips"], {k: v for k, v in data.get("palette", {}).items()})
    allowed = set(strips) | ({water.name} if water else set())
    os.makedirs(outdir, exist_ok=True)

    points, lo, hi, mid = piece_points(piece)
    ax, _ = long_axis(piece)
    axis_deg = math.degrees(math.atan2(ax[1], ax[0]))
    extent = float(np.linalg.norm(hi[:2] - lo[:2]))
    top_z = max((t["z"] for t in piece["tops"]), default=float(hi[2]))
    water_z = data.get("water_z")
    if water_z is None and water is not None:
        water_z = float(min((water.matrix_world @ v.co).z for v in water.data.vertices))
    low = water_z if water_z is not None else float(lo[2])
    views = {
        "overview": orbit(sc, points, allowed | {name}, (mid[0], mid[1], top_z),
                          fit_dist(extent, opt["lens"], 60.0),
                          OVERVIEW_DEG, axis_deg),
        "water": orbit(sc, points, allowed | {name}, (mid[0], mid[1], (low + top_z) / 2),
                       fit_dist(extent, opt["lens"], 35.0), 0.0, axis_deg, z=low + 1.0),
        "gameplay": gameplay(sc, name, piece, routes, allowed),
    }
    for view, v in views.items():
        v["lens"] = opt["lens"]
        v["file"] = os.path.join(outdir, f"{name}_{view}.png")
        shoot(sc, cam, v, opt["lens"], v["file"])
    with open(os.path.join(outdir, f"{name}_views.json"), "w") as f:
        json.dump({"piece": name, "views": views}, f, indent=1)
    for view, v in views.items():
        extra = v.get("how") or f"bearing {v['bearing_deg']} deg"
        print(f"{view:9} {extra}; {v['blocked_lines']}/{v['lines']} sight lines blocked"
              f"{' by ' + ', '.join(v['blockers']) if v['blockers'] else ''} -> {v['file']}")


main()
