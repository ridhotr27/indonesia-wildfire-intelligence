# D02 — Historical FIRMS access and geographic validation

**Status:** D02 evidence complete with documented blockers; G1 is not passed.  
**Validation timestamp:** 2026-10-21T07:30:06Z  
**Observation source:** NASA LANCE FIRMS only; administrative polygons are reference geometry, not wildfire observations.

## Outcome

Historical NASA FIRMS access for Indonesia is verified through NASA's public yearly-country summary route. The pinned source is the 2023 VIIRS S-NPP standard-processing file, not the one-day NRT/URT tutorial sample used for D01. NASA's server-reported SHA-256 and the downloaded file's SHA-256 match exactly.

A bounded five-calendar-day sample (2023-09-01 through 2023-09-05) was extracted and joined by point-in-polygon against 38 province polygons from Indonesia's Badan Informasi Geospasial (BIG). Of 15,804 satellite detections, 15,770 (99.785%) received one province and 34 (0.215%) were unassigned. There were no multiple-province matches. The results demonstrate a real administrative-boundary join; they do not prove boundary-perfect classification because the downloadable feasibility geometry is generalized and its explicit redistribution license is missing.

Hotspot rows are satellite detections and thermal anomalies, not confirmed wildfire incidents or burned hectares.

## Historical access and secure authentication

### Verified public historical route

| Item | Value |
|---|---|
| Public index | `https://firms.modaps.eosdis.nasa.gov/data/country/yearly_summary_files.txt` |
| Source URL | `https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp_2023_Indonesia.csv` |
| Access | Direct HTTPS; no credential required for this country-summary object |
| Retrieval | 2026-10-21T07:15:26.716826Z |
| Server last-modified | 2025-06-24T17:07:37Z |
| Bytes | 20,067,598 |
| Rows | 253,388 |
| Local/server SHA-256 | `2dba3b772b5a3a2cc0feed128af74637810021dd41dc34d584cb99b40411665a` |

### Authenticated area API

`data/scripts/firms_historical_access.py` provides a bounded area-API client using only `NASA_FIRMS_MAP_KEY` from the process environment. It allowlists VIIRS sources, validates bounding coordinates, enforces NASA's 1–5 day limit, writes atomically, verifies that the response begins with the expected VIIRS CSV header, and suppresses authenticated URLs from success evidence and errors because the key is embedded in the URL path.

No supported credential variable was present. The missing-secret path was exercised and reported `configured: false`; authenticated area-API access was **not** claimed. Historical access was instead verified through the public country file above.

Examples:

```bash
python3 data/scripts/firms_historical_access.py check-config

# After NASA_FIRMS_MAP_KEY is supplied by the shell or secret manager:
python3 data/scripts/firms_historical_access.py area-api \
  --source VIIRS_SNPP_SP \
  --bbox 95,-11,141,6 \
  --days 5 \
  --start-date 2023-09-01 \
  --output /secure/path/viirs-snpp-sp.csv
```

Do not put the map key in `.env` files committed to the repository, command output, provenance URLs, or filenames.

## Actual historical schema

The annual standard-processing CSV has 15 fields:

| Column | Observed representation | Meaning / handling |
|---|---|---|
| `latitude`, `longitude` | float | WGS84 detection-pixel centre |
| `bright_ti4` | float | I-4 brightness temperature, kelvin |
| `scan`, `track` | float | Actual pixel dimensions, kilometres |
| `acq_date` | `YYYY-MM-DD` | UTC acquisition date |
| `acq_time` | zero-padded `HHMM` text | UTC acquisition time; retain leading zero before timestamp parsing |
| `satellite` | `N` | Suomi NPP |
| `instrument` | `VIIRS` | Visible Infrared Imaging Radiometer Suite |
| `confidence` | `l`, `n`, `h` | Categorical low/nominal/high, not a numeric percentage |
| `version` | `2` | Collection 2 standard processing; unlike D01, there is no NRT/URT suffix |
| `bright_ti5` | float | I-5 brightness temperature, kelvin |
| `frp` | float | Fire radiative power, megawatts; not burned area |
| `daynight` | `D`, `N` | Day/night acquisition |
| `type` | `0`, `1`, `2`, `3` | Presumed vegetation fire, active volcano, other static land source, offshore detection |

This confirms the D01 tutorial schema cannot be frozen as the archive schema: the archive adds `type`, preserves leading zeros in `acq_time`, and uses standard-processing `version=2`.

## Annual source profile

| Measure | Result |
|---|---:|
| Date range | 2023-01-01 through 2023-12-31 UTC |
| Calendar dates with rows | 363 |
| Zero-row dates | 2023-07-26, 2023-07-27 |
| Rows | 253,388 |
| Exact duplicate excess rows | 0 |
| Candidate-identity duplicate excess rows | 0 |
| Blank fields | 0 |
| Invalid dates/times/timestamps | 0 / 0 / 0 |
| Invalid/non-finite numerics | 0 / 0 |
| Invalid coordinates | 0 |
| Negative / zero FRP | 0 / 8 |
| Confidence low / nominal / high | 19,071 / 225,901 / 8,416 |
| Day / night | 186,966 / 66,422 |
| Type 0 / 1 / 2 / 3 | 236,123 / 4,494 / 11,812 / 959 |

The two zero-row dates are not automatically labeled missing satellite coverage. NASA's missing-data page currently fails to load its table, and a country file can theoretically have no detections on a valid observation day. D03 must resolve that distinction before claiming annual completeness.

## Bounded five-day sample

| UTC date | Detections |
|---|---:|
| 2023-09-01 | 3,788 |
| 2023-09-02 | 3,956 |
| 2023-09-03 | 3,724 |
| 2023-09-04 | 2,374 |
| 2023-09-05 | 1,962 |
| **Total** | **15,804** |

All five requested calendar dates are present. The earliest sample acquisition is 2023-09-01T03:20Z and the latest is 2023-09-05T18:12Z; polar-orbiting acquisition times do not span every clock hour. The sample has no blanks, parsing failures, invalid coordinates, negative FRP, or duplicates. Seven records have zero FRP and are preserved rather than silently removed.

Artifacts:

- Raw five-day extract: `data/derived/feasibility/viirs-snpp_sp_2023-09-01_2023-09-05_indonesia.csv` — SHA-256 `eafbb1ebefe1702d2a980b1a36fe4d96471ee42282d5b4e9b1299465142b8401`
- ADM1-enriched extract: `data/derived/feasibility/viirs-snpp_sp_2023-09-01_2023-09-05_indonesia_adm1.csv` — SHA-256 `73db2d5a1f9caa26df3a0ffa7cbeb098239e3d0d668f9c988694fd1e0bd713f6`
- Machine profile: `data/reports/d02_historical_validation_profile.json`

## Administrative-boundary validation

### Source

| Item | Value |
|---|---|
| Provider | Badan Informasi Geospasial (BIG), Republic of Indonesia |
| Service | `https://geoservices.big.go.id/gis/rest/services/STIG/Batas_Provinsi/MapServer/0` |
| ArcGIS item | `0b64041ca8e54d6092b652f11ce16c7e` |
| Item modified | 2024-09-11T11:31:10.604Z |
| CRS | EPSG:4326 / WGS84 |
| Features | 38 province polygons with `KDPPUM` code and `WADMPR` name |
| Generalization | Server-side `maxAllowableOffset=0.001` degree, approximately 109–111 m in Indonesia |
| Bytes / SHA-256 | 7,069,852 / `1c0db9d378d66eba7bce50c04c4d145ef2f1d312f7652b170ebf9f0e03eb4f9f` |
| Access / attribution | Public service; attribution identifies BIG |
| Explicit license | `licenseInfo` is null in service metadata |

The ungeneralized all-province GeoJSON request returned HTTP 500. A single full-resolution Riau feature was 7.98 MB, so the feasibility run used BIG's server-side generalization. The join code supports Polygon and MultiPolygon geometries plus interior holes; it does not use the D01 screening rectangle.

### Join results

| Status | Rows |
|---|---:|
| Assigned to exactly one province | 15,770 |
| Unassigned | 34 |
| Multiple province matches | 0 |
| Within 0.001 degree of generalized boundary | 45 |

Unassigned records comprise 23 `type=0` presumed vegetation-fire detections and 11 `type=3` offshore detections. Twelve unassigned points are within the boundary-ambiguity threshold. These rows remain unassigned; the validator does not force the nearest province.

The five-day sample contains assigned detections in 36 of 38 polygons. North Sumatra (`12`) and Southwest Papua (`96`) have no assigned detections in this sample. Examples from the actual join are Riau (`14`): 62 detections, and Central Kalimantan (`62`): 1,962 detections. These are five-day detection counts, not the PRD's full-September answers.

### Geometry limitations

- A 0.001-degree generalized polygon is suitable for feasibility, not final boundary-sensitive classification.
- The BIG service does not publish an explicit license in its item metadata. The artifact must not be externally redistributed until reuse terms are confirmed.
- NASA's country membership geometry and BIG's province geometry need not share coastlines; offshore detections and small islands can remain unassigned.
- The 45 near-boundary rows require comparison with full-resolution or otherwise approved geometry before a final contract or accuracy claim.
- Province codes are BIG `KDPPUM` strings. Their stability/vintage must be approved before D04 publishes them to Backend.

## Source terms and documentation

The NASA-supplied `AttributesReadme.txt` states WGS84, asks downstream distributors to follow NASA citation guidance and reproduce or link the disclaimer, and describes the data as openly shared. Preserve provider, product/platform, processing version, source URL, retrieval timestamp, checksum, and disclaimer link.

Relevant NASA documentation was reachable:

- Attributes: `https://www.earthdata.nasa.gov/data/tools/firms/active-fire-data-attributes-modis-viirs`
- FIRMS FAQ and NRT/standard distinction: `https://www.earthdata.nasa.gov/data/tools/firms/faq`
- Data use and disclaimer: `https://www.earthdata.nasa.gov/data/tools/firms`
- Collection 2 VIIRS guide: `https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf`

BIG metadata identifies the public service and attribution but has `licenseInfo: null`. This is a legal/reuse blocker, not permission to assume public-domain status.

## Reproduction

The public source can be re-downloaded with:

```bash
python3 data/scripts/firms_historical_access.py public-country \
  --product viirs-snpp \
  --year 2023 \
  --output data/raw/nasa_firms/viirs-snpp_2023_Indonesia.csv
```

Rebuild the sample, profile, and spatial join:

```bash
python3 data/scripts/validate_historical_sample.py \
  --source data/raw/nasa_firms/viirs-snpp_2023_Indonesia.csv \
  --boundaries data/raw/reference/idn_adm1_big_2026_generalized.geojson \
  --date-from 2023-09-01 \
  --date-to 2023-09-05 \
  --sample-output data/derived/feasibility/viirs-snpp_sp_2023-09-01_2023-09-05_indonesia.csv \
  --enriched-output data/derived/feasibility/viirs-snpp_sp_2023-09-01_2023-09-05_indonesia_adm1.csv \
  --profile-output data/reports/d02_historical_validation_profile.json
```

The pinned generalized boundary can be re-requested from BIG using the exact `source_query_url` in `data/provenance/d02_historical_firms_and_big_adm1.json`. The `maxAllowableOffset=0.001`, `geometryPrecision=6`, `outSR=4326`, and selected `KDPPUM,WADMPR` fields are part of the artifact identity and must not be changed without producing a new checksum and join profile.

## Gate decision and next work

**D02 is complete:** historical access, actual archive schema, source terms, real multi-day data, and a real province join are evidenced and tested.

**G1 remains not passed** because:

1. The two annual zero-row dates have not been reconciled against a working NASA missing-data feed.
2. Authenticated API access and its current standard-product availability were not exercised because no MAP key was available; the public country route is verified instead.
3. BIG boundary redistribution terms are not explicit, and 45 near-boundary rows need full-resolution review.
4. The final single product and historical window require D03/Lead approval.
5. The ten minimum PRD questions have not all been reconciled against an approved window and boundary vintage.

Recommended next task: **D03 with Tech Lead** — resolve boundary licensing/full-resolution access and annual coverage, evaluate the ten questions, then approve one product/date window or revise scope. Do not start production ingestion or freeze D04 contracts before that decision.
