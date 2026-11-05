"""Metadata loading and lightweight keyword retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.retrieval.keyword import KeywordRetriever
from app.retrieval.models import KnowledgeDocument


class MetadataError(ValueError):
    """Raised when metadata files are missing or malformed."""


class MetadataCatalog:
    """Load the semantic layer and retrieve relevant metrics, datasets, and terms."""

    def __init__(self, metadata_dir: str | Path = "metadata") -> None:
        self.metadata_dir = Path(metadata_dir)
        self.datasets = self._load_list("datasets.yaml", "datasets")
        self.metrics = self._load_list("metrics.yaml", "metrics")
        self.terms = self._load_list("glossary.yaml", "terms")
        self.query_capabilities = self._load_list("query_capabilities.yaml", "datasets")
        self.relationships = self._load_list(
            "relationships.yaml", "relationships", required=False
        )
        self.examples = self._load_list("examples.yaml", "examples", required=False)
        self.documents = self._build_documents()
        self.retriever = KeywordRetriever(self.documents)

    def _load_list(
        self, filename: str, key: str, *, required: bool = True
    ) -> list[dict[str, Any]]:
        path = self.metadata_dir / filename
        if not path.is_file():
            if required:
                raise MetadataError(f"找不到元数据文件: {path}")
            return []
        with path.open(encoding="utf-8") as file:
            document = yaml.safe_load(file) or {}
        values = document.get(key, [])
        if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
            raise MetadataError(f"元数据格式错误: {path}")
        return values

    @staticmethod
    def _text(*values: object) -> str:
        parts: list[str] = []
        for value in values:
            if isinstance(value, list):
                parts.extend(str(item) for item in value)
            elif value is not None:
                parts.append(str(value))
        return "；".join(parts)

    def _build_documents(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []
        for item in self.metrics:
            documents.append(KnowledgeDocument(
                doc_id=f"metric:{item['name']}",
                doc_type="metric",
                title=str(item["name"]),
                content=self._text(
                    item.get("definition"), item.get("aggregation"), item.get("dimensions")
                ),
                keywords=tuple(str(value) for value in item.get("aliases", [])),
                metadata={"dataset": item.get("dataset")},
                payload=item,
            ))
        for item in self.datasets:
            documents.append(KnowledgeDocument(
                doc_id=f"dataset:{item['name']}",
                doc_type="dataset",
                title=str(item["name"]),
                content=self._text(
                    item.get("grain"), item.get("notes"), item.get("dimensions"),
                    item.get("metrics"),
                ),
                keywords=tuple(
                    str(value)
                    for value in [*item.get("dimensions", []), *item.get("metrics", [])]
                ),
                payload=item,
            ))
        for item in self.terms:
            documents.append(KnowledgeDocument(
                doc_id=f"term:{item['term']}",
                doc_type="term",
                title=str(item["term"]),
                content=self._text(item.get("meaning")),
                keywords=tuple(str(value) for value in item.get("aliases", [])),
                payload=item,
            ))
        for item in self.relationships:
            documents.append(KnowledgeDocument(
                doc_id=f"relationship:{item['name']}",
                doc_type="relationship",
                title=str(item["name"]),
                content=self._text(
                    item.get("description"), item.get("join"), item.get("from_dataset"),
                    item.get("to_dataset"),
                ),
                keywords=tuple(str(value) for value in item.get("keywords", [])),
                payload=item,
            ))
        for item in self.examples:
            documents.append(KnowledgeDocument(
                doc_id=f"example:{item['id']}",
                doc_type="example",
                title=str(item["question"]),
                content=self._text(
                    item.get("notes"), item.get("metrics"), item.get("dimensions"),
                    item.get("dataset"),
                ),
                keywords=tuple(str(value) for value in item.get("aliases", [])),
                payload=item,
            ))
        return documents

    @staticmethod
    def _terms(item: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("name", "term", "definition", "meaning", "description", "notes"):
            value = item.get(key)
            if isinstance(value, str):
                values.append(value.lower())
        aliases = item.get("aliases", [])
        if isinstance(aliases, list):
            values.extend(str(alias).lower() for alias in aliases)
        return values

    def search(self, question: str, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
        """Return typed metadata plus traceable RAG documents for one question."""
        # Eight documents reached full recall on the labelled baseline while
        # keeping the prompt far smaller than the complete metadata corpus.
        hits = self.retriever.retrieve(question, limit=max(limit, 8))

        def payloads(doc_type: str) -> list[dict[str, Any]]:
            return [
                hit.document.payload
                for hit in hits
                if hit.document.doc_type == doc_type
            ][:limit]

        return {
            "metrics": payloads("metric"),
            "datasets": payloads("dataset"),
            "terms": payloads("term"),
            "relationships": payloads("relationship"),
            "examples": payloads("example"),
            "documents": [hit.to_context() for hit in hits[:limit]],
        }

    def supports_query(self, metrics: list[str], dimensions: list[str]) -> bool:
        """Return whether one generic dataset supports the whole requested combination."""
        requested_metrics = set(metrics)
        requested_dimensions = set(dimensions)
        return any(
            requested_metrics <= set((dataset.get("metrics") or {}).keys())
            and requested_dimensions <= set(dataset.get("dimensions") or [])
            for dataset in self.query_capabilities
        )
