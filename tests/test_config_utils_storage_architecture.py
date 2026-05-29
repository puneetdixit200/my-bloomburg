from __future__ import annotations

import sqlite3
from pathlib import Path


def test_gap_patterns_config_loads_weighted_pain_terms():
    from internet_radar.config.settings import load_gap_patterns

    patterns = load_gap_patterns()

    assert Path("config/gap_patterns.yaml").exists()
    assert "broken" in patterns["pain_terms"]
    assert "why doesn't" in patterns["phrases"]
    assert patterns["weights"]["hate"] >= patterns["weights"]["manual"]
    assert "billing" in patterns["categories"]


def test_text_normalizer_cleans_topics_terms_and_whitespace():
    from internet_radar.utils.text_normalizer import normalize_text, normalize_topic, tokenize_terms

    raw = "  Show HN: Browser\xa0Agents!!! using Local LLMs & MCP servers...  "

    assert normalize_text(raw) == "show hn browser agents using local llms mcp servers"
    assert normalize_topic("AI Resume   Tools!!!") == "ai resume tools"
    assert tokenize_terms(raw)[:4] == ["show", "hn", "browser", "agents"]


def test_sentiment_pipeline_uses_configured_gap_patterns():
    from internet_radar.signals.sentiment_pipeline import analyze_sentiment
    from internet_radar.storage.models import SignalRecord

    signal = SignalRecord(
        id="pain",
        topic="billing",
        title="Why doesn't this app export invoices?",
        source="Hacker News",
        category="social",
        score=70,
        summary="The workflow is brittle and too expensive.",
    )

    result = analyze_sentiment(signal)

    assert result.label == "negative"
    assert {"why doesn't", "brittle", "expensive"}.issubset(set(result.pain_terms))


def test_storage_migrations_record_schema_versions(tmp_path):
    from internet_radar.storage.db import RadarStore

    store = RadarStore(tmp_path / "radar.sqlite")

    assert store.schema_versions() == [
        "001_initial",
        "002_signal_snapshots",
        "003_alert_outbox",
        "004_scheduler_heartbeats",
    ]
    with sqlite3.connect(store.db_path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}

    assert {"signals", "signal_snapshots", "alert_outbox", "scheduler_heartbeats", "schema_migrations"} <= tables
    assert {
        "idx_signals_category",
        "idx_signals_score",
        "idx_signal_snapshots_signal_metric_time",
        "idx_alert_outbox_status_updated",
        "idx_scheduler_heartbeats_recorded_at",
    } <= indexes


def test_supabase_store_upserts_and_lists_via_rest_without_client_dependency():
    from internet_radar.storage.models import SignalRecord
    from internet_radar.storage.supabase_store import SupabaseRadarStore

    calls: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload=None) -> None:
            self.payload = payload if payload is not None else []

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return self.payload

    def fake_post(url, **kwargs):
        calls.append({"method": "post", "url": url, **kwargs})
        return FakeResponse()

    def fake_get(url, **kwargs):
        calls.append({"method": "get", "url": url, **kwargs})
        return FakeResponse(
            [
                SignalRecord(
                    id="sig-1",
                    topic="browser agents",
                    title="Browser agents rise",
                    source="GitHub",
                    category="code",
                    score=88,
                ).as_row()
            ]
        )

    store = SupabaseRadarStore(
        url="https://example.supabase.co",
        api_key="service-key",
        http_post=fake_post,
        http_get=fake_get,
    )

    store.upsert_signals(
        [SignalRecord(id="sig-1", topic="browser agents", title="Browser agents rise", source="GitHub", category="code", score=88)]
    )
    signals = store.list_signals(category="code")

    assert signals[0].id == "sig-1"
    assert calls[0]["url"] == "https://example.supabase.co/rest/v1/signals"
    assert calls[0]["headers"]["Authorization"] == "Bearer service-key"
    assert calls[0]["params"]["on_conflict"] == "id"
    assert calls[1]["params"]["category"] == "eq.code"
