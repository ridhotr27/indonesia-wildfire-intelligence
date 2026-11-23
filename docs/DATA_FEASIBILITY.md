# Data Feasibility — Indonesia Wildfire Intelligence v1.0

**Status:** D01–D03 evidence complete; G1 pending Tech Lead approval and not passed · **Owner:** Data Engineer Codex · **Gate:** Required before schema freeze

## Purpose
Determine whether real NASA data can support the PRD's user journeys. D01–D03 now include inspected artifacts, ten-question calculations, a full-resolution boundary-point review, and a proposed logical contract. G1 still requires explicit Tech Lead approval and resolution of boundary reuse terms.

## Sources to validate
| Source | Role | Starting point | Verification required |
|---|---|---|---|
| NASA FIRMS VIIRS active-fire observations | Sole wildfire observation source | https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2023_Indonesia.csv | Public 2023 S-NPP standard-processing CSV verified; 253,388 rows and server/local checksum match |
| NASA FIRMS API | Optional acquisition route | https://firms.modaps.eosdis.nasa.gov/api/ | Secure `NASA_FIRMS_MAP_KEY` client implemented; authenticated route not exercised because the key was unset |
| NASA FIRMS documentation | RAG corpus | https://www.earthdata.nasa.gov/data/tools/firms | Attribute, FAQ, guide, citation and disclaimer URLs verified reachable |
| Indonesian province polygons | Reference geography, **not** wildfire observations | https://geoservices.big.go.id/gis/rest/services/STIG/Batas_Provinsi/MapServer/0 | 38 EPSG:4326 BIG polygons joined; 45 flagged points reviewed server-side at full resolution without downloading geometry; explicit redistribution license remains unresolved |

## Scope decision
Recommend one product and one bounded window: VIIRS S-NPP Collection 2 standard processing (`VNP14IMG.002`, FIRMS `VIIRS_SNPP_SP`) for calendar 2023 UTC. This recommendation remains subject to G1 approval. **Do not assume** other years are accessible or comparable, and do not combine products or processing streams without separate validation and approval.

## Verified D02 evidence (2026-10-21)

- NASA public historical route: `viirs-snpp_2023_Indonesia.csv`, 20,067,598 bytes, SHA-256 `2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a`.
- Actual archive schema: 15 columns, adding `type` to the D01 tutorial schema; all 253,388 rows use satellite `N`, instrument `VIIRS`, and standard-processing version `2`.
- Annual date range is 2023-01-01 through 2023-12-31, with 363 dates containing rows. At the D02 stage, the zero-row dates 2023-07-26 and 2023-07-27 were not yet classified; D03 resolves them below.
- Bounded sample: 2023-09-01 through 2023-09-05, 15,804 detections, all five requested dates present, no blanks, invalid coordinates/timestamps, negative FRP, or duplicates; seven zero-FRP rows retained.
- BIG join: 15,770 assigned, 34 unassigned, zero multiple matches; 45 rows lie within 0.001 degree of the generalized boundary. BIG exposes 38 province codes in EPSG:4326.
- Detailed evidence: `data/reports/D02_HISTORICAL_ACCESS_GEOGRAPHIC_VALIDATION.md`, `data/reports/d02_historical_validation_profile.json`, and `data/provenance/d02_historical_firms_and_big_adm1.json`.

## Verified D03 evidence (2026-10-21)

- NASA LDOPE issue 480 classifies the 2023-07-26 through 2023-07-27 absence as a permanent S-NPP VIIRS data gap caused by a spacecraft non-nominal state. The two dates are unavailable, not zero-detection days: `https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480`.
- All ten minimum questions have reproducible calculations or explicit support decisions. Riau September 2023 has 690 provisional generalized-boundary detections; Central Kalimantan has 33,357 in 2023; October is the country file's maximum month with 78,784 observations. Province results remain provisional.
- All 45 D02 near-boundary rows were queried against BIG's full-resolution source geometry with `returnGeometry=false`: 30 assignments confirmed, one changed, three unassigned rows gained one match, two assignments lost their match, and nine remained unassigned. No full-resolution geometry was downloaded and the D02 artifact/34 unassigned rows were not rewritten.
- BIG item metadata still has no license text. Official public query access is not treated as redistribution permission.
- The canonical logical contract is proposed, not approved, in `data/contracts/hotspot_observation_contract_v0.1.0-proposal.md` and its JSON Schema. No ClickHouse ingestion was implemented.
- Detailed evidence: `data/reports/D03_FEASIBILITY_CLOSURE_AND_DATA_CONTRACT_PROPOSAL.md`, `data/reports/d03_ten_question_validation.json`, `data/reports/d03_big_full_resolution_point_review.json`, and `data/provenance/d03_feasibility_closure.json`.

## Validation checklist
- [x] Record exact URL, access method, download date, credentials requirements (never commit credentials).
- [x] Save a real sample and checksum; note file size, record count and date range.
- [x] Inspect actual columns and types: latitude, longitude, acquisition date/time, satellite/product, FRP, confidence and any version-specific fields.
- [x] Quantify nulls, duplicates, invalid coordinates, timestamp parsing failures and confidence categories.
- [x] Verify Indonesian spatial coverage using an authoritative boundary; test boundary and unassigned cases. Final licensing/full-resolution review remains open.
- [x] Validate timezone convention (store UTC; present timezone clearly).
- [x] Test monthly count aggregations and region comparisons with a consistent product.
- [x] Check available NASA documentation for FRP, detection limits, confidence and active-fire caveats.
- [x] Record license, attribution and redistribution constraints for **each** dataset and geometry source. BIG redistribution remains unresolved because its service metadata has `licenseInfo: null`.
- [x] Reconcile at least 10 PRD questions against actual fields and queries.

## Proposed exploratory notebook
`data/notebooks/01_firms_feasibility.ipynb` (or equivalent script). Produce: schema report, null profile, temporal coverage plot, map sample, monthly counts, province-join accuracy checks, and source provenance manifest.

## Minimum test questions
1. VIIRS hotspots in Riau during September 2023?  
2. Monthly VIIRS detections in Central Kalimantan in 2023?  
3. Compare Riau and Central Kalimantan for 2023 using the same product?  
4. Which months had the most observations in the selected dataset?  
5. Show observation points for a specified province/date range?  
6. What does FRP mean according to NASA?  
7. What are VIIRS detection limitations?  
8. How does confidence vary by selected product?  
9. What happens when a user requests an unavailable date?  
10. Can burned hectares be inferred from these detections? (Expected: **no**.)

## Decision log
| Question | Decision | Evidence / link | Status |
|---|---|---|---|
| Selected FIRMS product | Recommend VIIRS S-NPP Collection 2 standard processing (`VNP14IMG.002`, FIRMS `version=2`) only | D03 report/contract; NASA DOI | Proposed; Lead approval required |
| Historical window | Recommend calendar 2023 UTC; 2023-07-26 and 2023-07-27 are a documented permanent S-NPP data gap; 2020–2025 is not validated | D03 report; NASA LDOPE issue 480 | Proposed; Lead approval required |
| Geographic boundary provider/vintage | BIG service item `0b64041ca8e54d6092b652f11ce16c7e`, modified 2024-09-11, EPSG:4326, 38 provinces; point review shows material generalized-boundary changes | D02 provenance and D03 full-resolution point review | Provisional; terms unresolved |
| Allowed data redistribution | NASA requests citation/disclaimer; BIG service is public but publishes no explicit license | Source README and BIG item metadata | Blocked on BIG terms |
| Data quality thresholds | Preserve/flag zero FRP; reject malformed required fields; exact-row content deduplication only; never force unassigned/ambiguous province joins; publish daily coverage state | D03 contract proposal | Proposed; D04 review required |

## Exit criteria
D01–D03 satisfy sample inspection, region-join demonstration, ten-question evaluation, product/window recommendation, provenance, and zero-row-date classification. The remaining gate decisions are explicit Tech Lead acceptance and a legally reusable province-boundary path. **G1 is not passed until the Tech Lead says so.** If BIG terms cannot be confirmed, select and validate an explicitly reusable replacement boundary and rerun the geographic evidence; do not fabricate permission or silently drop province limitations.
