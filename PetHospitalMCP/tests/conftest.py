"""pytest 配置与共享 fixture。"""

from __future__ import annotations

import sys
from pathlib import Path

# 让测试能 import src 下的包
SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))
