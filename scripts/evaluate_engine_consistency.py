"""Compare representative DuckDB and MaxCompute query results."""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner
from app.query.maxcompute_runner import MaxComputeQueryRunner
from app.sql.generator import SafeSqlGenerator


def load_env(path: Path) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize(value: Any) -> Any:
    if isinstance(value, (float, Decimal)):
        return round(float(value), 4)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def canonical_rows(rows: list[dict[str, object]]) -> list[str]:
    normalized = [
        {key: normalize(value) for key, value in sorted(row.items())}
        for row in rows
    ]
    return sorted(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in normalized)


def main() -> None:
    load_env(PROJECT_DIR / ".env")
    catalog = MetadataCatalog(PROJECT_DIR / "metadata")
    generator = SafeSqlGenerator(catalog)
    local = LocalQueryRunner(
        PROJECT_DIR / "data" / "parquet", PROJECT_DIR / "metadata" / "datasets.yaml"
    )
    cloud = MaxComputeQueryRunner(PROJECT_DIR / "metadata" / "datasets.yaml")
    cases = [
        ("brand_sales_30d", QuestionIntent(
            metric="sales_amount", dimensions=["brand"], time_range="last_30_days",
            sort="descending", limit=5,
        )),
        ("overall_refund_rate_7d", QuestionIntent(
            metric="refund_rate", time_range="last_7_days",
        )),
        ("sku_sales_2026_08", QuestionIntent(
            metric="sales_amount", dimensions=["seller_sku", "asin"],
            filters={"stat_month": "2026-08"}, sort="descending", limit=10,
        )),
    ]
    results = []
    for case_id, intent in cases:
        sql = generator.generate(intent)
        local_rows = local.execute(sql, max_rows=int(intent.limit or 1000))
        cloud_rows = cloud.execute(sql, max_rows=int(intent.limit or 1000))
        results.append({
            "id": case_id,
            "local_rows": len(local_rows),
            "maxcompute_rows": len(cloud_rows),
            "passed": canonical_rows(local_rows) == canonical_rows(cloud_rows),
        })
    passed = sum(item["passed"] for item in results)
    print(json.dumps({
        "total": len(results), "passed": passed,
        "accuracy": passed / len(results), "cases": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
