"""Structured intent produced from a natural-language analytics question."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class QuestionIntent:
    """Provider-independent representation of an analytics question."""

    metric: str | None = None
    metrics: list[str] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    time_range: str | None = None
    sort: str | None = None
    limit: int | None = None
    filters: dict[str, str] = field(default_factory=dict)
    needs_clarification: bool = False
    clarification_question: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
