"""Common query-runner contract shared by local and cloud engines."""

from __future__ import annotations

from typing import Protocol


class QueryRunner(Protocol):
    def execute(self, sql: str, max_rows: int = 1000) -> list[dict[str, object]]:
        """Execute one read-only query and return rows as dictionaries."""
