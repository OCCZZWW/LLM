"""统一错误格式。

MCP SDK 2.x 约定：工具函数里 raise 普通异常 → 客户端收到 is_error=True 的结果，
模型可以读取异常消息并自行修正参数。这里的 MCPToolError 正是为这个场景设计的。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    BACKEND_API_ERROR = "BACKEND_API_ERROR"
    BACKEND_INVALID_RESPONSE = "BACKEND_INVALID_RESPONSE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class MCPToolError(Exception):
    """工具执行失败。

    客户端会收到 is_error=True 的 result，异常消息进入 content，
    模型可以看到并据此重试或修正。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            }
        }

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"
