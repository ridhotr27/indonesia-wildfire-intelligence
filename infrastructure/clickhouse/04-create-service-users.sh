#!/bin/sh
set -eu

: "${CLICKHOUSE_USER:?CLICKHOUSE_USER is required}"
: "${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD is required}"
: "${CLICKHOUSE_BACKEND_PASSWORD:?CLICKHOUSE_BACKEND_PASSWORD is required}"
: "${CLICKHOUSE_INGESTOR_PASSWORD:?CLICKHOUSE_INGESTOR_PASSWORD is required}"

clickhouse-client \
  --user "$CLICKHOUSE_USER" \
  --password "$CLICKHOUSE_PASSWORD" \
  --multiquery \
  --param_backend_password "$CLICKHOUSE_BACKEND_PASSWORD" \
  --param_ingestor_password "$CLICKHOUSE_INGESTOR_PASSWORD" <<'SQL'
CREATE USER IF NOT EXISTS wildfire_backend
IDENTIFIED WITH sha256_password BY {backend_password:String};
GRANT wildfire_backend_reader TO wildfire_backend;
SET DEFAULT ROLE wildfire_backend_reader TO wildfire_backend;

CREATE ROLE IF NOT EXISTS wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_ingestion_batches_v1 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_hotspot_observations_v1 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_daily_coverage_v1 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_provinces_v1 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_ingestion_batches_v11 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_hotspot_observations_v11 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_daily_coverage_v11 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_provinces_v11 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_dataset_releases_v1 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_dataset_release_batches_v1 TO wildfire_ingestor_role;
GRANT SELECT, INSERT ON wildfire.de_active_release_events_v1 TO wildfire_ingestor_role;
GRANT SELECT ON wildfire.analytics_ingestion_batches_v1 TO wildfire_ingestor_role;
GRANT SELECT ON wildfire.analytics_hotspot_observations_v1 TO wildfire_ingestor_role;
GRANT SELECT ON wildfire.analytics_daily_coverage_v1 TO wildfire_ingestor_role;
GRANT SELECT ON wildfire.analytics_provinces_v1 TO wildfire_ingestor_role;

CREATE USER IF NOT EXISTS wildfire_ingestor
IDENTIFIED WITH sha256_password BY {ingestor_password:String};
GRANT wildfire_ingestor_role TO wildfire_ingestor;
SET DEFAULT ROLE wildfire_ingestor_role TO wildfire_ingestor;
SQL
