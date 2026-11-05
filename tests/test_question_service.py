from pathlib import Path

import pytest

from app.audit import AuditLogger
from app.auth import AuthorizationError, Principal
from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner, QueryError
from app.questions.service import QuestionService

PROJECT_DIR = Path(__file__).parents[1]


def make_service() -> QuestionService:
    return QuestionService(
        LocalQueryRunner(
            PROJECT_DIR / "data" / "parquet",
            PROJECT_DIR / "metadata" / "datasets.yaml",
        ),
        MetadataCatalog(PROJECT_DIR / "metadata"),
    )


def test_service_retrieves_context_and_executes_supported_question() -> None:
    answer = make_service().ask("最近30天销售额最高的5个品牌是什么？")
    assert answer.status == "success"
    assert answer.datasets == ["dws_brand_day_us"]
    assert answer.metrics == ["sales_amount"]
    assert answer.rows
    assert any(item["name"] == "sales_amount" for item in answer.retrieved_context["metrics"])


def test_service_returns_unsupported_for_unknown_question() -> None:
    answer = make_service().ask("未来三个月销售额预测是多少？")
    assert answer.status == "unsupported"
    assert answer.rows == []
    assert answer.sql is None


def test_service_routes_model_intent_to_safe_handler() -> None:
    answer = make_service().ask_with_intent(
        "最近30天销售额最高的10个SKU是什么？",
        QuestionIntent(
            metric="sku_sales_30d",
            dimensions=["seller_sku", "asin"],
            time_range="last_30_days",
            sort="descending",
            limit=10,
        ),
    )
    assert answer.status == "success"
    assert answer.rows
    assert answer.datasets == ["dws_sku_tag_day_us"]
    assert "FROM dws_sku_tag_day_us" in answer.sql
    assert answer.retrieved_context["metrics"]


def test_operator_scope_is_added_to_shop_aware_sql() -> None:
    service = make_service()
    answer = service.ask_with_intent(
        "最近30天销售额最高的10个SKU是什么？",
        QuestionIntent(
            metric="sales_amount", dimensions=["seller_sku", "asin"],
            time_range="last_30_days", sort="descending", limit=10,
        ),
        principal=Principal(name="operator", role="operator", shops=("CuspinArtGallery-US",)),
    )
    assert "shop_code IN ('CuspinArtGallery-US')" in answer.sql


def test_operator_cannot_query_aggregate_without_shop_dimension() -> None:
    service = make_service()
    with pytest.raises(AuthorizationError):
        service.ask_with_intent(
            "最近30天哪个品牌卖得最好？",
            QuestionIntent(
                metric="sales_amount", dimensions=["brand"],
                time_range="last_30_days", sort="descending", limit=5,
            ),
            principal=Principal(name="operator", role="operator", shops=("CuspinArtGallery-US",)),
        )


def test_generic_query_requests_missing_time_range() -> None:
    answer = make_service().ask_with_intent(
        "哪个品牌销售额最高？",
        QuestionIntent(
            metric="sales_amount", dimensions=["brand"], sort="descending", limit=5,
        ),
    )
    assert answer.status == "clarification_needed"
    assert "时间范围" in answer.message
    assert answer.sql is None


def test_generic_query_explains_unsafe_shop_order_count() -> None:
    answer = make_service().ask_with_intent(
        "最近30天各店铺订单数是多少？",
        QuestionIntent(
            metric="order_count", dimensions=["shop_code"], time_range="last_30_days",
        ),
    )
    assert answer.status == "unsupported"
    assert "重复计算" in answer.message
    assert answer.sql is None


def test_operator_scope_applies_to_generic_shop_ranking() -> None:
    answer = make_service().ask_with_intent(
        "最近30天销售额最高的3个店铺是什么？",
        QuestionIntent(
            metric="sales_amount", dimensions=["shop_code"],
            time_range="last_30_days", sort="descending", limit=3,
        ),
        principal=Principal(name="operator", role="operator", shops=("CuspinArtGallery-US",)),
    )
    assert answer.status == "success"
    assert "shop_code IN ('CuspinArtGallery-US')" in answer.sql
    assert all(row["shop_code"] == "CuspinArtGallery-US" for row in answer.rows)


def test_query_failure_is_audited(tmp_path) -> None:
    class FailingRunner:
        def execute(self, sql: str, max_rows: int = 1000):
            raise QueryError("simulated timeout")

    audit_path = tmp_path / "audit.jsonl"
    service = QuestionService(
        FailingRunner(), MetadataCatalog(PROJECT_DIR / "metadata"), AuditLogger(audit_path)
    )
    with pytest.raises(QueryError):
        service.ask_with_intent(
            "最近30天销售额",
            QuestionIntent(metric="sales_amount", time_range="last_30_days"),
        )
    assert '"status": "query_error"' in audit_path.read_text(encoding="utf-8")
