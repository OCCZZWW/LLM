"""工具层：工具抽象、注册表与默认工具集。"""

from .base import Tool, ToolRegistry
from .file_ops import register_file_tools
from .general import register_general_tools


def build_default_registry() -> ToolRegistry:
    """构建包含全部内置工具的注册表。"""
    registry = ToolRegistry()
    register_general_tools(registry)
    register_file_tools(registry)
    return registry


__all__ = ["Tool", "ToolRegistry", "build_default_registry"]
