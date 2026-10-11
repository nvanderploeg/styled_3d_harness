"""Regression guards: rebuild a stage without touching its outputs, diff against what was approved and
re-check it under the current spec, and compare zone metrics across the pieces of a set."""
import contextlib
import hashlib
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


# Per attribute data type: the property that holds a value, its component count, and the dtype to read it as.
VALUES = {"FLOAT": ("value", 1, np.float64), "INT": ("value", 1, np.int64), "INT8": ("value", 1, np.int64),
          "BOOLEAN": ("value", 1, bool), "FLOAT2": ("vector", 2, np.float64),
          "FLOAT_VECTOR": ("vector", 3, np.float64), "FLOAT_COLOR": ("color", 4, np.float64),
          "BYTE_COLOR": ("color", 4, np.float64), "INT16_2D": ("value", 2, np.int64),
          "INT32_2D": ("value", 2, np.int64), "QUATERNION": ("value", 4, np.float64),
          "FLOAT4X4": ("value", 16, np.float64)}


def _arr(coll, attr, n, dtype):
    out = np.empty(len(coll) * n, dtype)
    coll.foreach_get(attr, out)
    return out


def snapshot(a):
    """Everything a stage decides about the asset: the mesh's geometry, zones, seams, sharp edges, UVs, weights
    and every other attribute it carries; the armature's rest bones; and every action the file keeps."""
    if a.mesh is None:
        return {"mesh": None}
    me = a.mesh.data
    snap = {
        "co": _arr(me.vertices, "co", 3, np.float64),
        "loops": _arr(me.loops, "vertex_index", 1, np.int64),
        "starts": _arr(me.polygons, "loop_start", 1, np.int64),
        "zone": _arr(me.polygons, "material_index", 1, np.int64),
        "zones": [m.name for m in me.materials],
        "edges": np.sort(_arr(me.edges, "vertices", 2, np.int64).reshape(-1, 2), axis=1).ravel(),
        "seams": _arr(me.edges, "use_seam", 1, bool),
        "uv": _arr(me.uv_layers.active.data, "uv", 2, np.float64) if me.uv_layers else np.empty(0),
    }
    sharp = me.attributes.get("sharp_edge")
    snap["sharp"] = _arr(sharp.data, "value", 1, bool) if sharp else np.zeros(len(me.edges), bool)
    groups = {g.index: g.name for g in a.mesh.vertex_groups}
    snap["weights"] = sorted((v.index, groups[g.group], round(g.weight, 6)) for v in me.vertices for g in v.groups)
    attrs = sorted((at for at in me.attributes if not at.name.startswith(".") and at.name != "position"),
                   key=lambda at: at.name)
    snap["attributes"] = [(at.name, at.domain, at.data_type) for at in attrs]
    for at in attrs:
        prop, n, dtype = VALUES.get(at.data_type, (None, 0, None))
        snap[f"attribute {at.name}"] = _arr(at.data, prop, n, dtype) if prop else [d.value for d in at.data]
    bones = sorted(a.armature.data.bones, key=lambda b: b.name) if a.armature else []
    snap["bones"] = [(b.name, b.parent.name if b.parent else None, b.use_deform, b.use_connect) for b in bones]
    snap["bone rest"] = np.array([[*np.ravel(b.matrix_local), *b.tail_local] for b in bones], np.float64).ravel()
    for act in sorted((act for act in bpy.data.actions if act.users), key=lambda act: act.name):
        channels, keys = [], [np.array(act.frame_range, np.float64)]
        for slot, fc in _channels(act):
            kps = fc.keyframe_points
            channels.append((slot, fc.data_path, fc.array_index, [k.interpolation for k in kps]))
            keys += [_arr(kps, "co", 2, np.float64), _arr(kps, "handle_left", 2, np.float64),
                     _arr(kps, "handle_right", 2, np.float64)]
        snap[f"action {act.name}"] = channels
        snap[f"action {act.name} keys"] = np.concatenate(keys)
    return snap


def _channels(act):
    """(slot identifier, fcurve) for every fcurve of act, by slot, data path and index."""
    if act.is_action_layered:
        found = [(bag.slot.identifier, fc) for layer in act.layers for strip in layer.strips
                 for bag in strip.channelbags for fc in bag.fcurves]
    else:
        found = [("", fc) for fc in act.fcurves]
    return sorted(found, key=lambda c: (c[0], c[1].data_path, c[1].array_index))


def digest(snap):
    """Short hash of a snapshot, its floats rounded to 6 decimals, the precision MESH_TOL compares at."""
    h = hashlib.sha1()
    for k in sorted(snap):
        v = snap[k]
        if isinstance(v, np.ndarray):
            if v.dtype.kind == "f":
                v = np.round(v, 6) + 0.0
            v = f"{v.dtype}{v.shape}".encode() + np.ascontiguousarray(v).tobytes()
        else:
            v = json.dumps(v, default=repr).encode()
        h.update(k.encode() + b"\0" + v + b"\0")
    return h.hexdigest()[:12]


def against_approval(approval, new, saved=None):
    """How the snapshot new strays from an approval: [] when it hashes as approved, else its diff against saved
    (the stage's snapshot as built) or, with nothing to diff, the two hashes."""
    if digest(new) == approval["snapshot"]:
        return []
    found = diff_snapshots(saved, new) if saved is not None else []
    return found or [f"snapshot {digest(new)}, approved {approval['snapshot']} on {approval['at']}"]


def diff_snapshots(old, new):
    out = []
    for k in sorted(set(old) - set(new)) + sorted(set(new) - set(old)):
        out.append(f"{k}: only in {'saved' if k in old else 'rebuild'}")
    for k, v in old.items():
        if k not in new:
            continue
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


def has_maps(stage):
    return stage.startswith("texture") or stage == "bake"


@contextlib.contextmanager
def scratch_maps(a, stage):
    """Point a.textures(stage) at a scratch folder in the asset for the block, removed after it; yields the
    saved maps' folder and the scratch one."""
    tmp = tempfile.mkdtemp(prefix=f"verify_{stage}_", dir=a.path())
    saved = a.textures
    a.textures = lambda s: os.path.join(tmp, s) if s == stage else saved(s)
    try:
        yield saved(stage), a.textures(stage)
    finally:
        a.textures = saved
        shutil.rmtree(tmp, ignore_errors=True)


def verify(a, stage, run_stage):
    """Rebuild `stage` from its upstream .blend and script into a scratch folder in the asset and diff it
    against the saved stage and any approval. An IDENTICAL stage is checked again under the current spec and
    takes the rebuild's data inputs; True when it is identical and passes."""
    bpy.ops.wm.open_mainfile(filepath=a.blend(stage))
    old = snapshot(a)
    approval = a.approvals().get(stage)
    with scratch_maps(a, stage) as (saved_maps, new_maps):
        inputs = run_stage(a, stage)
        new = snapshot(a)
        problems = diff_snapshots(old, new)
        if approval and digest(new) != approval["snapshot"]:
            problems.append(f"against the approval of {approval['at']}: snapshot {digest(new)}, "
                            f"approved {approval['snapshot']}")
        if has_maps(stage):
            problems += diff_maps(saved_maps, new_maps, a.slug)
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
    rep["inputs"] = inputs
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

