"""The Ore Load tab in the 3D Viewport sidebar (N panel)."""

import bpy

from . import load, operators, preset_store, scales


def _s(context):
    """The scene's Ore Load settings."""
    return context.scene.ore_load


def _u(s):
    """Short label for the prototype units: "in" or "mm"."""
    return "in" if s.proto_units == "IN" else "mm"


_last: list = [None, None]  # [spec key, (spec, plan)]


def compute(s):
    """(spec, plan) for the panel, recomputed only when the settings change."""
    spec = s.spec(seed=0)
    key = repr(spec)
    if _last[0] != key:
        _last[0], _last[1] = key, (spec, load.plan(spec))
    return _last[1]


def _hint(col, s, *lines):
    """Small grey info lines, shown only with Show Info on."""
    if not s.show_info:
        return
    sub = col.column()
    sub.scale_y = 0.8
    for i, line in enumerate(lines):
        sub.label(text=line, icon="INFO" if i == 0 else "BLANK1")


class ORELOAD_MT_presets(bpy.types.Menu):
    """Your saved load presets"""

    bl_label = "Load Presets"
    bl_idname = "ORELOAD_MT_presets"

    def draw(self, context):
        """Saved load presets, each with a delete button."""
        saved = preset_store.saved_names()
        if not saved:
            self.layout.label(text="No load presets saved yet")
        for name in saved:
            row = self.layout.row(align=True)
            row.operator("ore_load.apply_preset", text=name).name = name
            row.operator("ore_load.remove_preset", text="", icon="X").name = name


class _Panel:
    """Shared placement: the Ore Load tab in the 3D Viewport sidebar."""

    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Ore Load"


class ORELOAD_PT_main(_Panel, bpy.types.Panel):
    """Generate and export the ore load, and check its size"""

    bl_label = "Ore Load"

    def draw_header(self, context):
        """The Show Info toggle, beside the panel's name."""
        s = _s(context)
        self.layout.prop(s, "show_info", text="", icon="INFO" if s.show_info else "HIDE_ON",
                         emboss=False)

    def draw(self, context):
        """Presets, Generate and Export, then a live summary or the errors."""
        s = _s(context)
        col = self.layout.column()
        row = col.row(align=True)
        text = (s.load_preset or "Load Presets") + (
            " (modified)" if s.load_preset and s.load_modified else "")
        row.menu("ORELOAD_MT_presets", text=text)
        row.operator("ore_load.save_preset", text="", icon="ADD")

        spec, p = compute(s)
        row = col.row(align=True)
        row.scale_y = 1.4
        if operators.is_busy():
            row.alert = True
            row.label(text="Generating ore load, please wait...", icon="SORTTIME")
        else:
            row.enabled = not p.errors
            row.operator("ore_load.generate", icon="MESH_ICOSPHERE")
        col.operator("ore_load.export_stl", icon="EXPORT")
        if s.last_report and s.show_info:
            col.label(text=s.last_report)

        if p.errors:
            box = col.box()
            box.alert = True
            for e in p.errors:
                box.label(text=e, icon="ERROR")
            return
        if not s.show_info:
            if p.warnings:
                box = col.box()
                for w in p.warnings:
                    box.label(text=w, icon="ERROR")
            return
        n = s.scale_n()
        box = col.box()
        box.label(text=f"Load top {spec.length:.2f} x {spec.width:.2f} mm "
                       f"({scales.feet_inches(spec.length * n)} x "
                       f"{scales.feet_inches(spec.width * n)})", icon="INFO")
        box.label(text=f"Bottom of sides {p.bottom_length:.2f} x {p.bottom_width:.2f} mm, "
                       f"{-p.z_bottom:.2f} mm below the rim")
        box.label(text=f"Top of load {p.peak:.2f} mm above the rim (plus lumps)")
        box.label(text=f"Lumps {spec.size_min:.2f} to {spec.size_max:.2f} mm, about {p.lumps}")
        box.label(text=f"Grid {p.dx:.3f} mm, about {2 * p.nx * p.ny:,} triangles on top")
        for w in p.warnings:
            box.label(text=w, icon="ERROR")


class ORELOAD_PT_opening(_Panel, bpy.types.Panel):
    """The car opening the load drops into, and the scale"""

    bl_label = "Car Opening"
    bl_parent_id = "ORELOAD_PT_main"

    def draw(self, context):
        """Scale, prototype or model size, and the opening's length and width."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        col.prop(s, "scale")
        if s.scale == "CUSTOM":
            col.prop(s, "scale_custom")
        col.prop(s, "proto_units")
        col.separator()
        col.prop(s, "size_mode", expand=True)
        if s.size_mode == "PROTOTYPE":
            col.prop(s, "opening_length", text=f"Length ({u})")
            col.prop(s, "opening_width", text=f"Width ({u})")
            length, width = s.opening()
            if s.show_info:
                col.label(text=f"Model opening {length:.2f} x {width:.2f} mm", icon="INFO")
        else:
            col.prop(s, "model_length", text="Length (mm)")
            col.prop(s, "model_width", text="Width (mm)")
            _hint(col, s, "Measure inside the model car's", "opening, at the top of the sides.")
        col.prop(s, "show_outline")


class ORELOAD_PT_ore(_Panel, bpy.types.Panel):
    """The kind of ore and the size and shape of its lumps"""

    bl_label = "Ore"
    bl_parent_id = "ORELOAD_PT_main"

    def draw(self, context):
        """Ore type, lump sizes and density."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, "ore_type", text="")
        row.operator("ore_load.reset_ore", text="", icon="LOOP_BACK")
        col.prop(s, "size_min", text=f"Smallest Lump ({u})")
        col.prop(s, "size_max", text=f"Largest Lump ({u})")
        if s.show_info:
            n = s.scale_n()
            col.label(text=f"Model lumps {s.full_mm('size_min') / n:.2f} to "
                           f"{s.full_mm('size_max') / n:.2f} mm", icon="INFO")
        col.prop(s, "coverage")


class ORELOAD_PT_lump_shape(_Panel, bpy.types.Panel):
    """How angular, flat or rounded the lumps are"""

    bl_label = "Lump Shape"
    bl_parent_id = "ORELOAD_PT_ore"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Faces, height, flat top, roundness and face variation."""
        s = _s(context)
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, "facets_min")
        row.prop(s, "facets_max")
        col.prop(s, "flatness")
        col.prop(s, "cap")
        col.prop(s, "roundness")
        col.prop(s, "slope_jitter")
        _hint(col, s, "Choosing an ore fills these in.")


class ORELOAD_PT_shape(_Panel, bpy.types.Panel):
    """How the car was loaded and the load's overall shape"""

    bl_label = "Loading and Shape"
    bl_parent_id = "ORELOAD_PT_main"

    def draw(self, context):
        """Machine or hand loading, level to hump, edge height and mounds."""
        s, u = _s(context), _u(_s(context))
        col = self.layout.column()
        col.prop(s, "loading", expand=True)
        col.separator()
        col.prop(s, "hump_shape", expand=True)
        sub = col.column()
        sub.enabled = s.hump_shape != "LEVEL"
        sub.prop(s, "hump_height", text=f"Hump Height ({u})")
        if s.hump_shape == "PEAKS":
            col.prop(s, "peaks")
        col.prop(s, "edge_level", text=f"Edge Height ({u})")
        col.prop(s, "variation", text=f"Mounds and Hollows ({u})")
        _hint(col, s, "Edge Height is where the load meets", "the car sides, above the top of the",
              "sides; negative sits it lower.")


class ORELOAD_PT_shell(_Panel, bpy.types.Panel):
    """The hollow shell: thickness, and the tapered sides that drop into the car"""

    bl_label = "Shell and Fit"
    bl_parent_id = "ORELOAD_PT_main"

    def draw(self, context):
        """Thickness, skirt, taper, fit allowance and printer."""
        s = _s(context)
        col = self.layout.column()
        col.prop(s, "thickness", text="Thickness (mm)")
        col.prop(s, "skirt", text="Skirt Depth (mm)")
        col.prop(s, "taper", text="Taper (mm)")
        col.prop(s, "fit_allowance", text="Fit Allowance (mm)")
        col.prop(s, "printer", expand=True)
        _hint(col, s, "The load is hollow and open underneath.", "Its sides start Taper smaller "
              "at the", "bottom and flare out to the opening", "at the top, so it drops in.")


class ORELOAD_PT_build(_Panel, bpy.types.Panel):
    """Random seed, mesh detail and limits"""

    bl_label = "Build Options"
    bl_parent_id = "ORELOAD_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        """Seed, grid spacing and the cell and lump limits."""
        s = _s(context)
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, "seed")
        row.prop(s, "lock_seed", text="", icon="LOCKED" if s.lock_seed else "UNLOCKED")
        row.operator("ore_load.new_seed", text="", icon="FILE_REFRESH")
        row = col.row(align=True)
        row.prop(s, "grid_auto")
        sub = row.row()
        sub.enabled = not s.grid_auto
        sub.prop(s, "grid", text="Grid (mm)")
        col.prop(s, "max_cells")
        col.prop(s, "max_lumps")


classes = (
    ORELOAD_MT_presets,
    ORELOAD_PT_main, ORELOAD_PT_opening, ORELOAD_PT_ore, ORELOAD_PT_lump_shape,
    ORELOAD_PT_shape, ORELOAD_PT_shell, ORELOAD_PT_build,
)
