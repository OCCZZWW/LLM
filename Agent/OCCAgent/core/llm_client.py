"""Ollama OpenAI 兼容接口客户端。

只负责网络通信与流式解析，不打印任何内容。
通过生成器向调用方交付 StreamText / StreamToolCalls 两类事件。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator, Union

import requests

from .config import LLMConfig


class LLMError(RuntimeError):
    """LLM 通信或协议错误。"""


@dataclass(frozen=True)
class StreamText:
    """流式文本片段。"""

    text: str


@dataclass(frozen=True)
class StreamToolCalls:
    """一次流式响应结束时汇总出的完整工具调用列表。"""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)


StreamEvent = Union[StreamText, StreamToolCalls]


class OllamaClient:
    """极简 Ollama 客户端，仅实现对话补全 + function calling。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self._config = config or LLMConfig.from_env()
        self._headers = {"Content-Type": "application/json"}

    @property
    def config(self) -> LLMConfig:
        return self._config

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[StreamEvent]:
        """请求模型并逐块产出事件，最后一帧固定为 StreamToolCalls。"""
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        try:
            resp = requests.post(
                self._config.chat_url,
                headers=self._headers,
                json=payload,
                stream=True,
                timeout=self._config.timeout,
            )
        except requests.RequestException as exc:
            raise LLMError(
                f"无法连接 Ollama ({self._config.base_url})，请确认服务已启动: {exc}"
            ) from exc

        try:
            if resp.status_code != 200:
                raise LLMError(
                    f"Ollama 返回 HTTP {resp.status_code}: {resp.text[:300]}"
                )
            yield from self._parse_sse(resp)
        finally:
            resp.close()

    @staticmethod
    def _parse_sse(resp: requests.Response) -> Iterator[StreamEvent]:
        # 累积流式 tool_calls 增量：index -> {id, name, arguments}
        buffers: dict[int, dict[str, str]] = {}

        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            choices = data.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}

            content = delta.get("content")
            if content:
                yield StreamText(content)

            for call in delta.get("tool_calls") or []:
                index = call.get("index", 0)
                buf = buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if call.get("id"):
                    buf["id"] += call["id"]
                function = call.get("function") or {}
                if function.get("name"):
                    buf["name"] += function["name"]
                if function.get("arguments"):
                    buf["arguments"] += function["arguments"]

        tool_calls: list[dict[str, Any]] = []
        for index in sorted(buffers):
            buf = buffers[index]
            if not buf["name"]:
                continue
            tool_calls.append(
                {
                    "id": buf["id"] or f"call_{index}",
                    "type": "function",
                    "function": {
                        "name": buf["name"],
                        "arguments": buf["arguments"] or "{}",
                    },
                }
            )

        yield StreamToolCalls(tool_calls)
