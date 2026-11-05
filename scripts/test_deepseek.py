"""Make one real DeepSeek intent-parsing call."""

import sys
from pathlib import Path

# 直接执行 scripts/ 下的文件时，手动把项目根目录加入模块搜索路径。
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.intent.deepseek import DeepSeekIntentParser
from app.metadata.loader import MetadataCatalog

root = PROJECT_DIR
env_file = root / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            import os
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
parser = DeepSeekIntentParser(MetadataCatalog(root / "metadata"))
intent = parser.parse("最近30天销售额最高的10个SKU是什么？")
print(intent.to_dict())
