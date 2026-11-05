import pytest

from app.query.sql_security import SqlSecurityError, SqlSecurityValidator


@pytest.fixture
def validator() -> SqlSecurityValidator:
    return SqlSecurityValidator(
        {"dws_brand_day_us"},
        {"brand", "stat_dt", "ordered_product_sales", "refund_amount"},
    )


def test_allows_whitelisted_select_and_cte(validator: SqlSecurityValidator) -> None:
    validator.validate(
        "WITH daily AS (SELECT brand, SUM(ordered_product_sales) AS sales_amount "
        "FROM dws_brand_day_us GROUP BY brand) SELECT brand, sales_amount FROM daily"
    )


@pytest.mark.parametrize("sql", [
    "DROP TABLE dws_brand_day_us",
    "SELECT * FROM dws_brand_day_us; DELETE FROM dws_brand_day_us",
    "SELECT * FROM secret_orders",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM read_parquet('/etc/passwd')",
    "SELECT read_file('/etc/passwd')",
    "SELECT secret_margin FROM dws_brand_day_us",
])
def test_rejects_unsafe_sql(validator: SqlSecurityValidator, sql: str) -> None:
    with pytest.raises(SqlSecurityError):
        validator.validate(sql)
