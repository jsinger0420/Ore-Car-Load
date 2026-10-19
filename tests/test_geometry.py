"""Tests for the plain-Python parts: scales, ores, the load surface and the shell.

Run from the ORE LOAD folder (no Blender needed):

    python -m unittest discover -s tests -t .
"""

import math
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ore_load import load, ores, scales, shell  # noqa: E402
from ore_load.load import LoadSpec  # noqa: E402

N = 87.1
IN = 25.4


def ho(ore="HARD_ROCK", **kw) -> LoadSpec:
    """An HO 20 ft x 9 ft opening with the ore's lumps."""
    o = ores.get(ore)
    base = dict(length=240 * IN / N, width=108 * IN / N, hump_height=24 * IN / N,
                size_min=o.size_min * IN / N, size_max=o.size_max * IN / N,
                facets_min=o.facets_min, facets_max=o.facets_max, flatness=o.flatness,
                cap=o.cap, roundness=o.roundness, slope_jitter=o.slope_jitter,
                max_cells=60_000, seed=7)
    base.update(kw)
    return LoadSpec(**base)


class TestScales(unittest.TestCase):
    """Scale ratios and unit conversion."""

    def test_ratios(self):
        """Every scale has a ratio; custom uses the entered one."""
        self.assertEqual(scales.scale_n("HO", 1), 87.1)
        self.assertEqual(scales.scale_n("CUSTOM", 100), 100)
        self.assertTrue(all(v[1] > 1 for v in scales.SCALES.values()))

    def test_units_and_feet(self):
        """Inches to mm and back, and feet-and-inches text."""
        self.assertAlmostEqual(scales.from_full_mm(scales.to_full_mm(12, "IN"), "IN"), 12)
        self.assertEqual(scales.feet_inches(102 * IN), "8' 6\"")


class TestShell(unittest.TestCase):
    """The hollow load mesh."""

    def test_flat_box_is_closed_and_right_volume(self):
        """A flat top gives a closed shell whose volume matches its walls and roof."""
        xs = np.linspace(-10, 10, 21)
        ys = np.linspace(-5, 5, 11)
        h = np.zeros((21, 11))
        inset = 1.0
        xi = np.linspace(-9, 9, 7)
        yi = np.linspace(-4, 4, 5)
        hi = np.full((7, 5), -1.0)
        v, t = shell.build(xs, ys, h, xi, yi, hi, taper=0.0, inset=inset, z_bottom=-3.0)
        self.assertEqual(shell.open_edges(t), 0)
        outer = 20 * 10 * 3
        inner = 18 * 8 * 2
        self.assertAlmostEqual(shell.signed_volume(v, t), outer - inner, places=6)

    def test_taper_narrows_the_bottom(self):
        """The bottom of the sides is the taper smaller on every side."""
        spec = ho(taper=0.6)
        built = load.build(spec)
        bottom = built.vertices[np.isclose(built.vertices[:, 2], built.z_bottom)]
        self.assertAlmostEqual(bottom[:, 0].max(), spec.length / 2 - 0.6, places=6)
        self.assertAlmostEqual(bottom[:, 1].min(), -(spec.width / 2 - 0.6), places=6)
        self.assertAlmostEqual(built.vertices[:, 0].max(), spec.length / 2, places=6)


class TestLoad(unittest.TestCase):
    """Whole loads: closed, hollow, thick enough, the right shape."""

    def test_every_ore_method_and_shape_is_closed(self):
        """Every combination builds a watertight, outward-facing shell."""
        for ore in ores.ORES:
            for method in ("MACHINE", "HAND"):
                for shape in ("LEVEL", "RIDGE", "MOUND", "PEAKS"):
                    with self.subTest(ore=ore.key, method=method, shape=shape):
                        spec = ho(ore.key, method=method, hump_shape=shape, peaks=3,
                                  variation=12 * IN / N if method == "HAND" else 0.0,
                                  max_lumps=4000)
                        built = load.build(spec)
                        self.assertEqual(shell.open_edges(built.triangles), 0)
                        self.assertGreater(built.volume, 0)
                        self.assertGreater(built.lumps, 0)

    def test_shell_is_hollow_and_thick(self):
        """The inside is at least the thickness below the top everywhere, and far less solid."""
        spec = ho(thickness=1.0)
        p = load.plan(spec)
        rng = np.random.default_rng(1)
        xs = np.linspace(-spec.length / 2, spec.length / 2, p.nx)
        ys = np.linspace(-spec.width / 2, spec.width / 2, p.ny)
        h, _ = load.add_lumps(spec, xs, ys, load.base_surface(spec, xs, ys, rng), rng)
        xi, yi, hi = load.inside_surface(xs, ys, h, 1.0, p.inset, spec.max_cells)
        # brute force: no top point within 1 mm of any inside point
        X, Y = np.meshgrid(xs, ys, indexing="ij")
        top = np.column_stack([X.ravel(), Y.ravel(), h.ravel()])
        Xi, Yi = np.meshgrid(xi, yi, indexing="ij")
        ins = np.column_stack([Xi.ravel(), Yi.ravel(), hi.ravel()])
        pick = rng.choice(len(ins), 400, replace=False)
        for q in ins[pick]:
            near = top[(np.abs(top[:, 0] - q[0]) < 1.1) & (np.abs(top[:, 1] - q[1]) < 1.1)]
            self.assertGreaterEqual(np.min(np.linalg.norm(near - q, axis=1)), 1.0 - 1e-6)
        built = load.build(spec)
        solid = spec.length * spec.width * (built.top - built.z_bottom)
        self.assertLess(built.volume, solid * 0.5)

    def test_hump_rises_to_its_height(self):
        """A ridge's base surface reaches the hump height in the middle, edge level at the sides."""
        spec = ho(hump_shape="RIDGE", edge_level=0.5)
        xs = np.linspace(-spec.length / 2, spec.length / 2, 201)
        ys = np.linspace(-spec.width / 2, spec.width / 2, 101)
        z = load.base_surface(spec, xs, ys, np.random.default_rng(0))
        self.assertAlmostEqual(z.max(), 0.5 + spec.hump_height, places=2)
        self.assertAlmostEqual(z[100, 0], 0.5, places=6)
        level = load.base_surface(ho(hump_shape="LEVEL"), xs, ys, np.random.default_rng(0))
        self.assertTrue(np.allclose(level, 0.0))

    def test_hand_hollows_stay_above_the_edge(self):
        """Hand loading's random hollows never dip below the edge level."""
        spec = ho(method="HAND", hump_shape="LEVEL", variation=0.5)
        xs = np.linspace(-spec.length / 2, spec.length / 2, 101)
        ys = np.linspace(-spec.width / 2, spec.width / 2, 51)
        z = load.base_surface(spec, xs, ys, np.random.default_rng(3))
        self.assertGreaterEqual(z.min(), 0.0)
        self.assertGreater(z.max(), 0.0)

    def test_lumps_are_within_their_sizes(self):
        """Lump centres get sizes between the smallest and largest."""
        for method in ("MACHINE", "HAND"):
            spec = ho(method=method)
            c = load._centres(spec, np.random.default_rng(2))
            sizes = np.array([x[2] for x in c])
            self.assertGreaterEqual(sizes.min(), spec.size_min - 1e-9)
            self.assertLessEqual(sizes.max(), spec.size_max + 1e-9)

    def test_same_seed_same_load(self):
        """The seed repeats a load exactly; another seed changes it."""
        a = load.build(ho(seed=11))
        b = load.build(ho(seed=11))
        c = load.build(ho(seed=12))
        self.assertTrue(np.array_equal(a.vertices, b.vertices))
        self.assertFalse(np.array_equal(a.vertices, c.vertices))

    def test_plan_errors_and_warnings(self):
        """Impossible settings are errors; thin shells and tiny lumps are warnings."""
        self.assertTrue(load.plan(ho(length=0)).errors)
        self.assertTrue(load.plan(ho(size_min=5, size_max=1)).errors)
        self.assertTrue(load.plan(ho(length=2, width=2)).errors)
        self.assertTrue(any("thin" in w for w in load.plan(ho(thickness=0.3)).warnings))
        tiny = load.plan(ho(size_min=0.05, size_max=0.1))
        self.assertTrue(any("too small" in w for w in tiny.warnings))
        self.assertRaises(load.LoadError, load.build, ho(length=0))

    def test_grid_limited_by_max_cells(self):
        """The automatic grid gets coarser to stay under Max Grid Cells."""
        p = load.plan(ho("GRAVEL", max_cells=50_000))
        self.assertLessEqual((p.nx - 1) * (p.ny - 1), 50_000 * 1.02)


if __name__ == "__main__":
    unittest.main()
