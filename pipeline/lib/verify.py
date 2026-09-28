"""Regression guards: rebuild a stage without touching its outputs, diff against what was approved and
re-check it under the current spec, and compare zone metrics across the pieces of a set."""
import json
import os
import shutil
import time
import tempfile

import bpy
import numpy as np

import checks
import imgio

MESH_TOL = 1e-6
MAP_TOL = 2 / 255


def snapshot(a):
    """Everything a stage decides about the asset mesh: geometry, zones, seams, sharp edges, UVs, weights."""
    me = a.mesh.data

    def arr(coll, attr, n, dtype):
        out = np.empty(len(coll) * n, dtype)
        coll.foreach_get(attr, out)
        return out

    snap = {
        "co": arr(me.vertices, "co", 3, np.float64),
        "loops": arr(me.loops, "vertex_index", 1, np.int64),
        "starts": arr(me.polygons, "loop_start", 1, np.int64),
        "zone": arr(me.polygons, "material_index", 1, np.int64),
        "zones": [m.name for m in me.materials],
        "edges": np.sort(arr(me.edges, "vertices", 2, np.int64).reshape(-1, 2), axis=1).ravel(),
        "seams": arr(me.edges, "use_seam", 1, bool),
        "uv": arr(me.uv_layers.active.data, "uv", 2, np.float64) if me.uv_layers else np.empty(0),
    }
    sharp = me.attributes.get("sharp_edge")
    snap["sharp"] = arr(sharp.data, "value", 1, bool) if sharp else np.zeros(len(me.edges), bool)
    groups = {g.index: g.name for g in a.mesh.vertex_groups}
    snap["weights"] = sorted((v.index, groups[g.group], round(g.weight, 6)) for v in me.vertices for g in v.groups)
    return snap


def diff_snapshots(old, new):
    out = []
    for k, v in old.items():
        w = new[k]
        if isinstance(v, np.ndarray):
            if v.shape != w.shape:
                out.append(f"{k}: shape {v.shape} → {w.shape}")
            elif v.dtype.kind == "f":
                d = float(np.abs(v - w).max()) if v.size else 0.0
                if d > MESH_TOL:
                    out.append(f"{k}: max change {d:.6f}")
            elif not np.array_equal(v, w):
                out.append(f"{k}: {int((v != w).sum())} entries differ")
        elif v != w:
            out.append(f"{k}: differs")
    return out


def verify(a, stage, run_stage):
    """Rebuild `stage` from its upstream .blend and script into a scratch folder in the asset and diff it
    against the saved stage. An IDENTICAL stage is checked again under the current spec; True when it is
    identical and passes."""
    bpy.ops.wm.open_mainfile(filepath=a.blend(stage))
    old = snapshot(a)
    tmp = tempfile.mkdtemp(prefix=f"verify_{stage}_", dir=a.path())
    saved_textures = a.textures
    a.textures = lambda s: os.path.join(tmp, s) if s == stage else saved_textures(s)
    try:
        run_stage(a, stage)
        problems = diff_snapshots(old, snapshot(a))
        if stage.startswith("texture"):
            problems += diff_maps(saved_textures(stage), a.textures(stage), a.slug)
    finally:
        a.textures = saved_textures
        shutil.rmtree(tmp, ignore_errors=True)
    for p in problems:
        print(f"CHANGED {p}")
    print(f"verify {stage}: {'IDENTICAL' if not problems else 'CHANGED'}")
    if problems:
        return False
    # Re-check under the current spec: a limit can tighten while the build stays identical.
    bpy.ops.wm.open_mainfile(filepath=a.blend(stage))
    ok = checks.run(a, stage)
    rep = a.report(stage)
    rep["verified"] = time.time()
    with open(a.path("review", f"{stage}.json"), "w") as f:
        json.dump(rep, f, indent=2)
    return ok


def diff_maps(old_dir, new_dir, slug):
    out = []
    names = sorted(set(os.listdir(old_dir)) | set(os.listdir(new_dir)))
    for name in names:
        p, q = os.path.join(old_dir, name), os.path.join(new_dir, name)
        if not (os.path.exists(p) and os.path.exists(q)):
            out.append(f"{name}: only in {'saved' if os.path.exists(p) else 'rebuild'}")
            continue
        x, y = imgio.read(p)[..., :3], imgio.read(q)[..., :3]
        if x.shape != y.shape:
            out.append(f"{name}: size {x.shape[:2]} → {y.shape[:2]}")
            continue
        d = np.abs(x - y)
        moved = float((d.max(axis=-1) > MAP_TOL).mean())
        if moved > 0:
            out.append(f"{name}: {moved:.3%} of texels moved more than 2/255 (max {d.max() * 255:.0f}/255)")
    return out


def compare(assets, stage, tolerance=8.0):
    """Zone luma of each piece against the first (the lead). A zone more than `tolerance` luma off
    reads as a different material next to its neighbour in a level."""
    rows = []
    for a in assets:
        rep = a.report(stage)
        if not rep:
            raise SystemExit(f"{a.slug}: '{stage}' has no check report — build it first")
        rows.append((a.slug, rep["metrics"].get("zone_luma", {})))
    zones = sorted({z for _, lum in rows for z in lum})
    lead = rows[0][1]
    print(f"{'asset':32}" + "".join(f"{z:>12}" for z in zones))
    off = []
    for slug, lum in rows:
        cells = []
        for z in zones:
            v = lum.get(z)
            flag = ""
            if v is not None and z in lead and abs(v - lead[z]) > tolerance:
                flag = "!"
                off.append(f"{slug} {z}: {v} vs lead {lead[z]}")
            cells.append(f"{'—' if v is None else v:>11}{flag or ' '}")
        print(f"{slug:32}" + "".join(cells))
    for o in off:
        print(f"OFF {o}")
    print(f"compare {stage}: {'CONSISTENT' if not off else 'INCONSISTENT'} (tolerance {tolerance} luma)")
    return not off

