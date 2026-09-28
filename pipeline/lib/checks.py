import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import art
import uvmath


class Report:
    def __init__(self):
        self.fails, self.warns, self.metrics = [], [], {}

    def fail(self, msg):
        self.fails.append(msg)

    def warn(self, msg):
        self.warns.append(msg)

    def require(self, ok, msg):
        if not ok:
            self.fail(msg)
        return ok


def run(a, stage):
    r = Report()
    mesh_checks(a, r, stage)
    if a.mesh is not None:
        if stage == "model":
            uv_checks(a, r)
        if stage == "rig":
            rig_checks(a, r)
        if stage.startswith("texture"):
            texture_checks(a, r, stage)

    ok = not r.fails
    built = os.path.getmtime(a.blend(stage))
    rep = {"stage": stage, "pass": ok, "built": built, "spec": a.fingerprint(),
           "fail": r.fails, "warn": r.warns, "metrics": r.metrics}
    prev = a.report(stage)
    if prev and prev.get("built") == built and "verified" in prev:
        rep["verified"] = prev["verified"]
    os.makedirs(a.path("review"), exist_ok=True)
    with open(a.path("review", f"{stage}.json"), "w") as f:
        json.dump(rep, f, indent=2)
    for k, v in r.metrics.items():
        print(f"  {k}: {v}")
    for w in r.warns:
        print(f"WARN {w}")
    for e in r.fails:
        print(f"FAIL {e}")
    print(f"check {stage}: {'PASS' if ok else 'FAIL'}")
    return ok


def mesh_checks(a, r, stage):
    obj = a.mesh
    if not r.require(obj is not None and obj.type == "MESH", f"no mesh object named '{a.slug}'"):
        return
    allowed = {a.slug, f"{a.slug}_high", f"{a.slug}_rig"}
    stray = [o.name for o in bpy.data.objects if o.name not in allowed]
    r.require(not stray, f"stray objects (only {sorted(allowed)} may exist): {stray}")

    loc, rot, scale = obj.matrix_world.decompose()
    r.require(loc.length < 1e-4 and rot.angle < 1e-4 and (scale - scale.__class__((1, 1, 1))).length < 1e-4,
              "object transform is not identity — bake it into the mesh")

    mods = [m.type for m in obj.modifiers]
    want = ["ARMATURE"] if stage != "model" and a.rigged else []
    r.require(mods == want, f"modifiers must be {want}, found {mods}")

    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    faces = len(bm.faces)
    tris = sum(len(f.verts) - 2 for f in bm.faces)
    tri_faces = sum(1 for f in bm.faces if len(f.verts) == 3)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)
    r.metrics.update(tris=tris, faces=faces, verts=len(bm.verts),
                     tri_face_ratio=round(tri_faces / max(faces, 1), 3))
    r.require(faces > 0, "mesh has no faces")
    r.require(tris <= a.spec["tri_budget"], f"{tris} tris exceeds tri_budget {a.spec['tri_budget']}")
    r.require(ngons == 0, f"{ngons} n-gons — cut them into quads")
    r.require(tri_faces / max(faces, 1) <= a.limits["max_tri_ratio"],
              f"{tri_faces}/{faces} faces are triangles (limit {a.limits['max_tri_ratio']:.0%}) — keep it quad-dominant")

    size = max(obj.dimensions) or 1.0
    eps = size * 1e-5
    wire = sum(1 for e in bm.edges if not e.link_faces)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    multi = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    flipped = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
    degenerate = sum(1 for f in bm.faces if f.calc_area() < eps * eps)
    kd = KDTree(len(bm.verts))
    for v in bm.verts:
        kd.insert(v.co, v.index)
    kd.balance()
    doubles = sum(1 for v in bm.verts if len(kd.find_range(v.co, eps)) > 1)
    poles = sum(1 for v in bm.verts if len(v.link_edges) >= 6)
    r.metrics.update(boundary_edges=boundary, poles_6plus=poles)
    r.require(wire == 0 and loose == 0, f"{wire} wire edges, {loose} loose verts")
    r.require(multi == 0, f"{multi} edges shared by 3+ faces")
    r.require(doubles == 0, f"{doubles} overlapping verts — weld them")
    r.require(degenerate == 0, f"{degenerate} zero-area faces")
    r.require(flipped == 0, f"{flipped} edges between faces with opposite normals")
    if boundary and not a.limits["allow_open"]:
        r.fail(f"{boundary} open (boundary) edges — close the mesh or set limits.allow_open")
    if boundary == 0 and flipped == 0:
        vol = sum(f.verts[0].co.dot(f.verts[i].co.cross(f.verts[i + 1].co))
                  for f in bm.faces for i in range(1, len(f.verts) - 1)) / 6
        r.require(vol > 0, "normals point inward")
    bm.free()

    dims = obj.dimensions
    r.metrics["dimensions_m"] = [round(d, 3) for d in dims]
    h = a.spec.get("height_m")
    if h:
        r.require(abs(dims.z - h) <= 0.1 * h, f"height {dims.z:.3f} m is not within 10% of height_m {h}")
    lo = [min(v.co[i] for v in me.vertices) for i in range(3)]
    hi = [max(v.co[i] for v in me.vertices) for i in range(3)]
    r.require(abs(lo[2]) <= 0.01 * size, f"lowest point is z={lo[2]:.3f}, not on the ground (z=0)")
    r.require(abs(lo[0] + hi[0]) / 2 <= 0.05 * size and abs(lo[1] + hi[1]) / 2 <= 0.05 * size,
              "origin is not at the bottom centre of the bounds")

    slots = [s.material for s in obj.material_slots]
    r.require(slots and all(m and m.name.startswith("zone_") for m in slots),
              f"every material slot must be a zone_* material, found {[m.name if m else None for m in slots]}")
    used = {p.material_index for p in me.polygons}
    r.require(used == set(range(len(slots))), "unused or out-of-range material slots")
    r.metrics["zones"] = [m.name[5:] for m in slots if m]

    high = a.high
    if high is not None:
        hd = high.dimensions
        r.require(all(abs(hd[i] - dims[i]) <= 0.05 * size for i in range(3)),
                  f"{high.name} bounds {list(map(lambda d: round(d, 3), hd))} do not match the low mesh")


def uv_checks(a, r):
    me = a.mesh.data
    if not r.require(len(me.uv_layers) == 1, f"need exactly one UV map, found {len(me.uv_layers)}"):
        return
    tri_uv, tri_3d = uvmath.triangles(me)
    if not r.require(((tri_uv >= -1e-4) & (tri_uv <= 1 + 1e-4)).all(), "UVs fall outside 0–1"):
        return
    area_uv = uvmath.area2d(tri_uv)
    area_3d = uvmath.area3d(tri_3d)
    zero = int((area_uv < 1e-9).sum())
    r.require(zero == 0, f"{zero} triangles have zero UV area (collapsed or unmapped)")

    cov = uvmath.raster(tri_uv, 512)
    covered = (cov > 0).sum()
    overlap = (cov > 1).sum() / max(covered, 1)
    coverage = covered / cov.size
    r.metrics.update(uv_coverage=round(float(coverage), 3), uv_overlap=round(float(overlap), 4))
    if not a.limits["uv_overlap_ok"]:
        r.require(overlap <= 0.005, f"{overlap:.1%} of UV area overlaps — or set limits.uv_overlap_ok for stacked islands")
    r.require(coverage >= a.limits["min_uv_coverage"],
              f"UVs fill {coverage:.0%} of the texture (min {a.limits['min_uv_coverage']:.0%}) — pack tighter")

    ok = (area_uv > 1e-12) & (area_3d > 1e-12)
    density = np.sqrt(area_uv[ok] / area_3d[ok])
    w = area_3d[ok]
    order = np.argsort(density)
    median = density[order][np.searchsorted(np.cumsum(w[order]), w.sum() / 2)]
    tol = a.limits["texel_density_tolerance"]
    off = w[(density < median / tol) | (density > median * tol)].sum() / w.sum()
    px_per_m = median * a.spec["texture_size"]
    r.metrics.update(texel_density_px_per_m=round(float(px_per_m), 1), texel_density_outliers=round(float(off), 3))
    r.require(off <= 0.05, f"{off:.0%} of the surface is off the median texel density by more than {tol}x")
    band = a.limits["texel_density_px_per_m"]
    if band:
        r.require(band[0] <= px_per_m <= band[1],
                  f"texel density {px_per_m:.0f} px/m is outside limits.texel_density_px_per_m {band}"
                  " — change texture_size or the UV scale")

    sharp = me.attributes.get("sharp_edge")
    if sharp is not None:
        seams = uvmath.uv_split_edges(me)
        unsplit = sum(1 for i, d in enumerate(sharp.data) if d.value and i not in seams
                      and not me.edges[i].is_loose)
        if unsplit:
            r.warn(f"{unsplit} hard edges are not UV seams — normal-map bakes will show lines there")


def rig_checks(a, r):
    arm, obj = a.armature, a.mesh
    if not r.require(arm is not None and arm.type == "ARMATURE", f"no armature named '{a.slug}_rig'"):
        return
    r.require(arm.matrix_world == arm.matrix_world.Identity(4), "armature transform is not identity")
    r.require(obj.parent == arm, f"'{a.slug}' is not parented to the armature")
    mods = [m for m in obj.modifiers if m.type == "ARMATURE"]
    r.require(mods and mods[0].object == arm, "armature modifier does not point at the rig")

    deform = {b.name for b in arm.data.bones if b.use_deform}
    r.metrics["deform_bones"] = len(deform)
    r.require(0 < len(deform) <= a.limits["max_bones"], f"{len(deform)} deform bones (max {a.limits['max_bones']})")
    roots = [b.name for b in arm.data.bones if b.parent is None]
    r.require(len(roots) == 1, f"skeleton needs exactly one root bone, found {roots}")

    groups = {g.index: g.name for g in obj.vertex_groups}
    orphan = sorted({groups[g.group] for v in obj.data.vertices for g in v.groups
                     if g.weight > 1e-4 and groups[g.group] not in deform})
    r.require(not orphan, f"weights on vertex groups with no deform bone: {orphan}")
    unweighted = over = unnormal = 0
    maxinf = a.limits["max_influences"]
    for v in obj.data.vertices:
        ws = [g.weight for g in v.groups if g.weight > 1e-4 and groups[g.group] in deform]
        if not ws:
            unweighted += 1
        elif len(ws) > maxinf:
            over += 1
        elif abs(sum(ws) - 1) > 0.01:
            unnormal += 1
    r.require(unweighted == 0, f"{unweighted} vertices have no deform weight")
    r.require(over == 0, f"{over} vertices exceed {maxinf} influences")
    r.require(unnormal == 0, f"{unnormal} vertices have weights that do not sum to 1")

    act = bpy.data.actions.get("rig_test")
    if r.require(act is not None, "no 'rig_test' action to exercise the rig"):
        lo, hi = act.frame_range
        r.metrics["rig_test_frames"] = [int(lo), int(hi)]
        r.require(hi - lo >= 2, "rig_test must span at least 3 frames of distinct poses")
    r.require(arm.data.pose_position == "POSE", "armature is left in rest position")


REQUIRED_MAPS = {"texture_base": ["albedo", "orm"], "texture_ref": ["albedo", "orm", "normal"]}


def texture_checks(a, r, stage):
    size = a.spec["texture_size"]
    me = a.mesh.data
    tri_uv, _ = uvmath.triangles(me)
    mask = uvmath.raster(tri_uv, size) > 0
    maps = {}
    for name in REQUIRED_MAPS[stage] + (["normal"] if a.high and stage == "texture_base" else []):
        p = a.texture(stage, name)
        if not r.require(os.path.exists(p), f"missing map {os.path.relpath(p, a.dir)}"):
            continue
        img = bpy.data.images.load(p, check_existing=False)
        w, h = img.size
        if not r.require((w, h) == (size, size), f"{name} is {w}x{h}, expected {size}x{size}"):
            continue
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        maps[name] = px.reshape(h, w, 4)[..., :3]
        bpy.data.images.remove(img)

    if "albedo" in maps:
        zone_checks(a, r, stage, maps["albedo"], tri_uv, size)
        lum = maps["albedo"][mask].mean(axis=1)
        black = float((lum < 0.01).mean())
        r.require(black < 0.5, f"{black:.0%} of UV-covered albedo is black — the bake missed")
        if a.spec["texture_mode"] == "pbr":
            dark = float((lum < 30 / 255).mean())
            bright = float((lum > 243 / 255).mean())
            r.metrics.update(albedo_below_srgb30=round(dark, 3), albedo_above_srgb243=round(bright, 3))
            if dark > 0.02 or bright > 0.02:
                r.warn("albedo leaves the physically plausible 30–243 sRGB range — lighting may be baked in")
    if "normal" in maps:
        n = maps["normal"][mask]
        mean = n.mean(axis=0)
        r.metrics["normal_mean"] = [round(float(x), 3) for x in mean]
        r.require(mean[2] > 0.7 and abs(mean[0] - 0.5) < 0.1 and abs(mean[1] - 0.5) < 0.1,
                  "normal map is not a tangent-space map centred on (0.5, 0.5, 1)")
    if "orm" in maps:
        orm = maps["orm"][mask]
        r.metrics["orm_mean"] = [round(float(x), 3) for x in orm.mean(axis=0)]
        r.require(orm[:, 0].mean() > 0.2, "ORM occlusion (R) is near black — the AO bake missed")
        if orm[:, 0].mean() < 0.6:
            r.warn("mean occlusion is below 0.6 — check for geometry shadowing the whole surface")

    for m in a.mesh.data.materials:
        principled = [n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"] if m.use_nodes else []
        r.require(len(principled) == 1, f"{m.name} must end in exactly one Principled BSDF")


def zone_checks(a, r, stage, albedo, tri_uv, size):
    """zone_luma and zone_saturation: each zone's mean albedo as sRGB luma (0–255) and HSV saturation;
    set pieces compare zone_luma. limits.albedo_luma and limits.max_saturation bound every zone whose
    swatch is not an accent, and neighbouring zones closer than limits.min_zone_contrast will not separate
    at a squint. All three FAIL on texture_ref and WARN on texture_base."""
    me = a.mesh.data
    mats = np.empty(len(me.loop_triangles), np.int32)
    me.loop_triangles.foreach_get("material_index", mats)
    res = min(size, 1024)
    step = size / res
    luma, sat = {}, {}
    for i, m in enumerate(me.materials):
        mask = uvmath.raster(tri_uv[mats == i], res) > 0
        if not mask.any():
            continue
        ys, xs = np.nonzero(mask)
        mean = albedo[(ys * step).astype(int), (xs * step).astype(int)].mean(axis=0)
        luma[m.name[5:]] = round(float(art.luma(mean)), 1)
        sat[m.name[5:]] = round(float(art.saturation(mean)), 3)
    r.metrics["zone_luma"] = luma
    r.metrics["zone_saturation"] = sat
    band, cap = a.limits["albedo_luma"], a.limits["max_saturation"]
    report = r.fail if stage == "texture_ref" else r.warn
    for z in luma:
        swatch = a.swatch(z)
        if swatch and swatch["accent"]:
            continue
        if band and not band[0] <= luma[z] <= band[1]:
            report(f"zone {z} has luma {luma[z]}, outside the value key limits.albedo_luma {band}")
        if cap is not None and sat[z] > cap:
            report(f"zone {z} has saturation {sat[z]}, above limits.max_saturation {cap}")
    floor = a.limits["min_zone_contrast"]
    for z1, z2 in neighbours(a.mesh):
        if z1 in luma and z2 in luma and abs(luma[z1] - luma[z2]) < floor:
            report(f"neighbouring zones {z1} ({luma[z1]}) and {z2} ({luma[z2]}) differ by less than "
                   f"{floor} luma — they merge at a squint")


def neighbours(obj, gap=0.002):
    """Sorted pairs of mesh zones that meet: across a shared edge, where their shells intersect, or where
    one comes within gap × the mesh size of the other."""
    me = obj.data
    names = [m.name[5:] for m in me.materials]
    pairs = set()
    edge_zones = {}
    for p in me.polygons:
        for ek in p.edge_keys:
            edge_zones.setdefault(ek, set()).add(p.material_index)
    for zs in edge_zones.values():
        if len(zs) > 1:
            pairs.update((i, j) for i in zs for j in zs if i < j)
    verts = [v.co.copy() for v in me.vertices]
    by_zone = {}
    for p in me.polygons:
        by_zone.setdefault(p.material_index, []).append(p)
    trees = {i: BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in ps]) for i, ps in by_zone.items()}
    corners = {i: {v for p in ps for v in p.vertices} for i, ps in by_zone.items()}
    reach = gap * (max(obj.dimensions) or 1.0)
    zones = sorted(trees)
    for n, i in enumerate(zones):
        for j in zones[n + 1:]:
            if (i, j) in pairs:
                continue
            if trees[i].overlap(trees[j]) or any(trees[j].find_nearest(verts[v], reach)[0] is not None
                                                 for v in corners[i]):
                pairs.add((i, j))
    return sorted(tuple(sorted((names[i], names[j]))) for i, j in pairs)
