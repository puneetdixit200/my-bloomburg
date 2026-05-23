from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from internet_radar.storage.models import BriefingPayload


def default_payload_cache_path() -> Path:
    return Path(os.getenv("INTERNET_RADAR_PAYLOAD_CACHE", "data/latest_payload.json"))


def save_briefing_payload(payload: BriefingPayload, path: str | Path | None = None) -> Path:
    cache_path = Path(path) if path else default_payload_cache_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")
    return cache_path


def load_briefing_payload(path: str | Path | None = None) -> BriefingPayload | None:
    cache_path = Path(path) if path else default_payload_cache_path()
    if not cache_path.exists():
        return None
    payload = BriefingPayload.model_validate_json(cache_path.read_text(encoding="utf-8"))
    payload.loaded_from_cache = True
    return payload


def payload_cache_age_seconds(path: str | Path | None = None, now: datetime | None = None) -> float | None:
    payload = load_briefing_payload(path)
    if payload is None:
        return None
    current = now or datetime.now(UTC)
    generated_at = payload.generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return max(0.0, (current - generated_at).total_seconds())
