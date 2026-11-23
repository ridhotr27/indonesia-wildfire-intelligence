-- D06 physical model for approved D04 contract v1.0.0.
-- Apply with clickhouse-client --multiquery after creating the `wildfire` database.
CREATE DATABASE IF NOT EXISTS wildfire;

CREATE TABLE IF NOT EXISTS wildfire.de_ingestion_batches_v1
(
    contract_version String,
    ingestion_batch_id String,
    product_id LowCardinality(String),
    source_url String,
    source_artifact_sha256 FixedString(64),
    source_bytes UInt64,
    retrieved_at_utc DateTime64(0, 'UTC'),
    provider_last_modified_utc Nullable(DateTime64(0, 'UTC')),
    coverage_start_utc DateTime64(0, 'UTC'),
    coverage_end_utc DateTime64(0, 'UTC'),
    source_row_count UInt64,
    canonical_row_count UInt64,
    duplicate_excess_rows UInt64,
    rejected_row_count UInt64,
    transform_version String,
    provenance_manifest_path String,
    publication_status LowCardinality(String),
    published_at_utc DateTime64(0, 'UTC'),
    CONSTRAINT d06_batch_contract CHECK contract_version = '1.0.0',
    CONSTRAINT d06_batch_product CHECK product_id = 'VNP14IMG.002_SNPP_FIRMS_SP',
    CONSTRAINT d06_batch_published CHECK publication_status = 'published',
    CONSTRAINT d06_batch_counts CHECK canonical_row_count + duplicate_excess_rows = source_row_count AND rejected_row_count = 0
)
ENGINE = MergeTree
ORDER BY (product_id, published_at_utc, ingestion_batch_id);

CREATE TABLE IF NOT EXISTS wildfire.de_hotspot_observations_v1
(
    contract_version String,
    observation_id FixedString(64),
    product_id LowCardinality(String),
    source_product LowCardinality(String),
    collection_version LowCardinality(String),
    processing_stream LowCardinality(String),
    satellite_code LowCardinality(String),
    satellite_name LowCardinality(String),
    instrument LowCardinality(String),
    acquired_at_utc DateTime64(0, 'UTC'),
    latitude Float64,
    longitude Float64,
    brightness_i4_kelvin Float32,
    brightness_i5_kelvin Float32,
    scan_km Float32,
    track_km Float32,
    frp_mw Float32,
    confidence_code LowCardinality(String),
    confidence_label LowCardinality(String),
    daynight_code LowCardinality(String),
    hotspot_type_code UInt8,
    province_code Nullable(FixedString(2)),
    province_name Nullable(String),
    geo_assignment_status LowCardinality(String),
    geo_assignment_method LowCardinality(String),
    boundary_source_id Nullable(String),
    ingestion_batch_id String,
    source_row_number UInt64,
    source_record_hash FixedString(64),
    quality_flags Array(LowCardinality(String)),
    CONSTRAINT d06_obs_contract CHECK contract_version = '1.0.0',
    CONSTRAINT d06_obs_product CHECK product_id = 'VNP14IMG.002_SNPP_FIRMS_SP',
    CONSTRAINT d06_obs_coords CHECK latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180,
    CONSTRAINT d06_obs_frp CHECK frp_mw >= 0,
    CONSTRAINT d06_obs_confidence CHECK confidence_code IN ('l', 'n', 'h'),
    CONSTRAINT d06_obs_daynight CHECK daynight_code IN ('D', 'N'),
    CONSTRAINT d06_obs_gap CHECK toDate(acquired_at_utc) NOT IN ('2023-07-26', '2023-07-27')
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(acquired_at_utc)
ORDER BY (product_id, ifNull(province_code, ''), acquired_at_utc, observation_id);

CREATE TABLE IF NOT EXISTS wildfire.de_daily_coverage_v1
(
    contract_version String,
    product_id LowCardinality(String),
    date_utc Date,
    coverage_status LowCardinality(String),
    observation_count Nullable(UInt64),
    evidence_url Nullable(String),
    note Nullable(String),
    ingestion_batch_id Nullable(String),
    load_batch_id String,
    CONSTRAINT d06_coverage_contract CHECK contract_version = '1.0.0',
    CONSTRAINT d06_coverage_product CHECK product_id = 'VNP14IMG.002_SNPP_FIRMS_SP',
    CONSTRAINT d06_coverage_state CHECK
        (coverage_status = 'observations_present' AND observation_count > 0)
     OR (coverage_status = 'known_satellite_gap' AND observation_count IS NULL AND evidence_url IS NOT NULL)
     OR (coverage_status = 'zero_detections_verified' AND observation_count = 0 AND evidence_url IS NOT NULL)
     OR (coverage_status = 'unknown' AND observation_count IS NULL)
)
ENGINE = MergeTree
ORDER BY (product_id, date_utc);

CREATE TABLE IF NOT EXISTS wildfire.de_provinces_v1
(
    contract_version String,
    province_code FixedString(2),
    province_name String,
    source_code String,
    source_name String,
    boundary_source_id String,
    snapshot String,
    commit String,
    crs String,
    source_sha256 FixedString(64),
    canonical_sha256 FixedString(64),
    license String,
    license_url String,
    required_attribution String,
    is_supported Bool,
    load_batch_id String,
    CONSTRAINT d06_province_contract CHECK contract_version = '1.0.0',
    CONSTRAINT d06_boundary CHECK boundary_source_id = 'osm-idn-adm1-2026-10-10b'
)
ENGINE = MergeTree
ORDER BY province_code;

CREATE OR REPLACE VIEW wildfire.analytics_ingestion_batches_v1 SQL SECURITY DEFINER AS
SELECT * FROM wildfire.de_ingestion_batches_v1 WHERE publication_status = 'published';

CREATE OR REPLACE VIEW wildfire.analytics_hotspot_observations_v1 SQL SECURITY DEFINER AS
SELECT o.* FROM wildfire.de_hotspot_observations_v1 AS o
INNER JOIN wildfire.analytics_ingestion_batches_v1 AS b USING (ingestion_batch_id, product_id, contract_version);

CREATE OR REPLACE VIEW wildfire.analytics_daily_coverage_v1 SQL SECURITY DEFINER AS
SELECT
    c.contract_version,
    c.product_id,
    c.date_utc,
    c.coverage_status,
    c.observation_count,
    c.evidence_url,
    c.note,
    c.ingestion_batch_id
FROM wildfire.de_daily_coverage_v1 AS c
INNER JOIN wildfire.analytics_ingestion_batches_v1 AS b
    ON c.load_batch_id = b.ingestion_batch_id
   AND c.product_id = b.product_id
   AND c.contract_version = b.contract_version;

CREATE OR REPLACE VIEW wildfire.analytics_provinces_v1 SQL SECURITY DEFINER AS
SELECT
    p.contract_version,
    p.province_code,
    p.province_name,
    p.source_code,
    p.source_name,
    p.boundary_source_id,
    p.snapshot,
    p.commit,
    p.crs,
    p.source_sha256,
    p.canonical_sha256,
    p.license,
    p.license_url,
    p.required_attribution,
    p.is_supported
FROM wildfire.de_provinces_v1 AS p
INNER JOIN wildfire.analytics_ingestion_batches_v1 AS b
    ON p.load_batch_id = b.ingestion_batch_id
   AND p.contract_version = b.contract_version;
