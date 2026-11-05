from app.evaluation.security_eval import evaluate_sql_security, summarize_sql_security
from app.query.sql_security import SqlSecurityValidator


def test_security_evaluation_summary() -> None:
    results = evaluate_sql_security(
        SqlSecurityValidator({"safe_table"}, {"safe_column"}),
        [
            {"id": "safe", "expected": "allowed", "sql": "SELECT safe_column FROM safe_table"},
            {"id": "unsafe", "expected": "denied", "sql": "DROP TABLE safe_table"},
        ],
    )
    assert summarize_sql_security(results) == {"total": 2, "passed": 2, "accuracy": 1.0}
