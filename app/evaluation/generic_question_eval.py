"""Evaluate natural-language parsing through deterministic query planning."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.intent.parser import IntentParser
from app.query_planning.planner import QueryClarificationNeeded
from app.sql.generator import SafeSqlGenerator, SqlGenerationError


@dataclass
class GenericQuestionEvalResult:
    question_id: str
    question: str
    expected_statuses: list[str]
    actual_status: str
    metric_correct: bool
    dimensions_correct: bool
    time_correct: bool
    filters_correct: bool
    dataset_correct: bool
    sql_correct: bool
    passed: bool
    actual_intent: dict[str, object]
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_generic_questions(
    parser: IntentParser,
    generator: SafeSqlGenerator,
    questions: list[dict[str, Any]],
) -> list[GenericQuestionEvalResult]:
    results: list[GenericQuestionEvalResult] = []
    for item in questions:
        intent = parser.parse(item["question"])
        expected_statuses = item["expected_statuses"]
        actual_status = "success"
        detail = ""
        sql = ""
        datasets: list[str] = []
        if intent.needs_clarification:
            actual_status = "clarification_needed"
            detail = intent.clarification_question or ""
        else:
            try:
                sql = generator.generate(intent)
                datasets = generator.datasets_for(intent)
            except QueryClarificationNeeded as exc:
                actual_status = "clarification_needed"
                detail = str(exc)
            except SqlGenerationError as exc:
                actual_status = "unsupported"
                detail = str(exc)

        expected_metrics = item.get("expected_metrics", [])
        actual_metrics = intent.metrics or ([intent.metric] if intent.metric else [])
        metric_correct = not expected_metrics or set(actual_metrics) == set(expected_metrics)
        expected_dimensions = item.get("expected_dimensions")
        dimensions_correct = (
            expected_dimensions is None
            or set(intent.dimensions) == set(expected_dimensions)
        )
        expected_time = item.get("expected_time_range")
        time_correct = expected_time is None or intent.time_range == expected_time
        expected_filters = item.get("expected_filters", {})
        filters_correct = all(
            str(intent.filters.get(key)) == str(value)
            for key, value in expected_filters.items()
        )
        expected_dataset = item.get("expected_dataset")
        dataset_correct = expected_dataset is None or expected_dataset in datasets
        sql_correct = all(fragment in sql for fragment in item.get("sql_contains", []))
        passed = (
            actual_status in expected_statuses
            and metric_correct
            and dimensions_correct
            and time_correct
            and filters_correct
            and dataset_correct
            and sql_correct
        )
        results.append(GenericQuestionEvalResult(
            question_id=item["id"],
            question=item["question"],
            expected_statuses=expected_statuses,
            actual_status=actual_status,
            metric_correct=metric_correct,
            dimensions_correct=dimensions_correct,
            time_correct=time_correct,
            filters_correct=filters_correct,
            dataset_correct=dataset_correct,
            sql_correct=sql_correct,
            passed=passed,
            actual_intent=intent.to_dict(),
            detail=detail,
        ))
    return results


def expand_generic_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand canonical questions and paraphrases with identical expectations."""
    expanded: list[dict[str, Any]] = []
    for item in questions:
        canonical = {key: value for key, value in item.items() if key != "paraphrases"}
        expanded.append(canonical)
        for index, paraphrase in enumerate(item.get("paraphrases", []), start=1):
            variant = dict(canonical)
            variant["id"] = f"{item['id']}_p{index}"
            variant["question"] = paraphrase
            expanded.append(variant)
    return expanded


def summarize_generic_questions(
    results: list[GenericQuestionEvalResult],
) -> dict[str, float | int]:
    total = len(results)
    passed = sum(result.passed for result in results)
    return {
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4) if total else 0.0,
        "metric_accuracy": _rate(results, "metric_correct"),
        "dimension_accuracy": _rate(results, "dimensions_correct"),
        "time_accuracy": _rate(results, "time_correct"),
        "filter_accuracy": _rate(results, "filters_correct"),
        "dataset_accuracy": _rate(results, "dataset_correct"),
        "sql_accuracy": _rate(results, "sql_correct"),
    }


def _rate(results: list[GenericQuestionEvalResult], field: str) -> float:
    if not results:
        return 0.0
    return round(sum(bool(getattr(result, field)) for result in results) / len(results), 4)
