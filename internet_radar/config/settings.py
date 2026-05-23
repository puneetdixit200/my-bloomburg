from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from internet_radar.storage.models import UserProfile


DEFAULT_PROFILE_PATH = Path("config/interests.yaml")


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
