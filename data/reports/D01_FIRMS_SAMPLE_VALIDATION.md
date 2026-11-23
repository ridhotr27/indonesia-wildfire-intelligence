# D01 — NASA FIRMS real-sample validation

**Status:** Real public sample downloaded and profiled; D01 sample evidence is complete, but the G1 data-feasibility gate remains open.  
**Profile date:** 2026-10-21 UTC  
**Scope:** The exact file below only. No claim is made about an uninspected historical archive extract.

## Outcome

NASA's own FIRMS training material exposes a credential-free, real VIIRS S-NPP CSV sample. The downloaded file parses successfully and contains 74,605 satellite hotspot detections and 14 columns. It is a partial global day from 2023-07-12 and mixes Near Real-Time (NRT) and Ultra Real-Time (URT) processing. It is suitable for validating the observed CSV schema and profiling workflow, but it is **not** evidence that the requested 2020–2025 Indonesia historical archive is accessible, complete, or suitable for time-series analysis.

The sample has 6 exact duplicate excess rows and 17 zero-FRP rows. It has no blanks, invalid numeric values, non-finite numeric values, invalid UTC timestamps, or out-of-range coordinates under the checks recorded in the generated profile. Hotspots are satellite detections, not confirmed wildfire incidents or burned hectares.

## Provenance and reproducibility

| Item | Recorded value |
|---|---|
| Provider | NASA Land, Atmosphere Near real-time Capability for EOS (LANCE), FIRMS |
| Source URL | `https://firms.modaps.eosdis.nasa.gov/content/notebooks/sample_viirs_snpp_071223.csv` |
| Official tutorial | `https://firms.modaps.eosdis.nasa.gov/content/academy/data_ingest/firms_data_ingest.html` |
| Access method | Direct HTTPS GET; no credentials required for this tutorial file |
| Retrieval time | 2026-10-21T07:00:15Z |
| Local artifact | `data/raw/nasa_firms/sample_viirs_snpp_2023-07-12.csv` |
| File size | 6,077,404 bytes |
| SHA-256 | `edf79f62b35ba4485d7c85e01be5f6f61d30ab7b4addcf2eea00e2581982c30f` |
| Observed platform code | `N` in all rows; NASA's attribute table defines this as Suomi NPP |
| Observed instrument | `VIIRS` in all rows |
| Collection mapping | The official S-NPP 375 m NRT catalog is `VNP14IMG_NRT.002`; this mapping is inferred from NASA documentation because the CSV does not carry a collection short name or DOI |
| Processing values | `2.0NRT` and `2.0URT` |

Machine-readable evidence is in:

- `data/provenance/nasa_firms_viirs_snpp_sample_2023-07-12.json`
- `data/reports/d01_firms_sample_profile.json`
- `data/scripts/profile_firms_sample.py`

Reproduce the profile from the pinned raw artifact:

```bash
python3 data/scripts/profile_firms_sample.py \
  data/raw/nasa_firms/sample_viirs_snpp_2023-07-12.csv \
  --output data/reports/d01_firms_sample_profile.json
```

## Actual CSV schema

The CSV header and every row in this file have these 14 fields, in this order. Types below are observed parse types plus NASA's published field semantics; they are not yet a frozen ingestion contract.

| Column | Observed type | NASA meaning / handling implication |
|---|---|---|
| `latitude` | float | Center latitude of the nominal 375 m detection pixel, decimal degrees |
| `longitude` | float | Center longitude of the nominal 375 m detection pixel, decimal degrees |
| `bright_ti4` | float | VIIRS I-4 brightness temperature, kelvin |
| `scan` | float | Along-scan pixel size, kilometres; actual size varies from nominal resolution |
| `track` | float | Along-track pixel size, kilometres; actual size varies from nominal resolution |
| `acq_date` | `YYYY-MM-DD` string | Acquisition date |
| `acq_time` | integer-encoded `HHMM` | Acquisition time in UTC; zero-pad to four digits before parsing (`3` means `00:03`) |
| `satellite` | categorical string | `N` in this file, meaning Suomi NPP |
| `instrument` | categorical string | `VIIRS` in this file |
| `confidence` | categorical string | `l`, `n`, or `h` (low, nominal, high); do not model as a numeric percentage |
| `version` | categorical string | Collection plus processing source; this sample contains `2.0NRT` and `2.0URT` |
| `bright_ti5` | float | VIIRS I-5 brightness temperature, kelvin |
| `frp` | float | Fire radiative power in megawatts; it is not burned area |
| `daynight` | categorical string | `D` or `N` for day/night acquisition |

For an eventual normalized schema, `acq_date` and zero-padded `acq_time` should be combined into one timezone-aware UTC timestamp. The raw categorical values and raw source row should remain traceable. The final contract must carry an explicit product ID rather than deriving product identity from `satellite`, `instrument`, and `version` alone.

## Measured coverage

| Measure | Result |
|---|---:|
| Rows | 74,605 |
| Columns | 14 |
| Earliest parsed UTC timestamp | 2023-07-12T00:03:00Z |
| Latest parsed UTC timestamp | 2023-07-12T19:50:00Z |
| Observed latitude range | -77.52732 to 71.09212 |
| Observed longitude range | -164.05351 to 178.79655 |
| NRT rows | 69,507 |
| URT rows | 5,098 |
| Day rows | 55,714 |
| Night rows | 18,891 |
| Low / nominal / high confidence | 4,792 / 64,901 / 4,912 |

These are extents of observations present, not proof of complete satellite swath coverage. The sample ends before the UTC day ends and therefore cannot support a complete daily count.

### Preliminary Indonesia screen

A deliberately coarse rectangle (`95°E..141°E`, `11°S..6°N`) selects 176 rows, all `2.0NRT` and daytime, from 04:17Z through 07:44Z. This only demonstrates that the global sample contains observations in the broad Indonesia region. It is **not** an Indonesia subset: the rectangle includes neighbouring countries and waters, can omit outlying geometry, and cannot assign provinces. Country/province coverage remains unverified until D02 uses a legally reusable authoritative boundary in a documented CRS.

## Data-quality profile

| Check | Measured result | Proposed handling, not yet a gate threshold |
|---|---:|---|
| Blank values across all 14 columns | 0 | Reject or quarantine missing required identity/time/coordinate fields |
| Invalid/non-finite numeric values | 0 | Reject malformed numeric fields |
| Invalid dates, times, or combined timestamps | 0 | Parse strictly as UTC; reject invalid values |
| Coordinates outside latitude/longitude bounds | 0 | Reject outside `[-90,90]` / `[-180,180]` |
| Non-positive `scan` / `track` | 0 / 0 | Reject non-positive footprint dimensions |
| Negative FRP | 0 | Reject negative FRP |
| Zero FRP | 17 (0.0228%) | Preserve and flag; do not silently coerce to null or remove without product guidance |
| Exact duplicate groups | 6 | Deduplicate idempotently and record duplicate counts |
| Exact duplicate excess rows | 6 (0.0080%) | Do not count duplicate source rows twice |
| Duplicate excess on candidate identity key | 6 | A key using coordinates, acquisition date/time, satellite and instrument is insufficiently documented; do not freeze it yet |

All six exact duplicate pairs are URT rows at 17:50Z. The 17 zero-FRP records are also URT rows. These observations reinforce that processing source must be preserved and that NRT/URT should not be silently mixed in analytical counts.

## Access, attribution, and redistribution

- The tutorial CSV was genuinely downloaded without credentials. Its URL is public but not content-addressed or advertised as immutable, so the local checksum is the reproducibility anchor.
- The FIRMS archive download page requires Earthdata or email-code authentication. The FIRMS API requires a free MAP key and limits an area request to 1–5 days. No credential was provided or committed, so an Indonesia historical archive download was not attempted and its availability has not been verified.
- NASA's archive page says NRT observations are replaced by standard science-quality data when available. NASA's VIIRS guide warns that low-latency NRT data can have processing-chain coverage gaps and recommends standard processing for latency-insensitive scientific work. The v1 historical product should therefore remain undecided until a standard-processing archive extract is inspected.
- NASA Earthdata's general policy says NASA-led mission data are CC0 unless marked with a restriction, and its active-fire catalog describes the collection as openly shared. The tutorial CSV contains no embedded license/terms file. Before redistribution, confirm the final archive extract has no artifact-specific restriction and retain NASA/FIRMS attribution, the collection DOI, retrieval date, source URL, and checksum.
- Candidate collection citation: `https://doi.org/10.5067/VIIRS/VNP14IMG_NRT.002`. The final citation must match the selected standard or near-real-time collection rather than copying this candidate blindly.

Official references:

- FIRMS VIIRS field definitions: `https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html`
- FIRMS archive and access notes: `https://firms.modaps.eosdis.nasa.gov/download/`
- FIRMS API area constraints: `https://firms.modaps.eosdis.nasa.gov/api/area/`
- S-NPP VIIRS NRT product catalog: `https://www.earthdata.nasa.gov/data/catalog/lancemodis-vnp14img-nrt-2`
- VIIRS Collection 2 user guide: `https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf`
- NASA Earthdata data-use guidance: `https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy`

## Limitations and gate decision

This evidence validates only the physical schema and contents of one real NASA tutorial CSV. It does not validate:

- authenticated archive/API access for the intended ingestion process;
- 2020–2025 (or 2020–2024) Indonesia temporal completeness;
- a standard-processing, science-quality product;
- missing-data dates, swath gaps, late replacements, or archive revisions;
- country or province membership, boundary vintage, CRS, legal reuse, or spatial-join accuracy;
- monthly/province counts or any of the PRD's historical example answers;
- comparability with NOAA-20, NOAA-21, MODIS, or another processing stream;
- a stable production observation identifier.

Therefore:

1. **D01 real-sample schema/profiling evidence:** complete for the pinned tutorial file.
2. **Historical Indonesia acquisition validation:** open; requires an authorized archive request or MAP key and a pinned standard-processing extract.
3. **G1 feasibility gate:** not passed. D02 and D03 remain required.

## Handoff / next work

- Obtain a real standard-processing Indonesia extract for a narrow historical window first, then expand only after access and completeness checks pass.
- Validate province geometry and point-in-polygon joins under D02; do not substitute the screening rectangle.
- Compare the archive file's header and categorical domains with this sample before defining `data/contracts/` under D04.
- Decide whether a single S-NPP standard product is adequate or whether another single VIIRS platform better fits the target period. Do not merge platforms or NRT/URT/SP records silently.
- Define duplicate and zero-FRP policy from the selected product's documentation and observed archive behavior before ingestion implementation.
