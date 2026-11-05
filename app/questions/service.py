"""Question entry point combining metadata retrieval and query execution."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic
from typing import Any

from app.audit import AuditLogger
from app.auth import AuthorizationError, Principal
from app.intent.models import QuestionIntent
from app.metadata.loader import MetadataCatalog
from app.query.base import QueryRunner
from app.query.local_runner import QueryError
from app.query_planning.planner import QueryClarificationNeeded
from app.questions.fixed_questions import (
    brand_overview_last_30_days,
    brand_refund_rate_last_30_days,
    daily_sales_trend_last_30_days,
    failed_skus_after_30_days,
    north_star_daily_last_30_days,
    top_brands_last_30_days,
)
from app.questions.models import AnalyticsAnswer
from app.sql.generator import SafeSqlGenerator

QuestionHandler = Callable[[QueryRunner], dict[str, Any]]


class QuestionService:
    """Retrieve semantic context and route currently supported questions."""

    def __init__(self, runner: QueryRunner, catalog: MetadataCatalog, audit: AuditLogger | None = None) -> None:
        self.runner = runner
        self.catalog = catalog
        self.sql_generator = SafeSqlGenerator(catalog)
        self.audit = audit
        self.handlers: dict[str, QuestionHandler] = {
            "最近30天销售额最高的5个品牌是什么": top_brands_last_30_days,
            "最近30天各品牌的销售额订单数和销量分别是多少": brand_overview_last_30_days,
            "最近30天销售额按天的趋势是什么": daily_sales_trend_last_30_days,
            "最近30天各品牌的退款率是多少": brand_refund_rate_last_30_days,
            "最近30天每天的高价值订单数和目标达成率是多少": north_star_daily_last_30_days,
            "上架满30天但30天销量没有达到20单的sku有哪些": failed_skus_after_30_days,
        }

    @staticmethod
    def _normalize(question: str) -> str:
        """Normalize harmless wording differences for deterministic routing."""
        return "".join(character.lower() for character in question if character.isalnum())

    def ask(self, question: str) -> AnalyticsAnswer:
        """Retrieve context, execute a supported question, or return unsupported."""
        clean_question = question.strip()
        context = self.catalog.search(clean_question)
        handler = self.handlers.get(self._normalize(clean_question))
        if handler is None:
            return AnalyticsAnswer(
                question=clean_question,
                status="unsupported",
                message="当前固定问数流程尚未支持这个问题；后续将由 Text-to-SQL 处理。",
                retrieved_context=context,
            )

        result = handler(self.runner)
        datasets = result.get("datasets") or [result["dataset"]]
        metrics = result.get("metrics") or [result["metric"]]
        return AnalyticsAnswer(
            question=clean_question,
            status="success",
            message="查询成功",
            datasets=datasets,
            metrics=metrics,
            metric_definition=result.get("metric_definition"),
            data_start_date=result.get("data_start_date"),
            data_end_date=result.get("data_end_date"),
            sql=result.get("sql"),
            rows=result.get("rows", []),
            retrieved_context=context,
        )

    def ask_with_intent(
        self, question: str, intent: QuestionIntent, principal: Principal | None = None
    ) -> AnalyticsAnswer:
        """Route a model-produced intent through deterministic safe handlers."""
        started = monotonic()
        try:
            sql = self.sql_generator.generate(intent)
            if principal and not principal.is_admin and principal.shops:
                sql = self._apply_shop_scope(sql, principal.shops)
            elif principal and not principal.is_admin:
                raise AuthorizationError("当前用户未配置可访问店铺")
        except AuthorizationError:
            self._audit(question, "denied", 0, monotonic() - started, principal)
            raise
        except QueryClarificationNeeded as exc:
            self._audit(question, "clarification_needed", 0, monotonic() - started, principal)
            return AnalyticsAnswer(
                question=question,
                status="clarification_needed",
                message=str(exc),
                retrieved_context=self.catalog.search(question),
            )
        except ValueError as exc:
            self._audit(question, "unsupported", 0, monotonic() - started, principal)
            return AnalyticsAnswer(
                question=question,
                status="unsupported",
                message=f"当前无法安全执行该查询：{exc}",
                retrieved_context=self.catalog.search(question),
            )
        try:
            rows = self.runner.execute(sql, max_rows=int(intent.limit or 1000))
        except QueryError:
            self._audit(question, "query_error", 0, monotonic() - started, principal)
            raise
        self._audit(question, "success", len(rows), monotonic() - started, principal)
        metric_info = self.sql_generator.metrics[intent.metric]
        return AnalyticsAnswer(
            question=question,
            status="success",
            message="查询成功",
            datasets=self.sql_generator.datasets_for(intent),
            metrics=intent.metrics or [intent.metric],
            metric_definition=metric_info.get("definition"),
            sql=sql,
            rows=rows,
            retrieved_context=self.catalog.search(question),
        )

    @staticmethod
    def _apply_shop_scope(sql: str, shops: tuple[str, ...]) -> str:
        """Constrain only templates that expose shop_code; reject unsafe aggregates."""
        shop_aware_sources = (
            "dws_sku_tag_day_us",
            "ads_aws_sku_period_sales",
            "dwi_aws_sku_listing_date",
        )
        if not any(source in sql.lower() for source in shop_aware_sources):
            raise AuthorizationError("当前指标暂不支持按店铺授权查询")
        safe_shops = []
        for shop in shops:
            if "'" in shop or "\n" in shop or "\r" in shop:
                raise AuthorizationError("店铺授权配置不合法")
            safe_shops.append("'" + shop.replace("'", "''") + "'")
        if " where " not in sql.lower():
            raise AuthorizationError("查询模板缺少安全过滤入口")
        return sql.replace("WHERE", "WHERE shop_code IN (" + ", ".join(safe_shops) + ")\n              AND", 1)

    def _audit(
        self,
        question: str,
        status: str,
        row_count: int,
        duration: float,
        principal: Principal | None = None,
    ) -> None:
        if self.audit:
            self.audit.record(
                question=question,
                status=status,
                row_count=row_count,
                duration_ms=round(duration * 1000, 2),
                engine=type(self.runner).__name__,
                principal=principal.name if principal else "anonymous",
                role=principal.role if principal else "unconfigured",
                shop_scope=list(principal.shops) if principal else [],
            )
