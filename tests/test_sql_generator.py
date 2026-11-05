from pathlib import Path

import pytest

from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.sql.generator import SafeSqlGenerator, SqlGenerationError


def test_generator_builds_safe_sku_sql() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount", dimensions=["seller_sku", "asin"],
        time_range="last_30_days", sort="descending", limit=10,
    ))
    assert "FROM dws_sku_tag_day_us" in sql
    assert "LIMIT 10" in sql
    assert "DROP" not in sql.upper()
    assert generator.datasets_for(QuestionIntent(
        metric="sales_amount", dimensions=["seller_sku", "asin"],
        time_range="last_30_days",
    )) == ["dws_sku_tag_day_us"]


def test_generator_builds_brand_overview_sql() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount", metrics=["sales_amount", "order_count", "units_sold"],
        dimensions=["brand"], time_range="last_30_days",
    ))
    assert "FROM dws_brand_day_us" in sql
    assert "GROUP BY brand" in sql
    assert "order_count" in sql


def test_generator_builds_daily_refund_rate_sql() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="refund_rate", dimensions=["stat_dt"], time_range="last_30_days",
    ))
    assert "GROUP BY stat_dt" in sql
    assert "NULLIF" in sql


def test_generator_builds_north_star_join_sql() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="high_value_order_cnt", metrics=["high_value_order_cnt", "north_star_achievement_rate"],
        dimensions=["stat_dt"], time_range="last_30_days",
    ))
    assert "dim_north_star_target" in sql
    assert "achievement_rate" in sql
    assert generator.datasets_for(QuestionIntent(
        metric="high_value_order_cnt", dimensions=["stat_dt"], time_range="last_30_days",
    )) == ["dws_brand_day_us", "dim_north_star_target"]


def test_generator_builds_sku_success_sql() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sku_units_30d", dimensions=["seller_sku", "asin", "listing_date"],
    ))
    assert "FROM ads_aws_sku_period_sales" in sql
    assert "units_ordered_30d < 20" in sql


def test_generator_applies_brand_and_threshold_filters() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount", dimensions=["seller_sku", "asin"],
        time_range="last_30_days", sort="descending", limit=10,
        filters={"brand": "Cuspin", "sales_amount_min": "10000"},
    ))
    assert "brand = 'Cuspin'" in sql
    assert "HAVING sales_amount > 10000" in sql


def test_generator_uses_units_sold_for_recent_sku_volume() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="units_sold", dimensions=["seller_sku", "asin"],
        time_range="last_30_days", sort="descending", limit=5,
    ))
    assert "SUM(units_ordered) AS units_sold" in sql
    assert "ORDER BY units_sold DESC" in sql
    assert "ads_aws_sku_period_sales" not in sql


def test_generator_orders_brand_ranking() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount", dimensions=["brand"],
        time_range="last_30_days", sort="descending", limit=1,
    ))
    assert "ORDER BY sales_amount DESC" in sql
    assert "LIMIT 1" in sql


def test_generator_supports_monthly_sku_volume_ranking() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="units_sold", dimensions=["seller_sku", "asin"],
        sort="descending", limit=10, filters={"stat_month": "2026-06"},
    ))
    assert "FROM dws_sku_tag_day_us" in sql
    assert "SUBSTR(CAST(stat_dt AS STRING), 1, 7) = '2026-06'" in sql
    assert "SUM(units_ordered) AS units_sold" in sql


def test_generator_ranks_top_sku_within_each_brand() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount", dimensions=["brand", "seller_sku", "asin"],
        time_range="last_30_days", sort="descending",
    ))
    assert "PARTITION BY brand" in sql
    assert "ROW_NUMBER()" in sql


def test_generator_calculates_sales_trend() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount", dimensions=["stat_dt"], time_range="last_30_days",
        filters={"analysis": "trend"},
    ))
    assert "CASE WHEN last_day_sales > first_day_sales" in sql


def test_generator_calculates_overall_refund_rate() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="refund_rate", time_range="last_30_days",
    ))
    assert "SUM(refund_amount)" in sql
    assert "NULLIF(SUM" in sql
    assert "GROUP BY" not in sql


def test_generator_counts_unmet_north_star_days() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="high_value_order_cnt", dimensions=["stat_dt"],
        time_range="last_30_days", filters={"analysis": "unmet_target"},
    ))
    assert "COUNT(*) AS days_without_target" in sql
    assert "d.high_value_order_count < t.daily_target" in sql


def test_generic_planner_ranks_shops_by_sales() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    intent = QuestionIntent(
        metric="sales_amount",
        dimensions=["shop_code"],
        time_range="last_30_days",
        sort="descending",
        limit=3,
    )
    sql = generator.generate(intent)
    assert "FROM dws_sku_tag_day_us" in sql
    assert "GROUP BY shop_code" in sql
    assert "ORDER BY sales_amount DESC" in sql
    assert "LIMIT 3" in sql
    assert generator.datasets_for(intent) == ["dws_sku_tag_day_us"]


def test_generic_planner_calculates_last_7_day_refund_rate() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    intent = QuestionIntent(metric="refund_rate", time_range="last_7_days")
    sql = generator.generate(intent)
    assert "FROM dws_brand_day_us" in sql
    assert "INTERVAL 6 DAY" in sql
    assert "NULLIF" in sql
    assert "GROUP BY" not in sql


def test_generic_planner_supports_last_90_day_brand_units() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="units_sold",
        dimensions=["brand"],
        time_range="last_90_days",
    ))
    assert "FROM dws_brand_day_us" in sql
    assert "INTERVAL 89 DAY" in sql
    assert "GROUP BY brand" in sql


def test_shop_filter_forces_shop_aware_dataset() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    sql = generator.generate(QuestionIntent(
        metric="sales_amount",
        time_range="last_7_days",
        filters={"shop_code": "CuspinArtGallery-US"},
    ))
    assert "FROM dws_sku_tag_day_us" in sql
    assert "shop_code = 'CuspinArtGallery-US'" in sql


def test_unsupported_filter_is_not_silently_ignored() -> None:
    generator = SafeSqlGenerator(MetadataCatalog(Path(__file__).parents[1] / "metadata"))
    with pytest.raises(SqlGenerationError, match="不支持过滤条件"):
        generator.generate(QuestionIntent(
            metric="sales_amount",
            dimensions=["brand"],
            time_range="last_30_days",
            filters={"gross_margin_pct_max": "0.2"},
        ))
