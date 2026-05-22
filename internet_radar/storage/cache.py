from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Generic, TypeVar


T = TypeVar("T")


class TTLMemoryCache(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, tuple[datetime, T]] = {}

    def get(self, key: str) -> T | None:
        item = self._items.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < datetime.now(UTC):
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T, ttl_seconds: int) -> None:
        self._items[key] = (datetime.now(UTC) + timedelta(seconds=ttl_seconds), value)
