"""BigQuery schema management and stage-then-MERGE loading.

BigQuery has no unique constraints or UPSERT, so every load goes:
truncate a `_staging` table -> load rows into it -> MERGE into the target
table keyed by its natural key (title_id, or np_communication_id+trophy_id).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from .psn_client import GameRow, TrophyDefRow, TrophyProgressRow

SCHEMA_FILE = Path(__file__).resolve().parent.parent.parent / "sql" / "schema.sql"


def ensure_schema(client: bigquery.Client, project: str, dataset: str, location: str) -> None:
    dataset_ref = bigquery.DatasetReference(project, dataset)
    ds = bigquery.Dataset(dataset_ref)
    ds.location = location
    client.create_dataset(ds, exists_ok=True)

    ddl = SCHEMA_FILE.read_text().format(project=project, dataset=dataset)
    for statement in filter(None, (s.strip() for s in ddl.split(";"))):
        client.query(statement).result()


def get_existing_games(
    client: bigquery.Client, project: str, dataset: str
) -> dict[str, tuple[float, int]]:
    """{title_id: (playtime_hours, play_count)} as currently stored."""
    query = f"SELECT title_id, playtime_hours, play_count FROM `{project}.{dataset}.games`"
    return {
        row.title_id: (row.playtime_hours or 0.0, row.play_count or 0)
        for row in client.query(query).result()
    }


def _load_staging(
    client: bigquery.Client,
    project: str,
    dataset: str,
    table: str,
    schema: list[bigquery.SchemaField],
    rows: list[dict[str, Any]],
) -> None:
    table_ref = f"{project}.{dataset}.{table}"
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    client.load_table_from_json(rows, table_ref, job_config=job_config).result()


def load_games(
    client: bigquery.Client, project: str, dataset: str, games: list[GameRow], now: datetime
) -> None:
    if not games:
        return
    schema = [
        bigquery.SchemaField("title_id", "STRING"),
        bigquery.SchemaField("np_communication_id", "STRING"),
        bigquery.SchemaField("title", "STRING"),
        bigquery.SchemaField("system", "STRING"),
        bigquery.SchemaField("playtime_hours", "FLOAT"),
        bigquery.SchemaField("play_count", "INTEGER"),
        bigquery.SchemaField("last_played", "TIMESTAMP"),
        bigquery.SchemaField("first_synced_at", "TIMESTAMP"),
        bigquery.SchemaField("last_synced_at", "TIMESTAMP"),
    ]
    rows = [
        {
            "title_id": g.title_id,
            "np_communication_id": g.np_communication_id,
            "title": g.title,
            "system": g.system,
            "playtime_hours": g.playtime_hours,
            "play_count": g.play_count,
            "last_played": g.last_played.isoformat() if g.last_played else None,
            "first_synced_at": now.isoformat(),
            "last_synced_at": now.isoformat(),
        }
        for g in games
    ]
    _load_staging(client, project, dataset, "games_staging", schema, rows)
    client.query(f"""
        MERGE `{project}.{dataset}.games` T
        USING `{project}.{dataset}.games_staging` S
        ON T.title_id = S.title_id
        WHEN MATCHED THEN UPDATE SET
            np_communication_id = COALESCE(S.np_communication_id, T.np_communication_id),
            title = S.title,
            system = S.system,
            playtime_hours = S.playtime_hours,
            play_count = S.play_count,
            last_played = S.last_played,
            last_synced_at = S.last_synced_at
        WHEN NOT MATCHED THEN INSERT (
            title_id, np_communication_id, title, system, playtime_hours,
            play_count, last_played, first_synced_at, last_synced_at
        ) VALUES (
            S.title_id, S.np_communication_id, S.title, S.system, S.playtime_hours,
            S.play_count, S.last_played, S.first_synced_at, S.last_synced_at
        )
    """).result()


def load_trophy_definitions(
    client: bigquery.Client, project: str, dataset: str, definitions: list[TrophyDefRow]
) -> None:
    if not definitions:
        return
    schema = [
        bigquery.SchemaField("np_communication_id", "STRING"),
        bigquery.SchemaField("trophy_id", "INTEGER"),
        bigquery.SchemaField("trophy_name", "STRING"),
        bigquery.SchemaField("trophy_type", "STRING"),
        bigquery.SchemaField("trophy_detail", "STRING"),
    ]
    # Dedup: the same (np_communication_id, trophy_id) can repeat across runs.
    unique = {(d.np_communication_id, d.trophy_id): d for d in definitions}
    rows = [
        {
            "np_communication_id": d.np_communication_id,
            "trophy_id": d.trophy_id,
            "trophy_name": d.trophy_name,
            "trophy_type": d.trophy_type,
            "trophy_detail": d.trophy_detail,
        }
        for d in unique.values()
    ]
    _load_staging(client, project, dataset, "trophy_definitions_staging", schema, rows)
    client.query(f"""
        MERGE `{project}.{dataset}.trophy_definitions` T
        USING `{project}.{dataset}.trophy_definitions_staging` S
        ON T.np_communication_id = S.np_communication_id AND T.trophy_id = S.trophy_id
        WHEN MATCHED THEN UPDATE SET
            trophy_name = S.trophy_name,
            trophy_type = S.trophy_type,
            trophy_detail = S.trophy_detail
        WHEN NOT MATCHED THEN INSERT (
            np_communication_id, trophy_id, trophy_name, trophy_type, trophy_detail
        ) VALUES (
            S.np_communication_id, S.trophy_id, S.trophy_name, S.trophy_type, S.trophy_detail
        )
    """).result()


def load_trophy_progress(
    client: bigquery.Client,
    project: str,
    dataset: str,
    progress: list[TrophyProgressRow],
    now: datetime,
) -> None:
    if not progress:
        return
    schema = [
        bigquery.SchemaField("title_id", "STRING"),
        bigquery.SchemaField("trophy_id", "INTEGER"),
        bigquery.SchemaField("np_communication_id", "STRING"),
        bigquery.SchemaField("earned", "BOOLEAN"),
        bigquery.SchemaField("earned_at", "TIMESTAMP"),
        bigquery.SchemaField("rarity", "STRING"),
        bigquery.SchemaField("last_synced_at", "TIMESTAMP"),
    ]
    rows = [
        {
            "title_id": p.title_id,
            "trophy_id": p.trophy_id,
            "np_communication_id": p.np_communication_id,
            "earned": p.earned,
            "earned_at": p.earned_at.isoformat() if p.earned_at else None,
            "rarity": p.rarity,
            "last_synced_at": now.isoformat(),
        }
        for p in progress
    ]
    _load_staging(client, project, dataset, "trophy_progress_staging", schema, rows)
    client.query(f"""
        MERGE `{project}.{dataset}.trophy_progress` T
        USING `{project}.{dataset}.trophy_progress_staging` S
        ON T.title_id = S.title_id AND T.trophy_id = S.trophy_id
        WHEN MATCHED THEN UPDATE SET
            earned = S.earned,
            earned_at = S.earned_at,
            rarity = S.rarity,
            last_synced_at = S.last_synced_at
        WHEN NOT MATCHED THEN INSERT (
            title_id, trophy_id, np_communication_id, earned, earned_at, rarity, last_synced_at
        ) VALUES (
            S.title_id, S.trophy_id, S.np_communication_id, S.earned, S.earned_at, S.rarity, S.last_synced_at
        )
    """).result()


def insert_sync_run(
    client: bigquery.Client,
    project: str,
    dataset: str,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    games_synced: int,
    trophies_synced: int,
    status: str,
    error_message: str | None,
) -> None:
    table_ref = f"{project}.{dataset}.sync_runs"
    row = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "games_synced": games_synced,
        "trophies_synced": trophies_synced,
        "status": status,
        "error_message": error_message,
    }
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"failed to insert sync_runs row: {errors}")
