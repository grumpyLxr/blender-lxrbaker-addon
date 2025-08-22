bl_info = {
    "name": "LxrBaker",
    "description": "Simplify Blender baking workflow",
    "doc_url": "https://github.com/grumpyLxr/blender-lxrbaker-addon",
    "version": (1, 1, 0),
    "author": "grumpyLxr",
    "blender": (3, 5, 0),
    "category": "Render",
}

import os
import importlib

addon_folder = os.path.basename(os.path.dirname(os.path.realpath(__file__)))
modules = (
    ".log",
    ".object_bake_operator_properties",
    ".object_bake_operator",
)


def import_modules(reload: bool):
    """
    (Re)imports all modules.
    If reload is True all modules are reloaded even if they are already imported. This is useful during development.
    """
    print("\U0001f35e", bl_info["name"], ": Importing modules from", addon_folder)
    for mod in modules:
        module = importlib.import_module(mod, addon_folder)
        if reload:
            importlib.reload(module)


import_modules(True)

from . import log
from . import object_bake_operator


def register():
    log.log("Registering Add-on")
    object_bake_operator.register()


def unregister():
    log.log("Unregistering Add-on")
    object_bake_operator.unregister()
