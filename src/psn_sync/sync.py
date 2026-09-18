"""Entry point: fetch PSN library + trophies, load into BigQuery.

Usage:
    python -m psn_sync.sync             # full run (writes to BigQuery)
    python -m psn_sync.sync --dry-run   # fetch from PSN only, print a summary,
                                         # skip all GCP calls (no credentials needed)
    python -m psn_sync.sync --dry-run --limit 5   # same, capped to 5 changed titles
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

from .config import Config
from .psn_client import authenticate, fetch_games, fetch_trophies_for_titles


def run(dry_run: bool, limit: int | None = None) -> int:
    config = Config.from_env()
    started_at = datetime.now(timezone.utc)
    run_id = str(uuid.uuid4())

    if dry_run:
        npsso = config.npsso_override
        if not npsso:
            print("--dry-run requires $PSN_NPSSO to be set", file=sys.stderr)
            return 2
    else:
        from .secrets import fetch_npsso

        npsso = fetch_npsso(config)

    try:
        _, client = authenticate(npsso)
    except Exception as exc:  # noqa: BLE001 - surface any auth failure clearly
        print(f"PSN authentication failed: {exc}", file=sys.stderr)
        return 2

    print(f"authenticated as {client.online_id}")
    games = fetch_games(client)
    print(f"fetched {len(games)} titles from PSN")

    bq = None
    previous: dict[str, tuple[float, int, bool]] = {}
    if not dry_run:
        from google.cloud import bigquery

        from .bigquery_client import ensure_schema, get_existing_games

        bq = bigquery.Client(project=config.gcp_project)
        ensure_schema(bq, config.gcp_project, config.bq_dataset, config.bq_location)
        previous = get_existing_games(bq, config.gcp_project, config.bq_dataset)

    changed_title_ids = [
        g.title_id
        for g in games
        if g.title_id not in previous
        or previous[g.title_id][:2] != (g.playtime_hours, g.play_count)
        or not previous[g.title_id][2]
    ]
    if limit is not None:
        changed_title_ids = changed_title_ids[:limit]
    print(f"{len(changed_title_ids)} title(s) changed since last sync; fetching their trophies")

    def _report_progress(done: int, total: int) -> None:
        print(f"  trophy batch {done}/{total}")

    definitions, progress, comm_ids = fetch_trophies_for_titles(
        client, changed_title_ids, on_progress=_report_progress
    )
    print(f"fetched {len(progress)} trophy rows across {len(comm_ids)} title(s)")

    for g in games:
        if g.title_id in comm_ids:
            g.np_communication_id = comm_ids[g.title_id]

    status, error_message = "ok", None
    if not dry_run and bq is not None:
        from .bigquery_client import (
            insert_sync_run,
            load_games,
            load_trophy_definitions,
            load_trophy_progress,
        )

        try:
            load_games(bq, config.gcp_project, config.bq_dataset, games, started_at)
            load_trophy_definitions(bq, config.gcp_project, config.bq_dataset, definitions)
            load_trophy_progress(bq, config.gcp_project, config.bq_dataset, progress, started_at)
        except Exception as exc:  # noqa: BLE001 - record failure, still log the run
            status, error_message = "error", str(exc)
        finally:
            insert_sync_run(
                bq,
                config.gcp_project,
                config.bq_dataset,
                run_id,
                started_at,
                datetime.now(timezone.utc),
                len(games),
                len(progress),
                status,
                error_message,
            )

    if status == "error":
        print(f"sync failed: {error_message}", file=sys.stderr)
        return 1

    print("sync complete" + (" (dry run, nothing written)" if dry_run else ""))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch from PSN and print a summary only; skip BigQuery entirely",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap the number of changed titles processed for trophies (testing)",
    )
    args = parser.parse_args()
    sys.exit(run(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
