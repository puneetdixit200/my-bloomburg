from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CrowdPrediction:
    title: str
    projected_participants: int
    crowd_ratio: float
    recommendation: str
    alert: str


def predict_crowd(hackathon: dict[str, Any]) -> CrowdPrediction:
    title = str(hackathon.get("title") or hackathon.get("name") or "hackathon")
    current = _as_int(hackathon.get("current_participants", hackathon.get("participants", 0)))
    daily_growth = _as_int(hackathon.get("daily_growth", hackathon.get("participant_growth_per_day", 0)))
    days_left = _as_int(hackathon.get("days_left", 0))
    capacity = max(_as_int(hackathon.get("capacity", hackathon.get("max_participants", 150))), 1)
    projected = max(current, current + max(daily_growth, 0) * max(days_left, 0))
    crowd_ratio = round(projected / capacity, 2)
    recommendation = _recommendation(days_left, crowd_ratio)
    return CrowdPrediction(
        title=title,
        projected_participants=projected,
        crowd_ratio=crowd_ratio,
        recommendation=recommendation,
        alert=_alert(recommendation, daily_growth, crowd_ratio),
    )


def _recommendation(days_left: int, crowd_ratio: float) -> str:
    if days_left <= 0:
        return "EXPIRED"
    if days_left <= 14 and crowd_ratio <= 0.65:
        return "APPLY NOW"
    if crowd_ratio <= 0.85:
        return "WATCH"
    return "WAIT"


def _alert(recommendation: str, daily_growth: int, crowd_ratio: float) -> str:
    if recommendation == "EXPIRED":
        return "deadline passed"
    if recommendation == "APPLY NOW" and daily_growth > 0:
        return "crowd building but still favorable"
    if crowd_ratio > 0.85:
        return "competition is getting crowded"
    return "monitor for participant jumps"


def _as_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0
