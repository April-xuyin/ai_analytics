"""Run SQL AST security evaluation without executing any SQL."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.evaluation.security_eval import evaluate_sql_security, summarize_sql_security
from app.metadata.loader import MetadataCatalog
from app.query.sql_security import SqlSecurityValidator


def main() -> None:
    catalog = MetadataCatalog(PROJECT_DIR / "metadata")
    cases = yaml.safe_load(
        (PROJECT_DIR / "evals" / "sql_security_cases.yaml").read_text(encoding="utf-8")
    )["cases"]
    columns = {
        str(column)
        for dataset in catalog.datasets
        for column in [dataset.get("time_field"), *dataset["dimensions"], *dataset["metrics"]]
        if column
    }
    results = evaluate_sql_security(
        SqlSecurityValidator({item["name"] for item in catalog.datasets}, columns), cases
    )
    print(json.dumps(summarize_sql_security(results), ensure_ascii=False, indent=2))
    failures = [item for item in results if not item["passed"]]
    if failures:
        print(json.dumps({"failures": failures}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
