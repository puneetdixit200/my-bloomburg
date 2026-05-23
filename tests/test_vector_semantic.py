from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_deterministic_embedder_is_stable_and_normalized():
    from internet_radar.brain.embed_engine import DeterministicEmbedder

    embedder = DeterministicEmbedder(dimensions=16)
    first = embedder.embed("browser agents automate websites")
    second = embedder.embed("browser agents automate websites")

    assert first == second
    assert len(first) == 16
    assert round(sum(value * value for value in first), 6) == 1.0


def test_embed_router_prefers_ollama_nomic_when_available():
    from internet_radar.brain.embed_engine import EmbeddingRouter

    router = EmbeddingRouter(available_models=["qwen2.5:0.5b", "nomic-embed-text"])

    choice = router.route()

    assert choice.provider == "ollama"
    assert choice.model == "nomic-embed-text"


def test_embed_router_uses_cohere_key_as_online_fallback():
    from internet_radar.brain.embed_engine import CohereEmbedder, EmbeddingRouter

    router = EmbeddingRouter(available_models=[], cohere_api_key="cohere-key")

    choice = router.route()

    assert choice.provider == "cohere"
    assert choice.model == "embed-english-light-v3.0"
    assert isinstance(router.embedder(), CohereEmbedder)


def test_cohere_embedder_normalizes_response_without_real_network():
    from internet_radar.brain.embed_engine import CohereEmbedder

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"embeddings": [[3, 4]]}

    calls: list[dict[str, object]] = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    embedder = CohereEmbedder(api_key="cohere-key", http_post=fake_post)

    assert embedder.embed("browser agents") == [0.6, 0.8]
    assert calls[0]["url"] == "https://api.cohere.com/v1/embed"
    assert calls[0]["headers"]["Authorization"] == "Bearer cohere-key"


def test_vector_store_search_ranks_semantic_matches():
    from internet_radar.storage.vector_store import SemanticVectorStore

    store = SemanticVectorStore()
    browser = SignalRecord(id="browser", topic="browser agents", title="Browser agents automate websites", source="GitHub", category="code", score=88)
    css = SignalRecord(id="css", topic="css", title="CSS grid layout tricks", source="Dev.to", category="news", score=60)

    store.add_signals([css, browser])
    results = store.search("agent browser automation", limit=2)

    assert [result.signal.id for result in results] == ["browser", "css"]
    assert results[0].similarity > results[1].similarity


def test_chroma_vector_store_uses_collection_upsert_and_query():
    from internet_radar.brain.embed_engine import DeterministicEmbedder
    from internet_radar.storage.vector_store import ChromaSemanticVectorStore

    class FakeCollection:
        def __init__(self) -> None:
            self.documents: list[str] = []
            self.embeddings: list[list[float]] = []

        def upsert(self, ids, documents, embeddings, metadatas):
            self.documents = documents
            self.embeddings = embeddings

        def query(self, query_embeddings, n_results, include):
            return {"documents": [self.documents[:n_results]], "distances": [[0.2 for _ in self.documents[:n_results]]]}

    class FakeClient:
        def __init__(self) -> None:
            self.collection = FakeCollection()

        def get_or_create_collection(self, name):
            self.name = name
            return self.collection

    client = FakeClient()
    store = ChromaSemanticVectorStore(client=client, embedder=DeterministicEmbedder(dimensions=8))
    store.add_signals(
        [SignalRecord(id="browser", topic="browser agents", title="Browser agents automate websites", source="GitHub", category="code", score=88)]
    )

    results = store.search("browser automation", limit=1)

    assert client.name == "internet_radar_signals"
    assert results[0].signal.id == "browser"
    assert results[0].similarity > 0


def test_semantic_clusters_group_related_pain_signals():
    from internet_radar.storage.vector_store import build_semantic_clusters

    signals = [
        SignalRecord(id="a", topic="ai resume tools", title="Resume app has broken export", source="Reddit", category="social", score=80),
        SignalRecord(id="b", topic="resume builder", title="AI resume builder export is painful", source="iTunes", category="app_stores", score=74),
        SignalRecord(id="c", topic="browser agents", title="Browser automation is growing", source="GitHub", category="code", score=88),
    ]

    clusters = build_semantic_clusters(signals, min_cluster_size=2)

    assert len(clusters) == 1
    assert clusters[0].label == "resume"
    assert clusters[0].signal_ids == ["a", "b"]
    assert clusters[0].sources == ["Reddit", "iTunes"]


def test_dashboard_payload_exposes_semantic_clusters():
    from internet_radar.dashboard_data import build_dashboard_payload

    signals = [
        SignalRecord(id="a", topic="ai resume tools", title="Resume app has broken export", source="Reddit", category="social", score=80),
        SignalRecord(id="b", topic="resume builder", title="AI resume builder export is painful", source="iTunes", category="app_stores", score=74),
    ]

    payload = build_dashboard_payload(signals)

    assert payload["startup_gaps"]["semantic_clusters"][0].label == "resume"
