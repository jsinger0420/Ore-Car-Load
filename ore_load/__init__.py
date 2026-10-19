"""Ore Load Generator: 3D-printable loads for model railroad ore cars.

Builds a hollow load that drops into an ore car's opening: hard rock,
coal, iron ore, limestone or gravel lumps on a level, ridged, mounded or
peaked surface, machine- or hand-loaded, as a shell (1 mm by default) open
underneath, with sides that taper so the load drops in and wedges at the
top of the car sides. Exported as an STL in millimetres.

The geometry (scales.py, ores.py, load.py, shell.py) is plain Python with
no bpy, so it can be tested outside Blender. Blender modules are only
imported in ``register``.
"""


def _load():
    """Import the Blender-only modules; returns (properties, operators, ui)."""
    from . import build, operators, properties, ui  # noqa: F401
    return properties, operators, ui


def _classes():
    """Every Blender class to register, in registration order."""
    properties, operators, ui = _load()
    return (properties.ORELOAD_Settings,) + operators.classes + ui.classes


def register():
    """Register the classes and add the Ore Load settings to every scene."""
    import bpy
    for cls in _classes():
        bpy.utils.register_class(cls)
    _load()[0].register()


def unregister():
    """Remove the scene settings and unregister the classes."""
    import bpy
    _load()[0].unregister()
    for cls in reversed(_classes()):
        bpy.utils.unregister_class(cls)
