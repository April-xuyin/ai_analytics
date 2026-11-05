
import pytest

from app.query.local_runner import QueryError
from app.query.maxcompute_runner import MaxComputeQueryRunner


def test_maxcompute_runner_rejects_write_sql_without_connecting() -> None:
    runner = object.__new__(MaxComputeQueryRunner)
    runner.datasets = {"dws_brand_day_us"}
    with pytest.raises(QueryError, match="只允许"):
        runner.execute("DROP TABLE dws_brand_day_us")


def test_maxcompute_runner_requires_select_or_with() -> None:
    runner = object.__new__(MaxComputeQueryRunner)
    runner.datasets = {"dws_brand_day_us"}
    with pytest.raises(QueryError, match="只允许"):
        runner.execute("CREATE TABLE test (id BIGINT)")


def test_maxcompute_sql_translates_known_duckdb_syntax() -> None:
    sql = MaxComputeQueryRunner._to_maxcompute_sql(
        """SELECT seller_sku, asin, MAX(brand) AS brand,
        ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount
        FROM dws_sku_tag_day_us
        WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_sku_tag_day_us)
        GROUP BY seller_sku, asin"""
    )
    assert "CAST(ordered_product_sales AS DOUBLE)" in sql
    assert "DATEADD(MAX(stat_dt), -29, 'dd')" in sql
    assert "brand AS brand" in sql
    assert "GROUP BY seller_sku, asin, brand" in sql


def test_maxcompute_sql_translates_variable_day_window() -> None:
    sql = MaxComputeQueryRunner._to_maxcompute_sql(
        "SELECT * FROM dws_brand_day_us "
        "WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 6 DAY FROM dws_brand_day_us)"
    )
    assert "DATEADD(MAX(stat_dt), -6, 'dd')" in sql


def test_maxcompute_sql_translates_previous_month_anchor() -> None:
    sql = MaxComputeQueryRunner._to_maxcompute_sql(
        "SELECT * FROM dws_brand_day_us WHERE stat_dt >= "
        "(SELECT MAX(stat_dt) - INTERVAL 1 MONTH FROM dws_brand_day_us)"
    )
    assert "DATEADD(MAX(stat_dt), -1, 'mm')" in sql


def test_maxcompute_runner_rejects_invalid_row_limit() -> None:
    runner = object.__new__(MaxComputeQueryRunner)
    runner.datasets = {"dws_brand_day_us"}
    with pytest.raises(QueryError, match="max_rows"):
        runner.execute("SELECT 1", max_rows=0)


def test_maxcompute_runner_wraps_timeout_as_query_error() -> None:
    class TimedOutInstance:
        def wait_for_success(self, timeout):
            assert timeout == 1
            raise TimeoutError("query timed out")

    class FakeClient:
        def execute_sql(self, statement):
            return TimedOutInstance()

    runner = object.__new__(MaxComputeQueryRunner)
    runner.datasets = {"dws_brand_day_us"}
    runner.columns = {"brand"}
    runner.timeout_seconds = 1
    runner.client = FakeClient()
    with pytest.raises(QueryError, match="MaxCompute SQL 执行失败"):
        runner.execute("SELECT brand FROM dws_brand_day_us")
