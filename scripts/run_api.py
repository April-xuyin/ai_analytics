"""Run the local FastAPI server."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

# 直接执行 ``python scripts/run_api.py`` 时，Python 默认只把 scripts/
# 放入模块搜索路径；补入项目根目录后才能找到 app 包。
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))


if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=False,
    )
