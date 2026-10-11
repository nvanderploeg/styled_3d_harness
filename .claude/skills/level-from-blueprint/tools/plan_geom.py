"""Plan (x, y) polygon geometry the pure-python tools share: area, winding, hull, distances, corners, frames and a
corner match. numpy only; imported by shape_fit.py and routes.py.
"""
import json
import math

import numpy as np


def load(path):
    with open(path) as f:
        return json.load(f)


def pieces(data, role):
    """The extract's pieces playing role (every piece when role is None or the extract names no roles)."""
    return {name: p for name, p in data["pieces"].items() if role is None or p.get("role", role) == role}


def area2(P):
    """Signed area of a closed polygon: positive counter-clockwise."""
    P = np.asarray(P, float)
    Q = np.roll(P, -1, axis=0)
    return float((P[:, 0] * Q[:, 1] - Q[:, 0] * P[:, 1]).sum() / 2)


def ccw(P):
    P = np.asarray(P, float)
    return P if area2(P) > 0 else P[::-1]


def hull(P):
    """Convex hull, counter-clockwise."""
    pts = sorted({(round(float(x), 6), round(float(y), 6)) for x, y in P})
    if len(pts) < 3:
        return np.array(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return np.array(lo[:-1] + up[:-1])


def seg_dist(pts, a, b):
    pts = np.atleast_2d(pts)
    ab = b - a
    t = np.clip(((pts - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
    return np.linalg.norm(pts - (a + t[:, None] * ab), axis=1)


def signed_dist(pts, poly):
    """Signed plan distance of points to a closed polygon: negative inside."""
    pts = np.atleast_2d(np.asarray(pts, float))[:, :2]
    P = np.asarray(poly, float)[:, :2]
    d = np.full(len(pts), np.inf)
    inside = np.zeros(len(pts), bool)
    for a, b in zip(P, np.roll(P, -1, axis=0)):
        d = np.minimum(d, seg_dist(pts, a, b))
        cross = (a[1] > pts[:, 1]) != (b[1] > pts[:, 1])
        xc = a[0] + (pts[:, 1] - a[1]) * (b[0] - a[0]) / np.where(b[1] != a[1], b[1] - a[1], 1)
        inside ^= cross & (pts[:, 0] < xc)
    return np.where(inside, -d, d)


def poly_gap(A, B):
    """Plan distance between two polygons (0 when they overlap)."""
    A, B = np.asarray(A, float)[:, :2], np.asarray(B, float)[:, :2]
    d = min(float(signed_dist(A, B).min()), float(signed_dist(B, A).min()))
    return max(d, 0.0)


def corners(pts):
    """The polygon's true corners (collinear points dropped), counter-clockwise."""
    out = []
    for i in range(len(pts)):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
        u, v = b - a, c - b
        if abs(u[0] * v[1] - u[1] * v[0]) > 1e-4 * np.linalg.norm(u) * np.linalg.norm(v):
            out.append(b)
    cs = np.array(out)
    return cs if area2(cs) > 0 else cs[::-1]


def to_local(pts, centre, angle):
    c, s = math.cos(angle), math.sin(angle)
    d = pts - centre
    return np.stack([d[:, 0] * c + d[:, 1] * s, -d[:, 0] * s + d[:, 1] * c], axis=1)


def to_world(pts, centre, angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.stack([pts[:, 0] * c - pts[:, 1] * s, pts[:, 0] * s + pts[:, 1] * c], axis=1) + centre


def match(a, b):
    """Largest distance from a corner of either polygon to the nearest corner of the other."""
    return float(max(np.linalg.norm(a[:, None] - b[None], axis=2).min(axis=1).max(),
                     np.linalg.norm(b[:, None] - a[None], axis=2).min(axis=1).max()))


def outline(piece, top):
    """A top's outline as world (x, y, z) points."""
    return np.array(piece["verts"], float)[top["outline"]]
