-- D07 operator checks for the approved immutable calendar-2023 v1 publication.
-- Run as the DE/operator identity after loading. The throwIf makes
-- clickhouse-client exit non-zero when any blocking threshold fails.
WITH
    (SELECT count() FROM wildfire.analytics_ingestion_batches_v1) AS batches,
    (SELECT count() FROM wildfire.analytics_hotspot_observations_v1) AS observations,
    (SELECT count() FROM wildfire.analytics_daily_coverage_v1) AS coverage_days,
    (SELECT count() FROM wildfire.analytics_provinces_v1) AS provinces,
    (SELECT count() FROM wildfire.analytics_daily_coverage_v1
        WHERE coverage_status = 'known_satellite_gap'
          AND observation_count IS NULL AND evidence_url IS NOT NULL) AS known_gaps,
    (SELECT count() FROM wildfire.analytics_hotspot_observations_v1
        WHERE toDate(acquired_at_utc) IN ('2023-07-26', '2023-07-27')) AS gap_observations,
    (SELECT count() FROM wildfire.analytics_hotspot_observations_v1
        WHERE geo_assignment_status != 'assigned'
          AND (province_code IS NOT NULL OR province_name IS NOT NULL
               OR boundary_source_id IS NOT NULL)) AS invalid_null_geography,
    (SELECT count() FROM wildfire.de_hotspot_observations_v1 o
        WHERE NOT EXISTS (SELECT 1 FROM wildfire.de_ingestion_batches_v1 b
          WHERE b.ingestion_batch_id = o.ingestion_batch_id))
      + (SELECT count() FROM wildfire.de_daily_coverage_v1 c
        WHERE NOT EXISTS (SELECT 1 FROM wildfire.de_ingestion_batches_v1 b
          WHERE b.ingestion_batch_id = c.load_batch_id))
      + (SELECT count() FROM wildfire.de_provinces_v1 p
        WHERE NOT EXISTS (SELECT 1 FROM wildfire.de_ingestion_batches_v1 b
          WHERE b.ingestion_batch_id = p.load_batch_id)) AS unpublished_rows
SELECT
    batches,
    observations,
    coverage_days,
    provinces,
    known_gaps,
    gap_observations,
    invalid_null_geography,
    unpublished_rows,
    (batches != 1) + (observations != 253388) + (coverage_days != 365)
      + (provinces != 38) + (known_gaps != 2) + (gap_observations != 0)
      + (invalid_null_geography != 0) + (unpublished_rows != 0) AS failed_checks,
    throwIf(
      (batches != 1) + (observations != 253388) + (coverage_days != 365)
        + (provinces != 38) + (known_gaps != 2) + (gap_observations != 0)
        + (invalid_null_geography != 0) + (unpublished_rows != 0) != 0,
      'D07 publication QA failed'
    ) AS assertion;

-- Freshness is publication/provenance metadata for a frozen historical snapshot.
-- It is not a claim that the data refreshes continuously.
SELECT
    ingestion_batch_id,
    contract_version,
    transform_version,
    source_artifact_sha256,
    retrieved_at_utc,
    provider_last_modified_utc,
    coverage_start_utc,
    coverage_end_utc,
    published_at_utc
FROM wildfire.analytics_ingestion_batches_v1
ORDER BY published_at_utc DESC, ingestion_batch_id;
