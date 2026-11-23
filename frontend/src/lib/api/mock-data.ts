import type { ChatResponse, HotspotFeatureCollection, MetadataResponse, SummaryResponse } from "./types";

export const MOCK_SOURCE = {
  provider: "Synthetic fixture",
  dataset_version: "DEMO-FIXTURE-v1 — NOT AN OBSERVATION DATASET",
  data_status: "mock",
  url: "https://firms.modaps.eosdis.nasa.gov/",
  attribution: "Synthetic UI fixture; not NASA FIRMS observations",
} as const;

export const mockMetadata: MetadataResponse = {
  request_id: "demo-metadata-001",
  api_version: "1.0.0",
  products: [{ product_id: "DEMO_VIIRS", display_name: "VIIRS demo product (synthetic)" }],
  provinces: [
    { province_code: "ID-RI", display_name: "Riau" },
    { province_code: "ID-KT", display_name: "Central Kalimantan" },
    { province_code: "ID-SS", display_name: "South Sumatra" },
  ],
  coverage: { date_min: "2023-01-01", date_max: "2023-12-31", known_unavailable_dates: [] },
  source: MOCK_SOURCE,
  data_freshness_at: null,
  data_status: "mock",
};

const DEMO_SERIES = [18, 24, 21, 29, 34, 42, 58, 76, 112, 83, 49, 31];

export const mockSummary: SummaryResponse = {
  request_id: "demo-summary-001",
  metric: "satellite_hotspot_detections",
  product_id: "DEMO_VIIRS",
  filters: { province_codes: ["ID-RI"], date_from: "2023-01-01", date_to: "2023-12-31" },
  total: DEMO_SERIES.reduce((sum, value) => sum + value, 0),
  is_complete: true,
  coverage_issues: [],
  warnings: [],
  series: DEMO_SERIES.map((count, index) => ({ period: `2023-${String(index + 1).padStart(2, "0")}`, count, is_complete: true, coverage_issues: [] })),
  source: MOCK_SOURCE,
  caveat: "Synthetic demo counts for interface testing. Hotspot detections are not confirmed wildfires.",
};

const coordinates: [number, number][] = [
  [101.45, 0.52], [102.13, 0.91], [100.96, 1.27], [102.65, 0.14], [113.92, -2.21],
  [114.37, -1.76], [113.31, -2.67], [104.76, -3.18], [105.23, -2.71], [104.11, -3.61],
];

export const mockHotspots: HotspotFeatureCollection = {
  type: "FeatureCollection",
  features: coordinates.map(([longitude, latitude], index) => ({
    type: "Feature",
    id: `demo-${index + 1}`,
    geometry: { type: "Point", coordinates: [longitude, latitude] },
    properties: {
      observation_id: `synthetic-demo-${index + 1}`,
      acquired_at_utc: `2023-09-${String(index + 5).padStart(2, "0")}T04:30:00Z`,
      province_code: index < 4 ? "ID-RI" : index < 7 ? "ID-KT" : "ID-SS",
      confidence_code: index % 3 === 0 ? "n" : "h",
      frp_mw: index % 4 === 0 ? 0 : 3.5 + index,
      daynight_code: index % 2 === 0 ? "D" : "N",
      product_id: "DEMO_VIIRS",
    },
  })),
  metadata: {
    request_id: "demo-map-001",
    product_id: "DEMO_VIIRS",
    filters: { province_codes: ["ID-RI"], date_from: "2023-01-01", date_to: "2023-12-31" },
    truncated: false,
    returned: coordinates.length,
    limit: 500,
    is_complete: true,
    coverage_issues: [],
    source: MOCK_SOURCE,
    caveat: "Hotspot detections are not confirmed wildfires.",
  },
};

export const mockChatResponse: ChatResponse = {
  request_id: "demo-chat-001",
  answer: "Fire radiative power (FRP) describes the rate of radiant energy emitted by an actively burning fire, as observed by a satellite sensor. It can help compare detected fire intensity, but it does not establish burned area or confirm an incident on the ground.",
  mode: "rag",
  filters: null,
  metrics: null,
  chart: null,
  map: null,
  citations: [{ title: "NASA FIRMS — About Active Fire Data", url: "https://firms.modaps.eosdis.nasa.gov/", chunk_id: "demo-nasa-doc-frp" }],
  limitations: ["This demo response is a fixture, not a live retrieval result.", "Satellite hotspot detections are not confirmed wildfires."],
  usage: { llm_calls: 0 },
};
