"""Model railroad scales and unit conversion. No bpy, so it can be tested.

Prototype (full-size) sizes are entered in inches or millimetres and kept
as full-size millimetres; model sizes are printed millimetres, full-size
mm divided by N (as in 1:N). Narrow gauge shares its scale's ratio (HOn3 is
HO, On30 is O), so only the ratios are listed.
"""

from __future__ import annotations

MM_PER_INCH = 25.4

# key: (menu label, N in 1:N)
SCALES: dict[str, tuple[str, float]] = {
    "Z": ("Z 1:220", 220.0),
    "N": ("N 1:160", 160.0),
    "N_UK": ("N (UK) 1:148", 148.0),
    "TT": ("TT 1:120", 120.0),
    "HO": ("HO, HOn3 1:87.1", 87.1),
    "OO": ("OO 1:76.2", 76.2),
    "S": ("S, Sn3 1:64", 64.0),
    "O": ("O, On3, On30 1:48", 48.0),
    "O_UK": ("O (UK/Europe) 1:43.5", 43.5),
    "ONE": ("Gauge 1 1:32", 32.0),
    "LS": ("Large Scale 1:29", 29.0),
    "HALF": ("1/2 inch 1:24", 24.0),
    "G": ("G 1:22.5", 22.5),
    "FN3": ("Fn3 1:20.3", 20.3),
}
CUSTOM = "CUSTOM"


def scale_n(key: str, custom: float) -> float:
    """N in 1:N for a scale key (the custom ratio for CUSTOM)."""
    if key == CUSTOM or key not in SCALES:
        return float(custom)
    return SCALES[key][1]


def to_full_mm(value: float, units: str) -> float:
    """A prototype value in ``units`` ("IN" or "MM") as full-size millimetres."""
    return value * MM_PER_INCH if units == "IN" else value


def from_full_mm(value_mm: float, units: str) -> float:
    """Full-size millimetres back into ``units``."""
    return value_mm / MM_PER_INCH if units == "IN" else value_mm


def scale_label(key: str, custom: float) -> str:
    """Short text used in file names, e.g. 'HO' or '1-100'."""
    if key == CUSTOM or key not in SCALES:
        return f"1-{custom:g}"
    return key


def feet_inches(full_mm: float) -> str:
    """Full-size mm as feet and inches to the nearest 1/8 in, e.g. 8' 6\"."""
    sign = "-" if full_mm < 0 else ""
    inches = round(abs(full_mm) / MM_PER_INCH * 8) / 8
    if inches >= 12:
        feet, rest = divmod(inches, 12)
        return sign + (f"{int(feet)}' {rest:g}\"" if rest else f"{int(feet)}'")
    return f"{sign}{inches:g}\""
