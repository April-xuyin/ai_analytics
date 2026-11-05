"""Ask one analytics question through DeepSeek and the safe query service."""
# 通过DeepSeek和安全查询服务,提出一个分析问题。

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 下面两行必须在 import app 之前：Python 只把"脚本所在目录"(scripts/) 放进
# 模块搜索清单 sys.path，项目根目录不在里面，直接 import app 会报 ModuleNotFoundError。
# 这里手动把项目根目录插到清单最前面，下面的 import 才能找到 app 包。
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.intent.deepseek import DeepSeekIntentParser
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner
from app.questions.service import QuestionService


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE settings without printing secrets."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit(
            '用法: uv run python scripts/ask_question.py "你的问题"'
        )

    load_env_file(PROJECT_DIR / ".env")
    catalog = MetadataCatalog(PROJECT_DIR / "metadata")
    runner = LocalQueryRunner(
        PROJECT_DIR / "data" / "parquet",
        PROJECT_DIR / "metadata" / "datasets.yaml",
    )
    parser = DeepSeekIntentParser(catalog)
    question = sys.argv[1].strip()
    intent = parser.parse(question)

    print("\n问题意图：")
    print(json.dumps(intent.to_dict(), ensure_ascii=False, indent=2, default=str))

    if intent.needs_clarification:
        print(f"\n需要补充信息：{intent.clarification_question}")
        return

    answer = QuestionService(runner, catalog).ask_with_intent(question, intent)
    print("\n问数结果：")
    print(json.dumps(answer.to_dict(), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

