from __future__ import annotations

from datetime import datetime
from typing import Any

from internet_radar.storage.models import ValidationResult


class CrossSourceValidator:
    SOURCE_WEIGHTS = {
        "github_star_spike": 0.25,
        "reddit_discussion": 0.15,
        "hn_front_page": 0.20,
        "arxiv_paper_velocity": 0.20,
        "funding_announced": 0.30,
        "producthunt_launch": 0.10,
        "bluesky_trending": 0.10,
        "google_trends_rising": 0.15,
        "npm_pypi_downloads": 0.20,
        "job_postings_rising": 0.25,
        "youtube_uploads": 0.10,
        "wiki_pageviews_spike": 0.05,
    }

    def validate(self, topic: str, signals: dict[str, dict[str, Any]]) -> ValidationResult:
        total_weight = 0.0
        active_sources: list[str] = []
        first_seen: dict[str, str] = {}

        for source, weight in self.SOURCE_WEIGHTS.items():
            signal = signals.get(source, {})
            if signal.get("detected"):
                total_weight += weight
                active_sources.append(source)
                first_seen[source] = str(signal.get("first_seen") or "")

        confidence = int(round(min(total_weight / 1.2 * 100, 100)))

        if len(active_sources) >= 5:
            phase = "CONFIRMED EMERGING TREND"
        elif len(active_sources) >= 3:
            phase = "LIKELY EMERGING"
        elif len(active_sources) >= 2:
            phase = "WEAK SIGNAL"
        else:
            phase = "SINGLE SOURCE - WATCH"

        earliest_signal = min(active_sources, key=lambda source: self._sort_date(first_seen.get(source, ""))) if active_sources else "none"
        return ValidationResult(
            topic=topic,
            confidence=confidence,
            phase=phase,
            sources_confirming=active_sources,
            earliest_signal=earliest_signal,
        )

    @staticmethod
    def _sort_date(value: str) -> datetime:
        if not value:
            return datetime.max
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.max
