# D03B — Reusable Indonesia province boundary validation

**Status:** Technical evidence complete; `IN_REVIEW`; Tech Lead approval required  
**Validation date:** 2026-10-21 UTC  
**Reference role:** Administrative geometry only; NASA FIRMS remains the sole wildfire-observation source

## Outcome

The existing BIG service remains unsuitable for redistribution because its public metadata does not state a reusable license. The current geoBoundaries `gbOpen` Indonesia ADM1 layer was also evaluated: it has explicit reuse terms but represents 2017 and only 34 units, so it fails the project's 38-province requirement.

D03B therefore proposes a pinned, OSM-derived 38-province snapshot from `ahsa29/kpu-osm-boundaries-2026`, commit `c4d208a03a71553a1082f960ebdaa88c1d8e9389`, snapshot `2026-10-10b`. Its geometry is derived from the 2026-10-09 Geofabrik Indonesia OSM extract with documented land-mask corrections. The publisher applies the Open Data Commons Open Database License 1.0 and requires attribution to © OpenStreetMap contributors.

This is a technically viable, redistributable candidate, not an official BIG product. Adoption, ODbL compliance, the code crosswalk, and its use for G1 require explicit Tech Lead review.

## Pinned source and license

| Item | Value |
|---|---|
| Source repository | `https://github.com/ahsa29/kpu-osm-boundaries-2026` |
| Immutable commit | `c4d208a03a71553a1082f960ebdaa88c1d8e9389` |
| Snapshot | `2026-10-10b` |
| Underlying source | Geofabrik Indonesia OpenStreetMap PBF, 2026-10-09; documented OSM API/land-mask corrections |
| Source URL | `https://raw.githubusercontent.com/ahsa29/kpu-osm-boundaries-2026/c4d208a03a71553a1082f960ebdaa88c1d8e9389/data/2026-10-10b/MapNational.geojson` |
| License evidence | `https://raw.githubusercontent.com/ahsa29/kpu-osm-boundaries-2026/c4d208a03a71553a1082f960ebdaa88c1d8e9389/DATA_LICENSE.md` |
| License | Open Data Commons Open Database License 1.0 (`https://opendatacommons.org/licenses/odbl/1-0/`) |
| Required attribution | © OpenStreetMap contributors |
| CRS | OGC:CRS84 / WGS84 longitude-latitude |
| Source artifact | 9,388,600 bytes; SHA-256 `9dd43439b284186c91a2443c9fb9e5eabb885f75597f1ab83221f43a7ef88de7` |
| Canonical artifact | 9,394,914 bytes; SHA-256 `e9bd1f1fb1ba39ea0e07a7ba71cbbb2f048e64d6b49316cad7e88689aade74dd` |

Redistribution is permitted only while the project satisfies ODbL attribution and applicable share-alike obligations. This report is a technical license review, not legal advice.

## Geometry and identifier validation

- Exactly 38 unique source province codes and 38 unique two-digit canonical codes were reconciled.
- The canonical artifact retains the OSM source code and records geometry source, vintage, and license on every feature.
- Structural checks covered geometry type, closed rings, finite numeric positions, coordinate range, and non-empty polygons.
- Profile: 38 features, 12,028 polygons, 12,033 rings, 380,953 positions, extent `[94.9719492, -11.0076711, 141.019444, 6.076744]`.
- Shapely/GEOS independently checked all 38 features: zero empty/non-positive geometries and zero invalid geometries.
- The two-digit crosswalk is fully recorded in `data/provenance/d03b_reusable_boundary.json`; source codes remain available for reversibility.

The source national geometry is a union of district geometry and is simplified by at most 0.0005 degree, with 0.0001 degree used for Southwest Papua. It is materially more detailed than the D02 0.001-degree BIG feasibility artifact, but it is still a community-maintained representation and not survey-grade geometry.

## Join regression

### Five-day sample

The same 15,804 NASA detections from 2023-09-01 through 2023-09-05 were evaluated:

| Status | BIG D02 generalized | D03B candidate |
|---|---:|---:|
| Assigned | 15,770 | 15,770 |
| Unassigned | 34 | 34 |
| Multiple | 0 | 0 |

Equal totals do not imply identical row assignments. The candidate keeps boundary, multiple, and unassigned observations null and never assigns the nearest province.

### D03 flagged points

All 45 D03 flagged points were re-evaluated against the candidate:

| Comparison with BIG full-resolution server result | Rows |
|---|---:|
| Same single province | 29 |
| Both unassigned | 8 |
| Different assignment/status | 8 |

These differences are disclosed in `data/reports/d03b_reusable_boundary_validation.json`. Neither source is silently treated as ground truth.

## Ten-question regression

All ten D03 questions were rerun. Country-wide, confidence, FRP, coverage-gap, documentation, and abstention results are unchanged because they do not depend on province geometry. Province-sensitive differences are:

| Question | D03 BIG feasibility result | D03B OSM candidate |
|---|---:|---:|
| Riau, September 2023 | 690 | 687 |
| Riau, all 2023 | 3,329 | 3,327 |
| Central Kalimantan, all 2023 | 33,357 | 33,359 |
| Riau points, Sep 1–5 | 62 | 61 |

Central Kalimantan monthly counts also changed slightly: July 351→350, August 3,706→3,712, September 13,487→13,491, and October 14,213→14,206. Full outputs are in `data/reports/d03b_ten_question_validation.json`. July continues to span the documented 2023-07-26/27 S-NPP observation gap; it is never presented as complete zero-free coverage.

## Artifacts

- Raw pinned source: `data/raw/reference/idn_adm1_osm_2026-10-10b.geojson`
- Canonical 38-province geometry: `data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson`
- Provenance, crosswalk, and geometry profile: `data/provenance/d03b_reusable_boundary.json`
- Machine validation and 45-point comparison: `data/reports/d03b_reusable_boundary_validation.json`
- Ten-question rerun: `data/reports/d03b_ten_question_validation.json`
- Reproducible validator: `data/scripts/validate_reusable_boundaries.py`
- Automated regression tests: `data/tests/test_reusable_boundaries.py`

## Reproduction

Install the optional topology validator in an isolated environment, then run:

```bash
python3 -m venv /tmp/wildfire-d03b-validation
/tmp/wildfire-d03b-validation/bin/pip install -r data/requirements-validation.txt
/tmp/wildfire-d03b-validation/bin/python data/scripts/validate_reusable_boundaries.py \
  --source data/raw/reference/idn_adm1_osm_2026-10-10b.geojson \
  --canonical-output data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson \
  --sample data/derived/feasibility/viirs-snpp_sp_2023-09-01_2023-09-05_indonesia.csv \
  --flagged-review data/reports/d03_big_full_resolution_point_review.json \
  --provenance-output data/provenance/d03b_reusable_boundary.json \
  --report-output data/reports/d03b_reusable_boundary_validation.json \
  --retrieved-at 2026-10-21T13:30:00+00:00 \
  --require-topology
```

Then rerun the questions and tests:

```bash
python3 data/scripts/validate_d03_requirements.py \
  --source data/raw/nasa_firms/viirs-snpp_2023_Indonesia.csv \
  --boundaries data/derived/reference/idn_adm1_osm_2026-10-10b_canonical.geojson \
  --output data/reports/d03b_ten_question_validation.json \
  --boundary-warning "Pinned OSM-derived 2026-10-10b province geometry under ODbL 1.0; community-maintained, nationally simplified by at most 0.0005 degree, and pending Tech Lead approval."

python3 -m unittest discover -s data/tests -p 'test_*.py'
```

Observed on 2026-10-21: topology validation passed for 38/38 features and the complete DE suite passed 19 tests.

## Recommendation and required decision

Recommend this pinned candidate for D04 if the Tech Lead accepts:

1. ODbL attribution/share-alike obligations for shipped geometry and derived database use.
2. Community-maintained OSM provenance instead of an official BIG redistribution right.
3. The snapshot vintage and national simplification tolerances.
4. The reversible OSM-to-two-digit province crosswalk.
5. The disclosed differences from provisional BIG calculations.

D03B must remain `IN_REVIEW` until that decision. This report does not approve G1, D04, the contract proposal, or any province result for public release.
