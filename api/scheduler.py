from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from api.ingestion import run


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ingestion on a fixed schedule.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=3600,
        help="Interval between ingestion runs in seconds (default: 3600).",
    )
    parser.add_argument(
        "--skip-initial-run",
        action="store_true",
        help="Wait one full interval before the first ingestion run.",
    )
    return parser


def _run_once() -> None:
    output_path = run()
    logging.info("Ingestion completed. Output artifact: %s", output_path)


def _sleep_until(next_run_ts: float) -> None:
    while True:
        remaining = next_run_ts - time.time()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 30))


def start_scheduler(interval_seconds: int = 3600, skip_initial_run: bool = False) -> None:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be > 0")

    logging.info("Scheduler started. Interval: %s seconds", interval_seconds)

    next_run_ts = time.time() + interval_seconds if skip_initial_run else time.time()

    while True:
        _sleep_until(next_run_ts)
        started_at = datetime.now(timezone.utc).isoformat()
        logging.info("Starting ingestion at %s", started_at)

        try:
            _run_once()
        except Exception:
            logging.exception("Ingestion run failed")

        next_run_ts = max(next_run_ts + interval_seconds, time.time() + interval_seconds)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    start_scheduler(
        interval_seconds=args.interval_seconds,
        skip_initial_run=args.skip_initial_run,
    )


if __name__ == "__main__":
    main()
