# LIR-04 schema and operation-registry review

**Status:** DONE  
**Date:** 2026-11-15

LIR-04 adds an internal, unused-by-runtime boundary for future structured intent proposals. Strict frozen Pydantic models reject extra fields and bound all strings and collections. The validator emits explicit rejection codes and accepts only catalog-approved metric, product, 38-province codes, 2023 dates, dimensions, filters, ranking operators, and operation-specific slot combinations.

The read-only registry consumes `hotspot-semantic-catalog-v1.0.0` and fails closed on schema, catalog, or data-contract version drift. Each accepted operation maps to exactly one existing typed adapter: summary/trend to `HotspotAnalyticsTool`, multi-province/ranking to `HotspotProvinceAnalyticsTool`, and NASA documentation to `NasaRetrievalTool`. GeoJSON/map, SQL, arbitrary tools, answers, confidence, and reasoning fields are excluded.

Verification:

- Focused: 25 passed in 0.10s.
- Full backend: 414 passed, 1 opt-in ClickHouse integration skipped in 5.89s.
- Ruff lint/format for all changed Python files: passed.
- Secret scan for changed Python files: passed.

No LangGraph node, runtime import, prompt, model, SQL, public API, dependency, configuration, or data contract changed. The existing Backend/Data Papua-code mismatch remains a future runtime-integration concern; this registry correctly consumes the approved LIR-02 catalog.
