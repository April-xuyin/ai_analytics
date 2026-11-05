"""Deterministic evaluation for the metadata-driven query planner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.intent.models import QuestionIntent
from app.query.base import QueryRunner
from app.query.local_runner import QueryError
from app.query_planning.planner import QueryClarificationNeeded
from app.sql.generator import SafeSqlGenerator, SqlGenerationError


@dataclass
class QueryPlanEvalResult:
    case_id: str
    expected_status: str
    actual_status: str
    dataset_correct: bool
    sql_correct: bool
    error_correct: bool
    execution_correct: bool
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_query_plans(
    generator: SafeSqlGenerator,
    cases: list[dict[str, Any]],
    runner: QueryRunner | None = None,
) -> list[QueryPlanEvalResult]:
    results: list[QueryPlanEvalResult] = []
    for case in cases:
        expected_status = case["expected_status"]
        actual_status = "success"
        dataset_correct = expected_status != "success"
        sql_correct = expected_status != "success"
        error_correct = expected_status == "success"
        execution_correct = not case.get("execute_local", False)
        detail = ""
        try:
            intent = QuestionIntent(**case["intent"])
            sql = generator.generate(intent)
            datasets = generator.datasets_for(intent)
            dataset_correct = case.get("expected_dataset") in datasets
            sql_correct = all(fragment in sql for fragment in case.get("sql_contains", []))
            if case.get("execute_local"):
                if runner is None:
                    execution_correct = False
                    detail = "缺少本地查询执行器"
                else:
                    runner.execute(sql)
                    execution_correct = True
        except QueryClarificationNeeded as exc:
            actual_status = "clarification_needed"
            detail = str(exc)
            error_correct = case.get("expected_error_contains", "") in detail
        except SqlGenerationError as exc:
            actual_status = "unsupported"
            detail = str(exc)
            error_correct = case.get("expected_error_contains", "") in detail
        except QueryError as exc:
            actual_status = "error"
            detail = str(exc)
        passed = (
            actual_status == expected_status
            and dataset_correct
            and sql_correct
            and error_correct
            and execution_correct
        )
        results.append(QueryPlanEvalResult(
            case_id=case["id"],
            expected_status=expected_status,
            actual_status=actual_status,
            dataset_correct=dataset_correct,
            sql_correct=sql_correct,
            error_correct=error_correct,
            execution_correct=execution_correct,
            passed=passed,
            detail=detail,
        ))
    return results


def summarize_query_plans(results: list[QueryPlanEvalResult]) -> dict[str, float | int]:
    total = len(results)
    passed = sum(result.passed for result in results)
    return {
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else 0.0,
    }
