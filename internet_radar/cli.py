from __future__ import annotations

import argparse
import json

from internet_radar.pipeline import run_radar_once


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Internet Radar once.")
    parser.add_argument("--live", action="store_true", help="Use live network collectors instead of bundled sample data.")
    parser.add_argument("--db", default="data/radar.sqlite", help="SQLite database path.")
    args = parser.parse_args()

    briefing = run_radar_once(db_path=args.db, use_live_network=args.live)
    print(json.dumps(briefing.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
