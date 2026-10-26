"""通用工具：日期时间与闰年判断。"""

from __future__ import annotations

import datetime
import subprocess

from .base import ToolRegistry


def register_general_tools(registry: ToolRegistry) -> None:
    """注册通用工具。"""

    @registry.tool(
        name="getDate",
        description="获取当前电脑的日期和时间。当用户询问今天几号、现在几点、当前日期时间等问题时调用此工具。",
    )
    def get_date() -> str:
        """Windows 下调用本地 date/time 命令，其他平台回退到 datetime。"""
        try:
            date_res = subprocess.run(
                ["cmd", "/c", "date", "/t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            time_res = subprocess.run(
                ["cmd", "/c", "time", "/t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return (
                f"当前日期: {date_res.stdout.strip()}\n"
                f"当前时间: {time_res.stdout.strip()}"
            )
        except FileNotFoundError:
            now = datetime.datetime.now()
            return now.strftime("当前日期: %Y/%m/%d\n当前时间: %H:%M:%S")
        except subprocess.TimeoutExpired:
            return "[错误] 调用本地 date 命令超时"

    @registry.tool(
        name="isLeapYear",
        description="判断某一年是否是闰年。当用户询问某一年是不是闰年、当年是否是闰年等问题时调用此工具。",
        parameters={
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "要判断的年份，例如 2024"},
            },
            "required": ["year"],
        },
    )
    def is_leap_year(year: int) -> str:
        """能被 4 整除但不能被 100 整除，或能被 400 整除。"""
        try:
            y = int(year)
        except (TypeError, ValueError):
            return f"[错误] 无法解析年份: {year}"

        if y < 1:
            return f"[错误] 年份无效: {y}"

        leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
        if leap:
            return f"{y} 年是闰年（2 月有 29 天）"
        return f"{y} 年不是闰年（2 月有 28 天）"
