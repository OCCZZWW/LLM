"""界面基类。

新增界面（Web / Desktop / 移动端）时：
1. 继承 BaseUI 并实现 run()；
2. 提供一个 AgentListener，将核心事件映射到自己的渲染方式；
3. 在 main.py 注册入口。核心层无需任何改动。

说明：此处不使用 ABCMeta，避免与 Textual App 的元类冲突；
run() 未实现时抛出 NotImplementedError，契约保持不变。
"""

from __future__ import annotations

from core.agent import Agent


class BaseUI:
    """所有界面实现的最小契约。"""

    def __init__(self, agent: Agent) -> None:
        self._agent = agent

    @property
    def agent(self) -> Agent:
        return self._agent

    def run(self) -> None:
        """启动界面主循环，阻塞直到用户退出。"""
        raise NotImplementedError
