"""Run deterministic clarification, refusal, and shop-scope evaluations."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.auth import AuthorizationError, Principal
from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner
from app.questions.service import QuestionService


def main() -> None:
    service = QuestionService(
        LocalQueryRunner(
            PROJECT_DIR / "data" / "parquet",
            PROJECT_DIR / "metadata" / "datasets.yaml",
        ),
        MetadataCatalog(PROJECT_DIR / "metadata"),
    )
    cases = []

    answer = service.ask_with_intent(
        "哪个品牌销售额最高？",
        QuestionIntent(metric="sales_amount", dimensions=["brand"], sort="descending"),
    )
    cases.append({"id": "missing_time", "passed": answer.status == "clarification_needed"})

    answer = service.ask_with_intent(
        "最近30天各店铺订单数是多少？",
        QuestionIntent(
            metric="order_count", dimensions=["shop_code"], time_range="last_30_days"
        ),
    )
    cases.append({"id": "unsafe_metric_grain", "passed": answer.status == "unsupported"})

    operator = Principal(
        name="operator", role="operator", shops=("CuspinArtGallery-US",)
    )
    try:
        service.ask_with_intent(
            "最近30天品牌销售额",
            QuestionIntent(
                metric="sales_amount", dimensions=["brand"], time_range="last_30_days"
            ),
            principal=operator,
        )
        denied = False
    except AuthorizationError:
        denied = True
    cases.append({"id": "operator_unsafe_aggregate", "passed": denied})

    answer = service.ask_with_intent(
        "最近30天店铺销售额",
        QuestionIntent(
            metric="sales_amount", dimensions=["shop_code"],
            time_range="last_30_days", sort="descending", limit=3,
        ),
        principal=operator,
    )
    cases.append({
        "id": "operator_shop_scope",
        "passed": answer.status == "success"
        and "shop_code IN ('CuspinArtGallery-US')" in (answer.sql or "")
        and all(row["shop_code"] == "CuspinArtGallery-US" for row in answer.rows),
    })

    passed = sum(bool(item["passed"]) for item in cases)
    print(json.dumps({
        "total": len(cases), "passed": passed,
        "accuracy": passed / len(cases), "cases": cases,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
