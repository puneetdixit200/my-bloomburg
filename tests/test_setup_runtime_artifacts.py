from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import yaml

from internet_radar.storage.models import SignalRecord, UserProfile


def test_architecture_root_runtime_commands_exist_without_import_side_effects():
    scheduler_wrapper = Path("scheduler/runner.py")
    telegram_wrapper = Path("alerts/telegram_bot.py")

    assert scheduler_wrapper.exists()
    assert telegram_wrapper.exists()
    assert "from internet_radar.scheduler.runner import main" in scheduler_wrapper.read_text()
    assert "from internet_radar.alerts.telegram_bot import main" in telegram_wrapper.read_text()
    assert "sys.path.insert" in scheduler_wrapper.read_text()
    assert "sys.path.insert" in telegram_wrapper.read_text()

    runpy.run_path(str(scheduler_wrapper))
    runpy.run_path(str(telegram_wrapper))


def test_scheduler_runner_once_mode_is_testable_without_sleep(monkeypatch, tmp_path):
    from internet_radar.scheduler.runner import main

    monkeypatch.setenv("INTERNET_RADAR_DB", str(tmp_path / "radar.sqlite"))
    calls: list[str] = []

    def collect_once() -> int:
        calls.append("collected")
        return 7

    main(argv=["--once"], collector=collect_once)

    assert calls == ["collected"]


def test_root_telegram_command_help_resolves_package_imports():
    completed = subprocess.run(
        [sys.executable, "alerts/telegram_bot.py", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Dispatch Internet Radar alerts to Telegram" in completed.stdout


def test_docker_compose_declares_architecture_services():
    compose = yaml.safe_load(Path("docker-compose.yml").read_text())
    services = compose["services"]

    assert {"dashboard", "scheduler", "telegram-bot", "ollama"} <= set(services)
    assert "streamlit run dashboard/app.py" in services["dashboard"]["command"]
    assert "python scheduler/runner.py" in services["scheduler"]["command"]
    assert "python alerts/telegram_bot.py --watch" in services["telegram-bot"]["command"]
    assert services["dashboard"]["environment"]["INTERNET_RADAR_DB"] == "/data/radar.sqlite"
    assert services["telegram-bot"]["environment"]["TELEGRAM_BOT_TOKEN"] == "${TELEGRAM_BOT_TOKEN:-}"
    assert services["dashboard"]["environment"]["COHERE_API_KEY"] == "${COHERE_API_KEY:-}"
    assert services["dashboard"]["environment"]["GROQ_API_KEY"] == "${GROQ_API_KEY:-}"
    assert services["dashboard"]["environment"]["LIBRARIES_IO_API_KEY"] == "${LIBRARIES_IO_API_KEY:-}"
    assert services["dashboard"]["environment"]["INTERNET_RADAR_STORAGE_BACKEND"] == "${INTERNET_RADAR_STORAGE_BACKEND:-sqlite}"
    assert services["dashboard"]["environment"]["SUPABASE_URL"] == "${SUPABASE_URL:-}"
    assert services["dashboard"]["environment"]["INTERNET_RADAR_VECTOR_BACKEND"] == "${INTERNET_RADAR_VECTOR_BACKEND:-auto}"
    assert "radar-data" in compose["volumes"]


def test_telegram_bot_builds_telegram_scoped_alerts():
    from internet_radar.alerts.telegram_bot import build_telegram_alerts

    alerts = build_telegram_alerts(
        [
            SignalRecord(
                id="skill-telegram-1",
                topic="browser agents",
                title="Browser agent skill demand rising",
                source="Skill Radar",
                category="jobs",
                score=88,
                metadata={"relevance_score": 91},
            )
        ],
        profile=UserProfile(alert_threshold=80, notification_channels=["ntfy"]),
    )

    assert len(alerts) == 1
    assert alerts[0].channels == ["telegram"]
    assert alerts[0].signal_id == "skill-telegram-1"


def test_telegram_dispatch_dry_run_skips_missing_credentials_without_network(tmp_path, monkeypatch):
    from internet_radar.alerts.telegram_bot import dispatch_telegram_alerts
    from internet_radar.storage.db import RadarStore

    db_path = tmp_path / "radar.sqlite"
    store = RadarStore(db_path)
    store.upsert_signals(
        [
            SignalRecord(
                id="skill-telegram-2",
                topic="local llm",
                title="Local LLM jobs accelerate",
                source="Skill Radar",
                category="jobs",
                score=90,
            )
        ]
    )
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    def fail_post(*args, **kwargs):
        raise AssertionError("network should not be called without Telegram credentials")

    results = dispatch_telegram_alerts(
        db_path=db_path,
        profile=UserProfile(alert_threshold=80),
        http_post=fail_post,
    )

    assert len(results) == 1
    assert not results[0].sent
    assert results[0].channel == "telegram"
    assert "missing" in results[0].detail
