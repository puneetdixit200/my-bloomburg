from __future__ import annotations

from internet_radar.pipeline import run_radar_once


def collect_high_frequency() -> int:
    briefing = run_radar_once(use_live_network=False)
    return briefing.signals_24h
