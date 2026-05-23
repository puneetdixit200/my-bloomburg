from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests


HttpPost = Callable[..., Any]


def send_telegram(
    message: str,
    bot_token: str,
    chat_id: str,
    http_post: HttpPost = requests.post,
    timeout: float = 5.0,
) -> bool:
    response = http_post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=timeout,
    )
    return bool(getattr(response, "ok", False))
