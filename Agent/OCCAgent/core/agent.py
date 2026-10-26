"""Agent 编排层：维护对话历史、驱动模型、执行工具、派发事件。

本模块不包含任何输入/输出代码，可被任意界面复用。
"""

from __future__ import annotations

import json
from typing import Any

from .config import LLMConfig
from .events import (
    AgentListener,
    AssistantMessage,
    ErrorRaised,
    NullListener,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)
from .llm_client import LLMError, OllamaClient, StreamText, StreamToolCalls
from .tools import ToolRegistry


class Agent:
    """一个会话级别的 Agent 实例。"""

    def __init__(
        self,
        client: OllamaClient | None = None,
        registry: ToolRegistry | None = None,
        listener: AgentListener | None = None,
    ) -> None:
        if registry is None:
            raise ValueError("Agent 需要显式传入 ToolRegistry")
        self._client = client or OllamaClient(LLMConfig.from_env())
        self._registry = registry
        self._listener: AgentListener = listener or NullListener()
        self._messages: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def set_listener(self, listener: AgentListener) -> None:
        """由界面层在启动时注入事件监听器。"""
        self._listener = listener

    def reset(self) -> None:
        """清空对话历史。"""
        self._messages.clear()

    @property
    def messages(self) -> list[dict[str, Any]]:
        """返回历史副本，避免界面层意外修改。"""
        return list(self._messages)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def ask(self, user_input: str) -> str:
        """处理一轮用户输入，返回最终文本回复。"""
        self._messages.append({"role": "user", "content": user_input})

        text, tool_calls, ok = self._stream_once(use_tools=True)
        if not ok:
            return ""

        if not tool_calls:
            self._messages.append({"role": "assistant", "content": text})
            self._emit(AssistantMessage(text))
            return text

        # 第一轮模型请求了工具：记录 assistant(tool_calls) 后逐个执行
        self._messages.append(
            {"role": "assistant", "content": text or None, "tool_calls": tool_calls}
        )
        self._execute_tools(tool_calls)

        # 第二轮不带 tools，强制模型基于工具结果给出自然语言答复
        final_text, _, ok = self._stream_once(use_tools=False)
        if ok:
            self._messages.append({"role": "assistant", "content": final_text})
            self._emit(AssistantMessage(final_text))
            return final_text
        return ""

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _stream_once(self, use_tools: bool) -> tuple[str, list[dict[str, Any]], bool]:
        """流式请求一次模型，返回 (文本, 工具调用, 是否成功)。"""
        parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tools = self._registry.schemas() if use_tools else None

        try:
            for event in self._client.stream(self._messages, tools=tools):
                if isinstance(event, StreamText):
                    parts.append(event.text)
                    self._emit(TextDelta(event.text))
                elif isinstance(event, StreamToolCalls):
                    tool_calls = event.tool_calls
        except LLMError as exc:
            self._emit(ErrorRaised(str(exc)))
            return "".join(parts), [], False

        return "".join(parts), tool_calls, True

    def _execute_tools(self, tool_calls: list[dict[str, Any]]) -> None:
        for call in tool_calls:
            call_id = call.get("id") or "call_0"
            name = (call.get("function") or {}).get("name", "")
            raw_args = (call.get("function") or {}).get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args)
            except json.JSONDecodeError:
                arguments = {}

            self._emit(ToolCallStarted(call_id, name, arguments))
            result = self._registry.execute(name, arguments)
            self._emit(ToolCallFinished(call_id, name, result))

            self._messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": name,
                    "content": result,
                }
            )

    def _emit(self, event: Any) -> None:
        try:
            self._listener.on_event(event)
        except Exception:
            # 界面层异常不应中断核心流程
            pass
