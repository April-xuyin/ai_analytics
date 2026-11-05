"""Run the free, deterministic query-planner evaluation suite."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.evaluation.query_plan_eval import evaluate_query_plans, summarize_query_plans
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner
from app.sql.generator import SafeSqlGenerator


def main() -> None:
    with (PROJECT_DIR / "evals" / "query_plans.yaml").open(encoding="utf-8") as file:
        cases = yaml.safe_load(file)["cases"]
    generator = SafeSqlGenerator(MetadataCatalog(PROJECT_DIR / "metadata"))
    runner = LocalQueryRunner(
        PROJECT_DIR / "data" / "parquet",
        PROJECT_DIR / "metadata" / "datasets.yaml",
    )
    results = evaluate_query_plans(generator, cases, runner)
    print(json.dumps(summarize_query_plans(results), ensure_ascii=False, indent=2))
    failures = [result.to_dict() for result in results if not result.passed]
    if failures:
        print("\n失败样例：")
        print(json.dumps(failures, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
