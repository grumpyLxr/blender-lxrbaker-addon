import re
import bpy
from bpy.types import (
    Image,
)
from . import log


def get_image(img_name: str) -> Image:
    return bpy.data.images.get(img_name)

def get_image_path(img_path: str, img_name: str) -> str:
    img_path = re.sub(r"[^\w_.-/]", "_", img_path)  # remove illegal characters
    img_name = bpy.path.clean_name(img_name)  # remove illegal characters
    return str.format("{}{}.png", img_path if img_path.endswith("/") else img_path + "/", img_name)


def save_result_image(img: Image, image_path: str, save_to_file: bool) -> None:
    if not img.has_data:
        raise RuntimeError("Cannot save image {} because it has not data.".format(img.name))
    if save_to_file:
        # We first have to save to an *absolute* path (i.e. not relative to blend file).
        # Then we can set the filepath property on the image. The reload tests if everything worked.
        file_path = get_image_path(image_path, img.name)
        log.log("Saving image '{}' to file: {}", img.name, file_path)
        img.save(filepath=bpy.path.abspath(file_path))
        if is_image_packed(img):
            img.unpack(method="REMOVE")
        img.filepath = file_path
        img.reload()
    else:
        log.log("Packing image '{}' into .blend file.", img.name)
        pack_image(img)


def is_image_packed(img: Image) -> bool:
    return img.packed_file != None


def pack_image(img: Image) -> bool:
    """Packs the image as embedded data into the .blend file. In case the image is already packed changes are saved."""
    img.pack()
    if img.filepath != "":
        img.filepath = ""
