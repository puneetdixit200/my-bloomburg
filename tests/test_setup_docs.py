from __future__ import annotations

from pathlib import Path

import yaml


def test_env_example_exists_for_documented_setup():
    env_example = Path(".env.example")

    assert env_example.exists()
    content = env_example.read_text()
    assert "INTERNET_RADAR_USE_LIVE" in content
    assert "TELEGRAM_BOT_TOKEN" in content
    assert "DISCORD_WEBHOOK_URL" in content
    assert "MAILGUN_API_KEY" in content
    assert "INTERNET_RADAR_STORAGE_BACKEND" in content
    assert "SUPABASE_URL" in content
    assert "INTERNET_RADAR_VECTOR_BACKEND" in content


def test_rss_config_declares_twenty_plus_feeds():
    data = yaml.safe_load(Path("config/rss_feeds.yaml").read_text())
    feeds = data["feeds"]

    assert len(feeds) >= 20
    assert all(feed.get("name") and feed.get("url") for feed in feeds)


def test_vector_requirements_file_exists_for_non_uv_installs():
    content = Path("requirements-vector.txt").read_text()

    assert "chromadb" in content
    assert "protobuf>=3.20,<4" in content
