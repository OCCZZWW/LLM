"""核心层向界面层输出的领域事件。

核心层只产生事件，不负责展示；任何界面（TUI / CLI / Web / Desktop）
只需实现 AgentListener.on_event 即可接入。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Union, runtime_checkable


@dataclass(frozen=True)
class TextDelta:
    """模型流式输出的一个文本片段。"""

    text: str


@dataclass(frozen=True)
class ToolCallStarted:
    """即将执行一次工具调用。"""

    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolCallFinished:
    """工具执行完毕，携带返回值。"""

    call_id: str
    name: str
    result: str


@dataclass(frozen=True)
class AssistantMessage:
    """本轮 assistant 最终回复（完整文本）。"""

    text: str


@dataclass(frozen=True)
class ErrorRaised:
    """核心层错误（连接失败、HTTP 异常等）。"""

    message: str


AgentEvent = Union[
    TextDelta,
    ToolCallStarted,
    ToolCallFinished,
    AssistantMessage,
    ErrorRaised,
]


@runtime_checkable
class AgentListener(Protocol):
    """界面层需要实现的唯一接口。"""

    def on_event(self, event: AgentEvent) -> None:
        ...


class NullListener:
    """空实现，便于无界面场景（测试、批处理）使用。"""

    def on_event(self, event: AgentEvent) -> None:
        pass
