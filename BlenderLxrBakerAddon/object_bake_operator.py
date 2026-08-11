from enum import Enum
import time
from typing import Final, Self, cast
import bpy
from bpy.types import (
    Context,
    Event,
    Image,
    Material,
    Menu,
    NodeSocketFloat,
    NodeSocket,
    ShaderNodeGroup,
    Object,
    Operator,
    ShaderNode,
    ShaderNodeBsdfPrincipled,
    ShaderNodeTexImage,
    ShaderNodeTree,
    Timer,
)
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from . import image_utils
from . import log
from .object_bake_operator_properties import BakingPass, LxrObjectBakeOperatorProperties


class NodeSocketState:
    def __init__(self: Self, value: float, connected_sockets: list[NodeSocket]):
        self.value: float = value
        self.connected_sockets: list[NodeSocket] = connected_sockets


class BsdfChanges:
    """Changes to a ShaderNodeBsdfPrincipled made during baking"""
    def __init__(self: Self):
        self.metallic_socket: NodeSocketState | None = None
        self.roughness_socket: NodeSocketState | None = None


class MaterialChanges:
    """Keeps track of all changes the materials that the operator does while baking. These changes are reverted when
    the baking is finished."""
    def __init__(self: Self):
         # A list of all temporary texture nodes that were created
        self.new_texture_nodes: list[ShaderNodeTexImage] = []
        # The changes to the BSDF Prinicpled nodes
        self.bsdf_changes: dict[ShaderNodeBsdfPrincipled, BsdfChanges] = {}



class LxrObjectBakeOperator(Operator, LxrObjectBakeOperatorProperties):
    """Bakes the material to textures"""

    bl_idname = "object.lxrbaker_bake"
    bl_label = "Bake Material to Textures (LxrBaker)"
    bl_options = {"REGISTER"}

    # The interval in seconds between timer events.
    _TIMER_INTERVAL_SECONDS: float = 1.0
    # When calling the baking operator it may take some time until Blender reports that the baking is in progrss.
    # We wait at least the given amount of time until we check if the baking process is done.
    _MIN_BAKE_TIME: float = 2.0
    _CUSTOM_PROP_NAME: Final[str] = "lxrbaker_properties"

    _previous_render_engine: str = ""
    _pass_queue: list[BakingPass] = []
    _num_passes: int = 0
    _running_pass: BakingPass = None
    _timer: Timer = None
    _pass_start_time: float = 0.0
    _material_changes: MaterialChanges = None

    @classmethod
    def poll(cls, context: Context) -> bool:
        return LxrObjectBakeOperator.is_valid_target_obj(context.active_object) and not bpy.app.is_job_running(
            "OBJECT_BAKE"
        )

    @classmethod
    def is_valid_target_obj(cls: type[Self], obj: Object | None) -> bool:
        return (
            obj != None
            and obj.type == "MESH"
            and obj.select_get()
            and len(LxrObjectBakeOperator.get_valid_materials(obj)) > 0
        )

    @classmethod
    def get_valid_materials(cls: type[Self], obj: Object) -> list[Material]:
        return [m.material for m in obj.material_slots if m.material.use_nodes]

    def get_target_object(self: Self) -> Object:
        return bpy.data.objects.get(self.target_object_prop)

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
            if self._material_changes != None:
                try:
                    image_names = ",".join([n.image.name for n in self._material_changes.new_texture_nodes])
                    pass_number = self._num_passes - len(self._pass_queue)
                    status_txt = str.format(
                        "\U0001f35e Baking ({}/{}): {} | Press END to cancel baking after current pass.",
                        pass_number,
                        self._num_passes,
                        image_names,
                    )
                    bpy.context.workspace.status_text_set(text=status_txt)
                except Exception as ex:
                    # Log and otherwise ignore all exceptions because failing to set the status text is not a 
                    # critical error.
                    log.warn(self, str(ex))
        elif event.type == "ESC" or event.type == "END":
            log.warn(self, "Baking was cancelled.")
            result = {"CANCELLED"}

        if "FINISHED" in result or "CANCELLED" in result:
            log.log("Baking finished with result {}. Cleaning up ...", result)
            if self._timer != None:
                context.window_manager.event_timer_remove(self._timer)
            log.log("... Timer removed")
            self.cleanup_after_bake()
            log.log("... Data cleaned")
            if self._previous_render_engine != "":
                context.scene.render.engine = self._previous_render_engine
                log.log("... Restored rendering engine to {}", self._previous_render_engine)
                self._previous_render_engine = ""
            bpy.context.workspace.status_text_set(text=None)
            log.log("Finished cleaning up!")
        return result

    def execute(self: Self, context: Context) -> set[str]:
        target_object = self.get_target_object()
        target_object[self._CUSTOM_PROP_NAME] = self.properties_to_dict()
        self._pass_queue = self.get_baking_passes()
        self._num_passes = len(self._pass_queue)
        self._running_pass = None
        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(self._TIMER_INTERVAL_SECONDS, window=context.window)
        self._previous_render_engine = context.scene.render.engine
        if self._previous_render_engine.upper() != "CYCLES":
            log.log("Changing rendering engine from {} to CYCLES.", self._previous_render_engine)
            context.scene.render.engine = "CYCLES"
        return {"RUNNING_MODAL"}

    def bake_next_pass(self: Self) -> set[str]:
        if bpy.app.is_job_running("OBJECT_BAKE") or (time.time() - self._pass_start_time) < self._MIN_BAKE_TIME:
            return {"RUNNING_MODAL"}

        self.cleanup_after_bake()
        if len(self._pass_queue) == 0:
            return {"FINISHED"}

        next_pass = self._pass_queue.pop()
        self.bake_image_pass(next_pass)
        return {"RUNNING_MODAL"}

    def cleanup_after_bake(self: Self) -> None:
        mat_changes = self._material_changes
        if mat_changes != None:
            # Save all images:
            for img in set([n.image for n in mat_changes.new_texture_nodes]):
                try:
                    image_utils.save_result_image(img, self.image_path_prop, self.is_image_save_to_file_prop)
                except Exception as ex:
                    log.warn(self, str(ex))
            # Revert all changes to the materials:
            for tex_node in mat_changes.new_texture_nodes:
                log.log("Removing temporary image node: {}", tex_node.name)   
                texture_node_tree: ShaderNodeTree = self.get_node_tree(tex_node) # Retrieve the parent ShaderNodeTree
                texture_node_tree.nodes.remove(tex_node)
            for bsdf_node, bsdf_node_changes in mat_changes.bsdf_changes.items():
                log.log("Restoring connections on node: {}", [bsdf_node.name, self.get_node_tree(bsdf_node).name] )
                if bsdf_node_changes.metallic_socket != None:
                    self.restore_node_input_connections(bsdf_node, "Metallic", bsdf_node_changes.metallic_socket)
                if bsdf_node_changes.roughness_socket != None:
                    self.restore_node_input_connections(bsdf_node, "Roughness", bsdf_node_changes.roughness_socket)
        self._material_changes = None
        self._running_pass = None

    def bake_image_pass(self: Self, baking_pass: BakingPass) -> None:
        pass_config = baking_pass.value
        material_changes = MaterialChanges()
        
        # Get or create Image:
        img_name: str = self.get_image_name(baking_pass)
        img = self.get_or_create_image(baking_pass, img_name)

        # Create Image Material Nodes and find BSDF Principled nodes:
        all_bsdf_nodes: set[ShaderNodeBsdfPrincipled] = set()
        for material in LxrObjectBakeOperator.get_valid_materials(self.get_target_object()):
            node_tree = material.node_tree
            img_node: ShaderNodeTexImage = node_tree.nodes.new("ShaderNodeTexImage")
            img_node.image = img
            img_node.select = True
            node_tree.nodes.active = img_node
            material_changes.new_texture_nodes.append(img_node)
            all_bsdf_nodes.update(self.get_principled_bsdf_nodes(node_tree))
        
        log.log("Created the following temporary image nodes: {}",  [n.name for n in material_changes.new_texture_nodes])    
        log.log(
            "Found the following BSDF Principled shader nodes: {}", 
            [[n.name, self.get_node_tree(n).name] for n in all_bsdf_nodes]
        )
        if baking_pass == BakingPass.METALLIC:
            if len(all_bsdf_nodes) == 0:
                log.warn(self, "Cannot bake metallic pass. Could not find Principled BSDF Node.")
                return
            for bsdf_node in all_bsdf_nodes:
                # Switch Metallic and Roughness input sockets on Principled BSDF Node.
                log.log(
                    "Switching Metallic and Roughness input sockets on node: {}", 
                    [bsdf_node.name, self.get_node_tree(bsdf_node).name]
                )
                bsdf_changes = BsdfChanges()
                material_changes.bsdf_changes[bsdf_node] = bsdf_changes
                bsdf_changes.metallic_socket = self.remove_node_input_connections(bsdf_node, "Metallic", 0.0)
                bsdf_changes.roughness_socket = self.remove_node_input_connections(bsdf_node, "Roughness", 0.0)
                self.restore_node_input_connections(bsdf_node, "Metallic", bsdf_changes.roughness_socket)
                self.restore_node_input_connections(bsdf_node, "Roughness", bsdf_changes.metallic_socket)
        else: 
            for bsdf_node in all_bsdf_nodes:
                # Remove connections from Metallic input socket on Principled BSDF Node. When baking the diffuse pass
                # the metallic value influences the result. And we don't want this.
                log.log(
                    "Removing connections from Metallic input socket on node: {}", 
                    [bsdf_node.name, self.get_node_tree(bsdf_node).name]
                )
                bsdf_changes = BsdfChanges()
                material_changes.bsdf_changes[bsdf_node] = bsdf_changes
                bsdf_changes.metallic_socket = self.remove_node_input_connections(bsdf_node, "Metallic", 0.0)
                
        self._material_changes = material_changes

        # Start Baking:
        self._running_pass = baking_pass
        self._pass_start_time = time.time()
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

    def get_or_create_image(self: Self, baking_pass: BakingPass, img_name: str) -> Image:
        pass_config = baking_pass.value
        img: Image = image_utils.get_image(img_name)

        # If the image contains no data we cannot reuse it. Thus we rename it and create a new image.
        if img != None:
            img.update()  # Try to load the image if it was not loaded before.
            wrong_alpha = pass_config.use_alpha if img.alpha_mode == "NONE" else not pass_config.use_alpha
            if not img.has_data or wrong_alpha or img.type != "IMAGE":
                old_name = img.name
                img.name = img.name + "_old"
                log.warn(
                    self, "Image '{}' has invalid data. Renaming to '{}' and creating a new image", old_name, img.name
                )
                img = None  # create new image

        if img == None:
            img = bpy.data.images.new(
                img_name, self.image_width_prop, self.image_height_prop, alpha=pass_config.use_alpha
            )
        else:
            log.log("Image '{}' already exists. Overwriting existing image ...", img_name)
            if img.size[0] != self.image_width_prop or img.size[1] != self.image_height_prop:
                log.log("Scaling image to {}x{} ...", self.image_width_prop, self.image_height_prop)
                # pack the image into the .blend file to not change external image file before the baking.
                image_utils.pack_image(img)
                img.scale(self.image_width_prop, self.image_height_prop)
                # save scaling
                image_utils.pack_image(img)
        img.alpha_mode = "STRAIGHT" if pass_config.use_alpha else "NONE"
        img.colorspace_settings.is_data = not pass_config.is_color
        return img


    def get_principled_bsdf_nodes(self: Self, node_tree: ShaderNodeTree) -> set[ShaderNodeBsdfPrincipled]:
        principled_nodes: set[ShaderNodeBsdfPrincipled] = set()
        if not node_tree:
            return set()
        for n in node_tree.nodes:
            if n.bl_idname == "ShaderNodeBsdfPrincipled":
                principled_nodes.add(cast(ShaderNodeBsdfPrincipled, n))
            elif n.bl_idname == "ShaderNodeGroup":
                group_node = cast(ShaderNodeGroup, n)
                principled_nodes.update(self.get_principled_bsdf_nodes(group_node.node_tree))
        return principled_nodes

    def remove_node_input_connections(self: Self, node: ShaderNode, socket_name: str, new_value: float) -> NodeSocketState:
        node_tree: ShaderNodeTree = self.get_node_tree(node) # Retrieve the parent ShaderNodeTree
        socket: NodeSocketFloat = node.inputs.get(socket_name)
        if socket is None or not socket.bl_idname.startswith("NodeSocketFloat"):
            log.warn(self, "Cannot remove node input connection because socket {} is not a NodeSocketFloat", socket_name)
            return NodeSocketState(0.0, [])
        value = socket.default_value
        socket.default_value = new_value
        linked_sockets = [s.from_socket for s in socket.links]
        for node_link in socket.links:
            node_tree.links.remove(node_link)
        return NodeSocketState(value, linked_sockets)

    def restore_node_input_connections(self: Self, node: ShaderNode, socket_name: str, state: NodeSocketState) -> None:
        node_tree: ShaderNodeTree = self.get_node_tree(node) # Retrieve the parent ShaderNodeTree
        socket: NodeSocketFloat = node.inputs.get(socket_name)
        if socket is None or not socket.bl_idname.startswith("NodeSocketFloat"):
            log.warn(self, "Cannot restore node input connection because socket {} is not a NodeSocketFloat", socket_name)
            return
        socket.default_value = state.value
        # First remove existing links from socket:
        for node_link in socket.links:
            node_tree.links.remove(node_link)
         # Then add (aka restore) the links from the NodeSocketState
        for connected_socket in state.connected_sockets:
            node_tree.links.new(connected_socket, socket)
            
    def get_node_tree(self: Self, node: ShaderNode) -> ShaderNodeTree:
        return node.id_data


def object_texture_bake_menu_draw(menu: Menu, _context: Context) -> None:
    menu.layout.operator(LxrObjectBakeOperator.bl_idname)


def register():
    bpy.utils.register_class(LxrObjectBakeOperator)
    bpy.types.VIEW3D_MT_object.append(object_texture_bake_menu_draw)


def unregister():
    bpy.types.VIEW3D_MT_object.remove(object_texture_bake_menu_draw)
    bpy.utils.unregister_class(LxrObjectBakeOperator)
