from __future__ import annotations

from collections.abc import Iterable
from collections import defaultdict
from dataclasses import dataclass

from internet_radar.scoring.funding_scorer import FundingScorer
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class FundingSignal:
    topic: str
    score: int
    amount: float
    investors: list[str]
    related_jobs: int
    market_validation: str
    sources: list[str]
    signal_ids: list[str]


def build_funding_signals(records: list[SignalRecord]) -> list[FundingSignal]:
    grouped: dict[str, list[SignalRecord]] = defaultdict(list)
    for record in records:
        if record.category in {"finance", "jobs", "hackathons"}:
            grouped[_topic_key(record.topic)].append(record)

    funding_signals: list[FundingSignal] = []
    scorer = FundingScorer()
    for topic, topic_records in grouped.items():
        finance_records = [record for record in topic_records if record.category == "finance"]
        if not finance_records:
            continue
        amount = max(_as_float(record.metadata.get("amount", record.metadata.get("funding_amount", 0))) for record in finance_records)
        investors = _unique(
            investor
            for record in finance_records
            for investor in _investor_values(record.metadata.get("investors", []))
        )
        related_jobs = sum(_as_int(record.metadata.get("related_jobs")) for record in topic_records)
        related_jobs += sum(1 for record in topic_records if record.category == "jobs" and not record.metadata.get("related_jobs"))
        days_ago = min((_as_int(record.metadata.get("days_ago", 30)) for record in finance_records), default=30)
        scored = scorer.score(
            {
                "sector": topic,
                "amount": amount,
                "investors": investors,
                "days_ago": days_ago,
                "related_jobs": related_jobs,
            }
        )
        funding_signals.append(
            FundingSignal(
                topic=topic,
                score=scored.score,
                amount=amount,
                investors=investors,
                related_jobs=related_jobs,
                market_validation=scored.market_validation,
                sources=_unique(record.source for record in topic_records),
                signal_ids=[str(record.id) for record in topic_records],
            )
        )

    return sorted(funding_signals, key=lambda signal: (signal.score, signal.amount, signal.related_jobs), reverse=True)


def _topic_key(topic: str) -> str:
    return " ".join(topic.strip().lower().split())


def _investor_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _unique(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            unique_values.append(text)
            seen.add(text)
    return unique_values


def _as_float(value: object) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: object) -> int:
    return int(_as_float(value))
