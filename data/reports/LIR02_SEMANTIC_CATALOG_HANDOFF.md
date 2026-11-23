# LIR-02 structured analytics semantic catalog handoff

**Status:** DONE; approved 2026-11-16  
**Owner:** Data Engineer  
**Consumer reviewer:** Backend Engineer

## Published boundary

The versioned catalog publishes the existing D04/A03/B13 analytics meaning without changing runtime behavior, schemas, views, or query execution. It defines one detection-count metric, the approved VIIRS S-NPP Collection 2 standard product, all 38 canonical provinces, 2023 UTC coverage, the four current operations, ranking/tie rules, null/zero/unavailable behavior, geography exclusions, and a bounded retrieval-filter allowlist with field cardinalities.

Artifacts:

- `data/contracts/hotspot_semantic_catalog_v1.0.0.json` (`282d1842869d557654bc7dd0694597ed865e70cd35acf464928f2295913ee926`)
- `data/contracts/hotspot_semantic_catalog_v1.0.0.schema.json`
- `data/contracts/fixtures/hotspot_semantic_catalog_v1.0.0.fixture.json` (`1c0e8070116cb90a4b15bed3c526450c3adb9b6a9c3a2c740d921944211cd98c`)
- `data/contracts/reference/hotspot_semantic_reference_queries_v1.0.0.sql`
- `data/contracts/reference/hotspot_semantic_reference_results_v1.0.0.json` (`4529028b79e76fd1bd306ea73d02fcfeb174f2bb4e69cd0a95c647c23d1d9066`)

The fixture is explicitly synthetic and covers positive and negative cases for each of eight semantic rules. Its five derived edge results cover a highest tie, covered-zero tie, partial subtotal, wholly unavailable null, and unassigned-geography exclusion. Separately labeled verified snapshot evidence preserves D06 truth: 253,388 observations, 252,582 assigned, 796 unassigned, 10 multiple matches, 806 excluded from exact-one-province rows, and 687 Riau detections in September 2023.

## Compatibility and migration

This is an additive v1 contract with an empty deprecation list. Backend adoption belongs to LIR-04 or a separately authorized consumer ticket; LIR-02 changes no Backend code. Consumers must reject incompatible catalog versions and use only the declared safe filters.

The approved Data Engineer crosswalk uses `91=Papua`, `92=Papua Barat`, `93=Papua Selatan`, `94=Papua Tengah`, `95=Papua Pegunungan`, and `96=Papua Barat Daya`. The existing Backend resolver uses a different Papua convention. Backend must reconcile that known mismatch before consuming this catalog; the catalog must not be changed to match the runtime defect.

## Verification

- Catalog validator: passed; 4 operations, 38 provinces, 16 semantic cases, 5 synthetic reference results.
- Focused test: `10 passed in 0.05s`.
- Full data regression: `71 passed in 71.40s`.
- LIR-02 Ruff lint and format checks: passed. Repository-wide `ruff check data` remains red on 40 pre-existing findings outside LIR-02 files.
- Dependency integrity: `No broken requirements found`.

No embedding, prompt, routing, rewriting, RAG, LangGraph, new metric, new view, or chatbot runtime behavior is included or claimed.
