from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

import requests

from internet_radar.alerts.alert_manager import AlertMessage, build_alerts
from internet_radar.config.settings import load_user_profile
from internet_radar.storage.db import RadarStore
from internet_radar.storage.models import SignalRecord, UserProfile


HttpPost = Callable[..., Any]
HttpGet = Callable[..., Any]
DEFAULT_DB_PATH = "data/radar.sqlite"

if TYPE_CHECKING:
    from internet_radar.alerts.dispatcher import AlertDispatchResult


def send_telegram(
    message: str,
    bot_token: str,
    chat_id: str,
    http_post: HttpPost = requests.post,
    timeout: float = 5.0,
) -> bool:
    sent, _detail = send_telegram_with_detail(
        message,
        bot_token=bot_token,
        chat_id=chat_id,
        http_post=http_post,
        timeout=timeout,
    )
    return sent


def send_telegram_with_detail(
    message: str,
    bot_token: str,
    chat_id: str,
    http_post: HttpPost = requests.post,
    timeout: float = 5.0,
) -> tuple[bool, str]:
    response = http_post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=timeout,
    )
    if bool(getattr(response, "ok", False)):
        return True, "sent"
    return False, _telegram_error_detail(response)


def _telegram_error_detail(response: Any) -> str:
    status_code = getattr(response, "status_code", None)
    description = ""
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        description = str(payload.get("description") or "").strip()
    if not description:
        description = str(getattr(response, "text", "") or "").strip()
    if description and status_code:
        return f"HTTP {status_code}: {description}"
    if description:
        return description
    if status_code:
        return f"HTTP {status_code}"
    return "failed"


def discover_telegram_chats(
    bot_token: str,
    http_get: HttpGet = requests.get,
    timeout: float = 5.0,
) -> list[dict[str, str]]:
    response = http_get(f"https://api.telegram.org/bot{bot_token}/getUpdates", timeout=timeout)
    data = response.json()
    chats: list[dict[str, str]] = []
    seen: set[str] = set()
    for update in data.get("result", []):
        if not isinstance(update, dict):
            continue
        chat = _chat_from_update(update)
        if not chat:
            continue
        chat_id = str(chat.get("id", "")).strip()
        if not chat_id or chat_id in seen:
            continue
        seen.add(chat_id)
        chats.append(
            {
                "chat_id": chat_id,
                "type": str(chat.get("type", "")),
                "name": _chat_name(chat),
            }
        )
    return chats


def verify_telegram_credentials(
    bot_token: str | None = None,
    chat_id: str | None = None,
    http_get: HttpGet = requests.get,
    timeout: float = 5.0,
) -> dict[str, object]:
    resolved_token = bot_token if bot_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
    resolved_chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
    if not resolved_token or not resolved_chat_id:
        return {
            "configured": False,
            "valid": False,
            "detail": "missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
            "chat": {},
        }
    try:
        response = http_get(
            f"https://api.telegram.org/bot{resolved_token}/getChat",
            params={"chat_id": resolved_chat_id},
            timeout=timeout,
        )
        payload = response.json()
        if payload.get("ok") and isinstance(payload.get("result"), dict):
            chat = payload["result"]
            return {
                "configured": True,
                "valid": True,
                "detail": "chat resolved",
                "chat": {
                    "chat_id": str(chat.get("id", resolved_chat_id)),
                    "type": str(chat.get("type", "")),
                    "name": _chat_name(chat),
                },
            }
        return {
            "configured": True,
            "valid": False,
            "detail": str(payload.get("description") or "getChat did not resolve chat"),
            "chat": {},
        }
    except Exception as exc:
        return {
            "configured": True,
            "valid": False,
            "detail": f"getChat failed: {exc.__class__.__name__}",
            "chat": {},
        }


def build_telegram_alerts(
    signals: list[SignalRecord],
    profile: UserProfile | None = None,
) -> list[AlertMessage]:
    profile = profile or load_user_profile()
    telegram_profile = profile.model_copy(update={"notification_channels": ["telegram"]})
    return build_alerts(signals, profile=telegram_profile)


def _chat_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    for key in ["message", "edited_message", "channel_post", "edited_channel_post", "my_chat_member"]:
        value = update.get(key)
        if isinstance(value, dict) and isinstance(value.get("chat"), dict):
            return value["chat"]
    return None


def _chat_name(chat: dict[str, Any]) -> str:
    for key in ["username", "title", "first_name"]:
        value = str(chat.get(key, "")).strip()
        if value:
            return value
    return str(chat.get("id", ""))


def dispatch_telegram_alerts(
    db_path: str | Path = DEFAULT_DB_PATH,
    profile: UserProfile | None = None,
    limit: int = 50,
    http_post: HttpPost = requests.post,
    sent_signal_ids: set[str] | None = None,
) -> list["AlertDispatchResult"]:
    from internet_radar.alerts.dispatcher import dispatch_alert

    store = RadarStore(db_path)
    alerts = build_telegram_alerts(store.list_signals(limit=limit), profile=profile)
    results: list[AlertDispatchResult] = []

    for alert in alerts[:limit]:
        if sent_signal_ids is not None and alert.signal_id in sent_signal_ids:
            continue
        alert_results = dispatch_alert(alert, http_post=http_post)
        results.extend(alert_results)
        if sent_signal_ids is not None and any(getattr(result, "sent", False) for result in alert_results):
            sent_signal_ids.add(alert.signal_id)

    return results


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Dispatch Internet Radar alerts to Telegram.")
    parser.add_argument("--db", default=os.getenv("INTERNET_RADAR_DB", DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of stored signals to inspect.")
    parser.add_argument("--watch", action="store_true", help="Keep polling instead of running once.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=int(os.getenv("INTERNET_RADAR_TELEGRAM_INTERVAL_SECONDS", "900")),
        help="Polling interval when --watch is set.",
    )
    args = parser.parse_args(argv)

    sent_signal_ids: set[str] = set()
    while True:
        results = dispatch_telegram_alerts(
            db_path=args.db,
            limit=args.limit,
            sent_signal_ids=sent_signal_ids if args.watch else None,
        )
        sent = sum(1 for result in results if getattr(result, "sent", False))
        skipped = len(results) - sent
        print(f"telegram alerts: sent={sent} skipped={skipped}")
        if not args.watch:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
