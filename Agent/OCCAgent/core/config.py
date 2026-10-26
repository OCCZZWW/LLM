"""LLM 连接配置。所有可调参数集中在此，UI 层不感知具体后端。"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    """Ollama OpenAI 兼容接口的配置。"""

    base_url: str = "http://localhost:11434"
    model: str = "qwen3-vl:4b-instruct"
    timeout: float = 120.0

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/chat/completions"

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量读取，便于切换模型或指向远程 Ollama。"""
        return cls(
            base_url=os.getenv("OCCAGENT_BASE_URL", cls.base_url),
            model=os.getenv("OCCAGENT_MODEL", cls.model),
            timeout=float(os.getenv("OCCAGENT_TIMEOUT", str(cls.timeout))),
        )
