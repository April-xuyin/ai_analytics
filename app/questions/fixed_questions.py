"""Deterministic business questions used before introducing an LLM."""

from __future__ import annotations

from typing import Any

from app.query.local_runner import LocalQueryRunner

SALES_DEFINITION = "US销售额；排除订单状态4、5，不含税，包含退退订单。"


def _latest_30_day_range(runner: LocalQueryRunner) -> tuple[object, object]:
    """Return the latest 30-day range available in the local brand dataset."""
    rows = runner.execute(
        """
        SELECT MAX(stat_dt) - INTERVAL 29 DAY AS data_start_date,
               MAX(stat_dt) AS data_end_date
        FROM dws_brand_day_us
        """,
        max_rows=1,
    )
    return rows[0]["data_start_date"], rows[0]["data_end_date"]


def top_brands_last_30_days(runner: LocalQueryRunner) -> dict[str, Any]:
    """Return the five brands with the highest sales in the latest 30 data days."""
    sql = """
        WITH date_range AS (
            SELECT
                MAX(stat_dt) AS data_end_date,
                MAX(stat_dt) - INTERVAL 29 DAY AS data_start_date
            FROM dws_brand_day_us
        )
        SELECT
            b.brand,
            ROUND(
                SUM(TRY_CAST(b.ordered_product_sales AS DOUBLE)),
                2
            ) AS sales_amount
        FROM dws_brand_day_us AS b
        CROSS JOIN date_range AS d
        WHERE b.stat_dt BETWEEN d.data_start_date AND d.data_end_date
        GROUP BY b.brand
        ORDER BY sales_amount DESC
        LIMIT 5
    """

    rows = runner.execute(sql, max_rows=5)
    start_date, end_date = _latest_30_day_range(runner)

    return {
        "question": "最近30天销售额最高的5个品牌是什么？",
        "dataset": "dws_brand_day_us",
        "metric": "sales_amount",
        "metric_definition": SALES_DEFINITION,
        "data_start_date": start_date,
        "data_end_date": end_date,
        "sql": sql.strip(),
        "rows": rows,
    }


def brand_overview_last_30_days(runner: LocalQueryRunner) -> dict[str, Any]:
    """Return sales, orders and units by brand for the latest 30 days."""
    sql = """
        SELECT brand,
               ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount,
               SUM(order_cnt) AS order_count,
               SUM(units_ordered) AS units_sold
        FROM dws_brand_day_us
        WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
        GROUP BY brand
        ORDER BY sales_amount DESC
    """
    start_date, end_date = _latest_30_day_range(runner)
    return {"question": "最近30天各品牌的销售额、订单数和销量分别是多少？",
            "datasets": ["dws_brand_day_us"], "metrics": ["sales_amount", "order_count", "units_sold"],
            "metric_definition": SALES_DEFINITION, "data_start_date": start_date,
            "data_end_date": end_date, "sql": sql.strip(), "rows": runner.execute(sql)}


def daily_sales_trend_last_30_days(runner: LocalQueryRunner) -> dict[str, Any]:
    """Return daily sales for the latest 30-day data window."""
    sql = """
        SELECT stat_dt,
               ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount
        FROM dws_brand_day_us
        WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
        GROUP BY stat_dt
        ORDER BY stat_dt
    """
    start_date, end_date = _latest_30_day_range(runner)
    return {"question": "最近30天销售额按天的趋势是什么？", "datasets": ["dws_brand_day_us"],
            "metrics": ["sales_amount"], "metric_definition": SALES_DEFINITION,
            "data_start_date": start_date, "data_end_date": end_date,
            "sql": sql.strip(), "rows": runner.execute(sql, max_rows=30)}


def brand_refund_rate_last_30_days(runner: LocalQueryRunner) -> dict[str, Any]:
    """Calculate brand refund rates from additive amounts, not averaged daily rates."""
    sql = """
        SELECT brand,
               ROUND(SUM(refund_amount) / NULLIF(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 0), 4)
                   AS refund_rate
        FROM dws_brand_day_us
        WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
        GROUP BY brand
        ORDER BY refund_rate DESC NULLS LAST
    """
    start_date, end_date = _latest_30_day_range(runner)
    return {"question": "最近30天各品牌的退款率是多少？", "datasets": ["dws_brand_day_us"],
            "metrics": ["refund_rate"], "metric_definition": "退款率=汇总退款金额/汇总销售额，不能平均每日退款率。",
            "data_start_date": start_date, "data_end_date": end_date,
            "sql": sql.strip(), "rows": runner.execute(sql)}


def north_star_daily_last_30_days(runner: LocalQueryRunner) -> dict[str, Any]:
    """Return daily high-value orders and target achievement rates."""
    sql = """
        WITH daily AS (
            SELECT stat_dt, SUM(high_value_order_cnt) AS high_value_order_count
            FROM dws_brand_day_us
            WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
            GROUP BY stat_dt
        ), targets AS (
            SELECT stat_month, MAX(daily_target) AS daily_target
            FROM dim_north_star_target GROUP BY stat_month
        )
        SELECT d.stat_dt, d.high_value_order_count, t.daily_target,
               ROUND(d.high_value_order_count * 1.0 / NULLIF(t.daily_target, 0), 4) AS achievement_rate
        FROM daily d LEFT JOIN targets t ON STRFTIME(d.stat_dt, '%Y-%m') = t.stat_month
        ORDER BY d.stat_dt
    """
    start_date, end_date = _latest_30_day_range(runner)
    return {"question": "最近30天每天的高价值订单数和目标达成率是多少？",
            "datasets": ["dws_brand_day_us", "dim_north_star_target"],
            "metrics": ["high_value_order_cnt", "north_star_achievement_rate"],
            "metric_definition": "达成率=每日高价值订单数/月度配置的每日目标。",
            "data_start_date": start_date, "data_end_date": end_date,
            "sql": sql.strip(), "rows": runner.execute(sql, max_rows=30)}


def failed_skus_after_30_days(runner: LocalQueryRunner) -> dict[str, Any]:
    """Return SKUs old enough for evaluation but below the 20-unit target."""
    sql = """
        SELECT seller_sku, asin, brand, TRY_CAST(listing_date AS DATE) AS listing_date,
               units_ordered_30d, ordered_product_sales_30d
        FROM ads_aws_sku_period_sales
        WHERE TRY_CAST(listing_date AS DATE) <= CURRENT_DATE - INTERVAL 30 DAY
          AND units_ordered_30d < 20
        ORDER BY units_ordered_30d DESC, seller_sku
    """
    return {"question": "上架满30天但30天销量没有达到20单的SKU有哪些？",
            "datasets": ["ads_aws_sku_period_sales"], "metrics": ["sku_units_30d"],
            "metric_definition": "上架满30天且上架30天窗口销量低于20件。",
            "sql": sql.strip(), "rows": runner.execute(sql)}


def top_skus_last_30_days(runner: LocalQueryRunner, limit: int = 10) -> dict[str, Any]:
    """Return top SKUs by sales in the latest 30 data days."""
    safe_limit = max(1, min(int(limit), 100))
    sql = f"""
        SELECT seller_sku, asin, MAX(brand) AS brand,
               ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount,
               SUM(units_ordered) AS units_sold
        FROM dws_sku_tag_day_us
        WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_sku_tag_day_us)
        GROUP BY seller_sku, asin
        ORDER BY sales_amount DESC
        LIMIT {safe_limit}
    """
    start_date, end_date = _latest_30_day_range(runner)
    return {"question": f"最近30天销售额最高的{safe_limit}个SKU是什么？",
            "datasets": ["dws_sku_tag_day_us"], "metrics": ["sales_amount", "units_sold"],
            "metric_definition": SALES_DEFINITION, "data_start_date": start_date,
            "data_end_date": end_date, "sql": sql.strip(),
            "rows": runner.execute(sql, max_rows=safe_limit)}
