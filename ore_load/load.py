"""The ore load: its surface, lumps and hollow shell. No bpy, so it can be tested.

All sizes here are model millimetres. The origin is the middle of the car
opening at the height of the top of the car sides (the rim); X runs along
the car, Y across it.

1. **Base surface.** The load's general shape: level, a ridge along the
   car, one mound, or a row of peaks (one per chute or bay), rising
   ``hump_height`` above the load's edge, which is ``edge_level`` above the
   rim (negative = below it). Hand loading adds random mounds and hollows
   (``variation``; hollows stop at the edge level) and shifts the peaks a
   little.
2. **Lumps.** Each lump is a small rock: a few sloping faces around a
   centre (angular), cut flat on top (cap) and trimmed by an ellipsoid
   (rounded), tilted a little and part-buried in the base. Machine loading
   packs them evenly on a staggered grid in two layers; hand loading
   scatters them at random with more small ones.
3. **Shell.** The surface is the top of a shell ``thickness`` thick, open
   underneath, with sides that go ``skirt`` below the load's edge and come
   in by ``taper``, so it drops into the car and wedges at the rim.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import shell

PRINTER_MIN = {"RESIN": {"grid": 0.025, "detail": 0.15, "wall": 0.6},
               "FDM": {"grid": 0.1, "detail": 0.5, "wall": 1.0}}


class LoadError(ValueError):
    """The settings can't make a load."""


@dataclass
class LoadSpec:
    """Everything the load is made from, in model millimetres."""

    length: float = 70.0          # opening along the car (top of the load)
    width: float = 30.0           # opening across the car
    edge_level: float = 0.0       # load edge height above the rim
    hump_shape: str = "RIDGE"     # LEVEL, RIDGE, MOUND, PEAKS
    hump_height: float = 6.0      # above the edge, at the top of the hump
    peaks: int = 2
    method: str = "MACHINE"       # MACHINE or HAND
    variation: float = 0.0        # height of random mounds and hollows
    size_min: float = 1.0         # lump sizes
    size_max: float = 3.0
    facets_min: int = 4
    facets_max: int = 6
    flatness: float = 0.55
    cap: float = 0.8
    roundness: float = 0.0
    slope_jitter: float = 0.35
    coverage: float = 1.0         # how many lumps, 1 = packed
    thickness: float = 1.0
    skirt: float = 3.0            # how far the sides reach below the load's edge
    taper: float = 0.5            # how far the sides come in, each side, top to bottom
    grid: float = 0.0             # surface grid spacing; 0 = automatic
    max_cells: int = 400_000
    max_lumps: int = 60_000
    printer: str = "RESIN"
    seed: int = 0


@dataclass
class Plan:
    """What a spec will make, worked out without building it (for the panel)."""

    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    dx: float = 0.0
    nx: int = 0
    ny: int = 0
    lumps: int = 0
    inset: float = 0.0
    z_bottom: float = 0.0
    bottom_length: float = 0.0
    bottom_width: float = 0.0
    peak: float = 0.0


@dataclass
class Load:
    """A built load: the shell mesh and some numbers about it."""

    vertices: np.ndarray
    triangles: np.ndarray
    plan: Plan
    lumps: int
    top: float          # highest point above the rim
    z_bottom: float     # bottom of the sides
    volume: float       # mm^3 of material
    warnings: list


def _mean_size(s: LoadSpec) -> float:
    """The average lump size."""
    return (s.size_min + s.size_max) / 2


def plan(s: LoadSpec) -> Plan:
    """Check the spec and work out the grid, lump count and shell sizes."""
    p = Plan()
    if s.length <= 0 or s.width <= 0:
        p.errors.append("Enter the car opening's length and width.")
        return p
    if s.size_min <= 0 or s.size_max <= 0:
        p.errors.append("Lump sizes must be more than 0.")
    elif s.size_min > s.size_max:
        p.errors.append("The smallest lump size is bigger than the largest.")
    if s.thickness <= 0:
        p.errors.append("The thickness must be more than 0.")
    if s.skirt <= 0:
        p.errors.append("The skirt depth must be more than 0.")
    slope = s.taper / s.skirt if s.skirt > 0 else 0.0
    p.inset = s.thickness * math.sqrt(1 + slope * slope)
    room = min(s.length, s.width) / 2 - s.taper - p.inset
    if room < 0.2:
        p.errors.append("The taper and thickness leave no room inside: make them smaller "
                        "or the opening bigger.")
    if p.errors:
        return p

    limits = PRINTER_MIN.get(s.printer, PRINTER_MIN["RESIN"])
    area = s.length * s.width
    dx = s.grid if s.grid > 0 else max(limits["grid"], s.size_min / 6)
    if area / (dx * dx) > s.max_cells:
        dx = math.sqrt(area / s.max_cells)
    p.nx = max(3, int(math.ceil(s.length / dx)) + 1)
    p.ny = max(3, int(math.ceil(s.width / dx)) + 1)
    p.dx = s.length / (p.nx - 1)

    mean = _mean_size(s)
    if s.method == "MACHINE":
        sp = mean * 0.72
        per_layer = (s.length + mean) * (s.width + mean) / (sp * sp * 0.866)
        p.lumps = int(per_layer * min(1.0, s.coverage) + per_layer * 0.55 * s.coverage)
    else:
        p.lumps = int(s.coverage * 3.2 * (s.length + mean) * (s.width + mean) / (mean * mean))
    if p.lumps > s.max_lumps:
        p.warnings.append(f"About {p.lumps} lumps; only {s.max_lumps} will be made. Use "
                          f"bigger lumps or raise Max Lumps.")
        p.lumps = s.max_lumps

    p.peak = s.edge_level + (0.0 if s.hump_shape == "LEVEL" else s.hump_height)
    p.z_bottom = s.edge_level - s.skirt
    p.bottom_length = s.length - 2 * s.taper
    p.bottom_width = s.width - 2 * s.taper

    if s.size_min < 3 * p.dx:
        p.warnings.append(f"The smallest lumps ({s.size_min:.2f} mm) are under 3 grid steps "
                          f"({p.dx:.3f} mm); they'll look like bumps. Lower the grid spacing "
                          f"or raise Max Grid Cells.")
    if s.size_min < limits["detail"]:
        p.warnings.append(f"The smallest lumps are {s.size_min:.2f} mm, too small to show "
                          f"well on a {'resin' if s.printer == 'RESIN' else 'FDM'} printer.")
    if s.thickness < limits["wall"]:
        p.warnings.append(f"A {s.thickness:.2f} mm shell is thin for a "
                          f"{'resin' if s.printer == 'RESIN' else 'FDM'} printer "
                          f"(about {limits['wall']:g} mm or more prints reliably).")
    return p


# ---------------------------------------------------------------- base surface

def _cos_profile(t):
    """1 at 0, falling to 0 at 1 and beyond, like the side of a pile."""
    return np.cos(np.pi / 2 * np.clip(t, 0.0, 1.0))


def base_surface(s: LoadSpec, xs, ys, rng) -> np.ndarray:
    """The load's general shape (no lumps) on the grid, heights above the rim."""
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    hl, hw = s.length / 2, s.width / 2
    hand = s.method == "HAND"
    shift = (lambda k: rng.uniform(-k, k)) if hand else (lambda k: 0.0)
    v = np.abs(Y - shift(0.08) * hw) / hw
    if s.hump_shape == "RIDGE":
        ends = np.minimum(X + hl, hl - X)  # distance to the nearest end
        f = _cos_profile(v) * np.sin(np.pi / 2 * np.clip(ends / hw, 0, 1))
    elif s.hump_shape == "MOUND":
        u = (X - shift(0.1) * hl) / hl
        f = _cos_profile(np.sqrt(u * u + v * v))
    elif s.hump_shape == "PEAKS":
        n = max(1, s.peaks)
        seg = s.length / n
        f = np.zeros_like(X)
        for k in range(n):
            cx = -hl + seg * (k + 0.5) + shift(0.12) * seg
            u = (X - cx) / (seg / 2 * 1.25)
            f = np.maximum(f, _cos_profile(np.sqrt(u * u + v * v)))
    else:
        f = np.zeros_like(X)
    z = s.edge_level + (0.0 if s.hump_shape == "LEVEL" else s.hump_height) * f

    if s.variation > 0:
        bumps = max(3, int(round(4 * s.length / s.width)) + (3 if hand else 0))
        noise = np.zeros_like(X)
        for _ in range(bumps):
            cx, cy = rng.uniform(-hl, hl), rng.uniform(-hw, hw)
            sig = rng.uniform(0.15, 0.35) * s.width
            amp = rng.uniform(-1.0, 1.0) * s.variation
            noise += amp * np.exp(-((X - cx) ** 2 + (Y - cy) ** 2) / (2 * sig * sig))
        wall = np.minimum(hw - np.abs(Y), hl - np.abs(X))
        noise *= 0.5 + 0.5 * np.sin(np.pi / 2 * np.clip(wall / (hw / 2), 0, 1))
        z = np.maximum(z + noise, s.edge_level)  # hollows stop at the load's edge level
    return z


# ---------------------------------------------------------------- lumps

def _centres(s: LoadSpec, rng) -> list[tuple[float, float, float, float]]:
    """(x, y, size, lift) for each lump, lift being a share of the lump height."""
    hl, hw, mean = s.length / 2, s.width / 2, _mean_size(s)
    pad = s.size_max / 2
    out = []
    if s.method == "MACHINE":
        sp = mean * 0.72
        row = sp * 0.866
        for layer, keep, lift in ((0, min(1.0, s.coverage), 0.0),
                                  (1, 0.55 * s.coverage, 0.12)):
            ny = int(math.ceil((2 * (hw + pad)) / row)) + 1
            nx = int(math.ceil((2 * (hl + pad)) / sp)) + 2
            for j in range(ny):
                y = -hw - pad + j * row + layer * row / 3
                x0 = -hl - pad + (sp / 2 if (j + layer) % 2 else 0.0)
                for i in range(nx):
                    if rng.random() >= keep:
                        continue
                    x = x0 + i * sp + rng.uniform(-0.3, 0.3) * sp
                    yy = y + rng.uniform(-0.3, 0.3) * row
                    size = rng.uniform(s.size_min, s.size_max)
                    out.append((x, yy, size, lift + rng.uniform(-0.05, 0.05)))
    else:
        count = int(s.coverage * 3.2 * (2 * hl + 2 * pad) * (2 * hw + 2 * pad) / (mean * mean))
        for _ in range(count):
            x = rng.uniform(-hl - pad, hl + pad)
            y = rng.uniform(-hw - pad, hw + pad)
            size = s.size_min + (s.size_max - s.size_min) * rng.random() ** 1.6
            out.append((x, y, size, rng.uniform(0.0, 0.35)))
    if len(out) > s.max_lumps:
        idx = rng.choice(len(out), s.max_lumps, replace=False)
        out = [out[i] for i in sorted(idx)]
    return out


def add_lumps(s: LoadSpec, xs, ys, base, rng) -> tuple[np.ndarray, int]:
    """The base surface with the lumps on it; returns (heights, number of lumps)."""
    h = base.copy()
    dx = xs[1] - xs[0]
    x0, y0 = xs[0], ys[0]
    nx, ny = len(xs), len(ys)
    centres = _centres(s, rng)
    fmin = max(3, int(s.facets_min))
    fmax = max(fmin, int(s.facets_max))
    round_k = 1.0 - min(1.0, max(0.0, s.roundness))
    sink = 0.3 if s.method == "MACHINE" else 0.25
    made = 0
    for cx, cy, size, lift in centres:
        R = size / 2
        elong = rng.uniform(0.7, 1.0)
        theta = rng.uniform(0, math.pi)
        n = int(rng.integers(fmin, fmax + 1))
        phis = theta + 2 * math.pi * np.arange(n) / n + rng.uniform(-0.3, 0.3, n) * math.pi / n
        reach = R * np.sqrt(np.cos(phis) ** 2 + (elong * np.sin(phis)) ** 2) \
            * rng.uniform(0.8, 1.0, n)
        slopes = 1.0 + s.slope_jitter * rng.uniform(-1, 1, n)
        H = s.flatness * size * rng.uniform(0.8, 1.2)
        slopes *= H / float(np.min(slopes * reach))
        cap = max(0.05, min(1.0, s.cap)) * H
        a = R * (1.0 + 0.5 * round_k)
        b = a * elong
        he = H * (1.0 + 1.5 * round_k)
        tilt = rng.normal(0.0, 0.15, 2) * H / R

        i0 = max(0, int(math.floor((cx - a - x0) / dx)))
        i1 = min(nx, int(math.ceil((cx + a - x0) / dx)) + 1)
        j0 = max(0, int(math.floor((cy - a - y0) / dx)))
        j1 = min(ny, int(math.ceil((cy + a - y0) / dx)) + 1)
        if i0 >= i1 or j0 >= j1:
            continue
        px = xs[i0:i1, None] - cx
        py = ys[None, j0:j1] - cy
        c, sn = math.cos(theta), math.sin(theta)
        u = c * px + sn * py
        v = -sn * px + c * py
        z = np.full(u.shape, cap)
        for phi, m, r in zip(phis - theta, slopes, reach):
            np.minimum(z, m * (r - (math.cos(phi) * u + math.sin(phi) * v)), out=z)
        q = 1.0 - (u / a) ** 2 - (v / b) ** 2
        np.minimum(z, np.where(q > 0, he * np.sqrt(np.clip(q, 0, None)), -1.0), out=z)
        inside = z > 0
        if not inside.any():
            continue
        ci = min(nx - 1, max(0, int(round((cx - x0) / dx))))
        cj = min(ny - 1, max(0, int(round((cy - y0) / dx))))
        zc = base[ci, cj] + (lift - sink) * H
        top = np.where(inside, zc + z + tilt[0] * u + tilt[1] * v, -np.inf)
        win = h[i0:i1, j0:j1]
        np.maximum(win, top, out=win)
        made += 1
    return h, made


# ---------------------------------------------------------------- inside surface

def _max_filter(a: np.ndarray, w: int) -> np.ndarray:
    """Maximum over a (2w+1) square window, edges repeated."""
    if w <= 0:
        return a
    out = a
    for axis in (0, 1):
        pad = [(0, 0), (0, 0)]
        pad[axis] = (w, w)
        p = np.pad(out, pad, mode="edge")
        n = out.shape[axis]
        res = p.take(range(0, n), axis=axis)
        for k in range(1, 2 * w + 1):
            np.maximum(res, p.take(range(k, k + n), axis=axis), out=res)
        out = res
    return out


def inside_surface(xs, ys, h, t: float, inset: float, max_cells: int):
    """The inside of the shell: every point at least ``t`` below the top surface.

    Returns (xi, yi, hi) over the opening less ``inset`` on every side, on a
    grid about t/2.5 apart (coarser than the top; it can't be seen).
    """
    dx = xs[1] - xs[0]
    hl, hw = xs[-1] - inset, ys[-1] - inset
    e = max(dx, t / 2.5)
    if (2 * hl) * (2 * hw) / (e * e) > max_cells / 4:
        e = math.sqrt((2 * hl) * (2 * hw) / (max_cells / 4))
    mx = max(2, int(math.ceil(2 * hl / e)) + 1)
    my = max(2, int(math.ceil(2 * hw / e)) + 1)
    xi = np.linspace(-hl, hl, mx)
    yi = np.linspace(-hw, hw, my)
    e = max(xi[1] - xi[0], yi[1] - yi[0])
    # lowest top within half a sample step (plus rounding) of each fine point
    H = -_max_filter(-h, int(math.ceil(0.5 * e / dx + 0.5)))
    reach = t + 0.25 * e
    k = int(math.ceil((reach + e) / e))
    out = np.full((mx, my), np.inf)
    nx, ny = len(xs), len(ys)
    for a in range(-k, k + 1):
        for b in range(-k, k + 1):
            d = math.hypot(a * e, b * e)
            deff = max(0.0, d - 0.75 * e)
            if deff >= reach:
                continue
            drop = math.sqrt(reach * reach - deff * deff)
            qx = xi + a * e
            qy = yi + b * e
            # samples past the edge use the edge's window, which covers the
            # top surface within half a step of them
            ii = np.clip(np.round((qx - xs[0]) / dx).astype(int), 0, nx - 1)
            jj = np.clip(np.round((qy - ys[0]) / dx).astype(int), 0, ny - 1)
            np.minimum(out, H[np.ix_(ii, jj)] - drop, out=out)
    return xi, yi, out


# ---------------------------------------------------------------- the whole load

def build(s: LoadSpec, progress=None) -> Load:
    """Make the load. Raises LoadError if the spec can't make one."""
    p = plan(s)
    if p.errors:
        raise LoadError("\n".join(p.errors))
    warnings = list(p.warnings)
    rng = np.random.default_rng(int(s.seed))
    xs = np.linspace(-s.length / 2, s.length / 2, p.nx)
    ys = np.linspace(-s.width / 2, s.width / 2, p.ny)
    base = base_surface(s, xs, ys, rng)
    if progress:
        progress(0.1)
    h, made = add_lumps(s, xs, ys, base, rng)
    if progress:
        progress(0.7)
    xi, yi, hi = inside_surface(xs, ys, h, s.thickness, p.inset, s.max_cells)
    z_bottom = s.edge_level - s.skirt
    lowest = float(hi.min()) - 0.2
    if lowest < z_bottom:
        warnings.append(f"The load dips below the skirt; the sides were made "
                        f"{z_bottom - lowest:.2f} mm deeper to keep the shell "
                        f"{s.thickness:g} mm thick.")
        z_bottom = lowest
    verts, tris = shell.build(xs, ys, h, xi, yi, hi, s.taper, p.inset, z_bottom)
    if progress:
        progress(0.95)
    p.z_bottom = z_bottom
    return Load(verts, tris, p, made, float(h.max()), z_bottom,
                shell.signed_volume(verts, tris), warnings)
