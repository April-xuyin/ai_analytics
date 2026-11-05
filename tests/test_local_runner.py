from pathlib import Path

import pytest

from app.query.local_runner import LocalQueryRunner, QueryError

DATA_DIR = Path(__file__).parents[1] / "data" / "parquet"
METADATA_FILE = Path(__file__).parents[1] / "metadata" / "datasets.yaml"


def test_query_brand_sales() -> None:
    runner = LocalQueryRunner(DATA_DIR, METADATA_FILE)
    rows = runner.execute(
        """
        SELECT brand, SUM(TRY_CAST(ordered_product_sales AS DOUBLE)) AS sales
        FROM dws_brand_day_us
        GROUP BY brand
        ORDER BY sales DESC
        """
    )
    assert rows
    assert "brand" in rows[0]


def test_reject_write_statement() -> None:
    runner = LocalQueryRunner(DATA_DIR, METADATA_FILE)
    with pytest.raises(QueryError):
        runner.execute("DROP TABLE anything")


def test_reject_dataset_outside_whitelist() -> None:
    runner = LocalQueryRunner(DATA_DIR, METADATA_FILE)
    with pytest.raises(QueryError, match="未加入白名单"):
        runner.parquet_path("secret_orders")
