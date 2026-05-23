from __future__ import annotations

import argparse
import os
import time
from collections.abc import Callable
from typing import Sequence

from internet_radar.scheduler.jobs import collect_high_frequency


Collector = Callable[[], int]


def run_cycle(collector: Collector = collect_high_frequency) -> int:
    return collector()


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
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=default_interval,
        help="Polling interval for continuous mode.",
    )
    args = parser.parse_args(argv)

    while True:
        signals_24h = run_cycle(collector)
        print(f"scheduler cycle: signals_24h={signals_24h}")
        if args.once:
            return
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
