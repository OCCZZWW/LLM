"""基于 Textual 的终端界面。

线程模型：
- Agent 在 worker 线程中执行（避免流式输出时界面冻结）；
- 核心事件通过 listener → call_from_thread 回到主线程渲染。
"""

from __future__ import annotations

from rich.markdown import Markdown
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, RichLog, Static

from core.agent import Agent
from core.events import (
    AgentEvent,
    AssistantMessage,
    ErrorRaised,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)

from ..base import BaseUI

WELCOME = (
    "# OCCAgent\n\n"
    "基于 Ollama + Function Calling 的本地智能体。\n\n"
    "- `Ctrl+L` 清空对话\n"
    "- `Ctrl+Q` 退出\n"
)


class TUIListener:
    """把核心事件安全地投递回 Textual 主线程。"""

    def __init__(self, app: "ChatTUI") -> None:
        self._app = app

    def on_event(self, event: AgentEvent) -> None:
        try:
            self._app.call_from_thread(self._app.apply_event, event)
        except RuntimeError:
            # 应用已退出时忽略迟到的流式事件
            pass


class ChatTUI(App, BaseUI):
    """终端聊天界面。"""

    CSS = """
    Screen { layout: vertical; }
    #chat-log {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }
    #stream-box {
        height: auto;
        max-height: 40%;
        border: round $accent;
        padding: 0 1;
    }
    #prompt { dock: bottom; }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "退出"),
        ("ctrl+c", "quit", "退出"),
        ("ctrl+l", "clear_chat", "清空"),
    ]

    def __init__(self, agent: Agent) -> None:
        App.__init__(self)
        self._agent = agent
        self._stream_buffer = ""
        self._busy = False

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield RichLog(id="chat-log", wrap=True, markup=True, highlight=True)
        with VerticalScroll(id="stream-box"):
            yield Static("", id="streaming")
        yield Input(placeholder="输入问题，回车发送", id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._agent.set_listener(TUIListener(self))
        self.query_one("#stream-box").display = False
        self.query_one("#chat-log", RichLog).write(Markdown(WELCOME))
        self.query_one("#prompt", Input).focus()

    # ------------------------------------------------------------------
    # 用户输入
    # ------------------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if not question or self._busy:
            return

        prompt = self.query_one("#prompt", Input)
        prompt.value = ""
        prompt.disabled = True
        self._busy = True

        self.query_one("#chat-log", RichLog).write(
            Text.assemble(("你 > ", "bold cyan"), (question, "white"))
        )
        self._stream_buffer = ""
        self._show_streaming(False)

        self.run_worker(
            lambda: self._run_agent(question),
            name="agent-turn",
            thread=True,
            exclusive=True,
        )

    def _run_agent(self, question: str) -> None:
        try:
            self._agent.ask(question)
        finally:
            try:
                self.call_from_thread(self._finish_turn)
            except RuntimeError:
                pass

    def _finish_turn(self) -> None:
        self._busy = False
        prompt = self.query_one("#prompt", Input)
        prompt.disabled = False
        prompt.focus()

    # ------------------------------------------------------------------
    # 事件渲染（主线程）
    # ------------------------------------------------------------------
    def apply_event(self, event: AgentEvent) -> None:
        log = self.query_one("#chat-log", RichLog)

        if isinstance(event, TextDelta):
            self._stream_buffer += event.text
            self._render_streaming()
        elif isinstance(event, ToolCallStarted):
            log.write(
                Text.assemble(("⚙ 调用工具 ", "bold yellow"), (event.name, "bold"), (f"({event.arguments})", "dim"))
            )
        elif isinstance(event, ToolCallFinished):
            log.write(Text.assemble(("  ↳ 返回 ", "green"), (event.result, "dim")))
        elif isinstance(event, AssistantMessage):
            self._flush_streaming()
        elif isinstance(event, ErrorRaised):
            self._flush_streaming()
            log.write(Text.assemble(("✗ 错误 ", "bold red"), (event.message, "red")))

    def _render_streaming(self) -> None:
        self._show_streaming(True)
        self.query_one("#streaming", Static).update(Markdown(self._stream_buffer))

    def _flush_streaming(self) -> None:
        if self._stream_buffer:
            self.query_one("#chat-log", RichLog).write(Markdown(self._stream_buffer))
            self._stream_buffer = ""
        self.query_one("#streaming", Static).update("")
        self._show_streaming(False)

    def _show_streaming(self, visible: bool) -> None:
        self.query_one("#stream-box").display = visible

    # ------------------------------------------------------------------
    # 快捷键
    # ------------------------------------------------------------------
    def action_clear_chat(self) -> None:
        self._agent.reset()
        self._stream_buffer = ""
        self.query_one("#streaming", Static).update("")
        self._show_streaming(False)
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        log.write(Markdown(WELCOME))

    # ------------------------------------------------------------------
    # BaseUI 契约
    # ------------------------------------------------------------------
    def run(self) -> None:  # type: ignore[override]
        App.run(self)
