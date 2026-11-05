"""Compile validated query plans into a small, deterministic SQL subset."""

from __future__ import annotations

import re
from typing import ClassVar

from app.query_planning.planner import QueryPlan, QueryPlanningError


class QueryPlanCompiler:
    ALLOWED_FILTERS: ClassVar[set[str]] = {
        "brand", "shop_code", "seller_sku", "asin", "stat_month", "sales_amount_min"
    }

    def compile(self, plan: QueryPlan) -> str:
        select_parts = [*plan.dimensions, *[plan.metric_expressions[item] for item in plan.metrics]]
        where_parts = ["1 = 1"]
        if plan.time_range in {"last_7_days", "last_30_days", "last_90_days"}:
            days = {"last_7_days": 7, "last_30_days": 30, "last_90_days": 90}[plan.time_range]
            where_parts.append(
                f"{plan.time_field} >= (SELECT MAX({plan.time_field}) - INTERVAL {days - 1} DAY "
                f"FROM {plan.dataset})"
            )
        elif plan.time_range:
            where_parts.extend(self._calendar_time_filters(plan))
        self._append_filters(plan, where_parts)

        group_clause = f"GROUP BY {', '.join(plan.dimensions)}" if plan.dimensions else ""
        having_clause = self._having_clause(plan)
        order_clause = ""
        if plan.sort:
            direction = "ASC" if plan.sort == "ascending" else "DESC"
            order_clause = f"ORDER BY {plan.metrics[0]} {direction}"
        limit_clause = ""
        if plan.limit is not None:
            limit_clause = f"LIMIT {max(1, min(int(plan.limit), 100))}"
        where_clause = "\n              AND ".join(where_parts)
        return f"""
            SELECT {', '.join(select_parts)}
            FROM {plan.dataset}
            WHERE {where_clause}
            {group_clause}
            {having_clause}
            {order_clause}
            {limit_clause}
        """.strip()

    @staticmethod
    def _calendar_time_filters(plan: QueryPlan) -> list[str]:
        field = plan.time_field
        maximum = f"(SELECT MAX({field}) FROM {plan.dataset})"
        if plan.time_range == "current_data_week":
            anchor = maximum
            return [f"YEAR({field}) = YEAR({anchor})", f"WEEKOFYEAR({field}) = WEEKOFYEAR({anchor})"]
        if plan.time_range == "previous_complete_week":
            anchor = f"(SELECT MAX({field}) - INTERVAL 7 DAY FROM {plan.dataset})"
            return [f"YEAR({field}) = YEAR({anchor})", f"WEEKOFYEAR({field}) = WEEKOFYEAR({anchor})"]
        if plan.time_range == "current_data_month":
            return [
                (
                    f"SUBSTR(CAST({field} AS STRING), 1, 7) = "
                    f"SUBSTR(CAST({maximum} AS STRING), 1, 7)"
                )
            ]
        if plan.time_range == "previous_complete_month":
            previous_month = f"(SELECT MAX({field}) - INTERVAL 1 MONTH FROM {plan.dataset})"
            return [
                (
                    f"SUBSTR(CAST({field} AS STRING), 1, 7) = "
                    f"SUBSTR(CAST({previous_month} AS STRING), 1, 7)"
                )
            ]
        raise QueryPlanningError(f"暂不支持时间范围: {plan.time_range}")

    def _append_filters(self, plan: QueryPlan, where_parts: list[str]) -> None:
        unknown = set(plan.filters) - self.ALLOWED_FILTERS
        if unknown:
            raise QueryPlanningError(f"通用查询暂不支持过滤条件: {', '.join(sorted(unknown))}")
        for field in ("brand", "shop_code", "seller_sku", "asin"):
            if value := plan.filters.get(field):
                where_parts.append(f"{field} = '{self._safe_string(value)}'")
        if month := plan.filters.get("stat_month"):
            if not re.fullmatch(r"\d{4}-\d{2}", str(month)):
                raise QueryPlanningError("月份过滤必须使用 YYYY-MM 格式")
            where_parts.append(f"SUBSTR(CAST({plan.time_field} AS STRING), 1, 7) = '{month}'")

    @staticmethod
    def _having_clause(plan: QueryPlan) -> str:
        minimum = plan.filters.get("sales_amount_min")
        if minimum is None:
            return ""
        if "sales_amount" not in plan.metrics:
            raise QueryPlanningError("销售额阈值只能用于销售额查询")
        if not re.fullmatch(r"\d+(?:\.\d+)?", str(minimum)):
            raise QueryPlanningError("销售额阈值必须是数字")
        return f"HAVING sales_amount > {minimum}"

    @staticmethod
    def _safe_string(value: str) -> str:
        text = str(value)
        if not re.fullmatch(r"[\w .-]+", text, flags=re.UNICODE):
            raise QueryPlanningError("过滤条件包含不安全字符")
        return text
