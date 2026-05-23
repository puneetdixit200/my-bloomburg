from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from internet_radar.brain.embed_engine import DeterministicEmbedder, EmbeddingRouter, cosine_similarity
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class VectorSearchResult:
    signal: SignalRecord
    similarity: float


@dataclass(frozen=True)
class SemanticCluster:
    label: str
    signal_ids: list[str]
    sources: list[str]
    size: int
    keywords: list[str]


class SemanticVectorStore:
    def __init__(self, embedder: Any | None = None) -> None:
        self.embedder = embedder or DeterministicEmbedder()
        self._items: list[tuple[SignalRecord, list[float]]] = []

    def add_signals(self, signals: list[SignalRecord]) -> None:
        for signal in signals:
            self._items.append((signal, self.embedder.embed(_signal_text(signal))))

    def search(self, query: str, limit: int = 10) -> list[VectorSearchResult]:
        query_vector = self.embedder.embed(query)
        results = [
            VectorSearchResult(signal=signal, similarity=cosine_similarity(query_vector, vector))
            for signal, vector in self._items
        ]
        return sorted(results, key=lambda item: (item.similarity, item.signal.score), reverse=True)[:limit]


class ChromaSemanticVectorStore:
    def __init__(
        self,
        collection_name: str = "internet_radar_signals",
        persist_path: str | Path | None = None,
        embedder: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.embedder = embedder or EmbeddingRouter().embedder()
        if client is None:
            try:
                import chromadb
            except ImportError as exc:
                raise RuntimeError("Install chromadb or use INTERNET_RADAR_VECTOR_BACKEND=deterministic") from exc
            path = str(persist_path or os.getenv("INTERNET_RADAR_CHROMA_PATH", "data/chroma"))
            Path(path).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=path)
        self.client = client
        self.collection = client.get_or_create_collection(collection_name)

    def add_signals(self, signals: list[SignalRecord]) -> None:
        if not signals:
            return
        ids = [str(signal.id) for signal in signals]
        documents = [signal.model_dump_json() for signal in signals]
        embeddings = [self.embedder.embed(_signal_text(signal)) for signal in signals]
        metadatas = [
            {
                "topic": signal.topic,
                "source": signal.source,
                "category": signal.category,
                "score": int(signal.score),
            }
            for signal in signals
        ]
        self.collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

    def search(self, query: str, limit: int = 10) -> list[VectorSearchResult]:
        response = self.collection.query(
            query_embeddings=[self.embedder.embed(query)],
            n_results=limit,
            include=["documents", "distances"],
        )
        documents = (response.get("documents") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]
        results: list[VectorSearchResult] = []
        for index, document in enumerate(documents):
            try:
                signal = SignalRecord.model_validate_json(document)
            except ValueError:
                continue
            distance = float(distances[index]) if index < len(distances) else 1.0
            results.append(VectorSearchResult(signal=signal, similarity=1.0 / (1.0 + max(distance, 0.0))))
        return results


def create_vector_store(backend: str | None = None, **kwargs: Any) -> SemanticVectorStore | ChromaSemanticVectorStore:
    selected = (backend or os.getenv("INTERNET_RADAR_VECTOR_BACKEND", "auto")).strip().lower()
    if selected == "deterministic":
        return SemanticVectorStore(**kwargs)
    if selected in {"chroma", "chromadb"}:
        return ChromaSemanticVectorStore(**kwargs)
    try:
        return ChromaSemanticVectorStore(**kwargs)
    except RuntimeError:
        return SemanticVectorStore(**kwargs)


def build_semantic_clusters(signals: list[SignalRecord], min_cluster_size: int = 2) -> list[SemanticCluster]:
    grouped: dict[str, list[SignalRecord]] = {}
    for signal in signals:
        label = _cluster_label(signal)
        if label:
            grouped.setdefault(label, []).append(signal)

    clusters: list[SemanticCluster] = []
    for label, records in grouped.items():
        if len(records) < min_cluster_size:
            continue
        sources: list[str] = []
        for signal in records:
            if signal.source not in sources:
                sources.append(signal.source)
        clusters.append(
            SemanticCluster(
                label=label,
                signal_ids=[str(signal.id) for signal in records],
                sources=sources,
                size=len(records),
                keywords=_keywords(records),
            )
        )
    return sorted(clusters, key=lambda cluster: (cluster.size, len(cluster.sources)), reverse=True)


def _signal_text(signal: SignalRecord) -> str:
    return f"{signal.topic} {signal.title} {signal.summary} {signal.source} {signal.category}"


def _cluster_label(signal: SignalRecord) -> str:
    text = _signal_text(signal).lower()
    if "resume" in text or "cv" in text:
        return "resume"
    if "browser" in text or "automation" in text:
        return "browser agents"
    if "mcp" in text or "model context" in text:
        return "mcp"
    if "local llm" in text or "ollama" in text:
        return "local llm"
    return signal.topic.strip().lower().split()[0] if signal.topic.strip() else ""


def _keywords(signals: list[SignalRecord]) -> list[str]:
    stop = {"the", "and", "for", "with", "has", "are", "app", "tools", "signal"}
    words: list[str] = []
    for signal in signals:
        words.extend(word for word in _signal_text(signal).lower().replace("-", " ").split() if len(word) > 2 and word not in stop)
    return [word for word, _ in Counter(words).most_common(5)]
