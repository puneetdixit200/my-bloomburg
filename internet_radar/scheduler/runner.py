from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from typing import Any
from typing import Sequence

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from internet_radar.scheduler.jobs import ScheduledJob, build_job_plan, collect_high_frequency


Collector = Callable[[], int]
JobRunner = Callable[[str], Any]


def run_cycle(collector: Collector = collect_high_frequency) -> int:
    return collector()


def run_named_job(job_name: str, collector: Collector = collect_high_frequency) -> int:
    return collector()


def build_scheduler(job_runner: JobRunner | None = None) -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=os.getenv("TZ", "UTC"))
    runner = job_runner or run_named_job
    for job in build_job_plan().jobs:
        scheduler.add_job(
            runner,
            trigger=_trigger_for_job(job),
            args=[job.name],
            id=job.name,
            name=job.name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    return scheduler


def main(
    interval_seconds: int | None = None,
    argv: Sequence[str] | None = None,
    collector: Collector = collect_high_frequency,
) -> None:
    default_interval = (
        interval_seconds
        if interval_seconds is not None
        else int(os.getenv("INTERNET_RADAR_SCHEDULER_INTERVAL_SECONDS", "900"))
    )
    parser = argparse.ArgumentParser(description="Run Internet Radar scheduled collection.")
    parser.add_argument("--once", action="store_true", help="Run one collection cycle and exit.")
    parser.add_argument("--loop", action="store_true", help="Run a simple high-frequency polling loop.")
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=default_interval,
        help="Polling interval when --loop is set.",
    )
    args = parser.parse_args(argv)

    if args.once:
        signals_24h = run_cycle(collector)
        print(f"scheduler cycle: signals_24h={signals_24h}")
        return

    if args.loop:
        while True:
            signals_24h = run_cycle(collector)
            print(f"scheduler cycle: signals_24h={signals_24h}")
            time.sleep(args.interval_seconds)

    scheduler = build_scheduler()
    scheduler.start()


def _trigger_for_job(job: ScheduledJob) -> IntervalTrigger | CronTrigger:
    if job.trigger == "interval":
        if job.minutes is not None:
            return IntervalTrigger(minutes=job.minutes)
        if job.hours is not None:
            return IntervalTrigger(hours=job.hours)
    if job.trigger == "cron":
        kwargs: dict[str, Any] = {"hour": job.hour if job.hour is not None else 0}
        if job.day_of_week:
            kwargs["day_of_week"] = job.day_of_week
        return CronTrigger(**kwargs)
    raise ValueError(f"Unsupported schedule for job {job.name}")


if __name__ == "__main__":
    main()
