from pathlib import Path

from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.query.local_runner import LocalQueryRunner
from app.sql.generator import SafeSqlGenerator

PROJECT_DIR = Path(__file__).parents[1]


def _execute(intent: QuestionIntent) -> tuple[str, list[dict[str, object]]]:
    generator = SafeSqlGenerator(MetadataCatalog(PROJECT_DIR / "metadata"))
    sql = generator.generate(intent)
    rows = LocalQueryRunner(
        PROJECT_DIR / "data" / "parquet",
        PROJECT_DIR / "metadata" / "datasets.yaml",
    ).execute(sql)
    return sql, rows


def test_shop_sales_top_3_executes_on_local_data() -> None:
    sql, rows = _execute(QuestionIntent(
        metric="sales_amount",
        dimensions=["shop_code"],
        time_range="last_30_days",
        sort="descending",
        limit=3,
    ))
    assert "GROUP BY shop_code" in sql
    assert len(rows) == 3
    assert {"shop_code", "sales_amount"} <= rows[0].keys()


def test_last_7_day_refund_rate_executes_on_local_data() -> None:
    sql, rows = _execute(QuestionIntent(metric="refund_rate", time_range="last_7_days"))
    assert "INTERVAL 6 DAY" in sql
    assert len(rows) == 1
    assert "refund_rate" in rows[0]


def test_current_data_week_executes_on_local_data() -> None:
    sql, rows = _execute(QuestionIntent(
        metric="sales_amount",
        dimensions=["stat_dt"],
        time_range="current_data_week",
    ))
    assert "WEEKOFYEAR(stat_dt)" in sql
    assert rows


def test_previous_complete_month_executes_on_local_data() -> None:
    sql, rows = _execute(QuestionIntent(
        metric="sales_amount",
        dimensions=["brand"],
        time_range="previous_complete_month",
    ))
    assert "INTERVAL 1 MONTH" in sql
    assert rows
