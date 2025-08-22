from enum import Enum
from typing import Iterable, Self
import bpy
from bpy.types import (
    Context,
    UILayout,
    Object,
)
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty


class BakingPassConfiguration:
    type: str
    use_alpha: bool
    is_color: bool

    def __init__(self: Self, type: str, use_alpha: bool, is_color: bool):
        self.type = type
        self.use_alpha = use_alpha
        self.is_color = is_color


class BakingPass(Enum):
    DIFFUSE = BakingPassConfiguration("DIFFUSE", False, True)
    DIFFUSE_WITH_ALPHA = BakingPassConfiguration("DIFFUSE", True, True)
    ROUGHNESS = BakingPassConfiguration("ROUGHNESS", False, False)
    METALLIC = BakingPassConfiguration("METALLIC", False, False)
    NORMAL = BakingPassConfiguration("NORMAL", False, False)
    EMIT = BakingPassConfiguration("EMIT", False, True)


class LxrObjectBakeOperatorProperties:
    """Properties that the user can configure for the LxrObjectBakeOperator."""

    # We have to store the target object name in a property because in an EnumProperty callback function you only have
    # access to Blener properties. You cannot access Python properties.
    target_object_prop: StringProperty(
        name="Active Object", description="The name of the object to which the operator is applied.", options={"HIDDEN"}
    )  # type: ignore

    image_name_prop: StringProperty(
        name="Images Name",
        description="The base name of the images that are created. The pass name (e.g. diffuse, roughness, normal) will be added to the base name",
    )  # type: ignore
    is_image_save_to_file_prop: BoolProperty(
        name="Save Images to Filesystem",
        description="Checked: save generated images externally. Unchecked: save images internally in .blend file.",
    )  # type: ignore
    image_path_prop: StringProperty(
        name="Images Path",
        description="The path where the images are saved.",
        default="//",
        options={"ANIMATABLE", "PATH_SUPPORTS_BLEND_RELATIVE"},
        subtype="DIR_PATH",
    )  # type: ignore

    image_width_prop: IntProperty(
        name="Images Width",
        description="The width of the generated images.",
        min=1,
        soft_min=1,
        soft_max=8192,
        subtype="PIXEL",
    )  # type: ignore
    image_height_prop: IntProperty(
        name="Images Height",
        description="The height of the generated images.",
        min=1,
        soft_min=1,
        soft_max=8192,
        subtype="PIXEL",
    )  # type: ignore

    uv_seam_margin_prop: IntProperty(
        name="UV Seam Margin",
        description="Extends the baked pixels at UV seams.",
        min=0,
        soft_min=0,
        soft_max=16,
        subtype="PIXEL",
    )  # type: ignore

    def get_target_object_uv_maps(self: Self, _context: Context = None) -> Iterable[tuple[str, str, str]]:
        obj = bpy.data.objects.get(self.target_object_prop)
        if obj != None and obj.type == "MESH":
            return [(uv.name, uv.name, "") for uv in obj.data.uv_layers]
        return [("NONE", "None", "")]

    uv_map_prop: EnumProperty(
        name="UV Map", description="UV Map to use for the generated images", items=get_target_object_uv_maps, default=0
    )  # type: ignore

    is_diffuse_pass_prop: BoolProperty(name="Diffuse", description="Bake Diffuse pass.")  # type: ignore
    is_alpha_pass_prop: BoolProperty(name="with alpha", description="Bake Diffuse pass with alpha.")  # type: ignore
    is_roughness_pass_prop: BoolProperty(name="Roughness", description="Bake Roughness pass.")  # type: ignore
    is_metallic_pass_prop: BoolProperty(name="Metallic", description="Bake Metallic pass.")  # type: ignore
    is_normal_pass_prop: BoolProperty(name="Normal", description="Bake Normal pass.")  # type: ignore
    is_emit_pass_prop: BoolProperty(name="Emit", description="Bake Emit pass.")  # type: ignore

    def __init__(self, blender_object: Object = None) -> None:
        self.image_name_prop = "" if blender_object == None else blender_object.name
        self.is_image_save_to_file_prop = False
        self.image_path_prop = "//"
        self.image_width_prop = 1024
        self.image_height_prop = 1024
        self.uv_seam_margin_prop = bpy.context.scene.render.bake_margin
        self.uv_map_prop = "NONE"
        self.is_diffuse_pass_prop = True
        self.is_alpha_pass_prop = False
        self.is_roughness_pass_prop = True
        self.is_metallic_pass_prop = False
        self.is_normal_pass_prop = True
        self.is_emit_pass_prop = False

    def get_baking_passes(self: Self) -> list[BakingPass]:
        passes = [
            (self.is_diffuse_pass_prop and not self.is_alpha_pass_prop, BakingPass.DIFFUSE),
            (self.is_diffuse_pass_prop and self.is_alpha_pass_prop, BakingPass.DIFFUSE_WITH_ALPHA),
            (self.is_roughness_pass_prop, BakingPass.ROUGHNESS),
            (self.is_metallic_pass_prop, BakingPass.METALLIC),
            (self.is_normal_pass_prop, BakingPass.NORMAL),
            (self.is_emit_pass_prop, BakingPass.EMIT),
        ]
        return [p[1] for p in passes if p[0] == True]

    def get_image_name(self: Self, baking_pass: BakingPass) -> str:
        return self.image_name_prop + "-" + baking_pass.value.type.lower()

    def copy_properties_from(self: Self, other: Self) -> Self:
        return self.copy_properties_from_dict(other.properties_to_dict())

    def copy_properties_from_dict(self: Self, dictionary: dict = None) -> Self:
        if dictionary.__contains__("image_name_prop"):
            self.image_name_prop = dictionary["image_name_prop"]
        if dictionary.__contains__("is_image_save_to_file_prop"):
            self.is_image_save_to_file_prop = dictionary["is_image_save_to_file_prop"]
        if dictionary.__contains__("image_path_prop"):
            self.image_path_prop = dictionary["image_path_prop"]
        if dictionary.__contains__("image_width_prop"):
            self.image_width_prop = dictionary["image_width_prop"]
        if dictionary.__contains__("image_height_prop"):
            self.image_height_prop = dictionary["image_height_prop"]
        if dictionary.__contains__("uv_seam_margin_prop"):
            self.uv_seam_margin_prop = dictionary["uv_seam_margin_prop"]
        if dictionary.__contains__("uv_map_prop"):
            # Only copy value from dictionary if it is a valid enum value. Otherwise Blender will raise an error.
            all_uv_map_enum_values = [t[0] for t in self.get_target_object_uv_maps()]
            if dictionary["uv_map_prop"] in all_uv_map_enum_values:
                self.uv_map_prop = dictionary["uv_map_prop"]
        if dictionary.__contains__("is_diffuse_pass_prop"):
            self.is_diffuse_pass_prop = dictionary["is_diffuse_pass_prop"]
        if dictionary.__contains__("is_alpha_pass_prop"):
            self.is_alpha_pass_prop = dictionary["is_alpha_pass_prop"]
        if dictionary.__contains__("is_roughness_pass_prop"):
            self.is_roughness_pass_prop = dictionary["is_roughness_pass_prop"]
        if dictionary.__contains__("is_metallic_pass_prop"):
            self.is_metallic_pass_prop = dictionary["is_metallic_pass_prop"]
        if dictionary.__contains__("is_normal_pass_prop"):
            self.is_normal_pass_prop = dictionary["is_normal_pass_prop"]
        if dictionary.__contains__("is_emit_pass_prop"):
            self.is_emit_pass_prop = dictionary["is_emit_pass_prop"]
        return self

    def properties_to_dict(self: Self) -> dict:
        return {
            "image_name_prop": self.image_name_prop,
            "is_image_save_to_file_prop": self.is_image_save_to_file_prop,
            "image_path_prop": self.image_path_prop,
            "image_width_prop": self.image_width_prop,
            "image_height_prop": self.image_height_prop,
            "uv_seam_margin_prop": self.uv_seam_margin_prop,
            "uv_map_prop": self.uv_map_prop,
            "is_diffuse_pass_prop": self.is_diffuse_pass_prop,
            "is_alpha_pass_prop": self.is_alpha_pass_prop,
            "is_roughness_pass_prop": self.is_roughness_pass_prop,
            "is_metallic_pass_prop": self.is_metallic_pass_prop,
            "is_normal_pass_prop": self.is_normal_pass_prop,
            "is_emit_pass_prop": self.is_emit_pass_prop,
        }

    def _draw_properties(self: Self, layout: UILayout) -> None:
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        img_name_box = layout.box()
        img_name_box.prop(self, "image_name_prop")
        img_name_box.prop(self, "is_image_save_to_file_prop")
        if self.is_image_save_to_file_prop == True:
            img_name_box.prop(self, "image_path_prop")

        img_size_box = layout.box()
        img_size_box.prop(self, "image_width_prop", slider=True)
        img_size_box.prop(self, "image_height_prop", slider=True)
        img_size_box.prop(self, "uv_seam_margin_prop")
        img_size_box.prop(self, "uv_map_prop")

        passes_box = layout.box()
        passes_column = passes_box.column(align=False, heading="Baking passes")
        diffuse_pass_row = passes_column.row()
        diffuse_pass_row.prop(self, "is_diffuse_pass_prop")
        if self.is_diffuse_pass_prop:
            diffuse_pass_row.prop(self, "is_alpha_pass_prop")
        passes_column.prop(self, "is_roughness_pass_prop")
        passes_column.prop(self, "is_metallic_pass_prop")
        passes_column.prop(self, "is_normal_pass_prop")
        passes_column.prop(self, "is_emit_pass_prop")

        img_names = [self.get_image_name(p) for p in self.get_baking_passes()]
        existing_images = [n for n in img_names if bpy.data.images.get(n) != None]
        if len(existing_images) > 0:
            warning_box = layout.box()
            split = warning_box.split(factor=0.08)
            c1 = split.column()
            c1.label(text="", icon="WARNING_LARGE")
            c2 = split.column()
            c2.label(text="Images already exist and will be overwritten:")
            for img_name in existing_images:
                c2.label(text="  \u2022 " + img_name)
