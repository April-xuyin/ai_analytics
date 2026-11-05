"""Run the local metadata retrieval evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.evaluation.retrieval_eval import evaluate_retrieval, summarize_retrieval
from app.metadata.loader import MetadataCatalog


def main() -> None:
    document = yaml.safe_load((PROJECT_DIR / "evals" / "retrieval_questions.yaml").read_text(encoding="utf-8"))
    retriever = MetadataCatalog(PROJECT_DIR / "metadata").retriever
    results = evaluate_retrieval(retriever, document["questions"], k=5)
    results_at_8 = evaluate_retrieval(retriever, document["questions"], k=8)
    summary = {
        **summarize_retrieval(results, metric_name="recall_at_5"),
        "recall_at_8": summarize_retrieval(
            results_at_8, metric_name="recall_at_8"
        )["recall_at_8"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    failures = [item for item in results_at_8 if item["recall_at_k"] < 1]
    if failures:
        print(json.dumps({"failures": failures}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
