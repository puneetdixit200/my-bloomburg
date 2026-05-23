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
    response = http_post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True},
        timeout=timeout,
    )
    return bool(getattr(response, "ok", False))


def build_telegram_alerts(
    signals: list[SignalRecord],
    profile: UserProfile | None = None,
) -> list[AlertMessage]:
    profile = profile or load_user_profile()
    telegram_profile = profile.model_copy(update={"notification_channels": ["telegram"]})
    return build_alerts(signals, profile=telegram_profile)


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
