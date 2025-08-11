from bpy.types import Operator
from . import bl_info


def warn(op: Operator, msg: str, *args) -> None:
    op.report({"WARNING"}, msg.format(*args))


def log(msg: str, *args) -> None:
    print("\U0001f35e", "{}:".format(bl_info["name"]), msg.format(*args))
