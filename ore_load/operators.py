"""Operators: the buttons in the Ore Load panel. Each docstring is its tooltip."""

import os
import random

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ExportHelper

from . import build, preset_store
from .preset_store import PresetError


def _settings(context):
    """The scene's Ore Load settings."""
    return context.scene.ore_load


_busy = False


def is_busy() -> bool:
    """True while a load is being generated (the panel shows a wait message)."""
    return _busy


def _redraw(context):
    """Ask every area on the screen to redraw, so the panel shows the busy state."""
    screen = context.screen
    if screen:
        for area in screen.areas:
            area.tag_redraw()


class ORELOAD_OT_generate(bpy.types.Operator):
    """Add a new ore load at the 3D cursor from these settings, with a random seed unless Lock Seed is on. Loads made earlier are kept"""

    bl_idname = "ore_load.generate"
    bl_label = "Generate Ore Load"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None

    def _run(self, context, progress=None):
        """Build the load and report errors, warnings and the summary line."""
        try:
            result = build.generate(context, progress)
        except build.BuildError as err:
            for line in str(err).splitlines():
                self.report({"ERROR"}, line)
            _settings(context).last_report = str(err).splitlines()[0]
            return {"CANCELLED"}
        for w in result.warnings:
            self.report({"WARNING"}, w)
        self.report({"INFO"}, _settings(context).last_report)
        return {"FINISHED"}

    def execute(self, context):
        """Build straight away, with no wait message (scripts and the redo panel)."""
        return self._run(context)

    def invoke(self, context, event):
        """Show the wait message and busy cursor first, then build on the next timer tick."""
        global _busy
        if _busy:
            return {"CANCELLED"}
        _busy = True
        wm = context.window_manager
        context.window.cursor_modal_set("WAIT")
        if context.workspace:
            context.workspace.status_text_set("Generating ore load, please wait...")
        _redraw(context)
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        """On the first timer tick, build with a progress bar, then restore the cursor."""
        global _busy
        if event.type != "TIMER":
            return {"RUNNING_MODAL"}
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_begin(0, 1)
        try:
            return self._run(context, wm.progress_update)
        finally:
            wm.progress_end()
            context.window.cursor_modal_restore()
            if context.workspace:
                context.workspace.status_text_set(None)
            _busy = False
            _redraw(context)


class ORELOAD_OT_new_seed(bpy.types.Operator):
    """Pick a new random seed for a different arrangement of lumps"""

    bl_idname = "ore_load.new_seed"
    bl_label = "New Seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        """Set a random seed."""
        _settings(context).seed = random.randrange(1, 2**31 - 1)
        return {"FINISHED"}


class ORELOAD_OT_reset_ore(bpy.types.Operator):
    """Put the chosen ore's lump sizes and shape back to its defaults"""

    bl_idname = "ore_load.reset_ore"
    bl_label = "Reset Ore"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    def execute(self, context):
        """Fill in the ore's defaults again."""
        s = _settings(context)
        s.apply_ore(s.ore_type)
        return {"FINISHED"}


def _safe(name: str) -> str:
    """``name`` with characters a file name can't hold replaced by _ (spaces too)."""
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name)


class ORELOAD_OT_export_stl(bpy.types.Operator, ExportHelper):
    """Export the selected ore loads as STL files in millimetres, one file per load"""

    bl_idname = "ore_load.export_stl"
    bl_label = "Export STL"
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        """Only available when an ore load (or its outline) is selected."""
        return bool(build.selected_loads(context))

    def invoke(self, context, event):
        """Open the file browser on the default file name, next to the .blend file."""
        folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(folder, build.file_name(_settings(context)))
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        """Write each selected load to its own file (the outline is never written)."""
        loads = build.selected_loads(context)
        stem, ext = os.path.splitext(self.filepath)
        try:
            for obj in loads:
                path = self.filepath if len(loads) == 1 else f"{stem}_{_safe(obj.name)}{ext}"
                build.export_stl(context, [obj], path)
        except RuntimeError as err:
            self.report({"ERROR"}, f"Export failed: {err}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported {len(loads)} load(s) starting {os.path.basename(stem)}")
        return {"FINISHED"}


# ---- load presets ----

class ORELOAD_OT_apply_preset(bpy.types.Operator):
    """Fill in every setting from this saved load preset"""

    bl_idname = "ore_load.apply_preset"
    bl_label = "Apply Load Preset"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}
    name: StringProperty()

    def execute(self, context):
        """Load the saved preset's values into the settings."""
        try:
            values = preset_store.load(self.name)
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        stored = next((n for n in preset_store.saved_names()
                       if n.casefold() == self.name.casefold()), self.name)
        _settings(context).apply_load_values(values, stored)
        return {"FINISHED"}


class ORELOAD_OT_save_preset(bpy.types.Operator):
    """Save every current setting as a load preset, for example 'HO ore car, hard rock'"""

    bl_idname = "ore_load.save_preset"
    bl_label = "Save Load Preset"
    name: StringProperty(name="Name", description="Saving under an existing name replaces it")

    def invoke(self, context, event):
        """Ask for a name, suggesting the current preset."""
        self.name = _settings(context).load_preset
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Save every setting under the name."""
        name = preset_store.clean_name(self.name)
        if not name:
            self.report({"ERROR"}, "Give the preset a name.")
            return {"CANCELLED"}
        s = _settings(context)
        try:
            preset_store.save(name, s.load_values())
        except PresetError as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s.load_preset, s.load_modified = name, False
        self.report({"INFO"}, f"Saved load preset '{name}'.")
        return {"FINISHED"}


class ORELOAD_OT_remove_preset(bpy.types.Operator):
    """Delete one of your saved load presets"""

    bl_idname = "ore_load.remove_preset"
    bl_label = "Delete Load Preset"
    bl_options = {"INTERNAL"}
    name: StringProperty()

    def invoke(self, context, event):
        """Ask before deleting."""
        return context.window_manager.invoke_confirm(
            self, event, title=f"Delete load preset '{self.name}'?", confirm_text="Delete")

    def execute(self, context):
        """Delete the preset file, and clear the panel's preset name if it was this one."""
        try:
            preset_store.remove(self.name)
        except (PresetError, OSError) as err:
            self.report({"ERROR"}, str(err))
            return {"CANCELLED"}
        s = _settings(context)
        if s.load_preset == self.name:
            s.load_preset = ""
        return {"FINISHED"}


classes = (
    ORELOAD_OT_generate, ORELOAD_OT_new_seed, ORELOAD_OT_reset_ore, ORELOAD_OT_export_stl,
    ORELOAD_OT_apply_preset, ORELOAD_OT_save_preset, ORELOAD_OT_remove_preset,
)
