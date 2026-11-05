"""Dependency-free, low-cardinality Prometheus metrics for the API process."""

from __future__ import annotations

from collections import Counter
from threading import Lock


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._http_requests: Counter[tuple[str, str, int]] = Counter()
        self._http_duration_sum: Counter[tuple[str, str]] = Counter()
        self._http_duration_count: Counter[tuple[str, str]] = Counter()
        self._question_outcomes: Counter[str] = Counter()

    def record_http(self, method: str, path: str, status: int, duration_seconds: float) -> None:
        labels = (method, self._normalized_path(path))
        with self._lock:
            self._http_requests[(*labels, status)] += 1
            self._http_duration_sum[labels] += duration_seconds
            self._http_duration_count[labels] += 1

    def record_question_outcome(self, outcome: str) -> None:
        allowed = {"success", "clarification_needed", "unsupported", "unauthorized", "denied", "error"}
        safe_outcome = outcome if outcome in allowed else "error"
        with self._lock:
            self._question_outcomes[safe_outcome] += 1

    def render(self) -> str:
        with self._lock:
            lines = [
                "# HELP vg_http_requests_total Total HTTP requests.",
                "# TYPE vg_http_requests_total counter",
            ]
            for (method, path, status), value in sorted(self._http_requests.items()):
                lines.append(
                    f'vg_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {value}'
                )
            lines.extend(
                [
                    "# HELP vg_http_request_duration_seconds HTTP request duration.",
                    "# TYPE vg_http_request_duration_seconds summary",
                ]
            )
            for (method, path), value in sorted(self._http_duration_sum.items()):
                labels = f'method="{method}",path="{path}"'
                lines.append(f"vg_http_request_duration_seconds_sum{{{labels}}} {value:.6f}")
                lines.append(
                    f"vg_http_request_duration_seconds_count{{{labels}}} "
                    f"{self._http_duration_count[(method, path)]}"
                )
            lines.extend(
                [
                    "# HELP vg_question_outcomes_total Total question outcomes.",
                    "# TYPE vg_question_outcomes_total counter",
                ]
            )
            for outcome, value in sorted(self._question_outcomes.items()):
                lines.append(f'vg_question_outcomes_total{{outcome="{outcome}"}} {value}')
            return "\n".join(lines) + "\n"

    @staticmethod
    def _normalized_path(path: str) -> str:
        if path in {"/", "/ask", "/health", "/metrics"}:
            return path
        return "/static"


metrics = MetricsRegistry()
