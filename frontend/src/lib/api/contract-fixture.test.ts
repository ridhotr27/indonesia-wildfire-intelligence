import { describe, expect, it } from "vitest";
import fixtureDocument from "../../../../docs/fixtures/api_contract_v1.0.0.fixture.json";
import type {
  ChatResponse,
  ErrorResponse,
  HotspotFeatureCollection,
  MetadataResponse,
  SummaryResponse,
} from "./types";

const fixture = fixtureDocument as unknown as {
  fixture_classification: string;
  api_version: string;
  metadata: MetadataResponse;
  summary_complete: SummaryResponse;
  summary_empty: SummaryResponse;
  summary_partial: SummaryResponse;
  summary_unavailable: SummaryResponse;
  geojson: HotspotFeatureCollection;
  geojson_empty: HotspotFeatureCollection;
  chat: ChatResponse;
  errors: Record<string, ErrorResponse>;
};

describe("A01 shared API contract fixture", () => {
  it("is explicitly synthetic and versioned", () => {
    expect(fixture.fixture_classification).toBe("synthetic_api_contract_example");
    expect(fixture.api_version).toBe("1.0.0");
    expect(fixture.metadata.data_status).toBe("mock");
    expect(fixture.metadata.source.attribution).toMatch(/not NASA observations/i);
  });

  it("distinguishes complete, partial, and wholly unavailable summaries", () => {
    expect(fixture.summary_complete).toMatchObject({ total: 2, is_complete: true, coverage_issues: [] });
    expect(fixture.summary_empty).toMatchObject({ total: 0, is_complete: true, coverage_issues: [] });
    expect(fixture.summary_partial.total).toBe(1);
    expect(fixture.summary_partial.is_complete).toBe(false);
    expect(fixture.summary_partial.coverage_issues).toHaveLength(2);
    expect(fixture.summary_unavailable.total).toBeNull();
    expect(fixture.summary_unavailable.series[0].count).toBeNull();
    expect(fixture.summary_unavailable.coverage_issues.every((issue) => issue.coverage_status === "known_satellite_gap")).toBe(true);
  });

  it("preserves bounded GeoJSON metadata and WGS84 coordinate order", () => {
    const [longitude, latitude] = fixture.geojson.features[0].geometry.coordinates;
    expect(longitude).toBeGreaterThan(90);
    expect(latitude).toBeGreaterThan(-90);
    expect(fixture.geojson.metadata).toMatchObject({ truncated: true, returned: 1, limit: 1 });
    expect(fixture.geojson.features[0].properties.frp_mw).toBe(0);
    expect(fixture.geojson_empty.features).toEqual([]);
    expect(fixture.geojson_empty.metadata).toMatchObject({ returned: 0, truncated: false, is_complete: true });
  });

  it("provides typed chat and error examples without claiming live execution", () => {
    expect(fixture.chat.mode).toBe("unsupported");
    expect(fixture.chat.usage.llm_calls).toBe(0);
    expect(fixture.errors.invalid_filter.error.code).toBe("INVALID_FILTER");
    expect(fixture.errors.rate_limited.error.retry_after_seconds).toBe(60);
  });
});
