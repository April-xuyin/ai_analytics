import json

from app.audit import AuditLogger


def test_audit_logger_writes_jsonl(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    AuditLogger(path).record(question="测试", status="success", row_count=1)
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["question"] == "测试"
    assert record["status"] == "success"
    assert "timestamp" in record
