from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CredentialSetupItem:
    key: str
    status: str
    configured_env: list[str]
    missing_env: list[str]
    setup: str
    verify_command: str
    app_type: str = ""
    redirect_uri: str = ""


def build_credential_setup_report() -> dict[str, object]:
    items = [_reddit_item(), _ntfy_item(), _telegram_item()]
    ready_count = sum(1 for item in items if item.status == "ready")
    return {
        "credential_setup": True,
        "ready_count": ready_count,
        "blocked_count": len(items) - ready_count,
        "items": [asdict(item) for item in items],
    }


def _reddit_item() -> CredentialSetupItem:
    required = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]
    missing = _missing(required)
    return CredentialSetupItem(
        key="reddit_oauth",
        status="ready" if not missing else "blocked",
        configured_env=_configured(required),
        missing_env=missing,
        setup="Create a Reddit developer app of type script, then add the client id and secret to .env.",
        verify_command="uv run internet-radar-run --reddit-check",
        app_type="script",
        redirect_uri="http://localhost:8080",
    )


def _ntfy_item() -> CredentialSetupItem:
    required = ["INTERNET_RADAR_NTFY_TOPIC"]
    missing = _missing(required)
    return CredentialSetupItem(
        key="ntfy",
        status="ready" if not missing else "blocked",
        configured_env=_configured(required),
        missing_env=missing,
        setup="Pick a private ntfy topic name and set INTERNET_RADAR_NTFY_TOPIC in .env.",
        verify_command="uv run internet-radar-run --ntfy-check",
    )


def _telegram_item() -> CredentialSetupItem:
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = _missing(required)
    return CredentialSetupItem(
        key="telegram",
        status="ready" if not missing else "blocked",
        configured_env=_configured(required),
        missing_env=missing,
        setup="Create a bot with @BotFather, message it once, run --telegram-chats, then set TELEGRAM_CHAT_ID.",
        verify_command="uv run internet-radar-run --telegram-check",
    )


def _configured(keys: list[str]) -> list[str]:
    return [key for key in keys if os.getenv(key)]


def _missing(keys: list[str]) -> list[str]:
    return [key for key in keys if not os.getenv(key)]
