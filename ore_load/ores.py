"""The ore types and the shape of their lumps. No bpy, so it can be tested.

Each ore type fills in the lump sizes (prototype inches) and the lump
shape settings, which can then be edited:

- facets: how many sloping faces a lump has (fewer = more angular).
- flatness: lump height as a share of its size (coal lies flatter).
- cap: the top is cut flat at this share of the lump's height (1 = pointed).
- roundness: 0 = sharp edges and corners, 1 = rounded like gravel.
- slope_jitter: how much the faces of one lump differ in steepness.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ore:
    """One ore type: its sizes, lump shape and colour."""

    key: str
    label: str
    description: str
    size_min: float  # prototype inches
    size_max: float
    facets_min: int
    facets_max: int
    flatness: float
    cap: float
    roundness: float
    slope_jitter: float
    color: tuple[float, float, float]


ORES: tuple[Ore, ...] = (
    Ore("HARD_ROCK", "Hard Rock", "Blasted hard rock ore (copper, gold, silver, lead): "
        "angular, broken lumps", 3.0, 12.0, 4, 6, 0.55, 0.8, 0.0, 0.35, (0.36, 0.34, 0.31)),
    Ore("COAL", "Coal", "Run-of-mine or lump coal: blocky, flat-faced lumps that lie flat",
        2.0, 8.0, 4, 5, 0.45, 0.65, 0.0, 0.25, (0.03, 0.03, 0.035)),
    Ore("IRON_ORE", "Iron Ore", "Natural (direct shipping) iron ore: small, lumpy, "
        "slightly rounded", 1.0, 6.0, 5, 8, 0.5, 0.85, 0.4, 0.3, (0.28, 0.11, 0.06)),
    Ore("LIMESTONE", "Limestone", "Crushed limestone or flux stone: angular, fairly even "
        "lumps", 2.0, 6.0, 5, 7, 0.55, 0.75, 0.15, 0.3, (0.62, 0.6, 0.55)),
    Ore("GRAVEL", "Gravel", "Gravel or river rock: small rounded stones",
        0.75, 3.0, 6, 8, 0.55, 1.0, 0.85, 0.2, (0.45, 0.42, 0.38)),
)
BY_KEY = {o.key: o for o in ORES}
SHAPE_KEYS = ("facets_min", "facets_max", "flatness", "cap", "roundness", "slope_jitter")


def get(key: str) -> Ore:
    """The ore type for ``key`` (hard rock if unknown)."""
    return BY_KEY.get(key, ORES[0])
