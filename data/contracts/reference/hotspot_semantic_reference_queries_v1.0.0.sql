-- LIR-02 reference queries only. Execute with the Backend read-only identity.
-- All values are typed parameters; no user-supplied SQL or identifier is accepted.

-- query_id: province_counts_with_geography_exclusion
SELECT p.province_code, p.province_name, p.province_order,
       coalesce(c.detection_count, 0) AS detection_count,
       (SELECT count()
        FROM analytics_hotspot_observations_v1
        WHERE product_id = {product_id:String}
          AND acquired_at_utc >= toDateTime({date_from:Date}, 'UTC')
          AND acquired_at_utc < toDateTime(addDays({date_to:Date}, 1), 'UTC')
          AND geo_assignment_status != 'assigned') AS not_assigned_to_exactly_one_province_count
FROM (
  SELECT province_code, province_name,
         row_number() OVER (ORDER BY province_code) AS province_order
  FROM analytics_provinces_v1
  WHERE is_supported = true
) AS p
LEFT JOIN (
  SELECT province_code, count() AS detection_count
  FROM analytics_hotspot_observations_v1
  WHERE product_id = {product_id:String}
    AND acquired_at_utc >= toDateTime({date_from:Date}, 'UTC')
    AND acquired_at_utc < toDateTime(addDays({date_to:Date}, 1), 'UTC')
    AND geo_assignment_status = 'assigned'
  GROUP BY province_code
) AS c ON c.province_code = p.province_code
WHERE empty({province_codes:Array(String)})
   OR has({province_codes:Array(String)}, p.province_code)
ORDER BY p.province_code
FORMAT JSON;

-- query_id: coverage_for_range
SELECT date_utc, coverage_status, observation_count, evidence_url
FROM analytics_daily_coverage_v1
WHERE product_id = {product_id:String}
  AND date_utc BETWEEN {date_from:Date} AND {date_to:Date}
ORDER BY date_utc
FORMAT JSON;
