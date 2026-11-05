"""Deterministic SQL security policy evaluation."""

from __future__ import annotations

from typing import Any

from app.query.sql_security import SqlSecurityError, SqlSecurityValidator


def evaluate_sql_security(
    validator: SqlSecurityValidator, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    results = []
    for item in cases:
        try:
            validator.validate(item["sql"])
            actual = "allowed"
            detail = ""
        except SqlSecurityError as exc:
            actual = "denied"
            detail = str(exc)
        results.append({
            "id": item["id"],
            "expected": item["expected"],
            "actual": actual,
            "passed": actual == item["expected"],
            "detail": detail,
        })
    return results


def summarize_sql_security(results: list[dict[str, Any]]) -> dict[str, float | int]:
    total = len(results)
    passed = sum(bool(item["passed"]) for item in results)
    return {"total": total, "passed": passed, "accuracy": passed / total if total else 0.0}
