"""The hollow load as a closed mesh, from its top and inside surfaces. No bpy.

The load is a shell ``thickness`` thick, open underneath:

- the **top**: the ore surface, a height field over the full opening;
- the **sides**: from the top's edge down to the bottom of the skirt,
  sloping inward by the taper, so the load is smaller at the bottom and
  flares out to the full opening at the top, and drops into the car;
- the **inside**: the top surface lowered by the thickness, and inside
  walls one thickness in from the sides;
- a flat **rim** joining the outside and inside walls at the bottom.

Everything returns (vertices (N, 3) float64, triangles (M, 3) int32),
triangles wound outward, watertight.
"""

from __future__ import annotations

import numpy as np


def _grid_tris(nx: int, ny: int, up: bool, h=None) -> np.ndarray:
    """Triangles of an nx x ny vertex grid (index i * ny + j), facing +Z if ``up``.

    With heights ``h``, each square is split along the diagonal whose ends
    are closest in height, so steep lump faces stay crisp, not saw-toothed.
    """
    i, j = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1), indexing="ij")
    a = (i * ny + j).ravel()
    b = a + ny          # (i+1, j)
    c = b + 1           # (i+1, j+1)
    d = a + 1           # (i, j+1)
    if h is None:
        flip = ((i + j) % 2 == 1).ravel()
    else:
        z = np.asarray(h).ravel()
        flip = np.abs(z[b] - z[d]) < np.abs(z[a] - z[c])
    t1 = np.where(flip[:, None], np.stack([a, b, d], 1), np.stack([a, b, c], 1))
    t2 = np.where(flip[:, None], np.stack([b, c, d], 1), np.stack([a, c, d], 1))
    tris = np.concatenate([t1, t2])
    return tris if up else tris[:, ::-1]


def _sides(nx: int, ny: int) -> list[np.ndarray]:
    """The grid's four edges as vertex indices, counter-clockwise from above, corner to corner."""
    i, j = np.arange(nx), np.arange(ny)
    return [
        i * ny,                          # y min, x rising
        (nx - 1) * ny + j,               # x max, y rising
        (i * ny + (ny - 1))[::-1],       # y max, x falling
        j[::-1],                         # x min, y falling
    ]


def _loop(sides: list[np.ndarray]) -> np.ndarray:
    """The four sides joined into one closed loop (each corner once)."""
    return np.concatenate([s[:-1] for s in sides])


def _wall(top: np.ndarray, bottom: np.ndarray, outward: bool) -> np.ndarray:
    """Quads between a counter-clockwise top loop and the bottom loop below it."""
    t0, b0 = top, bottom
    t1, b1 = np.roll(top, -1), np.roll(bottom, -1)
    tris = np.concatenate([np.stack([t0, b0, b1], 1), np.stack([t0, b1, t1], 1)])
    return tris if outward else tris[:, ::-1]


def _zip(outer: np.ndarray, op: np.ndarray, inner: np.ndarray, ip: np.ndarray) -> list:
    """Downward-facing triangles joining two parallel rows (outer and inner) of one rim side.

    ``op`` and ``ip`` are the vertices' positions along the side, 0 to 1.
    """
    out, a, b = [], 0, 0
    while a < len(outer) - 1 or b < len(inner) - 1:
        if b == len(inner) - 1 or (a < len(outer) - 1 and op[a + 1] <= ip[b + 1]):
            out.append((outer[a], inner[b], outer[a + 1]))
            a += 1
        else:
            out.append((outer[a], inner[b], inner[b + 1]))
            b += 1
    return out


def build(xs, ys, h, xi, yi, hi, taper: float, inset: float, z_bottom: float):
    """The closed shell.

    ``xs``, ``ys`` and ``h`` (len(xs) x len(ys)) are the top surface over the
    full opening, centred on the origin. ``xi``, ``yi`` and ``hi`` are the
    inside surface over the opening less ``inset`` on every side. The
    outside walls come in by ``taper`` from the top's edge to ``z_bottom``.
    """
    nx, ny, mx, my = len(xs), len(ys), len(xi), len(yi)
    half_x, half_y = xs[-1], ys[-1]
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    top = np.column_stack([X.ravel(), Y.ravel(), np.asarray(h).ravel()])
    Xi, Yi = np.meshgrid(xi, yi, indexing="ij")
    ins = np.column_stack([Xi.ravel(), Yi.ravel(), np.asarray(hi).ravel()])

    o_sides, i_sides = _sides(nx, ny), _sides(mx, my)
    o_loop, i_loop = _loop(o_sides), _loop(i_sides)

    # bottom rings: the top's edge pulled in to the bottom rectangles
    def ring(pts, loop, hx, hy, bx, by):
        p = pts[loop].copy()
        p[:, 0] *= bx / hx
        p[:, 1] *= by / hy
        p[:, 2] = z_bottom
        return p

    bx, by = half_x - taper, half_y - taper
    o_ring = ring(top, o_loop, half_x, half_y, bx, by)
    i_ring = ring(ins, i_loop, xi[-1], yi[-1], bx - inset, by - inset)

    n_top, n_ins, n_or = len(top), len(ins), len(o_ring)
    verts = np.vstack([top, ins, o_ring, i_ring])
    off_ins, off_or, off_ir = n_top, n_top + n_ins, n_top + n_ins + n_or

    o_bot = off_or + np.arange(len(o_loop))
    i_bot = off_ir + np.arange(len(i_loop))
    parts = [
        _grid_tris(nx, ny, up=True, h=h),
        _grid_tris(mx, my, up=False) + off_ins,
        _wall(o_loop, o_bot, outward=True),
        _wall(i_loop + off_ins, i_bot, outward=False),
    ]

    # the rim, side by side: map each side's grid vertices to their bottom-ring copies
    o_pos = {int(v): k for k, v in enumerate(o_loop)}
    i_pos = {int(v): k for k, v in enumerate(i_loop)}
    rim = []
    for side, (os_, is_) in enumerate(zip(o_sides, i_sides)):
        axis = 0 if side % 2 == 0 else 1
        ob = np.array([o_bot[o_pos[int(v)]] for v in os_])
        ib = np.array([i_bot[i_pos[int(v)]] for v in is_])
        op = verts[ob, axis]
        ip = verts[ib, axis]
        op = (op - op[0]) / (op[-1] - op[0])
        ip = (ip - ip[0]) / (ip[-1] - ip[0])
        rim += _zip(ob, op, ib, ip)
    parts.append(np.array(rim, dtype=np.int64))
    tris = np.concatenate(parts).astype(np.int32)
    return verts, tris


def signed_volume(verts: np.ndarray, tris: np.ndarray) -> float:
    """Signed volume of a closed mesh; positive when its triangles face outward."""
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def open_edges(triangles: np.ndarray) -> int:
    """Number of edges not shared by exactly two triangles in opposite directions."""
    if len(triangles) == 0:
        return 0
    t = triangles.astype(np.int64)
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    n = int(e.max()) + 1
    fwd = e[:, 0] * n + e[:, 1]
    rev = e[:, 1] * n + e[:, 0]
    fwd_u, fwd_c = np.unique(fwd, return_counts=True)
    return int(np.sum(fwd_c != 1)) + int(np.isin(rev, fwd_u, invert=True).sum())
