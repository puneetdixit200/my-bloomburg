from __future__ import annotations

import time

from internet_radar.scheduler.jobs import collect_high_frequency


def main(interval_seconds: int = 900) -> None:
    while True:
        collect_high_frequency()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    main()
