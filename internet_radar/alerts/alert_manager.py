from __future__ import annotations

from dataclasses import dataclass

from internet_radar.alerts.alert_templates import alert_title, render_alert_template
from internet_radar.storage.models import SignalRecord, UserProfile


@dataclass(frozen=True)
class AlertMessage:
    signal_id: str
    kind: str
    title: str
    body: str
    channels: list[str]
    score: int


def signals_above_threshold(signals: list[SignalRecord], threshold: int = 80) -> list[SignalRecord]:
    return [signal for signal in signals if signal.score >= threshold]


def build_alerts(signals: list[SignalRecord], profile: UserProfile | None = None) -> list[AlertMessage]:
    profile = profile or UserProfile()
    channels = profile.notification_channels or ["ntfy"]
    alerts: list[AlertMessage] = []

    for signal in signals:
        if _is_blocked(signal, profile):
            continue
        score = _alert_score(signal)
        if score < profile.alert_threshold:
            continue
        alerts.append(format_alert(signal, channels=channels, score=score))

    return sorted(alerts, key=lambda alert: alert.score, reverse=True)


def format_alert(signal: SignalRecord, channels: list[str] | None = None, score: int | None = None) -> AlertMessage:
    kind = _alert_kind(signal)
    resolved_score = score if score is not None else _alert_score(signal)

    return AlertMessage(
        signal_id=str(signal.id),
        kind=kind,
        title=alert_title(kind),
        body=render_alert_template(kind, signal, resolved_score),
        channels=channels or ["ntfy"],
        score=resolved_score,
    )


def _alert_score(signal: SignalRecord) -> int:
    relevance_score = signal.metadata.get("relevance_score", 0)
    if isinstance(relevance_score, (int, float)):
        return int(max(signal.score, relevance_score))
    return signal.score


def _alert_kind(signal: SignalRecord) -> str:
    explicit = str(signal.metadata.get("alert_type", "")).upper()
    if explicit:
        return explicit
    if signal.category == "hackathons":
        return "HACKATHON"
    if signal.category == "research":
        return "RESEARCH_SIGNAL"
    if signal.category == "finance":
        return "FUNDING_ALERT"
    if signal.metadata.get("pain_level") or signal.metadata.get("complaint_count") or signal.category in {"social", "app_stores"}:
        return "STARTUP_GAP"
    return "SKILL_RADAR"


def _is_blocked(signal: SignalRecord, profile: UserProfile) -> bool:
    haystack = f"{signal.topic} {signal.title} {signal.summary} {signal.source}".lower()
    return any(blocked in haystack for blocked in profile.blocked_topics)
