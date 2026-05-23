from __future__ import annotations

import os
from pathlib import Path

from internet_radar.brain.llm_router import LLMRouter
from internet_radar.collectors.live import default_collectors
from internet_radar.collectors.runner import collect_from_sources
from internet_radar.signals.deduplicator import deduplicate_signals
from internet_radar.storage.db import RadarStore
from internet_radar.storage.models import BriefingPayload, SignalRecord


def run_radar_once(
    collectors: list[object] | None = None,
    db_path: str | Path | None = None,
    use_live_network: bool | None = None,
) -> BriefingPayload:
    if use_live_network is None:
        use_live_network = os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1"

    selected_collectors = collectors or default_collectors(use_live_network=use_live_network)
    collector_results = collect_from_sources(selected_collectors)
    source_health = {result.name: result.status for result in collector_results}
    signals = [signal for result in collector_results for signal in result.signals]

    deduped = deduplicate_signals(signals)
    store = RadarStore(db_path or os.getenv("INTERNET_RADAR_DB", "data/radar.sqlite"))
    store.upsert_signals(deduped)
    top_signals = store.list_signals(limit=100)
    router = LLMRouter()
    llm_choice = router.route("classify", content_length=120)

    return BriefingPayload(
        active_sources=sum(1 for status in source_health.values() if status.startswith("ok")),
        signals_24h=len(top_signals),
        top_signals=top_signals,
        source_health=source_health,
        llm_status=f"{llm_choice.provider}:{llm_choice.model}",
    )
