from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import requests

from internet_radar.storage.cache import TTLMemoryCache
from internet_radar.storage.models import SignalRecord
from internet_radar.utils.proxy_rotator import ProxyRotator
from internet_radar.utils.rate_limiter import DEFAULT_RATE_LIMITER, SourceRateLimiter


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
    rate_limiter: SourceRateLimiter | None = field(default_factory=lambda: DEFAULT_RATE_LIMITER)
    proxy_rotator: ProxyRotator | None = None
    http_get: Callable[..., Any] = requests.get
    http_post: Callable[..., Any] = requests.post
    cache_ttl_seconds: int = 300
    cache: TTLMemoryCache[Any] = field(default_factory=TTLMemoryCache)

    def get_json(self, url: str, **params: object) -> object:
        cache_key = self._cache_key("json", url, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        response = self._get(url, **params)
        response.raise_for_status()
        data = response.json()
        self._cache_set(cache_key, data)
        return data

    def get_text(self, url: str, **params: object) -> str:
        cache_key = self._cache_key("text", url, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return str(cached)
        response = self._get(url, **params)
        response.raise_for_status()
        text = str(response.text)
        self._cache_set(cache_key, text)
        return text

    def _get(self, url: str, **params: object) -> Any:
        return self._request(self.http_get, url, params=params or None)

    def _post(self, url: str, **kwargs: object) -> Any:
        return self._request(self.http_post, url, **kwargs)

    def _request(self, request: Callable[..., Any], url: str, **kwargs: object) -> Any:
        if self.rate_limiter:
            self.rate_limiter.wait(self.name)
        request_kwargs = dict(kwargs)
        request_kwargs.setdefault("timeout", self.timeout)
        request_kwargs["headers"] = self._headers(request_kwargs.get("headers"))
        if self.proxy_rotator:
            request_kwargs.update(self.proxy_rotator.requests_kwargs())
        return request(url, **request_kwargs)

    @staticmethod
    def _headers(headers: object) -> dict[str, str]:
        user_agent = os.getenv("INTERNET_RADAR_USER_AGENT", "internet-radar-v2/0.1")
        merged = {"User-Agent": user_agent}
        if isinstance(headers, dict):
            merged.update({str(key): str(value) for key, value in headers.items()})
        return merged

    def _cache_get(self, key: str) -> Any | None:
        if self.cache_ttl_seconds <= 0:
            return None
        return self.cache.get(key)

    def _cache_set(self, key: str, value: Any) -> None:
        if self.cache_ttl_seconds > 0:
            self.cache.set(key, value, self.cache_ttl_seconds)

    @staticmethod
    def _cache_key(kind: str, url: str, params: dict[str, object]) -> str:
        normalized_params = "&".join(f"{key}={value!r}" for key, value in sorted(params.items()))
        return f"{kind}:{url}?{normalized_params}"
