from __future__ import annotations

import os
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


def verify_ntfy_delivery(
    topic: str | None = None,
    server: str | None = None,
    *,
    http_post: HttpPost = requests.post,
) -> dict[str, object]:
    resolved_topic = (topic if topic is not None else os.getenv("INTERNET_RADAR_NTFY_TOPIC", "")).strip()
    resolved_server = (server if server is not None else os.getenv("INTERNET_RADAR_NTFY_SERVER", "https://ntfy.sh")).strip() or "https://ntfy.sh"
    if not resolved_topic:
        return {
            "configured": False,
            "valid": False,
            "detail": "missing INTERNET_RADAR_NTFY_TOPIC",
            "server": resolved_server,
        }
    try:
        sent = send_ntfy(
            topic=resolved_topic,
            message="Internet Radar ntfy delivery check",
            server=resolved_server,
            http_post=http_post,
        )
    except requests.RequestException as exc:
        return {
            "configured": True,
            "valid": False,
            "detail": f"network error: {exc.__class__.__name__}",
            "server": resolved_server,
        }
    return {
        "configured": True,
        "valid": sent,
        "detail": "sent" if sent else "failed",
        "server": resolved_server,
    }
