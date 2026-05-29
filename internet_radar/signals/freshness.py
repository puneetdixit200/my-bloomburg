from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from internet_radar.storage.models import SignalRecord


DEFAULT_MAX_SIGNAL_AGE_DAYS = 14

CONTENT_DATE_KEYS = (
    "published_at",
    "published",
    "published_date",
    "publication_date",
    "date",
    "created",
    "created_at",
    "updated_at",
    "last_updated",
    "seen_date",
    "seendate",
    "filing_date",
    "open_date",
    "openDate",
    "timestamp",
)
EXPIRY_DATE_KEYS = (
    "deadline",
    "deadline_at",
    "expires_at",
    "expiration_date",
    "close_date",
    "closeDate",
    "end_date",
    "end_time",
    "until",
    "apply_by",
)


def max_signal_age_days() -> int:
    try:
        return max(1, int(os.getenv("INTERNET_RADAR_SIGNAL_MAX_AGE_DAYS", str(DEFAULT_MAX_SIGNAL_AGE_DAYS))))
    except ValueError:
        return DEFAULT_MAX_SIGNAL_AGE_DAYS


def freshness_cutoff(now: datetime | None = None, max_age_days: int | None = None) -> datetime:
    current = _aware(now or datetime.now(UTC))
    return current - timedelta(days=max_age_days or max_signal_age_days())


def filter_fresh_signals(
    signals: list[SignalRecord],
    *,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> list[SignalRecord]:
    current = _aware(now or datetime.now(UTC))
    return [signal for signal in signals if is_signal_fresh(signal, now=current, max_age_days=max_age_days)]


def is_signal_fresh(
    signal: SignalRecord,
    *,
    now: datetime | None = None,
    max_age_days: int | None = None,
) -> bool:
    current = _aware(now or datetime.now(UTC))
    cutoff = freshness_cutoff(current, max_age_days=max_age_days)
    observed = _aware(signal.observed_at)
    if observed < cutoff:
        return False

    content_date = signal_content_datetime(signal.metadata)
    if content_date and content_date < cutoff:
        return False

    expiry_date = signal_expiry_datetime(signal.metadata)
    if expiry_date and expiry_date < current:
        return False

    return True


def signal_content_datetime(metadata: dict[str, Any]) -> datetime | None:
    return _first_datetime(metadata, CONTENT_DATE_KEYS)


def signal_expiry_datetime(metadata: dict[str, Any]) -> datetime | None:
    return _first_datetime(metadata, EXPIRY_DATE_KEYS, end_of_day=True)


def parse_datetime_value(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _aware(value)
    if isinstance(value, date):
        selected_time = time.max if end_of_day else time.min
        return datetime.combine(value, selected_time, tzinfo=UTC)
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        if numeric > 10_000_000_000:
            numeric = numeric / 1000
        try:
            return datetime.fromtimestamp(numeric, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "unknown"}:
        return None
    text = text.strip('"').strip("'")
    compact = re.sub(r"[^0-9]", "", text)
    if len(compact) == 14:
        try:
            return datetime.strptime(compact, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        except ValueError:
            pass
    if len(compact) == 8 and compact.startswith(("19", "20")):
        try:
            parsed = datetime.strptime(compact, "%Y%m%d").replace(tzinfo=UTC)
            return parsed.replace(hour=23, minute=59, second=59, microsecond=999999) if end_of_day else parsed
        except ValueError:
            pass

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    parsed = _aware(parsed)
    if end_of_day and parsed.time() == time.min:
        return parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _first_datetime(metadata: dict[str, Any], keys: tuple[str, ...], *, end_of_day: bool = False) -> datetime | None:
    for key in keys:
        parsed = parse_datetime_value(metadata.get(key), end_of_day=end_of_day)
        if parsed is not None:
            return parsed
    return None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
