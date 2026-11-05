"""Alibaba Cloud Bailian (Qwen) intent parser via an OpenAI-compatible API."""

from __future__ import annotations

import json
import os
import re
from time import monotonic
from typing import Any

from openai import OpenAI

from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog


class BailianConfigError(ValueError):
    """Raised when required Bailian settings are missing."""


class BailianIntentParser:
    """Parse analytics questions with Qwen while keeping a provider-neutral output."""

    def __init__(
        self,
        catalog: MetadataCatalog,
        client: Any | None = None,
        model: str | None = None,
    ) -> None:
        self.catalog = catalog
        self.model = model or os.getenv("BAILIAN_MODEL", "qwen-plus")
        self.usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "duration_ms": 0.0}
        if client is not None:
            self.client = client
            return
        api_key = os.getenv("BAILIAN_API_KEY")
        if not api_key:
            raise BailianConfigError("缺少 BAILIAN_API_KEY，请先配置环境变量。")
        self.client = OpenAI(
            api_key=api_key,
            base_url=os.getenv(
                "BAILIAN_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ),
        )

    def parse(self, question: str) -> QuestionIntent:
        context = self.catalog.search(question)
        prompt = self._build_prompt(question, context)
        started = monotonic()
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是企业智能问数的问题解析器。只返回合法JSON，不生成SQL。",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        self.usage["calls"] += 1
        self.usage["duration_ms"] += round((monotonic() - started) * 1000, 2)
        response_usage = getattr(response, "usage", None)
        self.usage["prompt_tokens"] += int(
            getattr(response_usage, "prompt_tokens", 0) or 0
        )
        self.usage["completion_tokens"] += int(
            getattr(response_usage, "completion_tokens", 0) or 0
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("百炼模型没有返回内容")
        data = json.loads(content)
        intent = QuestionIntent(
            metric=data.get("metric"),
            metrics=data.get("metrics") or ([data["metric"]] if data.get("metric") else []),
            dimensions=data.get("dimensions") or [],
            time_range=data.get("time_range"),
            sort=data.get("sort"),
            limit=data.get("limit"),
            filters=data.get("filters") or {},
            needs_clarification=bool(data.get("needs_clarification", False)),
            clarification_question=data.get("clarification_question"),
        )
        # These lexical facts are safer to enforce deterministically than to
        # leave entirely to a probabilistic model response.
        normalized = question.replace(" ", "").lower()
        if isinstance(intent.sort, dict):
            raw_direction = intent.sort.get("direction") or intent.sort.get("order")
            intent.sort = (
                "ascending"
                if raw_direction in {"ascending", "asc"}
                else "descending"
                if raw_direction in {"descending", "desc"}
                else None
            )
        if "店铺" in normalized or "shop" in normalized:
            if "shop_code" not in intent.dimensions:
                intent.dimensions.append("shop_code")
            if "品牌" not in normalized:
                intent.dimensions = [item for item in intent.dimensions if item != "brand"]
        is_product_query = "sku" in normalized or "商品" in normalized
        if is_product_query:
            for dimension in ("seller_sku", "asin"):
                if dimension not in intent.dimensions:
                    intent.dimensions.append(dimension)
            groups_by_brand = any(
                word in normalized for word in ("各品牌", "每个品牌", "按品牌")
            )
            if not groups_by_brand:
                intent.dimensions = [item for item in intent.dimensions if item != "brand"]
        if not any(word in normalized for word in ("每天", "按天", "日趋势", "趋势")):
            intent.dimensions = [item for item in intent.dimensions if item != "stat_dt"]
        if re.search(r"(?:最近|近)7天|近一周", normalized):
            intent.time_range = "last_7_days"
        elif re.search(r"(?:最近|近)90天|近三个月", normalized):
            intent.time_range = "last_90_days"
        elif re.search(r"(?:最近|近)30天|近一个月", normalized):
            intent.time_range = "last_30_days"
        if "上周" in normalized:
            intent.time_range = "previous_complete_week"
        elif "本周" in normalized or "这周" in normalized:
            intent.time_range = "current_data_week"
        elif "上个月" in normalized or "上月" in normalized:
            intent.time_range = "previous_complete_month"
        elif "本月" in normalized or "这个月" in normalized:
            intent.time_range = "current_data_month"
        limit_match = re.search(r"(?:前|top)(\d+)", normalized)
        if limit_match:
            intent.limit = int(limit_match.group(1))
        if any(word in normalized for word in ("最低", "最少", "最小", "倒数")):
            intent.sort = "ascending"
        elif any(word in normalized for word in ("最高", "最多", "排名", "top")):
            intent.sort = "descending"
        month_match = re.search(r"(?:20)?(\d{2})年(\d{1,2})月", normalized)
        if month_match:
            intent.filters["stat_month"] = f"20{month_match.group(1)}-{int(month_match.group(2)):02d}"
            intent.time_range = None
        explicit_metrics: list[str] = []
        metric_words = (
            ("sales_amount", ("销售额", "销售金额", "销售收入", "多少钱")),
            ("order_count", ("订单数", "订单量", "多少单", "几单")),
            ("units_sold", ("销量", "销售数量", "多少件", "几件")),
            ("refund_amount", ("退款金额", "退货金额")),
            ("refund_rate", ("退款率", "退款比例", "退货率")),
        )
        if "上架" not in normalized:
            explicit_metrics = [
                metric
                for metric, words in metric_words
                if any(word in normalized for word in words)
            ]
        if ("退款" in normalized or "退货" in normalized) and "占销售额" in normalized:
            explicit_metrics = ["refund_rate"]
        elif ("退了多少钱" in normalized or "退款多少钱" in normalized):
            explicit_metrics = ["refund_amount"]
        elif not explicit_metrics and (
            "卖得最好" in normalized
            or (is_product_query and "销售" in normalized)
        ):
            explicit_metrics = ["sales_amount"]
        if explicit_metrics:
            intent.metric = explicit_metrics[0]
            intent.metrics = explicit_metrics
        if intent.filters.get("brand") and "seller_sku" in intent.dimensions:
            intent.dimensions = [item for item in intent.dimensions if item != "brand"]
        if (
            "运营人员" in normalized or "运营负责人" in normalized
        ) and "operator" not in intent.dimensions:
            intent.dimensions.append("operator")
        if "上升还是下降" in normalized or "趋势" in normalized:
            intent.filters["analysis"] = "trend"
        if "未达成" in normalized or "没完成" in normalized:
            intent.filters["analysis"] = "unmet_target"
        has_time = intent.time_range is not None or "stat_month" in intent.filters
        if (
            explicit_metrics
            and has_time
            and self.catalog.supports_query(intent.metrics, intent.dimensions)
        ):
            intent.needs_clarification = False
            intent.clarification_question = None
        return intent

    def _build_prompt(self, question: str, context: dict[str, list[dict[str, Any]]]) -> str:
        compact_context = {
            "metrics": [
                {
                    "name": item.get("name"),
                    "aliases": item.get("aliases"),
                    "dataset": item.get("dataset"),
                    "dimensions": item.get("dimensions"),
                }
                for item in context["metrics"]
            ],
            "datasets": [
                {
                    "name": item.get("name"),
                    "grain": item.get("grain"),
                    "dimensions": item.get("dimensions"),
                }
                for item in context["datasets"]
            ],
            "terms": context["terms"],
            "relationships": context.get("relationships", []),
            "examples": [
                {
                    "question": item.get("question"),
                    "metrics": item.get("metrics"),
                    "dimensions": item.get("dimensions"),
                    "dataset": item.get("dataset"),
                    "notes": item.get("notes"),
                }
                for item in context.get("examples", [])
            ],
            "retrieval_trace": context.get("documents", []),
            "generic_query_capabilities": [
                {
                    "dataset": item.get("name"),
                    "dimensions": item.get("dimensions"),
                    "metrics": list((item.get("metrics") or {}).keys()),
                }
                for item in self.catalog.query_capabilities
            ],
        }
        return f"""解析用户的经营分析问题。
用户问题：{question}
可用语义上下文：{json.dumps(compact_context, ensure_ascii=False)}
返回字段：metric（主要指标）、metrics（所有指标列表）、dimensions、time_range、sort、limit、filters、
needs_clarification、clarification_question。
只能使用检索上下文中存在的指标和维度；relationships 用于理解跨表口径，examples 只是标准示例；generic_query_capabilities 是基础聚合可用组合的权威来源；信息不足时 needs_clarification=true。
“最近7天/近一周”是 last_7_days；“最近30天”是 last_30_days；“最近90天”是 last_90_days；“本周”是 current_data_week；“上周”是 previous_complete_week；“本月”是 current_data_month；“上个月”是 previous_complete_month；
注意：“最近30天销售额”指按 stat_dt 查询最近30个自然日，应使用 sales_amount；只有出现“上架30天/新品窗口”时才使用 sku_sales_30d 或 sku_units_30d。
“最近30天销量”使用 units_sold，按 stat_dt 汇总；不要误用 sku_units_30d。
“高价值订单/北极星”使用 high_value_order_cnt；“未完成目标天数”是基于 high_value_order_cnt 与 north_star_achievement_rate 的派生统计，不要创造新的指标名，仍返回这两个指标，并将 stat_dt 作为维度。
涉及 SKU 销售排行时，dimensions 必须同时包含 seller_sku 和 asin；涉及品牌时包含 brand；涉及店铺时包含 shop_code；涉及“每天/按天/趋势”时包含 stat_dt。
最高/最多/排名使用 descending，最低使用 ascending。过滤条件写入 filters：品牌使用 {{"brand":"Cuspin"}}，月份使用 {{"stat_month":"2026-06"}}，销售额超过某金额使用 {{"sales_amount_min":"10000"}}；“整体上升还是下降”使用 {{"analysis":"trend"}}；“未达成目标天数”使用 {{"analysis":"unmet_target"}}。不要返回SQL或Markdown。"""
