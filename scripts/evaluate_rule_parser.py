"""Evaluate the offline rule parser against questions and paraphrases."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.intent.parser import RuleBasedIntentParser
from app.metadata.loader import MetadataCatalog


def main() -> None:
    with (PROJECT_DIR / "evals" / "questions.yaml").open(encoding="utf-8") as file:
        questions = yaml.safe_load(file)["questions"]

    parser = RuleBasedIntentParser(MetadataCatalog(PROJECT_DIR / "metadata"))
    total = checked = passed = 0
    failures: list[str] = []
    for item in questions:
        if item.get("status") == "unsupported":
            continue
        for text in [item["question"], *item.get("paraphrases", [])]:
            total += 1
            intent = parser.parse(text)
            expected_metrics = set(item.get("expected_metrics", []))
            expected_dimensions = set(item.get("expected_dimensions", []))
            if not expected_metrics and not expected_dimensions:
                continue
            checked += 1
            metric_ok = not expected_metrics or intent.metric in expected_metrics
            dimensions_ok = expected_dimensions.issubset(set(intent.dimensions))
            if metric_ok and dimensions_ok:
                passed += 1
            else:
                failures.append(f"{item['id']}: {text} -> metric={intent.metric}, dimensions={intent.dimensions}")

    print(f"total={total}, checked={checked}, passed={passed}, accuracy={passed / checked:.1%}" if checked else "没有可评测问题")
    if failures:
        print("\n失败样例：")
        print("\n".join(failures[:20]))


if __name__ == "__main__":
    main()

