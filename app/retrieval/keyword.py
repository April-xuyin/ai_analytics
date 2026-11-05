"""Explainable keyword and structured-link retrieval baseline."""

from __future__ import annotations

import re
from collections import defaultdict

from app.retrieval.models import KnowledgeDocument, RetrievalHit


def _normalize(value: str) -> str:
    return re.sub(r"[\s，。！？、：；,.!?:;()（）\-]+", "", value).lower()


class KeywordRetriever:
    """Rank metadata without external embeddings or a vector database."""

    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        self.documents = documents

    def retrieve(self, question: str, limit: int = 8) -> list[RetrievalHit]:
        normalized_question = _normalize(question)
        latin_tokens = {
            token.lower()
            for token in re.findall(r"[A-Za-z0-9_]+", question)
            if len(token) >= 3 and not token.isdigit()
        }
        scores: dict[str, float] = defaultdict(float)
        matches: dict[str, set[str]] = defaultdict(set)
        by_id = {document.doc_id: document for document in self.documents}

        for document in self.documents:
            if document.doc_type == "term" and document.title in {"SKU", "ASIN"}:
                # Generic entity words are useful context but should not crowd
                # out the metric and dataset that answer the question.
                generic_term_cap = 2.0
            else:
                generic_term_cap = 100.0
            weighted_terms = [(document.title, 5.0)]
            weighted_terms.extend(
                (keyword, 0.5 if str(keyword).upper() in {"SKU", "ASIN"} else 4.0)
                for keyword in document.keywords
            )
            weighted_terms.append((document.content, 0.5))
            for raw_term, weight in weighted_terms:
                term = _normalize(str(raw_term))
                if len(term) >= 2 and term in normalized_question:
                    scores[document.doc_id] += weight
                    matches[document.doc_id].add(str(raw_term))
                if re.fullmatch(r"[A-Za-z0-9_]+", str(raw_term).strip()):
                    raw_token = str(raw_term).strip().lower()
                    if raw_token in latin_tokens:
                        scores[document.doc_id] += weight * 0.5
                        matches[document.doc_id].add(raw_token)
            scores[document.doc_id] = min(scores[document.doc_id], generic_term_cap)

        # A matched metric deterministically brings its authoritative dataset
        # into the candidate set. This is structured retrieval, not model guesswork.
        for document in self.documents:
            if document.doc_type != "metric" or scores[document.doc_id] <= 0:
                continue
            dataset = document.metadata.get("dataset")
            dataset_id = f"dataset:{dataset}"
            if dataset_id in by_id:
                scores[dataset_id] += scores[document.doc_id] * 0.4
                matches[dataset_id].add(document.doc_id)

        # Standard examples and relationship documents declare authoritative
        # datasets. Retrieving one expands those explicit links at a lower score.
        for document in self.documents:
            if scores[document.doc_id] <= 0:
                continue
            linked_datasets: list[str] = []
            if document.doc_type == "example" and document.payload.get("dataset"):
                linked_datasets.append(str(document.payload["dataset"]))
                for metric in document.payload.get("metrics", []):
                    metric_id = f"metric:{metric}"
                    if metric_id in by_id:
                        scores[metric_id] += scores[document.doc_id] * 0.4
                        matches[metric_id].add(document.doc_id)
            if document.doc_type == "relationship":
                linked_datasets.extend(
                    str(document.payload[key])
                    for key in ("from_dataset", "to_dataset")
                    if document.payload.get(key)
                )
            for dataset in linked_datasets:
                dataset_id = f"dataset:{dataset}"
                if dataset_id in by_id:
                    scores[dataset_id] += scores[document.doc_id] * 0.3
                    matches[dataset_id].add(document.doc_id)

        ranked = sorted(
            (
                RetrievalHit(by_id[doc_id], score, tuple(sorted(matches[doc_id])))
                for doc_id, score in scores.items()
                if score > 0
            ),
            key=lambda hit: (
                -hit.score,
                {"metric": 0, "dataset": 1, "example": 2, "relationship": 3, "term": 4}.get(
                    hit.document.doc_type, 5
                ),
                hit.document.doc_id,
            ),
        )
        return ranked[: max(1, limit)]
