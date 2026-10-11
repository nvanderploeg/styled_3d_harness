"""Fit every top of a block-out extract to a parametric shape, find the tops that are the same shape, and propose
the classes of cap modules that cover them within the plan's scale range.

    python3 shape_fit.py <extract.json> [--out fit.json] [--scale 0.85 1.15] [--grid 0.25] [--role gameplay]
        [--fit-tol 0.01] [--angle-tol 0.5] [--min-width 1.5] [--side-in 1.0] [--seed hex:10x5:flare ...]
        [--weld-snap 0.03]

Reads blockout_extract.py's json. A flat top is fitted from its outline's corners in its own frame:

- `rect(L, W)`, `hex(L, W)` (two parallel ends of W/2 joined by two points: a stretched hexagon), `pent(L, W)`
  (five corners with a mirror axis along L; `template` holds its corners in units of L and W, and `family` tells
  pents of different proportions apart), else `other` (a `weld` when it splits into two rectangles across the chord
  joining its only two reflex corners);
- a flat top narrower than --min-width is `small`: a marker or a frame member, not a cap;
- a sloped top is a `flow` when it is a rectangle in plan rising along L over `ramp` by `rise` and then running
  flat over `landing`, else a `slope`. Slopes and others are read with weld slivers (vertices and faces closer than
  --weld-snap) cleaned.

A fit's `residual_m` is the largest corner distance between the top and its fitted shape; past --fit-tol it is
`other`. `angle_deg` is L's direction, `centre` the shape's plan centre, `flare` the block-out's flare under the
top's edges (height, run, degrees) or null.

`same` lists the clusters of flat tops identical under rotation and mirror (corners within --fit-tol).

The cover proposes cap classes (L, W) for the fitted tops of each family: greedily the class that serves the most
tops within --scale on each axis, then sizes on the --grid, then exact block-out sizes, then the least scaling.
Seeds (`shape:LxW[:flare]`) are classes taken first. It runs twice: by shape alone (`cover.shape`), and with flared
and plain tops apart, a flared class keeping the members whose flare its height suits within --side-in
(`cover.shape_flare`).

Writes --out (default <extract>_fit.json beside the extract): `params`, `tops` (keyed `piece` or `piece#i`),
`same`, `flows` (groups of flows sharing ramp, rise and landing), `cover`. Prints the counts.
"""
import argparse
import itertools
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_geom as pg  # noqa: E402

SHORTFALL_MARGIN_M = 0.1


# ---------------------------------------------------------------- shapes


def template(shape, L, W, tpl=None):
    """The shape's outline, counter-clockwise, centred, L along +X."""
    if shape == "rect":
        return np.array([(L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2), (-L / 2, -W / 2)])
    if shape == "hex":
        return np.array([(L / 2, -W / 4), (L / 2, W / 4), (0, W / 2), (-L / 2, W / 4), (-L / 2, -W / 4), (0, -W / 2)])
    return np.array(tpl) * [L, W]


def fit_rect(cs, angle_tol):
    """(L, W, centre, angle) of a four-corner outline whose corners are square within angle_tol degrees, or None."""
    e = np.roll(cs, -1, axis=0) - cs
    lens = np.linalg.norm(e, axis=1)
    for i in range(4):
        cosang = np.dot(e[i], e[(i + 1) % 4]) / (lens[i] * lens[(i + 1) % 4])
        if abs(cosang) > math.sin(math.radians(angle_tol)):
            return None
    k = 0 if lens[0] >= lens[1] else 1
    L, W = (lens[0] + lens[2]) / 2, (lens[1] + lens[3]) / 2
    if k:
        L, W = W, L
    ax = e[k] / lens[k]
    return L, W, cs.mean(axis=0), math.atan2(ax[1], ax[0])


def fit_hex(cs, angle_tol):
    """(L, W, centre, angle) of a six-corner outline with two opposite edges square to the axis joining their
    midpoints, or None."""
    best = None
    e = np.roll(cs, -1, axis=0) - cs
    for k in range(3):
        m1 = (cs[k] + cs[(k + 1) % 6]) / 2
        m2 = (cs[k + 3] + cs[(k + 4) % 6]) / 2
        ax = m2 - m1
        L = np.linalg.norm(ax)
        ax = ax / L
        if abs(np.dot(e[k], ax)) / np.linalg.norm(e[k]) > math.sin(math.radians(angle_tol)):
            continue
        centre = (m1 + m2) / 2
        angle = math.atan2(ax[1], ax[0])
        loc = pg.to_local(cs, centre, angle)
        W = 2 * np.abs(loc[:, 1]).max()
        res = pg.match(loc, template("hex", L, W))
        if best is None or res < best[-1]:
            best = (L, W, centre, angle, res)
    return best[:-1] if best else None


def fit_pent(cs):
    """(L, W, centre, angle, template) of a five-corner outline about its most mirror-symmetric axis, the axis
    running from the base's midpoint to the opposite corner; template is the corners in units of L and W."""
    best = None
    for i in range(5):
        tip = cs[i]
        base = (cs[(i + 2) % 5] + cs[(i + 3) % 5]) / 2
        ax = (tip - base) / np.linalg.norm(tip - base)
        angle = math.atan2(ax[1], ax[0])
        loc = pg.to_local(cs, base, angle)
        res = pg.match(loc, loc * [1, -1])
        if best is None or res < best[0]:
            best = (res, angle, base, loc)
    _, angle, base, loc = best
    lo, hi = loc.min(axis=0), loc.max(axis=0)
    mid = (lo + hi) / 2
    L, W = hi[0] - lo[0], hi[1] - lo[1]
    centre = pg.to_world(mid[None], base, angle)[0]
    return L, W, centre, angle, (loc - mid) / [L, W]


def fit(cs, angle_tol):
    """(shape, L, W, centre, angle, template or None) of a corner outline, or None when no shape fits."""
    if len(cs) == 4:
        f = fit_rect(cs, angle_tol)
        return ("rect",) + f + (None,) if f else None
    if len(cs) == 6:
        f = fit_hex(cs, angle_tol)
        return ("hex",) + f + (None,) if f else None
    if len(cs) == 5:
        return ("pent",) + fit_pent(cs)
    return None


def residual(shape, cs, L, W, centre, angle, tpl):
    """Largest corner distance between the outline and the fitted shape; a pent against its mirror image."""
    if shape == "pent":
        loc = pg.to_local(cs, centre, angle)
        return pg.match(loc, loc * [1, -1])
    return pg.match(cs, pg.to_world(template(shape, L, W, tpl), centre, angle))


def turn(a, b, c):
    u, v = b - a, c - b
    return u[0] * v[1] - u[1] * v[0]


def split_weld(cs, angle_tol):
    """A welded outline's two rectangles, larger first, cut along the chord joining its only two reflex corners,
    each as (L, W, centre, angle); None when it is no such pair."""
    n = len(cs)
    reflex = [i for i in range(n) if turn(cs[i - 1], cs[i], cs[(i + 1) % n]) < 0]
    if len(reflex) != 2:
        return None
    i, j = reflex
    parts = []
    for part in ([cs[k % n] for k in range(j, i + n + 1)], [cs[k % n] for k in range(i, j + 1)]):
        pc = pg.corners(np.array(part))
        f = fit_rect(pc, angle_tol) if len(pc) == 4 else None
        if f is None:
            return None
        parts.append(f)
    return sorted(parts, key=lambda f: -f[0] * f[1])


# ---------------------------------------------------------------- flares, flows and slivers


def flare(p, top):
    """(height, run, degrees) of the block-out's flare under a flat top's edges, or None for a vertical band."""
    V = np.array(p["verts"], float)
    ol = top["outline"]
    edges = {frozenset(e) for e in zip(ol, ol[1:] + ol[:1])}
    found = []
    for f, kind in zip(p["faces"], p["kinds"]):
        if kind not in ("side", "under"):
            continue
        hit = [e for e in zip(f, f[1:] + f[:1]) if frozenset(e) in edges]
        if not hit:
            continue
        P = V[f] - V[f][0]
        n = sum(np.cross(a, b) for a, b in zip(P, np.roll(P, -1, axis=0)))
        if abs(n[2] / np.linalg.norm(n)) < 1e-3:
            continue
        a, b = hit[0]
        t = (V[b][:2] - V[a][:2]) / np.linalg.norm(V[b][:2] - V[a][:2])
        nn = np.array([t[1], -t[0]])
        low = [i for i in f if V[i][2] < top["z"] - 1e-4]
        h = top["z"] - min(V[i][2] for i in low)
        run = float(np.mean([abs(np.dot(V[i][:2] - V[a][:2], nn)) for i in low]))
        found.append((h, run))
    if not found:
        return None
    h = min(x[0] for x in found)
    run = float(np.mean([x[1] for x in found]))
    return h, run, math.degrees(math.atan2(h, run))


def _width(P):
    """A planar polygon's area over its longest edge: how wide it is across."""
    P = np.asarray(P, float)
    n = sum(np.cross(a, b) for a, b in zip(P, np.roll(P, -1, axis=0)))
    longest = max(np.linalg.norm(P[i] - P[i - 1]) for i in range(len(P)))
    return float(np.linalg.norm(n) / 2 / longest) if longest > 0 else 0.0


def clean_piece(p, snap):
    """The piece with its weld slivers gone: vertices within snap of one another become one (an outline vertex when
    one is among them), faces left with under three corners or narrower than snap dropped. Returns (piece, merged
    vertices, dropped faces), or None when two outline vertices lie within snap."""
    V = np.array(p["verts"], float)
    on_outline = {v for t in p["tops"] for v in t["outline"]}
    parent = list(range(len(V)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(V)):
        for j in range(i + 1, len(V)):
            if np.linalg.norm(V[i] - V[j]) < snap:
                a, b = find(i), find(j)
                if a == b:
                    continue
                if b in on_outline and a not in on_outline:
                    a, b = b, a
                if a in on_outline and b in on_outline:
                    return None
                parent[b] = a
    rep = [find(i) for i in range(len(V))]
    faces, kinds, remap, dropped = [], [], {}, []
    for fi, (f, k) in enumerate(zip(p["faces"], p["kinds"])):
        g = []
        for v in f:
            if not g or g[-1] != rep[v]:
                g.append(rep[v])
        while len(g) > 1 and g[0] == g[-1]:
            g.pop()
        if len(set(g)) < 3 or _width(V[g]) < snap:
            dropped.append(fi)
            continue
        remap[fi] = len(faces)
        faces.append(g)
        kinds.append(k)
    tops = [{**t, "faces": [remap[f] for f in t["faces"] if f in remap],
             "ring_faces": [remap[f] for f in t["ring_faces"] if f in remap],
             "lips": [{**lip, "face": remap[lip["face"]]} for lip in t["lips"] if lip["face"] in remap]}
            for t in p["tops"]]
    merged = sum(1 for i, r in enumerate(rep) if r != i)
    return {**p, "faces": faces, "kinds": kinds, "tops": tops}, merged, dropped


def fit_flow(p, top, fit_tol, angle_tol):
    """A sloped top as a flow: a rect L x W in plan whose top rises along L from its low end over `ramp` by `rise`,
    then runs flat over `landing`; +x of its frame runs uphill. None when the top is no such ramp and landing
    within fit_tol."""
    V = np.array(p["verts"], float)
    P3 = V[top["outline"]]
    cs = pg.corners(P3[:, :2])
    f = fit_rect(cs, angle_tol) if len(cs) == 4 else None
    if f is None:
        return None
    L, W, centre, angle = f
    loc = pg.to_local(P3[:, :2], centre, angle)
    if P3[loc[:, 0] < 0, 2].mean() > P3[loc[:, 0] > 0, 2].mean():
        angle += math.pi
        loc = -loc
    z_low, z_high = float(P3[:, 2].min()), float(P3[:, 2].max())
    xc = float(loc[P3[:, 2] > z_high - 1e-3, 0].min())
    ramp = xc + L / 2

    def profile(x, y):
        u = pg.to_local(np.array([[x, y]]), centre, angle)[0, 0]
        return z_low + (z_high - z_low) * min(max((u + L / 2) / ramp, 0.0), 1.0)

    on_top = sorted({v for fi in top["faces"] for v in p["faces"][fi]})
    res = max(abs(profile(*V[v][:2]) - V[v][2]) for v in on_top)
    if res > fit_tol:
        return None
    return {"L": L, "W": W, "centre": centre, "angle": angle, "z_low": z_low, "rise": z_high - z_low,
            "ramp": ramp, "landing": L / 2 - xc, "residual": res}


# ---------------------------------------------------------------- same shapes and the cover


def same_shape(a, b, tol):
    """Whether two corner outlines are one shape under rotation and mirror, every corner within tol."""
    if len(a) != len(b):
        return False
    A = a - a.mean(axis=0)
    for B in (b - b.mean(axis=0), (b - b.mean(axis=0)) * [-1, 1]):
        for k in range(len(B)):
            ang = math.atan2(B[k][1], B[k][0]) - math.atan2(A[0][1], A[0][0])
            if pg.match(pg.to_world(A, np.zeros(2), ang), B) <= tol:
                return True
    return False


def same_clusters(tops, tol):
    """Clusters (two or more keys) of flat tops whose outlines are one shape."""
    groups = []
    for t in tops:
        for g in groups:
            if same_shape(g[0]["cs"], t["cs"], tol):
                g.append(t)
                break
        else:
            groups.append([t])
    return [[t["key"] for t in g] for g in groups if len(g) > 1]


def covers(base, t, lo, hi):
    """Whether a class of size base serves top t: t's L and W each within [lo, hi] times base's."""
    return (lo - 1e-6 <= t["L"] / base[0] <= hi + 1e-6) and (lo - 1e-6 <= t["W"] / base[1] <= hi + 1e-6)


def flare_group(members, side_in):
    """The flare height that keeps the most members, and those members: a class flare may be shorter than a
    member's block-out flare, never taller, and the art stays within side_in less SHORTFALL_MARGIN_M of the
    block-out's flare. On a tie the taller flare wins: it sits closer to every member's own."""
    best = (0, None, [])
    for hc in sorted({t["flare"]["h"] for t in members}, reverse=True):
        keep = [t for t in members if t["flare"]["h"] >= hc - 1e-6 and
                (t["flare"]["h"] - hc) / math.tan(math.radians(t["flare"]["deg"])) <= side_in - SHORTFALL_MARGIN_M]
        if len(keep) > best[0]:
            best = (len(keep), hc, keep)
    return best[1], best[2]


def cover(tops, lo, hi, grid, seeds, side_in=None):
    """Classes (family, flared, L, W, flare h, members) every member lies within [lo, hi] of on each axis. With
    side_in, flared and plain tops never share a class and a flared class keeps the members its flare suits."""
    split = side_in is not None

    def flared(t):
        return split and t["flare"] is not None

    def take(is_flared, cand, pool):
        hc, members = flare_group(pool, side_in) if is_flared else (None, pool)
        exact = sum(1 for t in members if abs(t["L"] - cand[0]) < 1e-3 and abs(t["W"] - cand[1]) < 1e-3)
        dev = sum(abs(math.log(t["L"] / cand[0])) + abs(math.log(t["W"] / cand[1])) for t in members)
        return members, hc, exact, dev

    classes, left = [], list(tops)
    for family, want_flare, L0, W0 in seeds:
        pool = [t for t in left if t["family"] == family and flared(t) == (want_flare and split)
                and covers((L0, W0), t, lo, hi)]
        if pool:
            members, hc, _, _ = take(want_flare and split, (L0, W0), pool)
            classes.append({"family": family, "flared": want_flare and split, "L": L0, "W": W0, "h": hc,
                            "members": members})
            left = [t for t in left if t not in members]
    while left:
        best = None
        for (family, is_flared), group in itertools.groupby(
                sorted(left, key=lambda t: (t["family"], not flared(t))), key=lambda t: (t["family"], flared(t))):
            group = list(group)
            shape = group[0]["shape"]
            Ls, Ws = [t["L"] for t in group], [t["W"] for t in group]
            cands = {(t["L"], t["W"]) for t in group}
            for L0 in np.arange(math.floor(min(Ls) * lo / grid) * grid, max(Ls) * hi + grid, grid):
                for W0 in np.arange(math.floor(min(Ws) * lo / grid) * grid, max(Ws) * hi + grid, grid):
                    if L0 >= W0 - 1e-9 or shape == "pent":
                        cands.add((round(float(L0), 2), round(float(W0), 2)))
            for cand in sorted(cands):
                pool = [t for t in group if covers(cand, t, lo, hi)]
                if not pool:
                    continue
                members, hc, exact, dev = take(is_flared, cand, pool)
                on_grid = all(abs(x / grid - round(x / grid)) < 1e-6 for x in cand)
                key = (len(members), on_grid, exact, -dev)
                if best is None or key > best[0]:
                    best = (key, {"family": family, "flared": is_flared, "L": cand[0], "W": cand[1], "h": hc,
                                  "members": members})
        classes.append(best[1])
        left = [t for t in left if t not in best[1]["members"]]
    return classes


def size_name(x):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", "p")


def class_rows(classes):
    """The classes as json rows, named family_LxW[_flare], with each member's plan scale (L, W)."""
    out = []
    for c in classes:
        name = f"{c['family']}_{size_name(c['L'])}x{size_name(c['W'])}{'_flare' if c['flared'] else ''}"
        out.append({"name": name, "family": c["family"], "L": c["L"], "W": c["W"], "flared": c["flared"],
                    "flare_h": None if c["h"] is None else round(c["h"], 4),
                    "members": sorted(t["key"] for t in c["members"]),
                    "scales": {t["key"]: [round(t["L"] / c["L"], 4), round(t["W"] / c["W"], 4)]
                               for t in sorted(c["members"], key=lambda t: t["key"])}})
    return out


# ---------------------------------------------------------------- per top


def r(x, n=4):
    return round(float(x), n)


def cleaned(p, snap):
    """The piece with its weld slivers cleaned, or as it is when cleaning would merge two outline vertices."""
    c = clean_piece(p, snap)
    return c[0] if c else p


def fit_top(name, ti, p, t, a):
    """One top's record. `cs`, its plan corners, feeds the same-shape clusters and stays out of the json."""
    key = f"{name}#{ti}" if len(p["tops"]) > 1 else name
    rec = {"key": key, "piece": name, "top": ti, "corridor": p.get("corridor"), "z": t["z"], "flat": t["flat"]}
    V = np.array(p["verts"], float)
    if not t["flat"]:
        q = cleaned(p, a.weld_snap)
        fl = fit_flow(q, q["tops"][ti], a.fit_tol, a.angle_tol)
        if fl is None:
            return {**rec, "shape": "slope", "status": "slope"}
        return {**rec, "shape": "flow", "status": "flow", "L": r(fl["L"]), "W": r(fl["W"]),
                "centre": [r(c) for c in fl["centre"]],
                "angle_deg": r((math.degrees(fl["angle"]) + 180.0) % 360.0 - 180.0, 3),
                "residual_m": r(fl["residual"], 5), "flow": {"ramp": r(fl["ramp"]), "rise": r(fl["rise"]),
                                                             "landing": r(fl["landing"]), "z_low": r(fl["z_low"])}}
    cs = pg.corners(V[t["outline"]][:, :2])
    rec["corners"] = len(cs)
    f = fit(cs, a.angle_tol)
    res = residual(f[0], cs, *f[1:]) if f else None
    if f is None or res > a.fit_tol:
        q = cleaned(p, a.weld_snap)
        qcs = pg.corners(np.array(q["verts"], float)[q["tops"][ti]["outline"]][:, :2])
        parts = split_weld(qcs, a.angle_tol)
        why = (f"{len(cs)}-corner outline fits no rect, hex or pent" if f is None
               else f"{f[0]} fit leaves {res:.3f} m (tolerance {a.fit_tol})")
        out = {**rec, "shape": "weld" if parts else "other", "status": "other", "why": why, "cs": cs}
        if parts:
            out["weld"] = [{"L": r(L), "W": r(W), "centre": [r(c) for c in ctr], "angle_deg": r(math.degrees(an), 3)}
                           for L, W, ctr, an in parts]
        return out
    shape, L, W, centre, angle, tpl = f
    if shape in ("rect", "hex"):
        angle = (angle + math.pi / 2) % math.pi - math.pi / 2
    fl = flare(p, t)
    out = {**rec, "shape": shape, "family": shape, "status": "fit", "L": float(L), "W": float(W),
           "centre": [r(c) for c in centre], "angle_deg": r(math.degrees(angle), 3), "residual_m": r(res, 5),
           "flare": None if fl is None else {"h": fl[0], "run": fl[1], "deg": fl[2]}, "cs": cs}
    if tpl is not None:
        out["template"] = [[r(u, 6), r(v, 6)] for u, v in tpl]
    if min(L, W) < a.min_width:
        out.update(status="small", why=f"{L:.2f} x {W:.2f} m: narrower than {a.min_width} m")
    return out


def pent_families(tops, tol):
    """Name each pent's family by its template: pents whose templates at their own size match within tol share one."""
    seen = []
    for t in tops:
        if t.get("shape") != "pent":
            continue
        for k, tpl in enumerate(seen):
            if pg.match(np.array(tpl) * [t["L"], t["W"]], np.array(t["template"]) * [t["L"], t["W"]]) <= tol:
                t["family"] = "pent" if k == 0 else f"pent{k + 1}"
                break
        else:
            seen.append(t["template"])
            t["family"] = "pent" if len(seen) == 1 else f"pent{len(seen)}"


def parse_seed(s):
    """'hex:10x5[:flare]' as (family, flared, L, W)."""
    bits = s.split(":")
    L, W = (float(x) for x in bits[1].split("x"))
    return bits[0], len(bits) > 2 and bits[2] == "flare", L, W


def summary(tops, same, flows, covers_):
    """The printed counts, one line each."""
    flat = [t for t in tops if t["flat"]]
    by = {}
    for t in flat:
        by[t["shape"]] = by.get(t["shape"], 0) + 1
    small = [t["key"] for t in tops if t["status"] == "small"]
    fitted = [t for t in tops if t["status"] == "fit"]
    slopes = [t for t in tops if not t["flat"]]
    lines = [f"{len(flat)} flat tops: " + ", ".join(f"{by[s]} {s}" for s in ("rect", "hex", "pent", "weld", "other")
                                                    if s in by)
             + (f" ({len(small)} narrower than the minimum width: {', '.join(small)})" if small else "")
             + f"; {len(slopes)} slopes ({sum(1 for t in slopes if t['shape'] == 'flow')} flows in "
             f"{len(flows)} ramp/rise/landing groups)"]
    lines.append(f"{len(same)} clusters of identical tops (rotation, mirror): "
                 + "; ".join("/".join(c) for c in same))
    for mode, rows in covers_.items():
        single = sum(1 for c in rows if len(c["members"]) == 1)
        lines.append(f"cover by {mode.replace('_', ' + ')}: {len(rows)} classes cover {len(fitted)} tops, "
                     f"{single} singletons")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("extract")
    ap.add_argument("--out")
    ap.add_argument("--scale", nargs=2, type=float, default=[0.85, 1.15])
    ap.add_argument("--grid", type=float, default=0.25)
    ap.add_argument("--role", default="gameplay")
    ap.add_argument("--fit-tol", type=float, default=0.01)
    ap.add_argument("--angle-tol", type=float, default=0.5)
    ap.add_argument("--min-width", type=float, default=1.5)
    ap.add_argument("--side-in", type=float, default=1.0)
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--weld-snap", type=float, default=0.03)
    a = ap.parse_args(argv)
    out = a.out or os.path.splitext(a.extract)[0] + "_fit.json"
    data = pg.load(a.extract)
    tops = [fit_top(name, ti, p, t, a) for name, p in pg.pieces(data, a.role).items() for ti, t in enumerate(p["tops"])]
    pent_families(tops, a.fit_tol)
    same = same_clusters([t for t in tops if t["flat"]], a.fit_tol)
    fitted = [t for t in tops if t["status"] == "fit"]
    seeds = [parse_seed(s) for s in a.seed]
    lo, hi = a.scale
    covers_ = {"shape": class_rows(cover(fitted, lo, hi, a.grid, seeds)),
               "shape_flare": class_rows(cover(fitted, lo, hi, a.grid, seeds, a.side_in))}
    groups = {}
    for t in tops:
        if t["shape"] == "flow":
            k = (round(t["flow"]["ramp"], 2), round(t["flow"]["rise"], 2), round(t["flow"]["landing"], 2))
            groups.setdefault(k, []).append(t["key"])
    flows = [{"ramp": k[0], "rise": k[1], "landing": k[2], "members": v} for k, v in sorted(groups.items())]
    rows = []
    for t in tops:
        row = {k: v for k, v in t.items() if k != "cs"}
        if "L" in row:
            row["L"], row["W"] = r(row["L"]), r(row["W"])
        if row.get("flare"):
            row["flare"] = {k: r(v) for k, v in row["flare"].items()}
        rows.append(row)
    result = {"source": a.extract,
              "params": {"scale": [lo, hi], "grid": a.grid, "role": a.role, "fit_tol": a.fit_tol,
                         "angle_tol": a.angle_tol, "min_width": a.min_width, "side_in": a.side_in, "seeds": a.seed,
                         "weld_snap": a.weld_snap},
              "tops": {t["key"]: t for t in rows}, "same": same, "flows": flows, "cover": covers_}
    with open(out, "w") as f:
        json.dump(result, f, indent=1)
    for ln in summary(tops, same, flows, covers_):
        print(ln)
    for mode, rows_ in covers_.items():
        print(f"classes ({mode.replace('_', ' + ')}):")
        for c in rows_:
            print(f"  {c['name']:22} {len(c['members']):2}  {', '.join(c['members'])}")
    print(f"-> {out}")
    return result


if __name__ == "__main__":
    main()
