"""Intent parser interface and deterministic parser used before an LLM adapter."""

from __future__ import annotations

import re
from typing import Protocol

from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog


class IntentParser(Protocol):
    """Any external-model adapter must implement this method."""

    def parse(self, question: str) -> QuestionIntent: ...


class RuleBasedIntentParser:
    """Transparent baseline parser used for development and later evaluation."""

    def __init__(self, catalog: MetadataCatalog) -> None:
        self.catalog = catalog

    def parse(self, question: str) -> QuestionIntent:
        context = self.catalog.search(question)
        dimensions: list[str] = []
        normalized = question.lower()

        dimension_aliases = {
            "brand": ("品牌", "牌子", "brand"),
            "seller_sku": ("sku", "商品"),
            "asin": ("asin",),
            "stat_dt": ("每天", "按天", "日趋势"),
            "shop_code": ("店铺", "shop"),
        }
        for dimension, aliases in dimension_aliases.items():
            if any(alias in normalized for alias in aliases):
                dimensions.append(dimension)

        metric_names = {item["name"] for item in context["metrics"]}
        metric = context["metrics"][0]["name"] if context["metrics"] else None
        # 优先按明确的业务词选择指标，避免“30天”把 SKU 窗口指标排到前面。
        explicit_metric_aliases = {
            "refund_rate": ("退款率", "退款比例"),
            "refund_amount": ("退款金额",),
            "high_value_order_cnt": ("高价值订单", "北极星"),
            "units_sold": ("销量", "销售数量"),
            "sales_amount": ("销售额", "销售金额", "销售收入", "卖了多少钱"),
            "north_star_achievement_rate": ("目标达成率", "达成率"),
        }
        for candidate, aliases in explicit_metric_aliases.items():
            if candidate in metric_names and any(alias in normalized for alias in aliases):
                metric = candidate
                break
        if "北极星" in normalized and "high_value_order_cnt" in metric_names:
            metric = "high_value_order_cnt"
        if (
            "上架" in normalized
            and any(word in normalized for word in ("销量", "单", "件"))
            and "sku_units_30d" in metric_names
        ):
            metric = "sku_units_30d"
        # “最近30天销售额”和“上架30天销售额”是不同口径，结合分析维度消歧。
        if "sales_amount" in metric_names and "上架" not in normalized:
            metric = "sales_amount"
        elif "上架" in normalized and any(word in normalized for word in ("销量", "单", "件")):
            if "sku_units_30d" in metric_names:
                metric = "sku_units_30d"
        elif "seller_sku" in dimensions and "sku_sales_30d" in metric_names and "上架" in normalized:
            metric = "sku_sales_30d"
        elif "seller_sku" in dimensions and "sales_amount" in metric_names:
            metric = "sales_amount"

        time_range = None
        if re.search(r"最近\s*30\s*天|近\s*30\s*天|近一个月", question):
            time_range = "last_30_days"
        elif re.search(r"最近\s*7\s*天|近\s*7\s*天|近一周", question):
            time_range = "last_7_days"
        elif "上个月" in question or "最近一个完整自然月" in question:
            time_range = "previous_complete_month"

        limit_match = re.search(r"(?:前|top\s*)(\d+)", normalized)
        limit = int(limit_match.group(1)) if limit_match else None
        sort = "descending" if any(word in normalized for word in ("最高", "最多", "排名", "top")) else None

        needs_clarification = metric is None
        clarification = "你希望查询哪个指标，例如销售额、订单数或销量？" if needs_clarification else None
        return QuestionIntent(
            metric=metric,
            dimensions=dimensions,
            time_range=time_range,
            sort=sort,
            limit=limit,
            needs_clarification=needs_clarification,
            clarification_question=clarification,
        )
