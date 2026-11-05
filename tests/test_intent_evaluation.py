from app.evaluation.intent_eval import evaluate_questions, summarize
from app.intent.models import QuestionIntent


class FakeParser:
    def parse(self, question: str) -> QuestionIntent:
        return QuestionIntent(
            metric="sales_amount",
            dimensions=["brand"],
            time_range="last_30_days",
        )


def test_intent_evaluation_summary() -> None:
    questions = [{
        "id": "q1",
        "question": "最近30天各品牌销售额",
        "expected_metrics": ["sales_amount"],
        "expected_dimensions": ["brand"],
        "expected_time_range": "last_30_days",
    }]
    results = evaluate_questions(FakeParser(), questions)
    summary = summarize(results)
    assert summary["total"] == 1
    assert summary["accuracy"] == 1.0

