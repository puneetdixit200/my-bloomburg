from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from internet_radar.alerts.alert_manager import AlertMessage
from internet_radar.alerts.discord_webhook import send_discord_webhook
from internet_radar.alerts.email_sender import send_mailgun_email
from internet_radar.alerts.ntfy_notifier import send_ntfy
from internet_radar.alerts.telegram_bot import send_telegram_with_detail


HttpPost = Callable[..., Any]


@dataclass(frozen=True)
class AlertDispatchResult:
    channel: str
    sent: bool
    detail: str


@dataclass(frozen=True)
class AlertChannelReadiness:
    channel: str
    ready: bool
    detail: str


def alert_readiness(config: dict[str, str] | None = None) -> list[AlertChannelReadiness]:
    resolved = _config(config or {})
    free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
    return [
        AlertChannelReadiness(
            channel="ntfy",
            ready=bool(resolved.get("ntfy_topic")),
            detail="ready" if resolved.get("ntfy_topic") else "missing INTERNET_RADAR_NTFY_TOPIC",
        ),
        AlertChannelReadiness(
            channel="telegram",
            ready=bool(resolved.get("telegram_bot_token") and resolved.get("telegram_chat_id")),
            detail="ready"
            if resolved.get("telegram_bot_token") and resolved.get("telegram_chat_id")
            else "missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
        ),
        AlertChannelReadiness(
            channel="discord",
            ready=bool(resolved.get("discord_webhook_url")),
            detail="ready" if resolved.get("discord_webhook_url") else "missing DISCORD_WEBHOOK_URL",
        ),
        AlertChannelReadiness(
            channel="email",
            ready=not free_only
            and all(resolved.get(key) for key in ["mailgun_domain", "mailgun_api_key", "email_to", "email_from"]),
            detail=_email_readiness_detail(resolved, free_only),
        ),
    ]


def dispatch_alert(
    alert: AlertMessage,
    config: dict[str, str] | None = None,
    http_post: HttpPost = requests.post,
    outbox_db_path: str | Path | None = None,
) -> list[AlertDispatchResult]:
    resolved_config = _config(config or {})
    results: list[AlertDispatchResult] = []
    for channel in alert.channels:
        normalized = channel.lower().strip()
        try:
            if normalized == "ntfy":
                results.append(_send_ntfy(alert, resolved_config, http_post))
            elif normalized == "telegram":
                results.append(_send_telegram(alert, resolved_config, http_post))
            elif normalized == "discord":
                results.append(_send_discord(alert, resolved_config, http_post))
            elif normalized == "email":
                results.append(_send_email(alert, resolved_config, http_post))
            else:
                results.append(AlertDispatchResult(channel=channel, sent=False, detail="unsupported channel"))
        except requests.RequestException as exc:
            results.append(AlertDispatchResult(channel=normalized or channel, sent=False, detail=f"network error: {exc.__class__.__name__}"))
    if outbox_db_path is not None:
        from internet_radar.alerts.outbox import AlertOutbox

        AlertOutbox(outbox_db_path).record_results(alert, results)
    return results


def _send_ntfy(alert: AlertMessage, config: dict[str, str], http_post: HttpPost) -> AlertDispatchResult:
    topic = config.get("ntfy_topic")
    if not topic:
        return AlertDispatchResult(channel="ntfy", sent=False, detail="missing ntfy_topic")
    sent = send_ntfy(topic=topic, message=alert.body, server=config.get("ntfy_server", "https://ntfy.sh"), http_post=http_post)
    return AlertDispatchResult(channel="ntfy", sent=sent, detail="sent" if sent else "failed")


def _send_telegram(alert: AlertMessage, config: dict[str, str], http_post: HttpPost) -> AlertDispatchResult:
    token = config.get("telegram_bot_token")
    chat_id = config.get("telegram_chat_id")
    if not token or not chat_id:
        return AlertDispatchResult(channel="telegram", sent=False, detail="missing telegram credentials")
    sent, detail = send_telegram_with_detail(alert.body, bot_token=token, chat_id=chat_id, http_post=http_post)
    return AlertDispatchResult(channel="telegram", sent=sent, detail=detail)


def _send_discord(alert: AlertMessage, config: dict[str, str], http_post: HttpPost) -> AlertDispatchResult:
    webhook_url = config.get("discord_webhook_url")
    if not webhook_url:
        return AlertDispatchResult(channel="discord", sent=False, detail="missing discord_webhook_url")
    sent = send_discord_webhook(webhook_url, title=alert.title, message=alert.body, http_post=http_post)
    return AlertDispatchResult(channel="discord", sent=sent, detail="sent" if sent else "failed")


def _send_email(alert: AlertMessage, config: dict[str, str], http_post: HttpPost) -> AlertDispatchResult:
    required = ["mailgun_domain", "mailgun_api_key", "email_to", "email_from"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        return AlertDispatchResult(channel="email", sent=False, detail=f"missing {', '.join(missing)}")
    sent = send_mailgun_email(
        domain=config["mailgun_domain"],
        api_key=config["mailgun_api_key"],
        sender=config["email_from"],
        recipient=config["email_to"],
        subject=alert.title,
        message=alert.body,
        http_post=http_post,
    )
    return AlertDispatchResult(channel="email", sent=sent, detail="sent" if sent else "failed")


def _config(overrides: dict[str, str]) -> dict[str, str]:
    free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
    env = {
        "ntfy_topic": os.getenv("INTERNET_RADAR_NTFY_TOPIC", ""),
        "ntfy_server": os.getenv("INTERNET_RADAR_NTFY_SERVER", "https://ntfy.sh"),
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "mailgun_domain": "" if free_only else os.getenv("MAILGUN_DOMAIN", ""),
        "mailgun_api_key": "" if free_only else os.getenv("MAILGUN_API_KEY", ""),
        "email_to": os.getenv("INTERNET_RADAR_EMAIL_TO", ""),
        "email_from": os.getenv("INTERNET_RADAR_EMAIL_FROM", ""),
    }
    return {**env, **overrides}


def _email_readiness_detail(config: dict[str, str], free_only: bool) -> str:
    if free_only:
        return "disabled by free-only mode"
    missing = [
        key
        for key in ["mailgun_domain", "mailgun_api_key", "email_to", "email_from"]
        if not config.get(key)
    ]
    return "ready" if not missing else f"missing {', '.join(missing)}"
