"""Run a small, paid DeepSeek intent evaluation without querying business data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.evaluation.intent_eval import evaluate_questions, summarize
from app.intent.deepseek import DeepSeekIntentParser
from app.metadata.loader import MetadataCatalog


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="评测 DeepSeek 问题意图解析")
    argument_parser.add_argument("--limit", type=int, default=10, help="真实 API 调用题数，默认10")
    argument_parser.add_argument(
        "--id-prefix",
        help="只评测指定题目 ID 前缀，例如 ext_；不填则按文件顺序评测",
    )
    args = argument_parser.parse_args()
    limit = max(1, min(args.limit, 50))

    load_env_file(PROJECT_DIR / ".env")
    with (PROJECT_DIR / "evals" / "questions.yaml").open(encoding="utf-8") as file:
        all_questions = yaml.safe_load(file)["questions"]
    questions = [
        item for item in all_questions
        if item.get("status") not in {"unsupported", "deferred"}
        and item.get("expected_metrics")
        and (not args.id_prefix or str(item.get("id", "")).startswith(args.id_prefix))
    ][:limit]

    parser = DeepSeekIntentParser(MetadataCatalog(PROJECT_DIR / "metadata"))
    results = evaluate_questions(parser, questions)
    summary = summarize(results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = [result.to_dict() for result in results if not result.passed]
    if failures:
        print("\n失败样例：")
        print(json.dumps(failures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
