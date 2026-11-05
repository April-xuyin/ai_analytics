from pathlib import Path

import yaml

from app.evaluation.retrieval_eval import evaluate_retrieval, summarize_retrieval
from app.metadata.loader import MetadataCatalog


def test_retrieval_evaluation_has_expected_shape() -> None:
    root = Path(__file__).parents[1]
    questions = yaml.safe_load(
        (root / "evals" / "retrieval_questions.yaml").read_text(encoding="utf-8")
    )["questions"]
    results = evaluate_retrieval(MetadataCatalog(root / "metadata").retriever, questions)
    summary = summarize_retrieval(results)
    assert summary["total"] == 10
    assert 0 <= summary["recall_at_k"] <= 1
