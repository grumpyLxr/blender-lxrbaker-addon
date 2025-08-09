bl_info = {
    "name": "LxrBaker",
    "description" : "Simplify Blender baking workflow",
    "doc_url": "https://github.com/grumpyLxr/blender-lxrbaker-addon",
    "version" : (1, 0, 0),
    "author": "grumpyLxr",
    "blender": (3, 5, 0),
    "category": "Render",
}

import importlib

addon_folder = "BlenderLxrBakerAddon"
modules = (
    ".object_bake_operator",
)

def import_modules():
    for mod in modules:
        importlib.import_module(mod, addon_folder)

def reimport_modules():
    '''
    Reimports the modules. Extremely useful while developing the addon.
    '''
    for mod in modules:
        # Reimporting modules during addon development
        want_reload_module = importlib.import_module(mod, addon_folder)
        importlib.reload(want_reload_module)   

import_modules()
reimport_modules()

from . import object_bake_operator

def register():
    print("Registering Add-on", bl_info["name"])
    object_bake_operator.register()


def unregister():
    print("Unregistering Add-on", bl_info["name"])
    object_bake_operator.unregister()