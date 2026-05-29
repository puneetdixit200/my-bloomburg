from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from internet_radar.storage.models import UserProfile


DEFAULT_PROFILE_PATH = Path("config/interests.yaml")
DEFAULT_GAP_PATTERNS_PATH = Path("config/gap_patterns.yaml")


def load_local_env(path: str | Path = ".env", *, override: bool = False) -> dict[str, str | None]:
    config_path = Path(path)
    if os.getenv("INTERNET_RADAR_DISABLE_DOTENV", "0") == "1" or not config_path.exists():
        return {}

    previous_values: dict[str, str | None] = {}
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = _env_value(value)
        if override or key not in os.environ:
            if key not in previous_values:
                previous_values[key] = os.environ.get(key)
            os.environ[key] = value
    return previous_values


def restore_env(previous_values: dict[str, str | None]) -> None:
    for key, value in previous_values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def load_user_profile(path: str | Path = DEFAULT_PROFILE_PATH) -> UserProfile:
    config_path = Path(path)
    if not config_path.exists():
        return UserProfile()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_data = data.get("profile", data)
    if not isinstance(profile_data, dict):
        return UserProfile()
    return UserProfile(**profile_data)


def load_source_settings(path: str | Path = "config/sources.yaml") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_gap_patterns(path: str | Path = DEFAULT_GAP_PATTERNS_PATH) -> dict[str, Any]:
    fallback = {
        "pain_terms": ["broken", "expensive", "hate", "manual", "slow"],
        "phrases": ["why doesn't", "too expensive", "hard to debug"],
        "weights": {"hate": 5, "broken": 4, "expensive": 3, "manual": 2},
        "categories": {},
    }
    config_path = Path(path)
    if not config_path.exists():
        return fallback
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return fallback
    return {
        "pain_terms": _string_list(data.get("pain_terms", fallback["pain_terms"])),
        "phrases": _string_list(data.get("phrases", fallback["phrases"])),
        "weights": {
            str(term): int(weight)
            for term, weight in dict(data.get("weights", fallback["weights"])).items()
        },
        "categories": data.get("categories", fallback["categories"]) if isinstance(data.get("categories", {}), dict) else {},
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip().lower() for item in value if str(item).strip()]


def _env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped
