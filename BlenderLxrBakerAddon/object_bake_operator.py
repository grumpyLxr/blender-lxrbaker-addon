from enum import Enum
import re
from typing import Final, Iterable, Self
import bpy
from bpy.types import (
    Context,
    Event,
    Image,
    UILayout,
    Material,
    Menu,
    NodeSocketFloat,
    Object,
    Operator,
    ShaderNodeBsdfPrincipled,
    ShaderNodeTexImage,
    ShaderNodeTree,
    Timer,
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
        if LxrObjectBakeOperator.is_valid_target_obj(obj):
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


class LxrObjectBakeOperator(Operator, LxrObjectBakeOperatorProperties):
    """Bakes the material to textures"""

    bl_idname = "object.lxrbaker_bake"
    bl_label = "Bake Material to Textures (LxrBaker)"
    bl_options = {"REGISTER"}

    _CUSTOM_PROP_NAME: Final[str] = "lxrbaker_properties"
    _pass_queue: list[BakingPass] = []
    _num_passes: int = 0
    _running_pass: BakingPass = None
    _timer: Timer = None
    _current_image_node: ShaderNodeTexImage = None

    @classmethod
    def poll(cls, context: Context) -> bool:
        return LxrObjectBakeOperator.is_valid_target_obj(context.active_object) and not bpy.app.is_job_running(
            "OBJECT_BAKE"
        )

    @classmethod
    def is_valid_target_obj(cls, obj: Object | None) -> bool:
        return (
            obj != None
            and obj.type == "MESH"
            and obj.select_get()
            and len(obj.material_slots.items()) > 0
            and obj.material_slots[0].material.node_tree != None
        )

    def get_target_object(self: Self) -> Object:
        return bpy.data.objects.get(self.target_object_prop)

    def get_target_material(self: Self) -> Material:
        return self.get_target_object().material_slots[0].material

    def draw(self: Self, _context: Context) -> None:
        self._draw_properties(self.layout)

    def invoke(self: Self, context: Context, _event: Event) -> set[str]:
        target_object = context.active_object
        if not LxrObjectBakeOperator.is_valid_target_obj(target_object):
            return "CANCELLED"

        self.target_object_prop = target_object.name_full
        self.copy_properties_from_dict(
            target_object.get(
                self._CUSTOM_PROP_NAME, LxrObjectBakeOperatorProperties(target_object).properties_to_dict()
            )
        )

        return context.window_manager.invoke_props_dialog(self)

    def modal(self: Self, context: Context, event: Event) -> set[str]:
        result: set[str] = {"PASS_THROUGH"}  # default: ignore event
        if event.type == "TIMER":
            result = self.bake_next_pass()
            if self._current_image_node != None:
                pass_number = self._num_passes - len(self._pass_queue)
                status_txt = str.format(
                    "\U0001f35e Baking ({}/{}): {} | Press END to cancel baking after current pass.",
                    pass_number,
                    self._num_passes,
                    self._current_image_node.image.name,
                )
                bpy.context.workspace.status_text_set(text=status_txt)
        elif event.type == "ESC" or event.type == "END":
            self.report({"WARNING"}, "Baking was cancelled.")
            result = {"CANCELLED"}

        if "FINISHED" in result or "CANCELLED" in result:
            if self._timer != None:
                context.window_manager.event_timer_remove(self._timer)
            self.cleanup_after_bake()
            bpy.context.workspace.status_text_set(text=None)
        return result

    def execute(self: Self, context: Context) -> set[str]:
        target_object = self.get_target_object()
        target_object[self._CUSTOM_PROP_NAME] = self.properties_to_dict()
        self._pass_queue = self.get_baking_passes()
        self._num_passes = len(self._pass_queue)
        self._running_pass = None
        context.window_manager.modal_handler_add(self)
        context.window_manager.event_timer_add(1.0, window=context.window)
        return {"RUNNING_MODAL"}

    def bake_next_pass(self: Self) -> set[str]:
        if bpy.app.is_job_running("OBJECT_BAKE"):
            return {"RUNNING_MODAL"}

        self.cleanup_after_bake()
        if len(self._pass_queue) == 0:
            return {"FINISHED"}

        next_pass = self._pass_queue.pop()
        self.bake_image_pass(next_pass)
        return {"RUNNING_MODAL"}

    def cleanup_after_bake(self: Self) -> None:
        if self._current_image_node != None:
            self.save_result_image(self._current_image_node.image)
            self.get_target_material().node_tree.nodes.remove(self._current_image_node)
            self._current_image_node = None
        if self._running_pass == BakingPass.METALLIC:
            node_tree = self.get_target_material().node_tree
            bsdf_node = self.get_principled_bsdf_node(node_tree)
            if bsdf_node != None:
                self.switch_metallic_and_roughness(node_tree, bsdf_node)
        self._running_pass = None

    def bake_image_pass(self: Self, baking_pass: BakingPass) -> None:
        pass_config = baking_pass.value
        # Create Image:
        img_name: str = self.get_image_name(baking_pass)
        img: Image = bpy.data.images.get(img_name)
        # If the image contains no data we cannot reuse it. Thus we rename it and create a new image.
        if img != None:
            if not img.has_data or (img.alpha_mode == "NONE" and pass_config.use_alpha) or img.type != "IMAGE":
                old_name = img.name
                img.name = img.name + "_old"
                self.report(
                    {"WARNING"},
                    str.format(
                        "Image '{}' has invalid data. Renaming to '{}' and creating a new image", old_name, img.name
                    ),
                )
                img = None  # create new image

        if img == None:
            img = bpy.data.images.new(
                img_name, self.image_width_prop, self.image_height_prop, alpha=pass_config.use_alpha
            )
        else:
            print("Image", img_name, "already exists. Overwriting existing image ...")
            if img.size[0] != self.image_width_prop or img.size[1] != self.image_height_prop:
                print("Scaling image to", self.image_width_prop, "x", self.image_height_prop, "...")
                # pack the image into the .blend file to not change external image file before the baking.
                pack_image(img)
                img.scale(self.image_width_prop, self.image_height_prop)
                # save scaling
                pack_image(img)
        img.alpha_mode = "STRAIGHT" if pass_config.use_alpha else "NONE"
        img.colorspace_settings.is_data = not pass_config.is_color

        # Create Image Material Node:
        mat_nodes = self.get_target_material().node_tree.nodes
        self._current_image_node = mat_nodes.new("ShaderNodeTexImage")
        self._current_image_node.image = img
        self._current_image_node.select = True
        mat_nodes.active = self._current_image_node

        if baking_pass == BakingPass.METALLIC:
            node_tree = self.get_target_material().node_tree
            bsdf_node = self.get_principled_bsdf_node(node_tree)
            if bsdf_node == None:
                self.report({"WARNING"}, "Cannot bake metallic pass. Could not find Principled BSDF Node.")
                return
            self.switch_metallic_and_roughness(node_tree, bsdf_node)

        # Start Baking:
        self._running_pass = baking_pass
        pass_str: str = BakingPass.ROUGHNESS.value.type if baking_pass == BakingPass.METALLIC else pass_config.type
        bpy.ops.object.bake(
            "INVOKE_DEFAULT",
            type=pass_str,
            # Only use color for the DIFFUSE pass, no lighting.
            pass_filter={"COLOR"},
            target="IMAGE_TEXTURES",
            use_clear=True,
            uv_layer=self.uv_map_prop,
            margin=self.uv_seam_margin_prop,
            margin_type="ADJACENT_FACES",
        )

    def get_principled_bsdf_node(self: Self, node_tree: ShaderNodeTree) -> ShaderNodeBsdfPrincipled:
        bsdf_nodes = [n for n in node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"]
        if len(bsdf_nodes) > 1:
            self.report({"WARNING"}, "Baked metallic pass might be wrong. Found more than one Principled BSDF Node.")
        return None if len(bsdf_nodes) == 0 else bsdf_nodes[0]

    def switch_metallic_and_roughness(
        self: Self, node_tree: ShaderNodeTree, bsdf_node: ShaderNodeBsdfPrincipled
    ) -> None:
        metallic: NodeSocketFloat = bsdf_node.inputs.get("Metallic")
        roughness: NodeSocketFloat = bsdf_node.inputs.get("Roughness")
        # Switch default value:
        metallic_value = metallic.default_value
        metallic.default_value = roughness.default_value
        roughness.default_value = metallic_value
        # Switch connected nodes:
        metallic_linked_sockets = [s.from_socket for s in metallic.links]
        roughness_linked_sockets = [s.from_socket for s in roughness.links]
        for socket in metallic.links:
            node_tree.links.remove(socket)
        for socket in roughness.links:
            node_tree.links.remove(socket)
        for socket in metallic_linked_sockets:
            node_tree.links.new(socket, roughness)
        for socket in roughness_linked_sockets:
            node_tree.links.new(socket, metallic)

    def get_image_path(self: Self, img_name: str) -> str:
        img_path = re.sub(r"[^\w_.-/]", "_", self.image_path_prop)  # remove illegal characters
        img_name = bpy.path.clean_name(img_name)  # remove illegal characters
        return str.format("{}{}.png", img_path if img_path.endswith("/") else img_path + "/", img_name)

    def save_result_image(self: Self, img: Image) -> None:
        if not img.has_data:
            self.report({"WARNING"}, "Cannot save image " + img.name + " because it has not data.")
            return
        if self.is_image_save_to_file_prop:
            # We first have to save to an *absolute* path (i.e. not relative to blend file).
            # Then we can set the filepath property on the image. The reload tests if everything worked.
            file_path = self.get_image_path(img.name)
            print("Saving image", img.name, "to file:", file_path)
            img.save(filepath=bpy.path.abspath(file_path))
            if is_image_packed(img):
                img.unpack(method="REMOVE")
            img.filepath = file_path
            img.reload()
        else:
            print("Packing image", img.name, "into .blend file.")
            pack_image(img)


def is_image_packed(img: Image) -> bool:
    return img.packed_file != None


def pack_image(img: Image) -> bool:
    """Packs the image as embedded data into the .blend file. In case the image is already packed changes are saved."""
    img.pack()
    if img.filepath != "":
        img.filepath = ""


def object_texture_bake_menu_draw(menu: Menu, _context: Context) -> None:
    menu.layout.operator(LxrObjectBakeOperator.bl_idname)


def register():
    bpy.utils.register_class(LxrObjectBakeOperator)
    bpy.types.VIEW3D_MT_object.append(object_texture_bake_menu_draw)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(object_texture_bake_menu_draw)
    bpy.utils.unregister_class(LxrObjectBakeOperator)
