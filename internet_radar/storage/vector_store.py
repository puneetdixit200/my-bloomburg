from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from internet_radar.brain.embed_engine import DeterministicEmbedder, cosine_similarity
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
    def __init__(self, embedder: DeterministicEmbedder | None = None) -> None:
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
