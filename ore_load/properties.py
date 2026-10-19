"""All Ore Load settings, kept on the scene (``scene.ore_load``) so they save with the .blend.

Prototype sizes (the car opening, lump sizes, hump height, edge level and
variation) are in the units chosen by ``proto_units``, inches by default.
The shell (thickness, skirt, taper, fit allowance), the grid and the model
opening are model millimetres.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import ores, scales
from .load import LoadSpec

PROTO_LENGTH_KEYS = ("opening_length", "opening_width", "size_min", "size_max", "hump_height",
                     "edge_level", "variation")
HAND_VARIATION_IN = 12.0

_quiet = False


class quiet:
    """Context manager: suppress update callbacks while writing settings."""

    def __enter__(self):
        """Turn updates off, remembering the previous state so blocks can nest."""
        global _quiet
        self._prev, _quiet = _quiet, True

    def __exit__(self, *exc):
        """Put updates back as they were."""
        global _quiet
        _quiet = self._prev


def _changed(self, context):
    """Mark the chosen load preset as modified when any setting is edited."""
    if not _quiet and self.load_preset:
        self.load_modified = True


def _units_update(self, context):
    """Convert every prototype length when the units change."""
    if _quiet or self.proto_units == self.proto_units_prev:
        return
    with quiet():
        for key in PROTO_LENGTH_KEYS:
            mm = scales.to_full_mm(getattr(self, key), self.proto_units_prev)
            setattr(self, key, scales.from_full_mm(mm, self.proto_units))
        self.proto_units_prev = self.proto_units


def _ore_update(self, context):
    """Fill in the chosen ore's lump sizes and shape."""
    if _quiet:
        return
    self.apply_ore(self.ore_type)
    _changed(self, context)


def _method_update(self, context):
    """Hand loading gets random mounds and hollows; machine loading a smooth surface."""
    if _quiet:
        return
    with quiet():
        inches = HAND_VARIATION_IN if self.loading == "HAND" else 0.0
        self.variation = scales.from_full_mm(scales.to_full_mm(inches, "IN"), self.proto_units)
    _changed(self, context)


def _proto(name, default, desc, update=None, soft_max=1000.0, signed=False):
    """A prototype length property, in the units chosen by ``proto_units``."""
    return FloatProperty(name=name, description=desc + " (prototype size, in the chosen units)",
                         default=default, min=-10000.0 if signed else 0.0, soft_max=soft_max,
                         precision=3, update=update or _changed)


def _model(name, default, desc, signed=False):
    """A model-millimetre length property."""
    return FloatProperty(name=name, description=desc + " (model millimetres)",
                         default=default, min=-50.0 if signed else 0.0, soft_max=50.0,
                         precision=3, step=1, update=_changed)


class ORELOAD_Settings(bpy.types.PropertyGroup):
    """Every Ore Load setting, stored on the scene as ``scene.ore_load``."""

    # ---- car opening and scale ----
    size_mode: EnumProperty(
        name="Opening Size", default="PROTOTYPE", update=_changed,
        description="How the car opening is entered",
        items=[("PROTOTYPE", "Prototype", "The full-size car's opening, scaled down by the scale"),
               ("MODEL", "Model", "The model car's opening, measured in millimetres")])
    proto_units: EnumProperty(
        name="Prototype Units", default="IN", update=_units_update,
        description="Units for the full-size (prototype) measurements. Changing it converts them",
        items=[("IN", "Inches", "Prototype sizes in inches"),
               ("MM", "Millimetres", "Prototype sizes in millimetres")])
    proto_units_prev: StringProperty(default="IN", options={"HIDDEN"})
    opening_length: _proto("Opening Length", 240.0,
                           "Inside length of the car's opening, along the car")
    opening_width: _proto("Opening Width", 108.0, "Inside width of the car's opening, across the car")
    model_length: _model("Model Opening Length", 70.0,
                         "Inside length of the model car's opening, along the car")
    model_width: _model("Model Opening Width", 31.5,
                        "Inside width of the model car's opening, across the car")
    scale: EnumProperty(
        name="Scale", default="HO", update=_changed,
        description="Model railroad scale; sets the size ratio",
        items=[(k, v[0], f"1:{v[1]:g}") for k, v in scales.SCALES.items()]
        + [(scales.CUSTOM, "Custom", "Enter your own ratio")])
    scale_custom: FloatProperty(name="Ratio 1:", default=87.1, min=1.0, soft_max=500.0,
                                description="N in 1:N for a custom scale", update=_changed)

    # ---- ore ----
    ore_type: EnumProperty(
        name="Ore", default="HARD_ROCK", update=_ore_update,
        description="The kind of ore; fills in the lump sizes and shape, which you can then edit",
        items=[(o.key, o.label, o.description) for o in ores.ORES])
    size_min: _proto("Smallest Lump", 3.0, "Size of the smallest lumps", soft_max=48.0)
    size_max: _proto("Largest Lump", 12.0, "Size of the largest lumps", soft_max=48.0)
    facets_min: IntProperty(name="Fewest Faces", default=4, min=3, max=12, update=_changed,
                            description="Fewest sloping faces on a lump; fewer is more angular")
    facets_max: IntProperty(name="Most Faces", default=6, min=3, max=12, update=_changed,
                            description="Most sloping faces on a lump")
    flatness: FloatProperty(name="Lump Height", subtype="FACTOR", default=0.55, min=0.15,
                            max=1.2, update=_changed,
                            description="Lump height as a share of its size; lower lies flatter")
    cap: FloatProperty(name="Flat Top", subtype="FACTOR", default=0.8, min=0.2, max=1.0,
                       update=_changed,
                       description="Lump tops are cut flat at this share of their height; "
                                   "1 leaves them pointed")
    roundness: FloatProperty(name="Roundness", subtype="FACTOR", default=0.0, min=0.0, max=1.0,
                             update=_changed,
                             description="0 = sharp broken edges, 1 = rounded like river gravel")
    slope_jitter: FloatProperty(name="Face Variation", subtype="FACTOR", default=0.35, min=0.0,
                                max=0.8, update=_changed,
                                description="How much the faces of one lump differ in steepness")
    coverage: FloatProperty(name="Lump Density", default=1.0, min=0.1, max=2.0, update=_changed,
                            description="How many lumps: 1 covers the load; less shows the "
                                        "fines between them, more piles them up")

    # ---- load shape ----
    loading: EnumProperty(
        name="Loading", default="MACHINE", update=_method_update,
        description="How the car was loaded",
        items=[("MACHINE", "Machine", "From a chute or loader: evenly packed lumps, a smooth, "
                                      "uniform shape"),
               ("HAND", "Hand", "Shovelled by hand: lumps scattered at random, with mounds "
                                "and hollows")])
    hump_shape: EnumProperty(
        name="Shape", default="RIDGE", update=_changed,
        description="The load's overall shape, from level to heaped",
        items=[("LEVEL", "Level", "Level with the load's edge"),
               ("RIDGE", "Ridge", "Heaped along the middle of the car, like a chute-loaded car"),
               ("MOUND", "Mound", "One heap in the middle"),
               ("PEAKS", "Peaks", "A row of heaps along the car, one per loading spout or bay")])
    hump_height: _proto("Hump Height", 24.0,
                        "How far the top of the hump rises above the load's edge", soft_max=120.0)
    peaks: IntProperty(name="Peaks", default=2, min=1, max=8, update=_changed,
                       description="How many heaps along the car")
    edge_level: _proto("Edge Height", 0.0,
                       "Height of the load where it meets the car sides, above the top of "
                       "the sides (negative = below them)", soft_max=48.0, signed=True)
    variation: _proto("Mounds and Hollows", 0.0,
                      "Height of the random mounds and hollows in the load (hand loading "
                      "sets 12 in)", soft_max=48.0)

    # ---- shell ----
    thickness: _model("Thickness", 1.0, "Thickness of the hollow load's shell")
    skirt: _model("Skirt Depth", 3.0,
                  "How far the load's sides reach down into the car, below the load's edge")
    taper: _model("Taper", 0.5,
                  "How much smaller the load is at the bottom of its sides, each side; it "
                  "flares out to the full opening at the top so it drops in")
    fit_allowance: _model("Fit Allowance", 0.0,
                          "Taken off each side of the opening so the load fits; negative "
                          "makes it bigger for a tight fit", signed=True)
    printer: EnumProperty(
        name="Printer", default="RESIN", update=_changed,
        description="Printer type: sets the automatic grid and the too-small-to-print warnings",
        items=[("RESIN", "Resin", "Fine detail"), ("FDM", "FDM", "Filament printer")])

    # ---- build ----
    seed: IntProperty(name="Seed", default=0, min=0, update=_changed,
                      description="Number that picks the random lumps. Generate shows the "
                                  "seed it used here")
    lock_seed: BoolProperty(
        name="Lock Seed", default=False,
        description="Use the seed above for new loads instead of a random one, to repeat one "
                    "you liked")
    grid_auto: BoolProperty(name="Auto Grid", default=True, update=_changed,
                            description="Set the surface grid from the smallest lump size")
    grid: _model("Grid Spacing", 0.1, "Spacing of the surface grid; smaller shows more detail")
    max_cells: IntProperty(name="Max Grid Cells", default=400_000, min=10_000,
                           soft_max=2_000_000, update=_changed,
                           description="The grid is made coarser to stay under this many cells "
                                       "(the top has about twice as many triangles)")
    max_lumps: IntProperty(name="Max Lumps", default=60_000, min=100, soft_max=200_000,
                           update=_changed, description="At most this many lumps")
    show_outline: BoolProperty(
        name="Opening Outline", default=True, update=_changed,
        description="Add an outline of the car opening at the top of the sides, to check the "
                    "fit. It isn't exported")

    # ---- presets and output ----
    load_preset: StringProperty(default="", options={"HIDDEN"})
    load_modified: BoolProperty(default=False, options={"HIDDEN"})
    export_template: StringProperty(
        name="File Name", default="ore_load_{scale}_{ore}.stl",
        description="Default STL file name; {scale} and {ore} are filled in")
    last_report: StringProperty(default="", options={"HIDDEN"})
    show_info: BoolProperty(
        name="Show Info", default=True,
        description="Show the informational lines in the panel (summary, sizes, hints). Turn "
                    "off to see only the settings; errors and warnings are always shown")

    # ------------------------------------------------------------------

    def scale_n(self) -> float:
        """N in 1:N for the chosen scale."""
        return scales.scale_n(self.scale, self.scale_custom)

    def full_mm(self, key: str) -> float:
        """A prototype setting in full-size millimetres."""
        return scales.to_full_mm(getattr(self, key), self.proto_units)

    def model_mm(self, key: str) -> float:
        """A prototype setting scaled to model millimetres."""
        return self.full_mm(key) / self.scale_n()

    def opening(self) -> tuple[float, float]:
        """The car opening in model mm (length, width), before the fit allowance."""
        if self.size_mode == "MODEL":
            return self.model_length, self.model_width
        return self.model_mm("opening_length"), self.model_mm("opening_width")

    def spec(self, seed=None) -> LoadSpec:
        """The settings as a load.LoadSpec, in model millimetres."""
        length, width = self.opening()
        m = self.model_mm
        return LoadSpec(
            length=length - 2 * self.fit_allowance, width=width - 2 * self.fit_allowance,
            edge_level=m("edge_level"), hump_shape=self.hump_shape,
            hump_height=m("hump_height"), peaks=self.peaks, method=self.loading,
            variation=m("variation"), size_min=m("size_min"), size_max=m("size_max"),
            facets_min=self.facets_min, facets_max=self.facets_max, flatness=self.flatness,
            cap=self.cap, roundness=self.roundness, slope_jitter=self.slope_jitter,
            coverage=self.coverage, thickness=self.thickness, skirt=self.skirt,
            taper=self.taper, grid=0.0 if self.grid_auto else self.grid,
            max_cells=self.max_cells, max_lumps=self.max_lumps, printer=self.printer,
            seed=self.seed if seed is None else seed)

    # ---- ore and presets ----

    def apply_ore(self, key: str) -> None:
        """Fill in the lump sizes (converted to the chosen units) and shape for ore ``key``."""
        o = ores.get(key)
        with quiet():
            for k in ("size_min", "size_max"):
                setattr(self, k, scales.from_full_mm(scales.to_full_mm(getattr(o, k), "IN"),
                                                     self.proto_units))
            for k in ores.SHAPE_KEYS:
                setattr(self, k, getattr(o, k))

    def load_values(self) -> dict:
        """Every setting, for a load preset."""
        skip = {"rna_type", "name", "proto_units_prev", "load_preset", "load_modified",
                "last_report", "show_info"}
        return {p.identifier: getattr(self, p.identifier)
                for p in self.bl_rna.properties if p.identifier not in skip}

    def apply_load_values(self, values: dict, name: str) -> None:
        """Load a preset's values and select it as ``name``.

        Units first, so saved lengths aren't converted. Unknown keys and
        values this version rejects are skipped, so older presets load.
        """
        names = {p.identifier for p in self.bl_rna.properties}
        with quiet():
            if "proto_units" in values:
                self.proto_units = self.proto_units_prev = values["proto_units"]
            for key, value in values.items():
                if key in names and key != "proto_units":
                    try:
                        setattr(self, key, value)
                    except (TypeError, ValueError, AttributeError):
                        pass
            self.load_preset = name
            self.load_modified = False


def register():
    """Add ``scene.ore_load``. ORELOAD_Settings must already be registered."""
    bpy.types.Scene.ore_load = bpy.props.PointerProperty(type=ORELOAD_Settings)


def unregister():
    """Remove ``scene.ore_load``."""
    del bpy.types.Scene.ore_load
