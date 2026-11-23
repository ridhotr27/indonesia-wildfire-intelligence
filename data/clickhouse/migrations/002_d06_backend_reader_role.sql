-- Apply as an administrator. User creation/password rotation is deliberately external.
CREATE ROLE IF NOT EXISTS wildfire_backend_reader;
GRANT SELECT ON wildfire.analytics_hotspot_observations_v1 TO wildfire_backend_reader;
GRANT SELECT ON wildfire.analytics_daily_coverage_v1 TO wildfire_backend_reader;
GRANT SELECT ON wildfire.analytics_provinces_v1 TO wildfire_backend_reader;
GRANT SELECT ON wildfire.analytics_ingestion_batches_v1 TO wildfire_backend_reader;

-- Example operator action (do not commit a password):
-- CREATE USER wildfire_backend IDENTIFIED WITH sha256_password BY '<secret>';
-- GRANT wildfire_backend_reader TO wildfire_backend;
-- SET DEFAULT ROLE wildfire_backend_reader TO wildfire_backend;
