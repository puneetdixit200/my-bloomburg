from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
import os
from pathlib import Path

from internet_radar.alerts.alert_manager import AlertMessage
from internet_radar.alerts.dispatcher import alert_readiness, dispatch_alert
from internet_radar.alerts.ntfy_notifier import verify_ntfy_delivery
from internet_radar.alerts.outbox import AlertOutbox
from internet_radar.alerts.telegram_bot import discover_telegram_chats, verify_telegram_credentials
from internet_radar.collectors.live import verify_reddit_oauth
from internet_radar.config.settings import load_local_env, restore_env
from internet_radar.operations.credentials import build_credential_setup_report
from internet_radar.operations.readiness import build_make_real_readiness
from internet_radar.pipeline import run_radar_once
from internet_radar.storage.payload_cache import load_briefing_payload, save_briefing_payload


def main(argv: list[str] | None = None) -> None:
    previous_env = load_local_env()
    try:
        parser = argparse.ArgumentParser(description="Run Internet Radar once.")
        parser.add_argument("--live", action="store_true", help="Use live network collectors instead of bundled sample data.")
        parser.add_argument("--db", default="data/radar.sqlite", help="SQLite database path.")
        parser.add_argument("--readiness", action="store_true", help="Print the make-it-real readiness report and exit.")
        parser.add_argument("--verify-external", action="store_true", help="With --readiness, verify Reddit and Telegram credentials with live API calls.")
        parser.add_argument("--credential-setup", action="store_true", help="Print safe setup guidance for remaining credential-gated integrations and exit.")
        parser.add_argument("--reddit-check", action="store_true", help="Verify Reddit OAuth credentials and exit.")
        parser.add_argument("--ntfy-check", action="store_true", help="Send one ntfy delivery probe without recording an outbox row and exit.")
        parser.add_argument("--telegram-chats", action="store_true", help="Discover Telegram chat IDs from getUpdates and exit.")
        parser.add_argument("--telegram-check", action="store_true", help="Verify Telegram bot token and chat id without sending a message.")
        parser.add_argument("--test-alert", action="store_true", help="Send a test alert to configured ready channels and exit.")
        parser.add_argument("--alert-outbox-compact", action="store_true", help="Compact duplicate pending alert outbox rows and exit.")
        parser.add_argument("--retry-alerts", action="store_true", help="Retry pending alert outbox rows for currently ready channels and exit.")
        parser.add_argument("--digest-alerts", action="store_true", help="Send one summary per ready channel for pending alert backlog rows and mark them digested.")
        parser.add_argument("--alert-retry-limit", type=int, default=25, help="Maximum pending alert rows to consider with --retry-alerts.")
        parser.add_argument("--force-alert-retry", action="store_true", help="With --retry-alerts, ignore outbox retry backoff and attempt ready pending rows immediately.")
        parser.add_argument(
            "--alert-channel",
            action="append",
            choices=["ntfy", "telegram", "discord", "email"],
            default=[],
            help="Restrict --test-alert to a specific channel. Repeat for multiple channels.",
        )
        args = parser.parse_args(argv)

        if args.readiness:
            payload = load_briefing_payload()
            external_checks = None
            if args.verify_external:
                external_checks = {
                    "reddit_oauth": verify_reddit_oauth(),
                    "telegram": verify_telegram_credentials(),
                }
            report = build_make_real_readiness(db_path=args.db, payload=payload, external_checks=external_checks)
            print(
                json.dumps(
                    {
                        "external_verification": args.verify_external,
                        "ready_count": report.ready_count,
                        "blocker_count": report.blocker_count,
                        "blockers": report.blockers,
                        "checks": [asdict(check) for check in report.checks],
                    },
                    indent=2,
                )
            )
            return

        if args.credential_setup:
            print(json.dumps(build_credential_setup_report(), indent=2))
            return

        if args.reddit_check:
            result = verify_reddit_oauth()
            print(
                json.dumps(
                    {
                        "reddit_oauth_check": True,
                        **result,
                    },
                    indent=2,
                )
            )
            return

        if args.ntfy_check:
            result = verify_ntfy_delivery()
            print(
                json.dumps(
                    {
                        "ntfy_check": True,
                        **result,
                    },
                    indent=2,
                )
            )
            return

        if args.telegram_chats:
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
            chats = discover_telegram_chats(bot_token) if bot_token else []
            detail = (
                "set TELEGRAM_CHAT_ID to one of the discovered chat_id values"
                if chats
                else "missing TELEGRAM_BOT_TOKEN or no updates found; message the bot once, then retry"
            )
            print(
                json.dumps(
                    {
                        "telegram_chat_discovery": True,
                        "chats": chats,
                        "detail": detail,
                    },
                    indent=2,
                )
            )
            return

        if args.telegram_check:
            result = verify_telegram_credentials()
            print(
                json.dumps(
                    {
                        "telegram_check": True,
                        **result,
                    },
                    indent=2,
                )
            )
            return

        if args.alert_outbox_compact:
            outbox = AlertOutbox(Path(args.db))
            deleted = outbox.compact_pending()
            print(
                json.dumps(
                    {
                        "alert_outbox_compact": True,
                        "deleted": deleted,
                        "pending_count": outbox.count_pending(),
                    },
                    indent=2,
                )
            )
            return

        if args.retry_alerts:
            outbox = AlertOutbox(Path(args.db))
            results = outbox.retry_pending(limit=args.alert_retry_limit, respect_backoff=not args.force_alert_retry)
            print(
                json.dumps(
                    {
                        "retry_alerts": True,
                        "force": args.force_alert_retry,
                        "attempted_count": len(results),
                        "pending_count": outbox.count_pending(),
                        "results": [asdict(result) for result in results],
                    },
                    indent=2,
                )
            )
            return

        if args.digest_alerts:
            outbox = AlertOutbox(Path(args.db))
            requested_channels = args.alert_channel or [item.channel for item in alert_readiness() if item.ready]
            ready_channels = {item.channel for item in alert_readiness() if item.ready}
            results = [
                outbox.send_pending_digest(channel=channel)
                for channel in requested_channels
                if channel in ready_channels
            ]
            print(
                json.dumps(
                    {
                        "digest_alerts": True,
                        "channels": requested_channels,
                        "pending_count": outbox.count_pending(),
                        "results": [asdict(result) for result in results],
                    },
                    indent=2,
                )
            )
            return

        if args.test_alert:
            channels = args.alert_channel or [item.channel for item in alert_readiness() if item.ready]
            alert = AlertMessage(
                signal_id="internet-radar-test-alert",
                kind="TEST_ALERT",
                title="Internet Radar Test Alert",
                body="Internet Radar test alert. If you received this, alert delivery is configured.",
                channels=channels,
                score=100,
            )
            results = dispatch_alert(alert, outbox_db_path=Path(args.db)) if channels else []
            detail = "no ready channels configured"
            if results and all(result.sent for result in results):
                detail = "sent to configured channels"
            elif results:
                detail = "completed with failures"
            print(
                json.dumps(
                    {
                        "test_alert": True,
                        "channels": channels,
                        "results": [asdict(result) for result in results],
                        "detail": detail,
                    },
                    indent=2,
                )
            )
            return

        briefing = run_radar_once(db_path=args.db, use_live_network=args.live)
        if args.live:
            save_briefing_payload(briefing)
        print(json.dumps(briefing.model_dump(mode="json"), indent=2))
    finally:
        restore_env(previous_env)


if __name__ == "__main__":
    main(sys.argv[1:])
