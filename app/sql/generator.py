"""Deterministic, whitelist-based SQL generation."""

from __future__ import annotations

import re

from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.query_planning.compiler import QueryPlanCompiler
from app.query_planning.planner import QueryPlanner, QueryPlanningError


class SqlGenerationError(ValueError):
    """Raised when an intent cannot be safely translated to SQL."""


class SafeSqlGenerator:
    """Generate SQL only from known metrics, dimensions, and templates."""

    def __init__(self, catalog: MetadataCatalog) -> None:
        self.catalog = catalog
        self.metrics = {item["name"]: item for item in catalog.metrics}
        self.query_planner = QueryPlanner(catalog.metadata_dir / "query_capabilities.yaml")
        self.query_compiler = QueryPlanCompiler()

    def generate(self, intent: QuestionIntent) -> str:
        metric = intent.metric
        if metric not in self.metrics:
            raise SqlGenerationError(f"未知指标: {metric}")
        if (intent.filters or {}).get("analysis") == "trend":
            return self._generate_sales_trend_sql()
        if (intent.filters or {}).get("analysis") == "unmet_target":
            return self._generate_unmet_target_sql()
        if (
            "seller_sku" in intent.dimensions
            and "brand" in intent.dimensions
            and "brand" not in (intent.filters or {})
        ):
            return self._generate_top_sku_per_brand_sql(intent)
        if (
            intent.time_range == "last_30_days"
            and "stat_dt" in intent.dimensions
            and metric in {"high_value_order_cnt", "north_star_achievement_rate"}
        ):
            return self._generate_north_star_sql()
        if metric == "sku_units_30d" and "seller_sku" in intent.dimensions:
            return self._generate_sku_success_sql(intent)
        planning_error: QueryPlanningError | None = None
        try:
            return self.query_compiler.compile(self.query_planner.plan(intent))
        except QueryPlanningError as exc:
            planning_error = exc
            requested = set(intent.metrics or ([intent.metric] if intent.metric else []))
            if requested and requested <= self.query_planner.supported_metrics:
                raise SqlGenerationError(str(exc)) from exc
        if (intent.time_range == "last_30_days" or "stat_month" in (intent.filters or {})) and "seller_sku" in intent.dimensions:
            if metric not in {"sales_amount", "units_sold", "sku_sales_30d"}:
                raise SqlGenerationError("当前 SKU 30 天模板不支持该指标")
            limit = max(1, min(int(intent.limit or 10), 100))
            metric_sql = (
                "SUM(units_ordered) AS units_sold"
                if metric == "units_sold"
                else "ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount"
            )
            order_alias = "units_sold" if metric == "units_sold" else "sales_amount"
            date_filter = self._daily_filters(intent)
            if "stat_month" not in (intent.filters or {}):
                date_filter = "AND stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_sku_tag_day_us)\n                  " + date_filter
            return f"""
                SELECT seller_sku, asin, MAX(brand) AS brand,
                       {metric_sql}
                FROM dws_sku_tag_day_us
                WHERE 1 = 1
                  {date_filter}
                GROUP BY seller_sku, asin
                {self._aggregate_filters(intent, "sales_amount")}
                ORDER BY {order_alias} {self._sort_direction(intent)}
                LIMIT {limit}
            """.strip()
        if intent.time_range == "last_30_days" and any(
            dimension in intent.dimensions for dimension in ("brand", "stat_dt")
        ):
            return self._generate_brand_day_sql(intent)
        if planning_error:
            raise SqlGenerationError(str(planning_error)) from planning_error
        raise SqlGenerationError("当前尚无适配该意图的安全 SQL 模板")

    @staticmethod
    def _generate_north_star_sql() -> str:
        return """
            WITH daily AS (
                SELECT stat_dt, SUM(high_value_order_cnt) AS high_value_order_count
                FROM dws_brand_day_us
                WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
                GROUP BY stat_dt
            ), targets AS (
                SELECT stat_month, MAX(daily_target) AS daily_target
                FROM dim_north_star_target
                GROUP BY stat_month
            )
            SELECT d.stat_dt,
                   d.high_value_order_count,
                   t.daily_target,
                   ROUND(d.high_value_order_count * 1.0 / NULLIF(t.daily_target, 0), 4)
                       AS achievement_rate
            FROM daily d
            LEFT JOIN targets t ON STRFTIME(d.stat_dt, '%Y-%m') = t.stat_month
            ORDER BY d.stat_dt
        """.strip()

    @staticmethod
    def _generate_top_sku_per_brand_sql(intent: QuestionIntent) -> str:
        limit = max(1, min(int(intent.limit or 1), 10))
        return f"""
            WITH sku_sales AS (
                SELECT brand, seller_sku, asin,
                       ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount
                FROM dws_sku_tag_day_us
                WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_sku_tag_day_us)
                GROUP BY brand, seller_sku, asin
            ), ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY brand ORDER BY sales_amount DESC) AS brand_rank
                FROM sku_sales
            )
            SELECT brand, seller_sku, asin, sales_amount
            FROM ranked
            WHERE brand_rank <= {limit}
            ORDER BY brand, sales_amount DESC
        """.strip()

    @staticmethod
    def _generate_sales_trend_sql() -> str:
        return """
            WITH daily AS (
                SELECT stat_dt, ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount
                FROM dws_brand_day_us
                WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
                GROUP BY stat_dt
            ), boundary AS (
                SELECT FIRST_VALUE(sales_amount) OVER (ORDER BY stat_dt) AS first_day_sales,
                       LAST_VALUE(sales_amount) OVER (ORDER BY stat_dt ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_day_sales
                FROM daily
            )
            SELECT first_day_sales, last_day_sales,
                   CASE WHEN last_day_sales > first_day_sales THEN '上升'
                        WHEN last_day_sales < first_day_sales THEN '下降'
                        ELSE '持平' END AS trend
            FROM boundary
            LIMIT 1
        """.strip()

    @staticmethod
    def _generate_overall_refund_rate_sql() -> str:
        return """
            SELECT ROUND(
                SUM(refund_amount) /
                NULLIF(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 0), 4
            ) AS refund_rate
            FROM dws_brand_day_us
            WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
        """.strip()

    @staticmethod
    def _generate_unmet_target_sql() -> str:
        return """
            WITH daily AS (
                SELECT stat_dt, SUM(high_value_order_cnt) AS high_value_order_count
                FROM dws_brand_day_us
                WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
                GROUP BY stat_dt
            ), targets AS (
                SELECT stat_month, MAX(daily_target) AS daily_target
                FROM dim_north_star_target
                GROUP BY stat_month
            )
            SELECT COUNT(*) AS days_without_target
            FROM daily d
            LEFT JOIN targets t ON STRFTIME(d.stat_dt, '%Y-%m') = t.stat_month
            WHERE d.high_value_order_count < t.daily_target
        """.strip()

    @staticmethod
    def _generate_sku_success_sql(intent: QuestionIntent) -> str:
        listing_condition = ""
        if "listing_date" in intent.dimensions:
            listing_condition = "AND TRY_CAST(listing_date AS DATE) <= CURRENT_DATE - INTERVAL 30 DAY"
        return f"""
            SELECT seller_sku, asin, brand, listing_date,
                   units_ordered_30d, ordered_product_sales_30d,
                   CASE WHEN units_ordered_30d >= 20 THEN '达标' ELSE '未达标' END AS success_tier
            FROM ads_aws_sku_period_sales
            WHERE units_ordered_30d < 20
              {listing_condition}
            ORDER BY units_ordered_30d DESC, seller_sku
        """.strip()

    def _generate_brand_day_sql(self, intent: QuestionIntent) -> str:
        supported_metrics = {
            "sales_amount": "ROUND(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 2) AS sales_amount",
            "order_count": "SUM(order_cnt) AS order_count",
            "units_sold": "SUM(units_ordered) AS units_sold",
            "refund_amount": "ROUND(SUM(refund_amount), 2) AS refund_amount",
            "refund_rate": "ROUND(SUM(refund_amount) / NULLIF(SUM(TRY_CAST(ordered_product_sales AS DOUBLE)), 0), 4) AS refund_rate",
        }
        requested = intent.metrics or ([intent.metric] if intent.metric else [])
        if not requested or any(metric not in supported_metrics for metric in requested):
            raise SqlGenerationError("当前品牌日模板不支持该指标")
        dimensions = [dimension for dimension in ("brand", "stat_dt") if dimension in intent.dimensions]
        select_parts = dimensions + [supported_metrics[metric] for metric in requested]
        group_clause = f"GROUP BY {', '.join(dimensions)}" if dimensions else ""
        order_alias = requested[0]
        order_clause = f"ORDER BY {order_alias} {self._sort_direction(intent)}" if intent.sort else ""
        limit_clause = f"LIMIT {max(1, min(int(intent.limit), 100))}" if intent.limit else ""
        return f"""
            SELECT {', '.join(select_parts)}
            FROM dws_brand_day_us
            WHERE stat_dt >= (SELECT MAX(stat_dt) - INTERVAL 29 DAY FROM dws_brand_day_us)
              {self._daily_filters(intent)}
            {group_clause}
            {self._aggregate_filters(intent, order_alias)}
            {order_clause}
            {limit_clause}
        """.strip()

    @staticmethod
    def _sort_direction(intent: QuestionIntent) -> str:
        return "ASC" if intent.sort == "ascending" else "DESC"

    @staticmethod
    def _sql_string(value: str) -> str:
        if not re.fullmatch(r"[\w .-]+", value, flags=re.UNICODE):
            raise SqlGenerationError("过滤条件包含不安全字符")
        return value.replace("'", "''")

    @classmethod
    def _daily_filters(cls, intent: QuestionIntent) -> str:
        filters = intent.filters or {}
        clauses: list[str] = []
        if brand := filters.get("brand"):
            clauses.append(f"AND brand = '{cls._sql_string(str(brand))}'")
        if month := filters.get("stat_month"):
            if not re.fullmatch(r"\d{4}-\d{2}", str(month)):
                raise SqlGenerationError("月份过滤必须使用 YYYY-MM 格式")
            clauses.append(f"AND STRFTIME(stat_dt, '%Y-%m') = '{month}'")
        return "\n                  ".join(clauses)

    @staticmethod
    def _aggregate_filters(intent: QuestionIntent, alias: str) -> str:
        minimum = (intent.filters or {}).get("sales_amount_min")
        if not minimum:
            return ""
        if not re.fullmatch(r"\d+(?:\.\d+)?", str(minimum)):
            raise SqlGenerationError("销售额阈值必须是数字")
        return f"HAVING {alias} > {minimum}"

    def datasets_for(self, intent: QuestionIntent) -> list[str]:
        """Return the physical datasets used by the selected SQL template."""
        if (intent.filters or {}).get("analysis") == "trend":
            return ["dws_brand_day_us"]
        if (intent.filters or {}).get("analysis") == "unmet_target":
            return ["dws_brand_day_us", "dim_north_star_target"]
        if (
            "seller_sku" in intent.dimensions
            and "brand" in intent.dimensions
            and "brand" not in (intent.filters or {})
        ):
            return ["dws_sku_tag_day_us"]
        if intent.metric in {"high_value_order_cnt", "north_star_achievement_rate"} and "stat_dt" in intent.dimensions:
            return ["dws_brand_day_us", "dim_north_star_target"]
        if intent.metric == "sku_units_30d" and "seller_sku" in intent.dimensions:
            return ["ads_aws_sku_period_sales"]
        try:
            return [self.query_planner.plan(intent).dataset]
        except QueryPlanningError:
            pass
        if (intent.time_range == "last_30_days" or "stat_month" in (intent.filters or {})) and "seller_sku" in intent.dimensions:
            return ["dws_sku_tag_day_us"]
        raise SqlGenerationError("当前尚无适配该意图的数据集")
