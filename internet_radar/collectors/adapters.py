from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from internet_radar.storage.models import SignalRecord


LiveFactory = Callable[[], object]


def architecture_collector(
    *,
    name: str,
    category: str,
    live_factory: LiveFactory | None = None,
    topic: str = "",
    score: int = 60,
) -> type:
    class ArchitectureCollector:
        def __init__(self, use_live_network: bool = True) -> None:
            self.name = name
            self.category = category
            self.use_live_network = use_live_network
            self._live = live_factory() if use_live_network and live_factory else None

        def collect(self) -> list[SignalRecord]:
            if self._live is not None:
                try:
                    return self._live.collect()  # type: ignore[attr-defined]
                except Exception:
                    pass
            return [sample_record(name=name, category=category, topic=topic or name, score=score)]

    ArchitectureCollector.__name__ = f"{_class_name(name)}Collector"
    return ArchitectureCollector


def sample_record(name: str, category: str, topic: str, score: int = 60) -> SignalRecord:
    normalized_topic = " ".join(str(topic).lower().split()) or "technology signal"
    return SignalRecord(
        id=f"architecture:{_slug(name)}",
        topic=normalized_topic,
        title=f"{name} architecture collector signal",
        source=name,
        category=category,  # type: ignore[arg-type]
        url="",
        score=max(0, min(score, 100)),
        velocity=max(score - 50, 1),
        summary=f"Deterministic fallback for the {name} collector.",
        metadata={"collector_module": _slug(name)},
    )


def _class_name(value: str) -> str:
    return "".join(part.capitalize() for part in re.findall(r"[A-Za-z0-9]+", value)) or "Architecture"


def _slug(value: str) -> str:
    return "-".join(part.lower() for part in re.findall(r"[A-Za-z0-9]+", value)) or "collector"
