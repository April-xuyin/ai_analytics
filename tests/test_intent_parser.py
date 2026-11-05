from pathlib import Path

from app.intent.parser import RuleBasedIntentParser
from app.metadata.loader import MetadataCatalog

METADATA_DIR = Path(__file__).parents[1] / "metadata"


def test_parse_top_brand_sales_question() -> None:
    parser = RuleBasedIntentParser(MetadataCatalog(METADATA_DIR))
    intent = parser.parse("最近30天销售额最高的前5个品牌是什么？")
    assert intent.metric == "sales_amount"
    assert intent.metrics == []
    assert intent.dimensions == ["brand"]
    assert intent.time_range == "last_30_days"
    assert intent.sort == "descending"
    assert intent.limit == 5
    assert intent.needs_clarification is False


def test_parse_unknown_metric_requests_clarification() -> None:
    parser = RuleBasedIntentParser(MetadataCatalog(METADATA_DIR))
    intent = parser.parse("最近哪些商品表现不好？")
    assert intent.needs_clarification is True
    assert intent.clarification_question
