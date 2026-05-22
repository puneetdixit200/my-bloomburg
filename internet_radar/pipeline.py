from __future__ import annotations

import os
from pathlib import Path

from internet_radar.brain.llm_router import LLMRouter
from internet_radar.collectors.live import default_collectors
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
    source_health: dict[str, str] = {}
    signals: list[SignalRecord] = []

    for collector in selected_collectors:
        name = str(getattr(collector, "name", collector.__class__.__name__))
        try:
            collected = collector.collect()  # type: ignore[attr-defined]
            signals.extend(collected)
            source_health[name] = f"ok ({len(collected)})"
        except Exception as exc:
            source_health[name] = f"error: {exc}"

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
