"""Evaluate retrieval with Recall@K and mean reciprocal rank."""

from __future__ import annotations

from typing import Any

from app.retrieval.keyword import KeywordRetriever


def evaluate_retrieval(
    retriever: KeywordRetriever, questions: list[dict[str, Any]], k: int = 5
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in questions:
        hits = retriever.retrieve(item["question"], limit=k)
        actual = [hit.document.doc_id for hit in hits]
        relevant = set(item["relevant_documents"])
        matched = [doc_id for doc_id in actual if doc_id in relevant]
        first_rank = next((index + 1 for index, doc_id in enumerate(actual) if doc_id in relevant), None)
        results.append({
            "id": item["id"],
            "question": item["question"],
            "actual_documents": actual,
            "relevant_documents": list(relevant),
            "recall_at_k": len(set(matched)) / len(relevant) if relevant else 1.0,
            "reciprocal_rank": 1 / first_rank if first_rank else 0.0,
        })
    return results


def summarize_retrieval(
    results: list[dict[str, Any]], *, metric_name: str = "recall_at_k"
) -> dict[str, float | int]:
    total = len(results)
    return {
        "total": total,
        metric_name: round(sum(item["recall_at_k"] for item in results) / total, 4) if total else 0.0,
        "mrr": round(sum(item["reciprocal_rank"] for item in results) / total, 4) if total else 0.0,
    }
