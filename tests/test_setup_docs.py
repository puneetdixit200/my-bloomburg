from __future__ import annotations

from pathlib import Path


def test_env_example_exists_for_documented_setup():
    env_example = Path(".env.example")

    assert env_example.exists()
    content = env_example.read_text()
    assert "INTERNET_RADAR_USE_LIVE" in content
    assert "TELEGRAM_BOT_TOKEN" in content
    assert "DISCORD_WEBHOOK_URL" in content
    assert "MAILGUN_API_KEY" in content
