"""Build validated query plans from provider-neutral question intents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.intent.models import QuestionIntent


class QueryPlanningError(ValueError):
    """Raised when no safe dataset supports the requested combination."""


class QueryClarificationNeeded(ValueError):
    """Raised when a safe plan requires information missing from the question."""


@dataclass(frozen=True)
class QueryPlan:
    dataset: str
    time_field: str
    metrics: tuple[str, ...]
    dimensions: tuple[str, ...]
    time_range: str | None
    filters: dict[str, str]
    sort: str | None
    limit: int | None
    metric_expressions: dict[str, str]


class QueryPlanner:
    """Select a dataset using one explicit metric/dimension capability matrix."""

    def __init__(self, capability_file: str | Path) -> None:
        document = yaml.safe_load(Path(capability_file).read_text(encoding="utf-8")) or {}
        datasets = document.get("datasets")
        if not isinstance(datasets, list) or not datasets:
            raise QueryPlanningError("通用查询能力矩阵为空")
        self.datasets: list[dict[str, Any]] = sorted(
            datasets, key=lambda item: int(item.get("priority", 100))
        )
        self.supported_metrics = {
            metric
            for dataset in self.datasets
            for metric in (dataset.get("metrics") or {})
        }

    def plan(self, intent: QuestionIntent) -> QueryPlan:
        metrics = tuple(intent.metrics or ([intent.metric] if intent.metric else []))
        dimensions = tuple(dict.fromkeys(intent.dimensions))
        if not metrics:
            raise QueryPlanningError("查询缺少指标")
        if not set(metrics) <= self.supported_metrics:
            raise QueryPlanningError("该指标不属于通用聚合能力")
        if intent.time_range is None and "stat_month" not in (intent.filters or {}):
            raise QueryClarificationNeeded(
                "请明确要查询的时间范围，例如最近7天、最近30天、上周或指定月份。"
            )
        if intent.time_range is not None and not isinstance(intent.time_range, str):
            raise QueryPlanningError("时间范围格式不合法")
        if (
            intent.time_range not in {
                "last_7_days",
                "last_30_days",
                "last_90_days",
                "current_data_week",
                "previous_complete_week",
                "current_data_month",
                "previous_complete_month",
                None,
            }
            and "stat_month" not in (intent.filters or {})
        ):
            raise QueryPlanningError(f"暂不支持时间范围: {intent.time_range}")

        requested_metrics = set(metrics)
        requested_dimensions = set(dimensions)
        filter_dimensions = set(intent.filters or {}) & {"brand", "shop_code", "seller_sku", "asin"}
        required_dimensions = requested_dimensions | filter_dimensions
        if "order_count" in requested_metrics and required_dimensions & {
            "shop_code", "seller_sku", "asin"
        }:
            raise QueryPlanningError(
                "当前订单数不能按店铺或SKU通用汇总：SKU日表可能重复计算包含多个SKU的订单，"
                "需要接入按店铺和订单号去重的汇总表。"
            )
        for dataset in self.datasets:
            available_metrics = set((dataset.get("metrics") or {}).keys())
            available_dimensions = set(dataset.get("dimensions") or [])
            if requested_metrics <= available_metrics and required_dimensions <= available_dimensions:
                expressions = {
                    metric: dataset["metrics"][metric]
                    for metric in metrics
                }
                return QueryPlan(
                    dataset=str(dataset["name"]),
                    time_field=str(dataset["time_field"]),
                    metrics=metrics,
                    dimensions=dimensions,
                    time_range=intent.time_range,
                    filters=dict(intent.filters or {}),
                    sort=intent.sort,
                    limit=intent.limit,
                    metric_expressions=expressions,
                )
        raise QueryPlanningError(
            "没有数据集同时支持指标 "
            f"{', '.join(metrics)} 和维度 {', '.join(dimensions) or '整体'}"
        )
