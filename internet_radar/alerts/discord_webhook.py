from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests


HttpPost = Callable[..., Any]


def send_discord_webhook(
    webhook_url: str,
    title: str,
    message: str,
    http_post: HttpPost = requests.post,
    timeout: float = 5.0,
) -> bool:
    response = http_post(webhook_url, json={"content": f"**{title}**\n{message}"}, timeout=timeout)
    return bool(getattr(response, "ok", False))
