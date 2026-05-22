from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests

from internet_radar.storage.models import SignalRecord


class Collector(Protocol):
    name: str
    category: str

    def collect(self) -> list[SignalRecord]:
        ...


@dataclass
class HTTPCollector:
    name: str
    category: str
    timeout: float = 10.0

    def get_json(self, url: str, **params: object) -> object:
        response = requests.get(url, params=params or None, timeout=self.timeout, headers={"User-Agent": "internet-radar-v2/0.1"})
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, **params: object) -> str:
        response = requests.get(url, params=params or None, timeout=self.timeout, headers={"User-Agent": "internet-radar-v2/0.1"})
        response.raise_for_status()
        return response.text
