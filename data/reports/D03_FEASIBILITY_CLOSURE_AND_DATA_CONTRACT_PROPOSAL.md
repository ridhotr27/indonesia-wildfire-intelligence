# D03 — Feasibility closure and data contract proposal

**Status:** D03 evidence complete; contract proposed; G1 remains pending Tech Lead approval  
**Validation date:** 2026-10-21 UTC  
**Observation source:** NASA LANCE FIRMS only; BIG polygons are reference geometry

## Outcome

D03 resolves the unexplained July absence, evaluates all ten minimum questions, reviews all 45 D02 near-boundary detections against BIG's official full-resolution server-side geometry, and proposes a versioned logical data contract. It does **not** approve G1, authorize BIG redistribution, alter shared API contracts, or implement ClickHouse ingestion.

The recommended bounded v1 dataset is the already verified NASA VIIRS S-NPP Collection 2 375 m standard-processing product (`VNP14IMG.002`, FIRMS `VIIRS_SNPP_SP`) for calendar 2023 UTC. The two missing dates are a documented permanent satellite-data gap and must be excluded from exact-date availability and disclosed on aggregates that span them.

Hotspots remain satellite active-fire/thermal-anomaly detections, not confirmed wildfire incidents or burned hectares.

## A. Historical coverage resolution

The zero-row dates 2023-07-26 and 2023-07-27 are **missing satellite observations**, not verified zero-detection days.

NASA's Land Data Operational Products Evaluation (LDOPE) issue 480 records that S-NPP entered a non-nominal state at approximately 02:03 UTC on July 26, VIIRS returned to full operational mode at approximately 16:50 UTC on July 27, and the missing data are not recoverable. It identifies S-NPP Level-1B and downstream products as affected. This directly applies to the S-NPP VNP14IMG-derived FIRMS product.

Evidence: `https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480`.

Classification and handling:

| Date | Country-file rows | D03 classification | Required behavior |
|---|---:|---|---|
| 2023-07-26 | 0 | Known permanent S-NPP VIIRS data gap | Unavailable; never return zero detections |
| 2023-07-27 | 0 | Known permanent S-NPP VIIRS data gap | Unavailable; never return zero detections |

The annual file contains observations on 363 dates and covers timestamps 2023-01-01T05:59Z through 2023-12-31T18:17Z, but those endpoint facts do not prove complete swath coverage on every other day. The proposed daily-coverage contract therefore distinguishes `observations_present`, `known_satellite_gap`, `zero_detections_verified`, and `unknown`. No date in this work is classified `zero_detections_verified` from row absence alone.

## B. Geographic boundary and licensing validation

### Licensing / redistribution

BIG's official item metadata identifies BIG as the access source but leaves `licenseInfo` empty. The official One Map portal describes access and sharing as governed by role-specific Indonesian rules; it does not provide an open redistribution license for this layer. Public ArcGIS query access is therefore recorded as access evidence only, not permission to redistribute geometry.

Official evidence:

- Service item metadata: `https://geoservices.big.go.id/gis/rest/services/STIG/Batas_Provinsi/MapServer/info/iteminfo`
- One Map portal terms/access context: `https://onemap.big.go.id/`

Conclusion: internal feasibility calculations and attribute-only service queries are reproducible, but external redistribution of the BIG GeoJSON remains blocked pending written terms/Tech Lead legal review or selection of an explicitly reusable boundary source. The repository's pinned generalized geometry must not be shipped as a public asset on the basis of this evidence.

### Full-resolution review of the 45 flagged points

`data/scripts/review_big_boundary_points.py` sent each flagged point to the same official BIG layer using full-resolution server-side `esriSpatialRelIntersects`. It requested only `KDPPUM` and `WADMPR` with `returnGeometry=false`; no higher-resolution geometry was downloaded or republished.

| Review outcome | Rows |
|---|---:|
| Generalized assignment confirmed | 30 |
| Generalized assignment changed province | 1 |
| Previously unassigned; one full-resolution match | 3 |
| Previously assigned; no full-resolution match | 2 |
| Unassigned under both methods | 9 |
| Multiple full-resolution matches | 0 |
| **Total** | **45** |

The D02 enriched artifact is immutable evidence and was not rewritten. Its 34 unassigned observations remain present. D03 records review outcomes separately; applying them to a canonical dataset requires an approved boundary license and assignment policy. In particular, nearest-province assignment remains prohibited.

Machine evidence: `data/reports/d03_big_full_resolution_point_review.json`.

## C. Ten-question validation

The reproducible calculations are in `data/scripts/validate_d03_requirements.py`; exact outputs are in `data/reports/d03_ten_question_validation.json`. Province calculations use the pinned 0.001-degree generalized BIG geometry and are deliberately marked provisional. Country totals and categorical profiles come directly from the pinned NASA file.

| # | Minimum question | Result | Support decision |
|---:|---|---|---|
| 1 | Riau detections, September 2023 | 690 | Provisional: query works, but boundary terms/method are unapproved |
| 2 | Central Kalimantan monthly detections, 2023 | Jan 136; Feb 51; Mar 18; Apr 111; May 237; Jun 221; Jul 351; Aug 3,706; Sep 13,487; Oct 14,213; Nov 764; Dec 62 | Provisional; July spans a known two-day data gap |
| 3 | Compare Riau and Central Kalimantan, 2023 | Riau 3,329; Central Kalimantan 33,357; difference 30,028 | Provisional; same single product, but geometry unapproved |
| 4 | Month with most source observations | October 2023: 78,784 | Supported for the NASA country file; not a fire count |
| 5 | Points for a province/date range | Riau, Sep 1–5: 62 points | Provisional; map must bound results and distinguish ambiguous/unassigned points |
| 6 | What does FRP mean? | NASA: pixel-integrated fire radiative power in MW; observed range 0–943.38 MW, 8 zero rows | Supported with NASA documentation; not burned area |
| 7 | VIIRS detection limitations | No numeric result from CSV | Supported only through NASA-document RAG; CSV cannot quantify missed fires/false alarms alone |
| 8 | Confidence distribution | low 19,071 (7.526402%); nominal 225,901 (89.152209%); high 8,416 (3.321389%) | Supported for this product only; categories are not probabilities |
| 9 | Unavailable date handling | Outside 2023 → unsupported; Jul 26–27 → known gap/unavailable; valid date → queryable | Supported validation behavior; gaps never become numeric zero |
| 10 | Burned hectares from detections? | No result | Unsupported; application must abstain and explain that a validated burned-area product is required |

Question 7 is answerable by the product's NASA-document retrieval path, not by an analytical calculation. Question 10 is intentionally unanswerable under the v1 data boundary. Questions 1–3 and 5 must not be presented as final public analytics until the province reference source is approved.

Relevant NASA semantics:

- FIRMS attributes, confidence, type and FRP: `https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html`
- Collection 2 375 m guide: `https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf`
- Standard product DOI: `https://doi.org/10.5067/VIIRS/VNP14IMG.002`

## D. Canonical data contract proposal

Proposal artifacts:

- `data/contracts/hotspot_observation_contract_v0.1.0-proposal.md`
- `data/contracts/hotspot_observation_contract_v0.1.0-proposal.schema.json`

The proposal defines product identity, strict UTC timestamps, raw measurement semantics, categorical confidence, non-negative FRP with valid zero handling, nullable province fields, explicit geographic status, provenance links, quality flags, exact-row duplicate handling, daily coverage states, and the 2023 supported range.

Key decisions:

1. Use only `VNP14IMG.002_SNPP_FIRMS_SP`; never silently merge platforms or latency streams.
2. Derive content identifiers from the exact ordered 15-field raw record plus product ID. Keep the first exact duplicate per product/batch, record duplicate counts, and perform no fuzzy/cross-product deduplication.
3. Populate province only for one approved, unambiguous match. `unassigned`, `ambiguous_boundary`, and `multiple_match` rows retain null province identifiers.
4. Preserve zero FRP and add `zero_frp`; do not coerce it to null or remove it.
5. Carry immutable ingestion-batch provenance and a separate daily coverage status. Dates with known missing observations have nullable counts, not zero.
6. Treat this as a logical proposal. ClickHouse DDL, production view names, fixtures, and Backend approval belong to D04 after G1.

## E. Product and date-range recommendation

Recommend the verified **Suomi NPP VIIRS 375 m Collection 2 standard-processing product** for a bounded calendar-2023 demo because it has an inspected stable schema, 253,388 actual Indonesia observations, zero exact duplicates, and NASA's science-quality standard processing rather than mixed NRT/RT/URT latency streams.

Recommend the supported range **2023-01-01 through 2023-12-31 UTC**, with 2023-07-26 and 2023-07-27 explicitly unavailable and warnings on aggregates spanning them. Do not claim 2020–2025 support: those yearly artifacts have not been downloaded and validated. A different single product, such as NOAA-20 standard processing, may later reduce the S-NPP outage problem, but it requires a separate feasibility run and cannot be substituted or merged from assumptions.

## Reproduction

Ten-question calculations:

```bash
python3 data/scripts/validate_d03_requirements.py \
  --source data/raw/nasa_firms/viirs-snpp_2023_Indonesia.csv \
  --boundaries data/raw/reference/idn_adm1_big_2026_generalized.geojson \
  --output data/reports/d03_ten_question_validation.json
```

Full-resolution attribute-only review (network access required):

```bash
python3 data/scripts/review_big_boundary_points.py \
  --enriched data/derived/feasibility/viirs-snpp_sp_2023-09-01_2023-09-05_indonesia_adm1.csv \
  --output data/reports/d03_big_full_resolution_point_review.json \
  --max-workers 8 --delay-seconds 0
```

Tests:

```bash
python3 -m unittest discover -s data/tests -p 'test_*.py'
```

## Remaining blockers and decisions

1. **Tech Lead approval:** G1 remains not passed until the Lead accepts the bounded product/window and documented limitations.
2. **Boundary reuse:** BIG redistribution permission remains unresolved. Approve written BIG terms or replace it with an explicitly reusable, verified 38-province source.
3. **Canonical geography method:** decide whether server-side BIG point results may be stored/published as derived province attributes and how to version boundary changes.
4. **D04 contract review:** Backend and Lead must approve view names, physical types, daily coverage interface, fixture, and maximum map return size.
5. **Window expansion:** 2020–2022 and 2024–2025 are unsupported until every source artifact, coverage gap, schema, checksum, and product version is validated separately.

Recommended next Data Engineer task: after explicit G1 approval and resolution of boundary terms, start **D04 with Backend** to approve the proposed contract and labeled fixtures. If boundary terms cannot be resolved, first perform a documented replacement-boundary evaluation and rerun the 45-point and ten-question calculations.

