"""纯文本（CLI）界面：无第三方依赖，作为最小可用实现与调试入口。"""

from __future__ import annotations

from core.agent import Agent
from core.events import (
    AgentEvent,
    AssistantMessage,
    ErrorRaised,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)

from .base import BaseUI


class CLIListener:
    """把核心事件打印到标准输出。"""

    def on_event(self, event: AgentEvent) -> None:
        if isinstance(event, TextDelta):
            print(event.text, end="", flush=True)
        elif isinstance(event, ToolCallStarted):
            print(f"\n[工具] 调用 {event.name}({event.arguments})")
        elif isinstance(event, ToolCallFinished):
            print(f"[工具] {event.name} 返回:\n{event.result}\n")
        elif isinstance(event, AssistantMessage):
            print()
        elif isinstance(event, ErrorRaised):
            print(f"\n[错误] {event.message}")


class CLIChatUI(BaseUI):
    """逐行问答式终端界面。"""

    def run(self) -> None:
        self.agent.set_listener(CLIListener())
        print("OCCAgent CLI（Ctrl+C 退出）")

        try:
            while True:
                question = input("你> ").strip()
                if not question:
                    continue
                print("助手> ", end="", flush=True)
                self.agent.ask(question)
        except (KeyboardInterrupt, EOFError):
            print("\n对话已结束")
