"""JSON logging 配置。"""

from __future__ import annotations

import json
import logging
import sys
import time


class JsonFormatter(logging.Formatter):
    """输出一行 JSON，带 timestamp、level、message。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created))
            + f".{int(record.msecs):03d}",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # 把额外字段（exc_info 以外的）合进去
        extras = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "process",
                "processName",
                "taskName",
                "pathname",
                "filename",
                "module",
                "funcName",
                "lineno",
                "exc_info",
                "exc_text",
                "stack_info",
                "levelno",
                "levelname",
                "message",
                "msecs",
            }
        }
        payload.update(extras)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    # 避免重复添加 handler
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)


def redact_sensitive(value: object) -> object:
    """递归脱敏：ownerPhone、ownerAddr、chipNo 及其 snake_case 写法。"""
    SENSITIVE = {
        "ownerphone", "owneraddr", "chipno",
        "owner_phone", "owner_addr", "chip_no",
        "phone", "address",
    }
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            lk = k.lower()
            if lk in SENSITIVE:
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_sensitive(v)
        return out
    if isinstance(value, list):
        return [redact_sensitive(v) for v in value]
    return value
