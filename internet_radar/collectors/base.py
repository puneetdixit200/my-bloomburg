from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

import requests

from internet_radar.storage.models import SignalRecord
from internet_radar.utils.proxy_rotator import ProxyRotator
from internet_radar.utils.rate_limiter import SourceRateLimiter


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
    rate_limiter: SourceRateLimiter | None = None
    proxy_rotator: ProxyRotator | None = None
    http_get: Callable[..., Any] = requests.get

    def get_json(self, url: str, **params: object) -> object:
        response = self._get(url, **params)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, **params: object) -> str:
        response = self._get(url, **params)
        response.raise_for_status()
        return response.text

    def _get(self, url: str, **params: object) -> Any:
        if self.rate_limiter:
            self.rate_limiter.wait(self.name)
        kwargs: dict[str, object] = {
            "params": params or None,
            "timeout": self.timeout,
            "headers": {"User-Agent": "internet-radar-v2/0.1"},
        }
        if self.proxy_rotator:
            kwargs.update(self.proxy_rotator.requests_kwargs())
        return self.http_get(url, **kwargs)
