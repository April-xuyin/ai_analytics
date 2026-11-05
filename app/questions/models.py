"""Shared response models for analytics questions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AnalyticsAnswer:
    """A stable response shape shared by fixed questions and future LLM flows."""

    question: str
    status: str
    message: str
    datasets: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    metric_definition: str | None = None
    data_start_date: object | None = None
    data_end_date: object | None = None
    sql: str | None = None
    rows: list[dict[str, Any]] = field(default_factory=list)
    retrieved_context: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the response to a dictionary for APIs and tests."""
        return asdict(self)

