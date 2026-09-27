import bmesh
import numpy as np


def triangles(me):
    """(uv, xyz) corner arrays for every loop triangle: shapes (n,3,2) and (n,3,3)."""
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    loops = np.empty(n * 3, np.int32)
    me.loop_triangles.foreach_get("loops", loops)
    verts = np.empty(n * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", verts)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    return uv.reshape(-1, 2)[loops].reshape(n, 3, 2), co.reshape(-1, 3)[verts].reshape(n, 3, 3)


def area2d(t):
    e1, e2 = t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]
    return np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2


def area3d(t):
    return np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) / 2


def raster(tri_uv, res):
    """Per-pixel count of UV triangles covering each pixel centre (row 0 = v 0)."""
    cov = np.zeros((res, res), np.int32)
    for a, b, c in tri_uv.astype(np.float64) * res:
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        x0, y0 = np.clip(np.floor(np.minimum(np.minimum(a, b), c)).astype(int), 0, res - 1)
        x1, y1 = np.clip(np.ceil(np.maximum(np.maximum(a, b), c)).astype(int), 0, res - 1)
        X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((b[1] - c[1]) * (X - c[0]) + (c[0] - b[0]) * (Y - c[1])) / d
        l2 = ((c[1] - a[1]) * (X - c[0]) + (a[0] - c[0]) * (Y - c[1])) / d
        cov[y0:y1 + 1, x0:x1 + 1] += (l1 > 0) & (l2 > 0) & (l1 + l2 < 1)
    return cov


def uv_split_edges(me):
    """Indices of edges whose two faces do not share UVs along the edge."""
    bm = bmesh.new()
    bm.from_mesh(me)
    uv = bm.loops.layers.uv.active
    split = set()
    for e in bm.edges:
        if len(e.link_loops) != 2:
            split.add(e.index)
            continue
        l1, l2 = e.link_loops
        # Adjacent faces wind the shared edge in opposite directions.
        if (l1[uv].uv - l2.link_loop_next[uv].uv).length > 1e-5 or \
           (l1.link_loop_next[uv].uv - l2[uv].uv).length > 1e-5:
            split.add(e.index)
    bm.free()
    return split


def uv_edges(me):
    """(n,2,2) UV segments of every face edge, for drawing layouts."""
    segs = []
    uv = me.uv_layers.active.data
    for p in me.polygons:
        idx = list(p.loop_indices)
        for i, j in zip(idx, idx[1:] + idx[:1]):
            segs.append((uv[i].uv[:], uv[j].uv[:]))
    return np.array(segs, np.float32)
