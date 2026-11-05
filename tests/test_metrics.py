from app.metrics import MetricsRegistry


def test_metrics_render_prometheus_format_and_normalize_paths() -> None:
    registry = MetricsRegistry()
    registry.record_http("POST", "/ask", 200, 0.25)
    registry.record_http("GET", "/unknown-resource", 404, 0.01)
    registry.record_question_outcome("success")

    rendered = registry.render()

    assert 'vg_http_requests_total{method="POST",path="/ask",status="200"} 1' in rendered
    assert 'vg_http_requests_total{method="GET",path="/static",status="404"} 1' in rendered
    assert 'vg_question_outcomes_total{outcome="success"} 1' in rendered
