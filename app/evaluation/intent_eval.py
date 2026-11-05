"""Evaluate an intent parser against the standard question set."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.intent.parser import IntentParser


@dataclass
class IntentEvalResult:
    question_id: str
    question: str
    expected_metrics: list[str]
    actual_metric: str | None
    actual_metrics: list[str]
    expected_dimensions: list[str]
    actual_dimensions: list[str]
    metric_correct: bool
    dimensions_correct: bool
    time_range_correct: bool
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_questions(
    parser: IntentParser,
    questions: list[dict[str, Any]],
) -> list[IntentEvalResult]:
    """Evaluate canonical supported questions without executing generated SQL."""
    results: list[IntentEvalResult] = []
    for item in questions:
        expected_metrics = item.get("expected_metrics", [])
        expected_dimensions = item.get("expected_dimensions", [])
        intent = parser.parse(item["question"])
        actual_metrics = intent.metrics or ([intent.metric] if intent.metric else [])
        metric_correct = not expected_metrics or bool(set(expected_metrics).intersection(actual_metrics))
        dimensions_correct = set(expected_dimensions).issubset(set(intent.dimensions))
        expected_time_range = item.get("expected_time_range")
        time_range_correct = expected_time_range is None or intent.time_range == expected_time_range
        results.append(
            IntentEvalResult(
                question_id=item["id"],
                question=item["question"],
                expected_metrics=expected_metrics,
                actual_metric=intent.metric,
                actual_metrics=actual_metrics,
                expected_dimensions=expected_dimensions,
                actual_dimensions=intent.dimensions,
                metric_correct=metric_correct,
                dimensions_correct=dimensions_correct,
                time_range_correct=time_range_correct,
                passed=metric_correct and dimensions_correct and time_range_correct,
            )
        )
    return results


def summarize(results: list[IntentEvalResult]) -> dict[str, float | int]:
    total = len(results)
    if total == 0:
        return {"total": 0, "passed": 0, "accuracy": 0.0}
    passed = sum(result.passed for result in results)
    return {
        "total": total,
        "passed": passed,
        "accuracy": round(passed / total, 4),
        "metric_accuracy": round(sum(result.metric_correct for result in results) / total, 4),
        "dimension_accuracy": round(sum(result.dimensions_correct for result in results) / total, 4),
        "time_range_accuracy": round(sum(result.time_range_correct for result in results) / total, 4),
    }
