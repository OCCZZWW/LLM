"""OCCAgent 核心层：与界面完全解耦的 Agent、LLM 客户端与工具注册表。"""

from .agent import Agent
from .config import LLMConfig
from .events import (
    AgentEvent,
    AgentListener,
    AssistantMessage,
    ErrorRaised,
    NullListener,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)
from .llm_client import LLMError, OllamaClient
from .tools import Tool, ToolRegistry, build_default_registry

__all__ = [
    "Agent",
    "LLMConfig",
    "LLMError",
    "OllamaClient",
    "Tool",
    "ToolRegistry",
    "build_default_registry",
    "AgentEvent",
    "AgentListener",
    "AssistantMessage",
    "ErrorRaised",
    "NullListener",
    "TextDelta",
    "ToolCallFinished",
    "ToolCallStarted",
]
