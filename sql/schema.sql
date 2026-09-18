-- BigQuery schema for PSN library + trophies.
-- Natural keys are used throughout (title_id, np_communication_id + trophy_id)
-- since BigQuery has no surrogate auto-increment / unique constraints; the
-- loader enforces uniqueness itself via stage-then-MERGE.

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.games` (
    title_id STRING NOT NULL,
    np_communication_id STRING,
    title STRING,
    system STRING,
    playtime_hours FLOAT64,
    play_count INT64,
    last_played TIMESTAMP,
    first_synced_at TIMESTAMP,
    last_synced_at TIMESTAMP
)
CLUSTER BY title_id;

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.games_staging` (
    title_id STRING NOT NULL,
    np_communication_id STRING,
    title STRING,
    system STRING,
    playtime_hours FLOAT64,
    play_count INT64,
    last_played TIMESTAMP,
    first_synced_at TIMESTAMP,
    last_synced_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.trophy_definitions` (
    np_communication_id STRING NOT NULL,
    trophy_id INT64 NOT NULL,
    trophy_name STRING,
    trophy_type STRING,
    trophy_detail STRING
)
CLUSTER BY np_communication_id;

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.trophy_definitions_staging` (
    np_communication_id STRING NOT NULL,
    trophy_id INT64 NOT NULL,
    trophy_name STRING,
    trophy_type STRING,
    trophy_detail STRING
);

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.trophy_progress` (
    title_id STRING NOT NULL,
    trophy_id INT64 NOT NULL,
    np_communication_id STRING,
    earned BOOL,
    earned_at TIMESTAMP,
    rarity STRING,
    last_synced_at TIMESTAMP
)
CLUSTER BY title_id;

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.trophy_progress_staging` (
    title_id STRING NOT NULL,
    trophy_id INT64 NOT NULL,
    np_communication_id STRING,
    earned BOOL,
    earned_at TIMESTAMP,
    rarity STRING,
    last_synced_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.sync_runs` (
    run_id STRING NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    games_synced INT64,
    trophies_synced INT64,
    status STRING,
    error_message STRING
);
