from pathlib import Path

from app.query.local_runner import LocalQueryRunner
from app.questions.fixed_questions import (
    brand_overview_last_30_days,
    brand_refund_rate_last_30_days,
    daily_sales_trend_last_30_days,
    failed_skus_after_30_days,
    north_star_daily_last_30_days,
    top_brands_last_30_days,
    top_skus_last_30_days,
)

PROJECT_DIR = Path(__file__).parents[1]
DATA_DIR = PROJECT_DIR / "data" / "parquet"
METADATA_FILE = PROJECT_DIR / "metadata" / "datasets.yaml"


def test_top_brands_last_30_days() -> None:
    runner = LocalQueryRunner(DATA_DIR, METADATA_FILE)

    answer = top_brands_last_30_days(runner)

    assert answer["question"] == "最近30天销售额最高的5个品牌是什么？"
    assert answer["dataset"] == "dws_brand_day_us"
    assert answer["metric"] == "sales_amount"
    assert answer["data_start_date"] is not None
    assert answer["data_end_date"] is not None
    assert 1 <= len(answer["rows"]) <= 5
    assert answer["rows"] == sorted(
        answer["rows"], key=lambda row: row["sales_amount"], reverse=True
    )


def test_second_batch_fixed_questions() -> None:
    runner = LocalQueryRunner(DATA_DIR, METADATA_FILE)
    overview = brand_overview_last_30_days(runner)
    trend = daily_sales_trend_last_30_days(runner)
    refunds = brand_refund_rate_last_30_days(runner)
    north_star = north_star_daily_last_30_days(runner)
    failed_skus = failed_skus_after_30_days(runner)

    assert overview["rows"] and {"sales_amount", "order_count", "units_sold"} <= overview["rows"][0].keys()
    assert 1 <= len(trend["rows"]) <= 30
    assert refunds["rows"] and all(row["refund_rate"] is None or row["refund_rate"] >= 0 for row in refunds["rows"])
    assert north_star["rows"] and "achievement_rate" in north_star["rows"][0]
    assert failed_skus["rows"] and all(row["units_ordered_30d"] < 20 for row in failed_skus["rows"])


def test_top_skus_last_30_days() -> None:
    runner = LocalQueryRunner(DATA_DIR, METADATA_FILE)
    answer = top_skus_last_30_days(runner, 10)
    assert len(answer["rows"]) <= 10
    assert answer["rows"]
    assert {"seller_sku", "asin", "sales_amount"} <= answer["rows"][0].keys()
