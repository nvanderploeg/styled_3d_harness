"""The routes a level's additions are measured against: every route top, its lips, the jumps they pair into, each
jump's gap corridor and flight envelope, and the reach around the tops. Importable (class Routes) and a CLI.

    python3 routes.py <extract.json> [--out routes.json] [--map map.png] [--world-guide <*_art.md> ...]
        [--lip-colours blue=D1,cyan=D2,green=D3,orange=D4] [--role gameplay] [--start <piece>]
        [--gap-clear-m 2] [--approach-m 15] [--reach-m 12.5] [--reach-up-m 3] [--walkable-deg 57]
        [--min-top-m2 1] [--min-width-m 1.2] [--pair-m 16] [--shared-pair-m 13] [--facing 0.2] [--px-per-m 4]

Reads blockout_extract.py's json (the pieces of --role). The rule values come, lowest priority first, from the
defaults above, the `shape` and `scale` blocks of each --world-guide (alias --guide) in the order given (world,
zone, set: a lower guide overrides), then any flag given.

A top under min_top_m2, or narrower than min_width_m (4 x area / perimeter), is a marker or a frame member, not a
landing: it is left out. Two lips pair into a jump when they face each other (each one's outward normal within
acos(facing) of the line between them) no further apart than pair_m, same colour first, best facing first; then a
leftover lip pairs with its best facing partner of any colour within shared_pair_m, since a landing edge shared by
two jumps carries the harder one's colour. A jump runs from the top nearer --start (in jumps; the lower top when
--start is not a piece or the tops are as near) to the other. Its gap corridor is the hull of its two lip edges,
its envelope that hull carried approach_m both ways along the jump, each kept clear by gap_clear_m.

Writes --out (default <extract>_routes.json beside the extract): `source`, `params` (every rule value, walkable_deg
among them though pairing never reads it), `lip_colours`, `start`, `tops` (`id` piece#i, `piece`, `corridor`, `z`,
`zmin`, `flat`, `outline` [x, y] counter-clockwise), `left_out` (id, area_m2, width_m), `lips` (`top`, `colour`,
`difficulty`, edge ends `a`, `b` [x, y, z], `mid`, outward normal `n`, `z`), `jumps` (`name` from->to, `from`, `to`
top ids, `lips` [take-off, landing] indices into lips, `gap_m`, `difficulty`, `corridors`, `gap` and `envelope`
polygons, `clear_m`, `z`) and `unpaired` lip indices. --map draws the top view to a PNG: reach band, envelopes, gap
corridors, tops by corridor, lips in their colours, jump lines from take-off (dot) to landing, unpaired lips ringed
white. Prints the jumps per corridor (gap, height change, difficulty, lip colours), unpaired lips and left-out tops.
"""
import argparse
import json
import math
import os
import re
import struct
import sys
import zlib
from collections import deque

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import plan_geom as pg  # noqa: E402

PARAMS = {"gap_clear_m": 2.0, "approach_m": 15.0, "reach_m": 12.5, "reach_up_m": 3.0, "walkable_deg": 57.0,
          "min_top_m2": 1.0, "min_width_m": 1.2, "pair_m": 16.0, "shared_pair_m": 13.0, "facing": 0.2}
# Where each rule lives in the art guides' json blocks.
GUIDE_KEYS = {"gap_clear_m": "shape", "approach_m": "shape", "walkable_deg": "shape", "reach_m": "scale",
              "reach_up_m": "scale"}
LIP_COLOURS = "blue=D1,cyan=D2,green=D3,orange=D4"
BLOCK = re.compile(r"^```json[ \t]*\n(.*?)^```", re.M | re.S)


def guide_rules(paths):
    """The json blocks of the guides, each guide's keys over the one before it."""
    rules = {}

    def merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                merge(dst[k], v)
            else:
                dst[k] = v

    for path in paths:
        with open(path) as f:
            text = f.read()
        for m in BLOCK.finditer(text):
            merge(rules, json.loads(m.group(1)))
    return rules


def params_from(guides, overrides):
    """The rule values: defaults, then the guides' shape/scale blocks, then the overrides that are not None."""
    out = dict(PARAMS)
    rules = guide_rules(guides)
    for k, block in GUIDE_KEYS.items():
        if k in rules.get(block, {}):
            out[k] = float(rules[block][k])
    out.update({k: float(v) for k, v in overrides.items() if v is not None})
    return out


def colour_map(s):
    """'blue=D1,cyan=D2' as {colour: difficulty}."""
    return dict(item.split("=", 1) for item in s.split(",") if item)


class Routes:
    """Route tops, lips, jumps, gap corridors and envelopes of one block-out extract. data is the extract (a dict
    or its path); params override PARAMS; lip_colours maps a lip colour to its difficulty; start is the piece the
    jumps run away from (None: each jump runs from its lower top)."""

    def __init__(self, data, lip_colours=None, role="gameplay", start=None, **params):
        if isinstance(data, str):
            data = pg.load(data)
        self.p = {**PARAMS, **params}
        self.lip_colours = colour_map(LIP_COLOURS) if lip_colours is None else dict(lip_colours)
        self.pieces = pg.pieces(data, role)
        self.tops, self.lips, self.left_out = [], [], []
        for name, piece in self.pieces.items():
            V = np.array(piece["verts"], float)
            for ti, top in enumerate(piece["tops"]):
                ring = V[top["outline"]]
                a = abs(pg.area2(ring[:, :2]))
                perimeter = float(np.linalg.norm(np.roll(ring[:, :2], -1, axis=0) - ring[:, :2], axis=1).sum())
                tid = f"{name}#{ti}"
                if a < self.p["min_top_m2"] or 4 * a / perimeter < self.p["min_width_m"]:
                    self.left_out.append({"id": tid, "piece": name, "z": top["z"], "area_m2": round(a, 3),
                                          "width_m": round(4 * a / perimeter, 3)})
                    continue
                self.tops.append({"id": tid, "piece": name, "corridor": piece["corridor"],
                                  "z": float(ring[:, 2].max()), "zmin": float(ring[:, 2].min()),
                                  "outline": pg.ccw(ring[:, :2]), "flat": top["flat"]})
                self._lips(tid, piece, top, V, ring)
        self.jumps = self._pair()
        self._orient(start)
        corridor = {t["id"]: t["corridor"] for t in self.tops}
        for j in self.jumps:
            A, B = self.lips[j["lips"][0]], self.lips[j["lips"][1]]
            pts = np.array([A["a"], A["b"], B["a"], B["b"]])[:, :2]
            d = B["mid"] - A["mid"]
            d = d / np.linalg.norm(d)
            j["gap"] = pg.hull(pts)
            j["envelope"] = pg.hull(np.concatenate([pts - self.p["approach_m"] * d, pts + self.p["approach_m"] * d]))
            j["clear_m"] = self.p["gap_clear_m"]
            j["z"] = max(A["z"], B["z"])
            j["corridors"] = sorted({corridor[j["from"]], corridor[j["to"]]} - {None})

    def _lips(self, tid, piece, top, V, ring):
        ol = top["outline"]
        edges = {frozenset((ol[k - 1], ol[k])): (ol[k - 1], ol[k]) for k in range(len(ol))}
        c = ring[:, :2].mean(axis=0)
        for lip in top["lips"]:
            f = piece["faces"][lip["face"]]
            for k in range(len(f)):
                e = frozenset((f[k - 1], f[k]))
                if e not in edges:
                    continue
                a, b = (V[i] for i in edges[e])
                mid = (a[:2] + b[:2]) / 2
                t = b[:2] - a[:2]
                n = np.array([t[1], -t[0]]) / np.linalg.norm(t)
                if n @ (mid - c) < 0:
                    n = -n
                self.lips.append({"top": tid, "colour": lip["colour"],
                                  "difficulty": self.lip_colours.get(lip["colour"]),
                                  "a": a, "b": b, "mid": mid, "n": n, "z": float(max(a[2], b[2]))})

    def _facing(self, i, j, limit):
        """(score, distance) when lips i and j face each other within limit, else None; lower scores face better."""
        a, b = self.lips[i], self.lips[j]
        if a["top"] == b["top"]:
            return None
        d = b["mid"] - a["mid"]
        dist = float(np.linalg.norm(d))
        if dist > limit or dist < 0.5:
            return None
        fa, fb = float(a["n"] @ d) / dist, -float(b["n"] @ d) / dist
        if fa < self.p["facing"] or fb < self.p["facing"]:
            return None
        return dist / (fa * fb), dist

    def _pair(self):
        """Lips into jumps: facing pairs of one colour, best first; then a leftover lip with its best facing
        partner of any colour."""
        cands = []
        for i in range(len(self.lips)):
            for j in range(i + 1, len(self.lips)):
                if self.lips[i]["colour"] != self.lips[j]["colour"]:
                    continue
                f = self._facing(i, j, self.p["pair_m"])
                if f:
                    cands.append((f[0], f[1], i, j))
        used, jumps = set(), []
        for _, dist, i, j in sorted(cands):
            if i in used or j in used:
                continue
            used.update((i, j))
            jumps.append({"lips": [i, j], "gap_m": dist})
        for i in [k for k in range(len(self.lips)) if k not in used]:
            best = None
            for j in range(len(self.lips)):
                f = self._facing(i, j, self.p["shared_pair_m"])
                if f and (best is None or f[0] < best[0]):
                    best = (f[0], f[1], j)
            if best:
                used.update((i, best[2]))
                jumps.append({"lips": [i, best[2]], "gap_m": best[1]})
        for j in jumps:
            A = self.lips[j["lips"][0]]
            j["difficulty"] = A["difficulty"]
        self.unpaired = [i for i in range(len(self.lips)) if i not in used]
        return jumps

    def _orient(self, start):
        """Put each jump's take-off lip first: from the top nearer start in jumps, else from the lower top."""
        tops = {t["id"]: t for t in self.tops}
        hops = {}
        for j in self.jumps:
            for k in (0, 1):
                hops.setdefault(self.lips[j["lips"][k]]["top"], set()).add(self.lips[j["lips"][1 - k]]["top"])
        seeds = [t["id"] for t in self.tops if t["piece"] == start]
        dist = {s: 0 for s in seeds}
        queue = deque(seeds)
        while queue:
            u = queue.popleft()
            for v in hops.get(u, ()):
                if v not in dist:
                    dist[v] = dist[u] + 1
                    queue.append(v)
        self.start = seeds[0] if seeds else None
        for j in self.jumps:
            a, b = (self.lips[i]["top"] for i in j["lips"])
            key_a = (dist.get(a, math.inf), tops[a]["z"])
            key_b = (dist.get(b, math.inf), tops[b]["z"])
            if key_b < key_a:
                j["lips"] = j["lips"][::-1]
            j["from"], j["to"] = (self.lips[i]["top"] for i in j["lips"])
            j["name"] = f"{j['from']}->{j['to']}"

    # ------------------------------------------------------------ queries

    def plan_dist(self, pts):
        """Per point: plan distance to every route top, as an array (points x tops); 0 inside a top."""
        pts = np.atleast_2d(np.asarray(pts, float))
        return np.stack([np.maximum(pg.signed_dist(pts[:, :2], t["outline"]), 0.0) for t in self.tops], axis=1)

    def reach(self, pts):
        """Per point (x, y, z): the reaching tops' mask, a top reaching a point within reach_m of it in plan and
        no more than reach_up_m below it."""
        pts = np.atleast_2d(np.asarray(pts, float))
        D = self.plan_dist(pts)
        Z = np.array([t["z"] for t in self.tops])
        return (D <= self.p["reach_m"]) & (pts[:, 2:3] <= Z[None] + self.p["reach_up_m"])

    def in_reach(self, pts):
        return self.reach(pts).any(axis=1)

    def gap_dist(self, pts):
        """Per point: plan distance outside the nearest gap corridor less its clearance (<= 0: inside)."""
        pts = np.atleast_2d(np.asarray(pts, float))[:, :2]
        return np.min(np.stack([pg.signed_dist(pts, j["gap"]) - j["clear_m"] for j in self.jumps], 1), axis=1)

    def envelope_dist(self, pts):
        """Per point: plan distance outside the nearest flight envelope less its clearance (<= 0: inside)."""
        pts = np.atleast_2d(np.asarray(pts, float))[:, :2]
        return np.min(np.stack([pg.signed_dist(pts, j["envelope"]) - j["clear_m"] for j in self.jumps], 1), axis=1)

    def nearest(self, pts):
        """(distance, top id) of the nearest route top in plan to any of the points."""
        D = self.plan_dist(pts)
        i, k = np.unravel_index(np.argmin(D), D.shape)
        return float(D[i, k]), self.tops[k]["id"]

    # ------------------------------------------------------------ output

    def as_json(self, source):
        def r(v):
            return [round(float(x), 4) for x in v]

        return {"source": source, "params": self.p, "lip_colours": self.lip_colours, "start": self.start,
                "tops": [{**t, "outline": [r(p) for p in t["outline"]]} for t in self.tops],
                "left_out": self.left_out,
                "lips": [{**lip, "a": r(lip["a"]), "b": r(lip["b"]), "mid": r(lip["mid"]), "n": r(lip["n"])}
                         for lip in self.lips],
                "jumps": [{**j, "gap_m": round(j["gap_m"], 3), "gap": [r(p) for p in j["gap"]],
                           "envelope": [r(p) for p in j["envelope"]]} for j in self.jumps],
                "unpaired": self.unpaired}


# ---------------------------------------------------------------- the map

CORRIDOR_RGB = [(0.73, 0.54, 0.42), (0.42, 0.55, 0.75), (0.66, 0.45, 0.66), (0.55, 0.7, 0.45), (0.8, 0.75, 0.45)]
NAMED_RGB = {"blue": (0.1, 0.35, 1.0), "cyan": (0.0, 0.85, 0.95), "green": (0.15, 0.85, 0.15),
             "orange": (1.0, 0.55, 0.0), "yellow": (1.0, 0.85, 0.1), "red": (1.0, 0.2, 0.2),
             "magenta": (1.0, 0.2, 1.0), "white": (1.0, 1.0, 1.0)}


class Canvas:
    """An RGB float image over a plan rectangle, +y up, painted with numpy."""

    def __init__(self, lo, hi, px_per_m, rgb):
        self.lo, self.s = np.asarray(lo, float), px_per_m
        self.w = int(math.ceil((hi[0] - lo[0]) * px_per_m))
        self.h = int(math.ceil((hi[1] - lo[1]) * px_per_m))
        self.img = np.ones((self.h, self.w, 3)) * rgb
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        self.xy = np.stack([lo[0] + (xs + 0.5) / px_per_m, hi[1] - (ys + 0.5) / px_per_m], axis=-1)

    def _window(self, P, pad):
        x0 = max(int((P[:, 0].min() - pad - self.lo[0]) * self.s), 0)
        x1 = min(int((P[:, 0].max() + pad - self.lo[0]) * self.s) + 2, self.w)
        top = self.lo[1] + self.h / self.s
        y0 = max(int((top - P[:, 1].max() - pad) * self.s), 0)
        y1 = min(int((top - P[:, 1].min() + pad) * self.s) + 2, self.h)
        return slice(y0, y1), slice(x0, x1)

    def mask(self, P, pad=0.0, fn=None):
        """(window, mask) of the pixels within pad of polygon P (inside it when pad is 0); fn replaces the test."""
        win = self._window(np.asarray(P, float), pad)
        pts = self.xy[win].reshape(-1, 2)
        d = pg.signed_dist(pts, P) if fn is None else fn(pts)
        return win, (d <= pad).reshape(self.xy[win].shape[:2])

    def paint(self, win, m, rgb, alpha=1.0):
        sub = self.img[win]
        sub[m] = sub[m] * (1 - alpha) + np.asarray(rgb) * alpha

    def poly(self, P, rgb, alpha=1.0, pad=0.0):
        win, m = self.mask(P, pad)
        self.paint(win, m, rgb, alpha)

    def line(self, a, b, rgb, width_m):
        a, b = np.asarray(a, float)[:2], np.asarray(b, float)[:2]
        win, m = self.mask(np.array([a, b]), width_m / 2, lambda pts: pg.seg_dist(pts, a, b))
        self.paint(win, m, rgb)

    def disc(self, c, r, rgb):
        c = np.asarray(c, float)[:2]
        win, m = self.mask(np.array([c, c]), r, lambda pts: np.linalg.norm(pts - c, axis=1))
        self.paint(win, m, rgb)

    def save(self, path):
        write_png(path, self.img)


def write_png(path, img):
    """An (h, w, 3) float image in 0-1 as an 8-bit RGB PNG."""
    a = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    raw = b"".join(b"\x00" + row.tobytes() for row in a)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", a.shape[1], a.shape[0], 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def draw_map(rt, path, px_per_m=4.0, palette=None):
    """The routes' top view as a PNG."""
    named = {**NAMED_RGB, **(palette or {})}
    outlines = np.vstack([t["outline"] for t in rt.tops])
    margin = rt.p["reach_m"] + 4.0
    cv = Canvas(outlines.min(axis=0) - margin, outlines.max(axis=0) + margin, px_per_m, (0.11, 0.2, 0.25))
    for t in rt.tops:
        cv.poly(t["outline"], (0.2, 0.3, 0.34), pad=rt.p["reach_m"])
    for j in rt.jumps:
        cv.poly(j["envelope"], (1.0, 0.35, 0.29), 0.18)
    for j in rt.jumps:
        cv.poly(j["gap"], (0.91, 0.2, 0.16), 0.5)
    corridors = sorted({t["corridor"] for t in rt.tops if t["corridor"]})
    for t in rt.tops:
        k = corridors.index(t["corridor"]) if t["corridor"] in corridors else -1
        rgb = CORRIDOR_RGB[k % len(CORRIDOR_RGB)] if k >= 0 else (0.6, 0.6, 0.6)
        cv.poly(t["outline"], (0.94, 0.9, 0.82), pad=0.25)
        cv.poly(t["outline"], rgb if t["flat"] else tuple(0.8 * c for c in rgb))
    for i, lip in enumerate(rt.lips):
        if i in rt.unpaired:
            cv.line(lip["a"], lip["b"], (1, 1, 1), 1.6)
        cv.line(lip["a"], lip["b"], named.get(lip["colour"], (1, 1, 1)), 0.7)
    for j in rt.jumps:
        A, B = rt.lips[j["lips"][0]], rt.lips[j["lips"][1]]
        cv.line(A["mid"], B["mid"], (0.05, 0.05, 0.05), 0.25)
        cv.disc(A["mid"], 0.5, (0.05, 0.05, 0.05))
    cv.save(path)
    return cv.w, cv.h


# ---------------------------------------------------------------- CLI


def summary(rt):
    lines = [f"{len(rt.tops)} route tops, {len(rt.lips)} lips, {len(rt.jumps)} jumps, {len(rt.unpaired)} unpaired"
             + (f"; jumps run from {rt.start}" if rt.start else "; no start piece: jumps run from the lower top")]
    by = {}
    for j in rt.jumps:
        by.setdefault(" / ".join(j["corridors"]) or "-", []).append(j)
    for c, js in sorted(by.items()):
        lines.append(f"{c}: {len(js)} jumps")
        for j in sorted(js, key=lambda j: (rt.lips[j["lips"][0]]["z"], j["name"])):
            A, B = rt.lips[j["lips"][0]], rt.lips[j["lips"][1]]
            colours = A["colour"] if A["colour"] == B["colour"] else f"{A['colour']}/{B['colour']}"
            lines.append(f"  {j['name']:34} gap {j['gap_m']:5.2f} m  {B['z'] - A['z']:+5.2f} m  "
                         f"{j['difficulty'] or '?'} ({colours})")
    for i in rt.unpaired:
        lip = rt.lips[i]
        lines.append(f"unpaired: {lip['top']} {lip['colour']} lip at ({lip['mid'][0]:.1f}, {lip['mid'][1]:.1f}, "
                     f"{lip['z']:.2f})")
    for t in rt.left_out:
        lines.append(f"left out: {t['id']} z={t['z']} {t['area_m2']} m2, {t['width_m']} m wide "
                     "(marker or frame member)")
    unknown = sorted({lip["colour"] for lip in rt.lips if lip["difficulty"] is None})
    if unknown:
        lines.append(f"lip colours with no difficulty: {', '.join(unknown)}")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("extract")
    ap.add_argument("--out")
    ap.add_argument("--map")
    ap.add_argument("--world-guide", "--guide", dest="guide", action="append", default=[])
    ap.add_argument("--lip-colours", default=LIP_COLOURS)
    ap.add_argument("--role", default="gameplay")
    ap.add_argument("--start")
    ap.add_argument("--px-per-m", type=float, default=4.0)
    for k in PARAMS:
        ap.add_argument("--" + k.replace("_", "-"), type=float)
    a = ap.parse_args(argv)
    params = params_from(a.guide, {k: getattr(a, k) for k in PARAMS})
    data = pg.load(a.extract)
    rt = Routes(data, colour_map(a.lip_colours), a.role, a.start, **params)
    out = a.out or os.path.splitext(a.extract)[0] + "_routes.json"
    with open(out, "w") as f:
        json.dump(rt.as_json(a.extract), f, indent=1, default=lambda o: o.tolist())
    for ln in summary(rt):
        print(ln)
    print(f"-> {out}")
    if a.map:
        w, h = draw_map(rt, a.map, a.px_per_m, {k: tuple(v) for k, v in data.get("palette", {}).items()})
        print(f"map {w} x {h} px -> {a.map}")
    return rt


if __name__ == "__main__":
    main()
