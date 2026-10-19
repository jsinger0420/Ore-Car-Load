"""Builds the load object in Blender and exports it as STL.

Each Generate adds a new load at the 3D cursor; loads made earlier are
kept. The load's origin is the middle of the car opening at the top of the
car sides, so it can be snapped onto a car model. An optional outline of
the opening (not exported) is parented to it to check the fit.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import bpy
import numpy as np

from . import load, ores
from .scales import scale_label

LOAD_TAG = "ore_load"            # on every load object
PART_TAG = "ore_load_part"       # on the opening outline ("OUTLINE")


class BuildError(RuntimeError):
    """The load couldn't be made; the message says why."""


@dataclass
class BuildResult:
    """The new load object, the built load and any warnings."""

    obj: object
    load: load.Load
    warnings: list


def set_scene_millimetres(scene) -> None:
    """Show the scene in millimetres, one Blender unit being one millimetre."""
    us = scene.unit_settings
    if us.system != "METRIC" or abs(us.scale_length - 0.001) > 1e-9:
        us.system = "METRIC"
        us.scale_length = 0.001
        us.length_unit = "MILLIMETERS"


def is_load(obj) -> bool:
    """True for a load made by this add-on."""
    return obj is not None and obj.type == "MESH" and bool(obj.get(LOAD_TAG))


def selected_loads(context) -> list:
    """The selected loads, each once; a selected outline counts as its load."""
    out = []
    for o in context.selected_objects:
        if o.get(PART_TAG) and is_load(o.parent):
            o = o.parent
        if is_load(o) and o not in out:
            out.append(o)
    return out


def mesh_from_arrays(name: str, verts: np.ndarray, tris: np.ndarray) -> bpy.types.Mesh:
    """A new Blender mesh from vertex and triangle arrays."""
    mesh = bpy.data.meshes.new(name)
    mesh.vertices.add(len(verts))
    mesh.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    mesh.loops.add(len(tris) * 3)
    mesh.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
    mesh.polygons.add(len(tris))
    mesh.polygons.foreach_set("loop_start", np.arange(0, len(tris) * 3, 3, dtype=np.int32))
    mesh.update()
    mesh.validate()
    return mesh


def _material(ore_key: str) -> bpy.types.Material:
    """A plain material in the ore's colour, shared by every load of that ore."""
    o = ores.get(ore_key)
    name = f"Ore Load {o.label}"
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = (*o.color, 1.0)
        mat.roughness = 0.35 if o.key == "COAL" else 0.9
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (*o.color, 1.0)
            bsdf.inputs["Roughness"].default_value = mat.roughness
    return mat


def _outline(name: str, length: float, width: float, coll) -> bpy.types.Object:
    """A wire rectangle: the car opening at the top of the sides."""
    hl, hw = length / 2, width / 2
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(-hl, -hw, 0), (hl, -hw, 0), (hl, hw, 0), (-hl, hw, 0)],
                     [(0, 1), (1, 2), (2, 3), (3, 0)], [])
    obj = bpy.data.objects.new(name, mesh)
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj.hide_select = False
    obj[PART_TAG] = "OUTLINE"
    coll.objects.link(obj)
    return obj


def generate(context, progress=None) -> BuildResult:
    """Build a load from the scene's settings and add it at the 3D cursor."""
    s = context.scene.ore_load
    if not s.lock_seed:
        s.seed = random.randrange(1, 2**31 - 1)
    spec = s.spec()
    try:
        built = load.build(spec, progress)
    except load.LoadError as err:
        raise BuildError(str(err)) from None

    set_scene_millimetres(context.scene)
    coll = context.collection or context.scene.collection
    ore = ores.get(s.ore_type)
    name = f"Ore Load {ore.label} {scale_label(s.scale, s.scale_custom)}"
    mesh = mesh_from_arrays(name, built.vertices, built.triangles)
    mesh.materials.append(_material(s.ore_type))
    obj = bpy.data.objects.new(name, mesh)
    obj[LOAD_TAG] = True
    obj["ore_load_seed"] = int(spec.seed)
    obj["ore_load_size_mm"] = f"{spec.length:.2f} x {spec.width:.2f}"
    obj.location = context.scene.cursor.location
    coll.objects.link(obj)
    if s.show_outline:
        length, width = s.opening()
        line = _outline(name + " Opening", length, width, coll)
        line.parent = obj

    for o in context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj

    ml = built.volume / 1000.0
    s.last_report = (f"{built.lumps} lumps, {len(built.triangles):,} triangles, "
                     f"about {ml:.1f} ml of resin, seed {spec.seed}")
    return BuildResult(obj, built, built.warnings)


def file_name(s) -> str:
    """The default STL file name from the settings' template."""
    ore = ores.get(s.ore_type).label.lower().replace(" ", "_")
    try:
        name = s.export_template.format(scale=scale_label(s.scale, s.scale_custom), ore=ore)
    except (KeyError, IndexError, ValueError):
        name = s.export_template
    return name if name.lower().endswith(".stl") else name + ".stl"


def export_stl(context, objects, path: str) -> None:
    """Write exactly ``objects`` to one STL file in millimetres, restoring the selection after."""
    before = list(context.selected_objects)
    active = context.view_layer.objects.active
    for o in before:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    try:
        bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0,
                              use_scene_unit=False, ascii_format=False, apply_modifiers=True)
    finally:
        for o in objects:
            o.select_set(False)
        for o in before:
            o.select_set(True)
        context.view_layer.objects.active = active
