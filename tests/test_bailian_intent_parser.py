import json
from pathlib import Path
from types import SimpleNamespace

from app.intent.bailian import BailianIntentParser
from app.metadata.loader import MetadataCatalog

METADATA_DIR = Path(__file__).parents[1] / "metadata"


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["model"] == "test-qwen"
        assert kwargs["response_format"] == {"type": "json_object"}
        payload = {
            "metric": "sales_amount",
            "dimensions": ["seller_sku", "asin"],
            "time_range": "last_30_days",
            "sort": "descending",
            "limit": 10,
            "filters": {},
            "needs_clarification": False,
            "clarification_question": None,
        }
        message = SimpleNamespace(content=json.dumps(payload))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_bailian_parser_with_fake_client() -> None:
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions())
    )
    parser = BailianIntentParser(
        MetadataCatalog(METADATA_DIR), client=client, model="test-qwen"
    )
    intent = parser.parse("最近30天销售额最高的10个SKU是什么？")
    assert intent.metric == "sales_amount"
    assert intent.dimensions == ["seller_sku", "asin"]
    assert intent.limit == 10


def test_bailian_parser_normalizes_calendar_month_sales() -> None:
    payload = {
        "metric": "monthly_sales",
        "metrics": ["monthly_sales"],
        "dimensions": ["seller_sku", "asin"],
        "time_range": {"type": "absolute", "start": "2026-08", "end": "2026-08"},
        "sort": "descending",
        "limit": 10,
        "filters": {},
    }
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **_: response)
        )
    )
    parser = BailianIntentParser(MetadataCatalog(METADATA_DIR), client=client)
    intent = parser.parse("2026年8月销售额最高的10个SKU是什么？")
    assert intent.metric == "sales_amount"
    assert intent.metrics == ["sales_amount"]
    assert intent.time_range is None
    assert intent.filters["stat_month"] == "2026-08"


def test_bailian_parser_normalizes_calendar_period_words() -> None:
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    parser = BailianIntentParser(
        MetadataCatalog(METADATA_DIR), client=client, model="test-qwen"
    )
    assert parser.parse("上周销售额是多少？").time_range == "previous_complete_week"
    assert parser.parse("本月销售额是多少？").time_range == "current_data_month"


def _parser_for_payload(payload: dict[str, object]) -> BailianIntentParser:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: response))
    )
    return BailianIntentParser(MetadataCatalog(METADATA_DIR), client=client)


def test_bailian_parser_normalizes_business_paraphrases() -> None:
    parser = _parser_for_payload({
        "metric": "order_count",
        "metrics": ["order_count"],
        "dimensions": ["brand"],
        "time_range": "last_30_days",
        "filters": {},
    })
    intent = parser.parse("近一个月各品牌卖了多少钱、多少单和多少件")
    assert intent.metrics == ["sales_amount", "order_count", "units_sold"]

    parser = _parser_for_payload({
        "metric": "sales_amount",
        "metrics": ["sales_amount", "refund_amount"],
        "dimensions": [],
        "time_range": "last_7_days",
        "filters": {},
    })
    intent = parser.parse("最近7天退款金额占销售额的比例")
    assert intent.metrics == ["refund_rate"]

    assert parser.parse("上月每个品牌退了多少钱").metrics == ["refund_amount"]


def test_bailian_parser_normalizes_sort_and_rejects_unknown_dimension() -> None:
    parser = _parser_for_payload({
        "metric": "sales_amount",
        "metrics": ["sales_amount"],
        "dimensions": [],
        "time_range": "last_90_days",
        "sort": {"field": "sales_amount", "order": "ascending"},
        "filters": {},
    })
    assert parser.parse("近三个月销售金额倒数5名的品牌").sort == "ascending"

    intent = parser.parse("近一个月按运营负责人看销售金额")
    assert "operator" in intent.dimensions
