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


def test_vector_store_search_ranks_semantic_matches():
    from internet_radar.storage.vector_store import SemanticVectorStore

    store = SemanticVectorStore()
    browser = SignalRecord(id="browser", topic="browser agents", title="Browser agents automate websites", source="GitHub", category="code", score=88)
    css = SignalRecord(id="css", topic="css", title="CSS grid layout tricks", source="Dev.to", category="news", score=60)

    store.add_signals([css, browser])
    results = store.search("agent browser automation", limit=2)

    assert [result.signal.id for result in results] == ["browser", "css"]
    assert results[0].similarity > results[1].similarity


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
