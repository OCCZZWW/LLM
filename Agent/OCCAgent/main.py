"""OCCAgent 统一入口：按参数选择界面实现。

用法:
    python main.py            # 默认 Textual TUI
    python main.py --ui cli   # 纯文本 CLI
"""

from __future__ import annotations

import argparse

from core.agent import Agent
from core.config import LLMConfig
from core.llm_client import OllamaClient
from core.tools import build_default_registry


def build_agent() -> Agent:
    """组装核心层依赖：配置 → 客户端 → 工具注册表 → Agent。"""
    return Agent(
        client=OllamaClient(LLMConfig.from_env()),
        registry=build_default_registry(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="OCCAgent - 多界面本地智能体")
    parser.add_argument(
        "--ui",
        choices=["tui", "cli"],
        default="tui",
        help="界面类型：tui（默认）/ cli",
    )
    args = parser.parse_args()

    agent = build_agent()

    if args.ui == "cli":
        from ui.cli import CLIChatUI

        CLIChatUI(agent).run()
    else:
        from ui.tui.app import ChatTUI

        ChatTUI(agent).run()


if __name__ == "__main__":
    main()
