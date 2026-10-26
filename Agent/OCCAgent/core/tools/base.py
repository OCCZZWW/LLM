"""工具抽象与注册表。

新增工具只需：
    @registry.tool(name="xxx", description="...", parameters={...})
    def xxx(...) -> str: ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

ToolHandler = Callable[..., str]


@dataclass(frozen=True)
class Tool:
    """一个可被模型调用的函数。"""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_schema(self) -> dict[str, Any]:
        """转换为 OpenAI function calling 格式。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册表：负责 schema 导出与按名分发执行。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def tool(
        self,
        *,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[ToolHandler], ToolHandler]:
        """函数装饰器形式的注册入口。"""

        def decorator(handler: ToolHandler) -> ToolHandler:
            self.register(
                Tool(
                    name=name,
                    description=description,
                    parameters=parameters
                    or {"type": "object", "properties": {}, "required": []},
                    handler=handler,
                )
            )
            return handler

        return decorator

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """执行工具；所有异常转换为文本结果返回给模型。"""
        tool = self._tools.get(name)
        if tool is None:
            return f"[错误] 未知工具: {name}"
        try:
            return tool.handler(**arguments)
        except TypeError as exc:
            return f"[错误] 工具参数不匹配: {exc}"
        except Exception as exc:  # 工具内部异常不应中断对话
            return f"[错误] 工具执行失败: {exc}"
