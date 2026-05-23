from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import requests

from internet_radar.storage.models import SignalRecord


HttpRequest = Callable[..., Any]


class SupabaseRadarStore:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        table: str | None = None,
        http_get: HttpRequest = requests.get,
        http_post: HttpRequest = requests.post,
        timeout: float = 20.0,
    ) -> None:
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.api_key = api_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
        self.table = table or os.getenv("SUPABASE_TABLE", "signals")
        self.http_get = http_get
        self.http_post = http_post
        self.timeout = timeout
        if not self.url or not self.api_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY are required")

    def upsert_signals(self, signals: list[SignalRecord]) -> None:
        if not signals:
            return
        payload = [signal.as_row() for signal in signals]
        response = self.http_post(
            f"{self.url}/rest/v1/{self.table}",
            params={"on_conflict": "id"},
            headers={
                **self._headers(),
                "Prefer": "resolution=merge-duplicates,return=minimal",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()

    def list_signals(self, category: str | None = None, limit: int = 100) -> list[SignalRecord]:
        params: dict[str, str | int] = {
            "select": "*",
            "order": "score.desc,observed_at.desc",
            "limit": limit,
        }
        if category:
            params["category"] = f"eq.{category}"
        response = self.http_get(
            f"{self.url}/rest/v1/{self.table}",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        return [SignalRecord(**row) for row in rows if isinstance(row, dict)]

    def schema_versions(self) -> list[str]:
        return ["supabase-rest"]

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
