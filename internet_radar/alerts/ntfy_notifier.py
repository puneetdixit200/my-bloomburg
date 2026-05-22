from __future__ import annotations

import requests


def send_ntfy(topic: str, message: str, server: str = "https://ntfy.sh", timeout: float = 5.0) -> bool:
    response = requests.post(f"{server.rstrip('/')}/{topic}", data=message.encode("utf-8"), timeout=timeout)
    return response.ok
