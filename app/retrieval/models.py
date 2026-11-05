"""Provider-neutral documents and hits for metadata retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeDocument:
    """One independently retrievable unit of warehouse knowledge."""

    doc_id: str
    doc_type: str
    title: str
    content: str
    keywords: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalHit:
    """A document together with its deterministic retrieval score."""

    document: KnowledgeDocument
    score: float
    matched_terms: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        return {
            "id": self.document.doc_id,
            "type": self.document.doc_type,
            "title": self.document.title,
            "content": self.document.content,
            "score": round(self.score, 4),
            "matched_terms": list(self.matched_terms),
        }
