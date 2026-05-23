from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests


HttpPost = Callable[..., Any]


def send_ntfy(
    topic: str,
    message: str,
    server: str = "https://ntfy.sh",
    timeout: float = 5.0,
    http_post: HttpPost = requests.post,
) -> bool:
    response = http_post(f"{server.rstrip('/')}/{topic}", data=message.encode("utf-8"), timeout=timeout)
    return response.ok
