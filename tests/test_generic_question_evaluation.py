from app.evaluation.generic_question_eval import (
    evaluate_generic_questions,
    expand_generic_questions,
    summarize_generic_questions,
)
from app.intent.models import QuestionIntent


class FakeParser:
    def parse(self, question: str) -> QuestionIntent:
        return QuestionIntent(
            metric="sales_amount",
            metrics=["sales_amount"],
            dimensions=["shop_code"],
            time_range="last_30_days",
            sort="descending",
            limit=3,
        )


class FakeGenerator:
    def generate(self, intent: QuestionIntent) -> str:
        return "SELECT shop_code, SUM(x) AS sales_amount GROUP BY shop_code LIMIT 3"

    def datasets_for(self, intent: QuestionIntent) -> list[str]:
        return ["dws_sku_tag_day_us"]


def test_generic_question_evaluation_summary() -> None:
    questions = [{
        "id": "q1",
        "question": "最近30天销售额排名前3的店铺",
        "expected_statuses": ["success"],
        "expected_metrics": ["sales_amount"],
        "expected_dimensions": ["shop_code"],
        "expected_time_range": "last_30_days",
        "expected_dataset": "dws_sku_tag_day_us",
        "sql_contains": ["GROUP BY shop_code", "LIMIT 3"],
    }]
    results = evaluate_generic_questions(FakeParser(), FakeGenerator(), questions)
    assert summarize_generic_questions(results)["accuracy"] == 1.0


def test_generic_question_paraphrases_expand_with_same_expectations() -> None:
    questions = [{
        "id": "q1",
        "question": "标准问法",
        "paraphrases": ["改写一", "改写二"],
        "expected_statuses": ["success"],
    }]
    expanded = expand_generic_questions(questions)
    assert [item["id"] for item in expanded] == ["q1", "q1_p1", "q1_p2"]
    assert all("paraphrases" not in item for item in expanded)
