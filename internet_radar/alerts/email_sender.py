from __future__ import annotations

from collections.abc import Callable
from typing import Any

import requests


HttpPost = Callable[..., Any]


def send_mailgun_email(
    domain: str,
    api_key: str,
    sender: str,
    recipient: str,
    subject: str,
    message: str,
    http_post: HttpPost = requests.post,
    timeout: float = 5.0,
) -> bool:
    response = http_post(
        f"https://api.mailgun.net/v3/{domain}/messages",
        auth=("api", api_key),
        data={"from": sender, "to": recipient, "subject": subject, "text": message},
        timeout=timeout,
    )
    return bool(getattr(response, "ok", False))
