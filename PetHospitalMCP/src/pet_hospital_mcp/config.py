"""Configuration — 环境变量驱动。"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """运行时配置，全部可通过环境变量覆盖。"""

    # Go REST API 上游
    pet_hospital_base_url: str = "http://127.0.0.1:8080"
    # MCP Streamable HTTP 监听
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    # REST 客户端
    request_timeout: float = 10.0
    max_retries: int = 2
    retry_backoff: float = 0.5
    # MCP 端点路径
    mcp_path: str = "/mcp"
    health_path: str = "/health"


def get_settings() -> Settings:
    return Settings(
        pet_hospital_base_url=os.getenv("PET_HOSPITAL_BASE_URL", "http://127.0.0.1:8080"),
        mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
        mcp_port=int(os.getenv("MCP_PORT", "8000")),
        request_timeout=float(os.getenv("REQUEST_TIMEOUT", "10.0")),
        max_retries=int(os.getenv("MAX_RETRIES", "2")),
        retry_backoff=float(os.getenv("RETRY_BACKOFF", "0.5")),
        mcp_path=os.getenv("MCP_PATH", "/mcp"),
        health_path=os.getenv("HEALTH_PATH", "/health"),
    )
