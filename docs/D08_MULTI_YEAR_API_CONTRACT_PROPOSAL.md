# D08 multi-year API contract

**Status:** Approved and implemented for local development on 2026-11-22  
**Dependency:** Approved DE data contract v1.1.0 and verified active ClickHouse release

## Compatible behavior

- Keep `/api/v1`, all existing response fields, GeoJSON properties, coverage states, source/caveat semantics, and request validation.
- Verified metadata expands to `date_min=2023-01-01` and `date_max=2025-12-31`. `known_unavailable_dates` remains the two documented 2023 dates; the 21 no-row dates are returned as `unknown` coverage issues when included in a query.
- Individual-year summary, map, and chat requests support 2023, 2024, or 2025. Missing dates yield partial results and null-backed issues, never fabricated zeros.
- Map requests retain the existing feature cap and maximum date-range bound. Dashboard initialization uses the latest available calendar year rather than requesting all three years.

## Additive year-over-year operation

Add one typed, server-owned operation `hotspot_year_comparison_v1` for two or three distinct years from `{2023, 2024, 2025}` and one validated province. It executes a fixed ClickHouse aggregation grouped by year; no generated SQL or per-year fan-out is allowed.

The typed result contains `product_id`, `province_code`, ordered `years`, one nullable detection count per year, per-year `is_complete` and `coverage_issues`, source provenance, and the existing hotspot caveat. Comparisons involving partial years must disclose incompleteness and must not calculate percentage/directional claims unless every compared year is complete. Existing chat/chart response shapes may carry the ordered yearly points; any new public request/result fields require a separately versioned OpenAPI proposal and BE/FE review.

## Approval gates

1. Tech Lead + DE approve data contract v1.1.0 and local publication plan.
2. BE approves API compatibility, typed year-comparison models/query, maximum range, and coverage semantics.
3. FE approves metadata-driven year/date filters, partial-coverage display, yearly chart points, and unchanged map behavior.
4. Only after approval: run local migration/load, exact reconciliation, focused API/UI/chat tests, and live browser verification. No production deployment is authorized.
