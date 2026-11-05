"""Run paid DeepSeek evaluation through the generic query planner."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.evaluation.generic_question_eval import (
    evaluate_generic_questions,
    expand_generic_questions,
    summarize_generic_questions,
)
from app.intent.deepseek import DeepSeekIntentParser
from app.metadata.loader import MetadataCatalog
from app.sql.generator import SafeSqlGenerator


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="评测DeepSeek到通用查询计划的完整语义链路")
    argument_parser.add_argument("--limit", type=int, default=32)
    args = argument_parser.parse_args()
    load_env_file(PROJECT_DIR / ".env")
    with (PROJECT_DIR / "evals" / "generic_questions.yaml").open(encoding="utf-8") as file:
        source_questions = yaml.safe_load(file)["questions"]
    questions = expand_generic_questions(source_questions)[: max(1, min(args.limit, 50))]
    catalog = MetadataCatalog(PROJECT_DIR / "metadata")
    parser = DeepSeekIntentParser(catalog)
    results = evaluate_generic_questions(
        parser,
        SafeSqlGenerator(catalog),
        questions,
    )
    summary = summarize_generic_questions(results)
    summary["llm_usage"] = {
        **parser.usage,
        "average_duration_ms": round(
            parser.usage["duration_ms"] / parser.usage["calls"], 2
        ) if parser.usage["calls"] else 0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = [result.to_dict() for result in results if not result.passed]
    if failures:
        print("\n失败样例：")
        print(json.dumps(failures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
